"""Session preflight: validate and measure the real configuration at start.

`goal.md` section 6 requires a trial to begin by validating "session ID,
allocation, stimulus hashes, device identities, available disk space and audio
clock health", and section 7 requires calibration on the final hardware with
the method and uncertainty recorded. This module is that step, as a first-class
part of the application rather than a bench script.

The operating decision behind it: rather than wait for a frozen timing
tolerance before the software can run, **measure the configuration at the start
of every session and store the measurements with the session record**. A
session therefore carries evidence of the hardware it actually ran on, and the
tolerance can be frozen later from accumulated real measurements instead of
being guessed up front.

Two consequences that follow, and are implemented here:

* Timing worse than the configured target does not refuse the session by
  default. It is recorded, surfaced to the operator, and carried into the
  export, so a session run on a bad configuration is identifiable afterwards
  rather than silently equivalent to a good one. `blocking` in the timing
  policy flips this for collection.
* Devices are pinned by identity, not by index. PortAudio indices move when a
  Bluetooth headset connects, and a remote-desktop session can redirect or
  claim endpoints entirely, so the preflight reports what it actually bound to
  and whether that differs from what the configuration pinned.

Nothing here opens the microphone unless the configuration explicitly enables
the capture check. The default is off, and a disabled check reports
``NOT_RUN``, never ``PASS``.
"""

from __future__ import annotations

import json
import platform
import shutil
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from audio_io import (
    CAPTURE_RATE,
    DEFAULT_BLOCKSIZE,
    AudioFault,
    ContinuousRecorder,
    OutputPlayer,
    SoundDeviceBackend,
    inventory,
    PROBE_COMMITTED_LATE,
    PROBE_STUCK,
    load_clip,
    run_commit_probe,
    tone_clip,
)
from timing import (
    DEFAULT_PROFILE,
    ESTIMATED,
    DetectorProfile,
    MonotonicClock,
    TimingLedger,
    validate_detector_profile,
)

__all__ = [
    "PASS", "FAIL", "WARN", "NOT_RUN", "BLOCKED",
    "CheckResult", "PreflightReport", "PreflightConfig", "SessionPreflight",
    "load_config",
]

PASS = "PASS"
FAIL = "FAIL"
#: Measured outside the configured target, but the session may proceed and the
#: measurement is recorded. Deliberately distinct from PASS and from FAIL.
WARN = "WARN"
NOT_RUN = "NOT_RUN"
BLOCKED = "BLOCKED"

#: Statuses that stop a session when the check is marked blocking.
_BAD = (FAIL, BLOCKED)


@dataclass(frozen=True)
class CheckResult:
    """One preflight check: what it asked, what it found, what it proves."""

    name: str
    status: str
    detail: str
    blocking: bool = False
    data: dict = field(default_factory=dict)

    @property
    def blocks_session(self) -> bool:
        return self.blocking and self.status in _BAD

    def as_record(self) -> dict:
        return {
            "check": self.name,
            "status": self.status,
            "detail": self.detail,
            "blocking": self.blocking,
            "blocks_session": self.blocks_session,
            **self.data,
        }


@dataclass
class PreflightReport:
    """The whole preflight outcome, written into the session record."""

    session_id: str
    started_at_utc: str
    environment: dict
    checks: list[CheckResult] = field(default_factory=list)

    def add(self, result: CheckResult) -> CheckResult:
        self.checks.append(result)
        return result

    @property
    def blockers(self) -> list[CheckResult]:
        return [c for c in self.checks if c.blocks_session]

    @property
    def warnings(self) -> list[CheckResult]:
        return [c for c in self.checks if c.status == WARN]

    @property
    def may_start(self) -> bool:
        return not self.blockers

    @property
    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for check in self.checks:
            counts[check.status] = counts.get(check.status, 0) + 1
        return counts

    def verdict(self) -> str:
        """One word for the operator view.

        ``PASS`` requires every check to have actually run and passed. A report
        containing NOT_RUN or BLOCKED checks is never a pass, even if nothing
        failed: missing evidence is not evidence, so "incomplete" outranks
        "passed with warnings". ``may_start`` is the separate question of
        whether this session can proceed, and a warning does not stop it.
        """
        counts = self.summary
        if self.blockers:
            return "BLOCKED"
        if counts.get(FAIL):
            return "FAIL"
        unrun = counts.get(NOT_RUN, 0) + counts.get(BLOCKED, 0)
        if unrun and counts.get(WARN):
            return "INCOMPLETE_WITH_WARNINGS"
        if unrun:
            return "INCOMPLETE"
        if counts.get(WARN):
            return "PASS_WITH_WARNINGS"
        return "PASS"

    @property
    def is_pass(self) -> bool:
        """True only when every check ran and none warned."""
        return self.verdict() == "PASS"

    def as_record(self) -> dict:
        return {
            "session_id": self.session_id,
            "started_at_utc": self.started_at_utc,
            "environment": self.environment,
            "checks": [c.as_record() for c in self.checks],
            "summary": self.summary,
            "verdict": self.verdict(),
            "may_start": self.may_start,
            "blocking_checks": [c.name for c in self.blockers],
            "warning_checks": [c.name for c in self.warnings],
        }

    def to_json(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.as_record(), indent=2, ensure_ascii=False)
                     + "\n", encoding="utf-8")
        return p

    def operator_lines(self) -> list[str]:
        """Compact text for the researcher view."""
        lines = [f"preflight {self.verdict()} — session {self.session_id}"]
        for check in self.checks:
            mark = {PASS: "ok", WARN: "warn", FAIL: "FAIL",
                    BLOCKED: "BLOCKED", NOT_RUN: "--"}.get(check.status, "?")
            lines.append(f"  [{mark:>7}] {check.name}: {check.detail}")
        if self.blockers:
            lines.append("  cannot start: "
                         + ", ".join(c.name for c in self.blockers))
        return lines


# --- configuration ------------------------------------------------------------

@dataclass
class PreflightConfig:
    """What the preflight checks and how strict each check is.

    Defaults are the engineering ones; a collection configuration is expected
    to pin devices and may set ``timing_blocking``.
    """

    session_id: str = "unnamed-session"
    #: True only for a session that will record a real participant. It turns
    #: the development defaults below into blocking requirements; it does not
    #: by itself authorise collection, which needs the research approvals in
    #: goal.md section 14.
    is_participant_session: bool = False
    samplerate: int = CAPTURE_RATE
    blocksize: int = DEFAULT_BLOCKSIZE
    channels: int = 1

    #: Pinned device identity keys (``DeviceIdentity.key()``). ``None`` means
    #: "use the default and record what that was".
    output_device_key: str | None = None
    input_device_key: str | None = None
    #: Explicit index override, used only when a key cannot be resolved and the
    #: operator has chosen a device by hand. Recorded either way.
    output_device_index: int | None = None
    input_device_index: int | None = None

    #: Candidate engineering target from goal.md section 7. A proposal, not a
    #: research-approved tolerance.
    max_onset_delay_ms: float = 100.0
    #: Out-of-target timing records a WARN and allows the session to start.
    #: Set true for participant collection once a tolerance is frozen.
    timing_blocking: bool = False
    commit_trials: int = 20
    probe_lead_ms: float = 10.0
    probe_amplitude: float = 0.02
    stream_warmup_s: float = 0.5

    #: Capture is measured only when this is explicitly enabled. The preflight
    #: opens the microphone when it is; the operator view must say so.
    check_capture: bool = False
    capture_seconds: float = 2.0
    capture_blocking: bool = True

    detector_profile: DetectorProfile = DEFAULT_PROFILE
    thresholds: tuple[float, ...] = (0.5, 1.0, 2.0)

    #: Research-data root. Kept outside the repository and the web root.
    data_root: str | None = None
    min_free_gb: float = 5.0

    #: Stimulus manifest to hash-verify, when one exists (M2).
    stimulus_manifest: str | None = None

    scratch_dir: str | None = None

    @classmethod
    def from_dict(cls, raw: dict) -> "PreflightConfig":
        # "$"-prefixed keys are comments. A research configuration has to be
        # readable by the people who own the decisions in it, so the file is
        # allowed to explain itself.
        data = {k: v for k, v in raw.items() if not k.startswith("$")}
        profile = data.pop("detector_profile", None)
        thresholds = data.pop("thresholds", None)
        known = {f for f in cls.__dataclass_fields__}
        unknown = sorted(set(data) - known)
        if unknown:
            raise ValueError(f"unknown preflight config keys: {unknown}")
        cfg = cls(**data)
        if profile:
            cfg.detector_profile = DetectorProfile(**profile)
        if thresholds:
            cfg.thresholds = tuple(float(t) for t in thresholds)
        return cfg

    def as_record(self) -> dict:
        return {
            "session_id": self.session_id,
            "is_participant_session": self.is_participant_session,
            "samplerate": self.samplerate,
            "blocksize": self.blocksize,
            "channels": self.channels,
            "output_device_key": self.output_device_key,
            "input_device_key": self.input_device_key,
            "output_device_index": self.output_device_index,
            "input_device_index": self.input_device_index,
            "max_onset_delay_ms": self.max_onset_delay_ms,
            "max_onset_delay_is_frozen_tolerance": False,
            "timing_blocking": self.timing_blocking,
            "commit_trials": self.commit_trials,
            "check_capture": self.check_capture,
            "capture_seconds": self.capture_seconds,
            "detector_profile": self.detector_profile.as_record(),
            "thresholds": list(self.thresholds),
            "data_root": self.data_root,
            "min_free_gb": self.min_free_gb,
            "stimulus_manifest": self.stimulus_manifest,
        }


def load_config(path: str | Path) -> PreflightConfig:
    """Read a preflight configuration from JSON.

    Accepts either a bare preflight object or an experiment configuration with
    a ``preflight`` key, so one file can hold the whole session configuration.
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if "preflight" in raw:
        merged = dict(raw["preflight"])
        if "session_id" in raw:
            merged.setdefault("session_id", raw["session_id"])
        if "is_participant_session" in raw:
            merged.setdefault("is_participant_session",
                              raw["is_participant_session"])
        # The data root and the stimulus manifest live in the experiment
        # configuration proper, not in its preflight section, so pull them
        # across rather than requiring them to be written twice.
        data = raw.get("data") or {}
        if data.get("research_data_root"):
            merged.setdefault("data_root", data["research_data_root"])
        materials = raw.get("materials") or {}
        if materials.get("stimulus_manifest"):
            merged.setdefault("stimulus_manifest", materials["stimulus_manifest"])
        policy = raw.get("timing_policy") or {}
        if "max_onset_delay_ms" in policy:
            merged.setdefault("max_onset_delay_ms", policy["max_onset_delay_ms"])
        if "blocking" in policy:
            merged.setdefault("timing_blocking", policy["blocking"])
        detector = raw.get("detector") or {}
        if detector and "detector_profile" not in merged:
            merged["detector_profile"] = {
                k: v for k, v in detector.items()
                if not k.startswith("$") and k != "status"
            }
        raw = merged
    return PreflightConfig.from_dict(raw)


# --- the preflight ------------------------------------------------------------

def _percentile(values: list[float], fraction: float) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    k = max(0, min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1)))))
    return ordered[k]


class SessionPreflight:
    """Runs the start-of-session checks and produces a storable report.

    ``backend_factory`` and ``inventory_fn`` are injectable so the whole
    preflight runs on the fake backend in tests, with no device at all.
    """

    def __init__(self, config: PreflightConfig, *,
                 clock: MonotonicClock | None = None,
                 backend_factory: Callable[[MonotonicClock], Any] | None = None,
                 inventory_fn: Callable[[], dict] = inventory,
                 ledger: TimingLedger | None = None,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.config = config
        self.clock = clock or MonotonicClock()
        self._backend_factory = backend_factory or (lambda c: SoundDeviceBackend(c))
        self._inventory = inventory_fn
        self.ledger = ledger or TimingLedger(clock=self.clock)
        self._sleep = sleep
        self.inventory_report: dict | None = None

    # -- environment

    def environment(self) -> dict:
        env: dict[str, Any] = {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "machine": platform.machine(),
        }
        for mod in ("numpy", "sounddevice"):
            try:
                env[mod] = __import__(mod).__version__
            except Exception as exc:
                env[mod] = f"unavailable: {type(exc).__name__}"
        if self.inventory_report:
            env["portaudio"] = self.inventory_report.get("portaudio")
        return env

    # -- individual checks

    def check_devices(self) -> list[CheckResult]:
        """Resolve pinned device identities and report what was actually bound.

        A pinned key that no longer resolves is a blocking failure: the timing
        of a session is a property of its devices, so silently falling back to
        whatever is present would make the recorded measurements describe
        different hardware than the configuration claims.
        """
        cfg = self.config
        info = self._inventory()
        self.inventory_report = info
        out: list[CheckResult] = []

        if not info.get("available"):
            return [CheckResult("audio_subsystem", BLOCKED,
                                info.get("error", "sounddevice unavailable"),
                                blocking=True)]

        devices = info.get("devices", [])
        by_key: dict[str, list[dict]] = {}
        for dev in devices:
            by_key.setdefault(dev["key"], []).append(dev)

        for role, key, index, need in (
                ("output", cfg.output_device_key, cfg.output_device_index,
                 "max_output_channels"),
                ("input", cfg.input_device_key, cfg.input_device_index,
                 "max_input_channels")):
            if role == "input" and not cfg.check_capture:
                out.append(CheckResult(
                    f"{role}_device", NOT_RUN,
                    "capture check disabled; no input device was resolved or "
                    "opened"))
                continue
            if key is None:
                default = info.get(f"default_{'playback' if role == 'output' else 'capture'}_available")
                resolved = (index if index is not None
                            else info.get(f"default_{'output' if role == 'output' else 'input'}_device"))
                candidates = [d for d in devices if d[need] > 0]
                if index is None and not default:
                    status = BLOCKED if role == "input" else FAIL
                    detail = (f"no default {role} device; "
                              f"{len(candidates)} {role}-capable device(s) exist "
                              f"but none is the default, so the configuration "
                              f"must pin one by identity")
                    out.append(CheckResult(
                        f"{role}_device", status, detail,
                        blocking=(cfg.capture_blocking if role == "input"
                                  else True),
                        data={"candidates": [d["key"] for d in candidates]}))
                    continue
                actual = next((d for d in devices if d["index"] == resolved), None)
                out.append(CheckResult(
                    f"{role}_device", PASS,
                    f"using {'explicit index' if index is not None else 'default'} "
                    f"{resolved}: {actual['key'] if actual else 'unknown'}",
                    data={"device_index": resolved,
                          "device_key": actual["key"] if actual else None,
                          "pinned": False,
                          "hostapi": actual["hostapi_name"] if actual else None}))
                continue

            matches = by_key.get(key, [])
            if not matches:
                out.append(CheckResult(
                    f"{role}_device", FAIL,
                    f"pinned {role} device not present: {key!r}. PortAudio "
                    f"indices move between sessions and a remote-desktop "
                    f"session can redirect endpoints, so the session must not "
                    f"fall back to another device",
                    blocking=True,
                    data={"pinned_key": key,
                          "available": sorted(by_key)}))
            elif len(matches) > 1:
                out.append(CheckResult(
                    f"{role}_device", FAIL,
                    f"pinned {role} device {key!r} matches "
                    f"{len(matches)} devices; the identity is ambiguous",
                    blocking=True,
                    data={"pinned_key": key,
                          "indices": [d["index"] for d in matches]}))
            else:
                dev = matches[0]
                out.append(CheckResult(
                    f"{role}_device", PASS,
                    f"pinned {role} device resolved to index {dev['index']} "
                    f"({dev['hostapi_name']})",
                    data={"device_index": dev["index"], "device_key": key,
                          "pinned": True, "hostapi": dev["hostapi_name"]}))

        warnings = info.get("warnings", [])
        out.append(CheckResult(
            "device_inventory",
            WARN if warnings else PASS,
            "; ".join(warnings) if warnings
            else f"{info.get('input_device_count')} input / "
                 f"{info.get('output_device_count')} output devices",
            data={"warnings": warnings,
                  "default_capture_available": info.get("default_capture_available"),
                  "capture_possible": info.get("capture_possible")}))
        return out

    def check_detector_profile(self) -> CheckResult:
        cfg = self.config
        budget = cfg.blocksize / cfg.samplerate
        try:
            validate_detector_profile(cfg.detector_profile, cfg.thresholds,
                                      decision_budget_s=budget)
        except ValueError as exc:
            return CheckResult("detector_profile", FAIL, str(exc), blocking=True,
                               data={"profile": cfg.detector_profile.as_record()})
        return CheckResult(
            "detector_profile", PASS,
            f"hangover {cfg.detector_profile.hangover_ms:.0f} ms + "
            f"{budget * 1000:.0f} ms decision budget < shortest threshold "
            f"{min(cfg.thresholds):.1f} s",
            data={"profile": cfg.detector_profile.as_record(),
                  "thresholds": list(cfg.thresholds),
                  "note": "band dwell is data-dependent and is bounded at "
                          "runtime by the pause timer's lateness budget, not "
                          "by this static check"})

    def check_participant_configuration(self) -> CheckResult:
        """A participant session must not run on the development defaults.

        The development configuration deliberately warns rather than refuses on
        out-of-target timing, leaves the microphone check off and has no data
        root. Every one of those is wrong for a session that records a real
        person, so the flag that says this is such a session turns them into
        blocking requirements. Previously the flag was read by nothing
        (R04-F03).

        Passing this check is not authorisation to collect: the research gates
        in goal.md section 14 are separate and are not represented here.
        """
        cfg = self.config
        if not cfg.is_participant_session:
            return CheckResult(
                "participant_configuration", NOT_RUN,
                "development session: participant configuration gates are not "
                "applied. Set is_participant_session for a session that "
                "records a participant")
        missing = []
        if not cfg.timing_blocking:
            missing.append("timing_policy.blocking must be true so a session "
                           "cannot run on out-of-target timing")
        if not cfg.check_capture:
            missing.append("preflight.check_capture must be true: recording "
                           "must be verified before a participant speaks")
        if not cfg.capture_blocking:
            missing.append("preflight.capture_blocking must be true")
        if not cfg.data_root:
            missing.append("data.research_data_root must be configured outside "
                           "the repository and the web root")
        if not cfg.stimulus_manifest:
            missing.append("materials.stimulus_manifest must be a frozen "
                           "reviewed manifest")
        if not cfg.output_device_key:
            missing.append("audio.output_device_key must pin the output device "
                           "by identity")
        if not cfg.input_device_key:
            missing.append("audio.input_device_key must pin the input device "
                           "by identity")
        if missing:
            return CheckResult(
                "participant_configuration", FAIL,
                f"{len(missing)} requirement(s) unmet for a participant "
                f"session: " + "; ".join(missing),
                blocking=True, data={"unmet": missing})
        return CheckResult(
            "participant_configuration", PASS,
            "participant-grade configuration: blocking timing, capture "
            "verified, pinned devices, data root and frozen manifest",
            data={"note": "configuration only; research approvals are a "
                          "separate gate (goal.md section 14)"})

    def check_disk_space(self) -> CheckResult:
        cfg = self.config
        if not cfg.data_root:
            return CheckResult(
                "disk_space", NOT_RUN,
                "no research-data root configured; sessions must write outside "
                "the repository and the web root (goal.md section 10)")
        root = Path(cfg.data_root)
        if not root.exists():
            return CheckResult("disk_space", FAIL,
                               f"research-data root does not exist: {root}",
                               blocking=True, data={"data_root": str(root)})
        usage = shutil.disk_usage(root)
        free_gb = usage.free / 1e9
        status = PASS if free_gb >= cfg.min_free_gb else FAIL
        return CheckResult(
            "disk_space", status,
            f"{free_gb:.1f} GB free at {root} (need {cfg.min_free_gb:.1f} GB)",
            blocking=True,
            data={"data_root": str(root), "free_gb": free_gb,
                  "min_free_gb": cfg.min_free_gb})

    def check_stimuli(self) -> CheckResult:
        """Hash-verify the pinned stimulus assets, when a manifest exists."""
        cfg = self.config
        if not cfg.stimulus_manifest:
            return CheckResult(
                "stimulus_hashes", NOT_RUN,
                "no stimulus manifest configured; frozen materials are M2 and "
                "the research materials are not finalized")
        path = Path(cfg.stimulus_manifest)
        if not path.exists():
            return CheckResult("stimulus_hashes", FAIL,
                               f"manifest not found: {path}", blocking=True)
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return CheckResult("stimulus_hashes", FAIL,
                               f"manifest unreadable: {type(exc).__name__}: {exc}",
                               blocking=True)
        assets = manifest.get("assets") or manifest.get("stories") or []
        checked, bad = 0, []
        for asset in assets:
            audio = asset.get("audio")
            digest = asset.get("sha256")
            if not audio or not digest:
                bad.append(f"{asset.get('id', '?')}: manifest entry incomplete")
                continue
            candidate = (path.parent / audio).resolve()
            try:
                load_clip(candidate, expect_sha256=digest,
                          expect_samplerate=cfg.samplerate)
                checked += 1
            except Exception as exc:
                bad.append(f"{asset.get('id', '?')}: {exc}")
        if bad:
            return CheckResult(
                "stimulus_hashes", FAIL,
                f"{len(bad)} of {len(assets)} assets failed verification",
                blocking=True,
                data={"failures": bad[:10], "verified": checked})
        return CheckResult("stimulus_hashes", PASS,
                           f"{checked} assets match the manifest",
                           data={"verified": checked,
                                 "manifest": str(path),
                                 "manifest_version": manifest.get("version")})

    def _report_probes(self, *, commit: list[float], offset: list[float],
                       onset: list[float], early: int, timed_out: int,
                       late: int, skipped_no_onset: int) -> list[CheckResult]:
        """Turn the probe distributions into checks.

        Separate from the loop so the degenerate inputs - no onset estimate at
        all, an empty offset list - are testable without a device. Every
        statistic below is guarded by the emptiness of the list it reads: an
        earlier ordering called ``median(offset)`` one check before the guard
        meant to report the empty case, so that case raised instead (R05-F02).
        """
        cfg = self.config
        out: list[CheckResult] = []
        if len(commit) < cfg.commit_trials:
            out.append(CheckResult(
                "commit_timing", FAIL,
                f"only {len(commit)}/{cfg.commit_trials} probes committed "
                f"({timed_out} timed out)",
                blocking=True,
                data={"committed": len(commit), "timed_out": timed_out}))
            return out

        out.append(CheckResult(
            "no_early_output", FAIL if early else PASS,
            f"{early} of {len(commit)} commitments landed before their "
            f"deadline",
            blocking=True, data={"early": early, "trials": len(commit)}))

        p95_commit = _percentile(commit, 0.95)
        out.append(CheckResult(
            "commit_delay", PASS,
            f"n={len(commit)} median {statistics.median(commit):.2f} ms, "
            f"p95 {p95_commit:.2f} ms, max {max(commit):.2f} ms"
            + (f"; {late} committed only in the timeout race" if late else ""),
            data={"n": len(commit),
                  "median_ms": statistics.median(commit),
                  "p95_ms": p95_commit, "max_ms": max(commit),
                  "committed_late": late}))

        if not onset or not offset:
            out.append(CheckResult(
                "device_offset", NOT_RUN,
                f"no probe produced a device-offset estimate "
                f"({skipped_no_onset} skipped)",
                data={"skipped_no_onset": skipped_no_onset}))
            out.append(CheckResult(
                "onset_delay_target", NOT_RUN,
                f"no probe produced an onset estimate "
                f"({skipped_no_onset} skipped)",
                data={"skipped_no_onset": skipped_no_onset}))
            return out

        out.append(CheckResult(
            "device_offset", PASS,
            f"median {statistics.median(offset):.2f} ms "
            f"(buffer time minus commit instant)",
            data={"median_ms": statistics.median(offset),
                  "max_ms": max(offset), "method": ESTIMATED}))

        p95_onset = _percentile(onset, 0.95)
        meets = p95_onset <= cfg.max_onset_delay_ms
        # The decision the user made: record it, warn, and let the session
        # start. Set timing_blocking for collection.
        status = PASS if meets else (FAIL if cfg.timing_blocking else WARN)
        out.append(CheckResult(
            "onset_delay_target", status,
            f"estimated p95 onset delay {p95_onset:.2f} ms vs the "
            f"{cfg.max_onset_delay_ms:.0f} ms configured target "
            f"({'within' if meets else 'ABOVE'} target; this is a "
            f"device-latency estimate, not an acoustic measurement, "
            f"and the target is a proposal rather than a frozen "
            f"tolerance)",
            blocking=cfg.timing_blocking,
            data={"p95_ms": p95_onset,
                  "median_ms": statistics.median(onset),
                  "max_ms": max(onset),
                  "target_ms": cfg.max_onset_delay_ms,
                  "meets_target": meets,
                  "method": ESTIMATED,
                  "skipped_no_onset": skipped_no_onset,
                  "components_median_ms": {
                      "commit_delay": statistics.median(commit),
                      "device_offset": statistics.median(offset),
                      "clip_leading_silence": cfg.probe_lead_ms,
                  }}))
        return out

    def measure_output(self, device_index) -> list[CheckResult]:
        """Open the output stream, measure its cadence and its commit timing.

        Emits a faint probe tone. The acoustic onset is still not measured:
        these are scheduling and device-latency figures, reported as three
        separate components so no single number mixes them.
        """
        cfg = self.config
        out: list[CheckResult] = []
        try:
            backend = self._backend_factory(self.clock)
        except Exception as exc:
            return [CheckResult("output_stream", BLOCKED,
                                f"audio backend unavailable: "
                                f"{type(exc).__name__}: {exc}", blocking=True)]

        entries: list[float] = []
        methods: set[str] = set()
        player = OutputPlayer(backend=backend, clock=self.clock,
                              samplerate=cfg.samplerate, channels=cfg.channels,
                              blocksize=cfg.blocksize, device=device_index,
                              ledger=self.ledger)
        inner = player._callback

        def instrumented(outdata, timing, status):
            entries.append(timing.entry_time)
            methods.add(timing.method)
            inner(outdata, timing, status)

        player._callback = instrumented
        try:
            player.open()
        except Exception as exc:
            return [CheckResult("output_stream", FAIL,
                                f"could not open output: "
                                f"{type(exc).__name__}: {exc}", blocking=True)]
        try:
            self._sleep(cfg.stream_warmup_s)
            latency = player.latency_s
            out.append(CheckResult(
                "output_stream", PASS,
                f"{cfg.samplerate} Hz, blocksize {cfg.blocksize}, "
                f"device-reported latency {latency * 1000:.1f} ms",
                data={"reported_output_latency_ms": latency * 1000,
                      "block_timing_method": sorted(methods)}))

            clip = tone_clip(0.05, amplitude=cfg.probe_amplitude,
                             lead_silence=cfg.probe_lead_ms / 1000.0,
                             samplerate=cfg.samplerate, channels=cfg.channels,
                             clip_id="preflight-probe")
            if not clip.has_audible_onset:
                out.append(CheckResult(
                    "commit_timing", FAIL,
                    "probe clip has no detectable onset, so no audible-onset "
                    "estimate can be formed", blocking=cfg.timing_blocking))
                return out

            commit, offset, onset = [], [], []
            early = timed_out = late = skipped_no_onset = 0
            for i in range(cfg.commit_trials):
                try:
                    probe = run_commit_probe(
                        player, clip, f"preflight-{i}", clock=self.clock,
                        sleep=self._sleep, threshold_s=min(cfg.thresholds))
                except AudioFault as exc:
                    # The helper is built not to leave the player unusable, but
                    # a device failure mid-loop must still end in a report, not
                    # a traceback (R05-F01c).
                    out.append(CheckResult(
                        "commit_timing", FAIL,
                        f"probe {i} raised {type(exc).__name__}: {exc}",
                        blocking=True,
                        data={"failed_trial": i, "committed": len(commit),
                              "timed_out": timed_out}))
                    return out
                if probe.outcome == PROBE_STUCK:
                    out.append(CheckResult(
                        "commit_timing", FAIL,
                        f"probe {i}: {probe.detail}", blocking=True,
                        data={"failed_trial": i, "committed": len(commit),
                              "timed_out": timed_out}))
                    return out
                if not probe.committed:
                    timed_out += 1
                    continue
                cand = probe.candidate
                if probe.outcome == PROBE_COMMITTED_LATE:
                    late += 1
                if cand.committed_at < probe.deadline:
                    early += 1
                commit.append((cand.committed_at - probe.deadline) * 1000.0)
                # An unknown term is skipped and counted, never written as zero
                # (R03-F10c). Defence in depth only: with the tone_clip probe
                # built above both terms are always set (R05-F02).
                if cand.device_offset_s is None or cand.onset_delay_s is None:
                    skipped_no_onset += 1
                else:
                    offset.append(cand.device_offset_s * 1000.0)
                    onset.append(cand.onset_delay_s * 1000.0)

            out.extend(self._report_probes(
                commit=commit, offset=offset, onset=onset, early=early,
                timed_out=timed_out, late=late,
                skipped_no_onset=skipped_no_onset))
            if any(c.name == "commit_timing" and c.status == FAIL
                   for c in out):
                return out

            if len(entries) > 2:
                gaps = [b - a for a, b in zip(entries, entries[1:])]
                nominal = cfg.blocksize / cfg.samplerate
                out.append(CheckResult(
                    "callback_cadence", PASS,
                    f"{len(entries)} callbacks, median "
                    f"{statistics.median(gaps) * 1000:.2f} ms, max "
                    f"{max(gaps) * 1000:.2f} ms (nominal "
                    f"{nominal * 1000:.2f} ms)",
                    data={"callbacks": len(entries),
                          "median_interval_ms": statistics.median(gaps) * 1000,
                          "max_interval_ms": max(gaps) * 1000,
                          "nominal_interval_ms": nominal * 1000,
                          "underruns": player.underruns}))
            out.append(CheckResult(
                "acoustic_onset", NOT_RUN,
                "no acoustic reference channel configured: every onset figure "
                "in this session is an estimate from the device latency "
                "report, not a measurement (goal.md section 7)"))
        finally:
            player.stop("preflight_complete")
            player.close()
        return out

    def measure_capture(self, device_index) -> list[CheckResult]:
        """Open the microphone briefly and check the capture path.

        Only runs when ``check_capture`` is enabled. This opens the live
        microphone, and the operator view must say so while it runs.
        """
        cfg = self.config
        if not cfg.check_capture:
            return [CheckResult(
                "capture_stream", NOT_RUN,
                "capture check disabled in configuration; the microphone was "
                "not opened")]
        info = self.inventory_report or self._inventory()
        if not info.get("capture_possible"):
            return [CheckResult(
                "capture_stream", BLOCKED,
                "no input-capable device: " + "; ".join(info.get("warnings", [])),
                blocking=cfg.capture_blocking)]
        if device_index is None:
            return [CheckResult(
                "capture_stream", BLOCKED,
                "no input device was resolved; pin one by identity",
                blocking=cfg.capture_blocking)]
        try:
            backend = self._backend_factory(self.clock)
        except Exception as exc:
            return [CheckResult("capture_stream", BLOCKED,
                                f"audio backend unavailable: "
                                f"{type(exc).__name__}: {exc}",
                                blocking=cfg.capture_blocking)]

        scratch = Path(cfg.scratch_dir or ".preparation") / "preflight"
        scratch.mkdir(parents=True, exist_ok=True)
        target = scratch / f"capture-check-{int(time.time())}.wav"
        rec = ContinuousRecorder(target, backend=backend, clock=self.clock,
                                 samplerate=cfg.samplerate,
                                 channels=cfg.channels,
                                 blocksize=cfg.blocksize, device=device_index,
                                 ledger=self.ledger)
        try:
            rec.start()
        except Exception as exc:
            return [CheckResult("capture_stream", FAIL,
                                f"could not open input: "
                                f"{type(exc).__name__}: {exc}",
                                blocking=cfg.capture_blocking)]
        out: list[CheckResult] = []
        try:
            self._sleep(cfg.capture_seconds)
            stall = rec.check_liveness(self.clock.now())
            result = rec.finalize(reason="preflight")
        finally:
            target.unlink(missing_ok=True)   # a device check is not research data

        integrity = result.integrity
        ok = result.frames > 0 and not stall
        out.append(CheckResult(
            "capture_stream", PASS if ok else FAIL,
            f"{result.frames} frames in {cfg.capture_seconds:.1f}s, "
            f"gaps={len(integrity['gaps'])}, basis={integrity['gap_basis']}"
            + ("" if not stall else f"; {stall.detail}"),
            blocking=cfg.capture_blocking,
            data={"integrity": integrity,
                  "faults": result.faults,
                  "frames": result.frames}))
        out.append(CheckResult(
            "capture_continuity",
            PASS if integrity["continuous"] else FAIL,
            f"continuous={integrity['continuous']}, "
            f"lost={integrity['frames_lost_estimate']} frames, "
            f"anomalies={len(integrity['clock_anomalies'])}",
            blocking=cfg.capture_blocking,
            data={"integrity": integrity}))
        drift = integrity.get("drift_ppm")
        out.append(CheckResult(
            "capture_clock", PASS if drift is not None else NOT_RUN,
            f"measured rate {integrity.get('measured_rate')}, "
            f"drift {drift} ppm" if drift is not None
            else f"baseline shorter than 1 s; drift not estimable from a "
                 f"{cfg.capture_seconds:.1f}s check",
            data={"drift_ppm": drift,
                  "measured_rate": integrity.get("measured_rate")}))
        return out

    # -- orchestration

    def run(self) -> PreflightReport:
        """Run every configured check and return the storable report."""
        cfg = self.config
        report = PreflightReport(
            session_id=cfg.session_id,
            started_at_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            environment={},
        )
        device_results = self.check_devices()
        for result in device_results:
            report.add(result)
        report.environment = self.environment()
        report.environment["config"] = cfg.as_record()

        report.add(self.check_participant_configuration())
        report.add(self.check_detector_profile())
        report.add(self.check_disk_space())
        report.add(self.check_stimuli())

        def resolved(role: str) -> int | None:
            for result in device_results:
                if result.name == f"{role}_device" and result.status == PASS:
                    return result.data.get("device_index")
            return None

        out_index = resolved("output")
        if any(r.name == "output_device" and r.status in _BAD
               for r in device_results):
            report.add(CheckResult(
                "output_stream", BLOCKED,
                "output device unresolved; stream not opened", blocking=True))
        else:
            for result in self.measure_output(out_index):
                report.add(result)

        for result in self.measure_capture(resolved("input")):
            report.add(result)
        return report


# --- command line -------------------------------------------------------------

def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description="Run the session preflight and write its report.")
    ap.add_argument("--config", help="experiment or preflight configuration JSON")
    ap.add_argument("--session-id", default=None)
    ap.add_argument("--device", default=None,
                    help="output device index, overriding the configuration")
    ap.add_argument("--check-capture", action="store_true",
                    help="also open the live microphone for a brief check")
    ap.add_argument("--trials", type=int, default=None)
    ap.add_argument("--out", default=None, help="write the JSON report here")
    args = ap.parse_args(argv)

    cfg = load_config(args.config) if args.config else PreflightConfig()
    if args.session_id:
        cfg.session_id = args.session_id
    if args.device is not None:
        cfg.output_device_index = int(args.device)
    if args.check_capture:
        cfg.check_capture = True
    if args.trials is not None:
        cfg.commit_trials = args.trials

    if cfg.check_capture:
        print("NOTE: the live microphone will be opened for "
              f"{cfg.capture_seconds:.1f}s.")

    report = SessionPreflight(cfg).run()
    for line in report.operator_lines():
        print(line)
    if args.out:
        print("report:", report.to_json(args.out))
    return 0 if report.may_start else 2


if __name__ == "__main__":
    raise SystemExit(main())
