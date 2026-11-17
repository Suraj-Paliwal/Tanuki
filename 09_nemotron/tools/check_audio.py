"""M1 audio feasibility checks for the Tanuki experiment controller.

Run from ``09_nemotron``:

    python tools/check_audio.py                       # inventory + synthetic
    python tools/check_audio.py --playback            # also opens the speakers
    python tools/check_audio.py --duplex --allow-microphone
    python tools/check_audio.py --out validation/audio_check.json

Three levels, deliberately separated by what they actually prove:

``inventory``
    Lists host APIs and devices and says whether capture and playback are even
    possible. Opens no stream.

``synthetic``
    Runs the controller's capture/playback state machine on the fake backend
    with a manual clock: no device, fully deterministic. Proves the logic, not
    the hardware.

``playback`` (``--playback``)
    Opens the real output device and plays a short quiet test tone, audibly.
    Measures callback cadence, device-reported latency and the delay between an
    eligibility deadline and the commit that follows it. These are scheduling
    and device-latency figures; the acoustic onset is *not* measured here. A
    microphone and a recorded playback reference are required for that, and
    this tool will not invent it.

``duplex`` (``--duplex --allow-microphone``)
    Opens the microphone. Needs both flags, and refuses if no input device
    exists. Nothing in the default or ``--playback`` path records audio.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

import audio_io  # noqa: E402
from audio_io import (  # noqa: E402
    CAPTURE_RATE,
    DEFAULT_BLOCKSIZE,
    ContinuousRecorder,
    FakeBackend,
    OutputPlayer,
    SoundDeviceBackend,
    inventory,
    silence_clip,
    tone_clip,
)
from dataclasses import replace  # noqa: E402

from timing import (  # noqa: E402
    DEFAULT_PROFILE,
    DetectorProfile,
    ManualClock,
    MonotonicClock,
    PauseTimer,
    PromptCandidate,
    ResampleMap,
    SpeechSegmenter,
    TimingLedger,
    validate_detector_profile,
)

PASS, FAIL, NOT_RUN, BLOCKED = "PASS", "FAIL", "NOT_RUN", "BLOCKED"
INCOMPLETE = "INCOMPLETE"


def _result(name: str, status: str, detail: str, **data) -> dict:
    return {"check": name, "status": status, "detail": detail, **data}


# --- environment --------------------------------------------------------------

def environment() -> dict:
    env = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "numpy": np.__version__,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    for mod in ("sounddevice", "soundfile", "onnxruntime"):
        try:
            env[mod] = __import__(mod).__version__
        except Exception as exc:
            env[mod] = f"unavailable: {type(exc).__name__}"
    return env


# --- synthetic checks ---------------------------------------------------------

def synthetic_checks() -> list[dict]:
    """Device-free end-to-end run of the capture/playback state machine."""
    out: list[dict] = []
    rate, block = CAPTURE_RATE, DEFAULT_BLOCKSIZE
    block_s = block / rate

    # The one named profile, so the tool, the tests and the documented
    # settings cannot drift apart (round-1 finding R02-F08).
    profile = replace(DEFAULT_PROFILE, detector="synthetic-probabilities")
    thresholds = [0.5, 1.0, 2.0]
    try:
        validate_detector_profile(profile, thresholds, decision_budget_s=block_s)
        out.append(_result(
            "detector_profile_serves_shortest_threshold", PASS,
            f"hangover {profile.hangover_ms:.0f} ms + {block_s * 1000:.0f} ms "
            f"decision budget < {min(thresholds):.1f} s"))
    except ValueError as exc:
        out.append(_result("detector_profile_serves_shortest_threshold", FAIL,
                           str(exc)))

    # Pause timing: the configured interval is added once to the real offset.
    for threshold in thresholds:
        seg = SpeechSegmenter(profile, ResampleMap(rate, 16_000),
                              lambda i: i * profile.frame_s)
        timer = PauseTimer(threshold, profile=profile)
        speech_frames = 10
        for event in seg.push_all([0.9] * speech_frames + [0.0] * 8):
            timer.note_event(event)
        expected = speech_frames * profile.frame_s + threshold
        ok = timer.deadline is not None and abs(timer.deadline - expected) < 1e-9
        out.append(_result(
            f"pause_deadline_{threshold}s", PASS if ok else FAIL,
            f"deadline {timer.deadline!r}, expected {expected:.6f} "
            f"(offset {speech_frames * profile.frame_s:.3f}s + {threshold}s)",
            detector_delay_s=profile.hangover_s))

    # Recording + deadline-gated prompt on one shared manual clock.
    clock = ManualClock(0.0)
    backend = FakeBackend(clock, output_latency=0.020)
    ledger = TimingLedger(clock=clock)
    with tempfile.TemporaryDirectory() as tmp:
        rec = ContinuousRecorder(Path(tmp) / "synthetic.wav", backend=backend,
                                 clock=clock, samplerate=rate, blocksize=block,
                                 ledger=ledger)
        player = OutputPlayer(backend=backend, clock=clock, samplerate=rate,
                              blocksize=block, ledger=ledger)
        rec.start()
        player.open()
        mic, speaker = backend.streams[0], backend.streams[1]

        clip = tone_clip(0.6, samplerate=rate, clip_id="synthetic-encouragement")
        player.begin_attempt("synthetic")
        deadline = clock.now() + 0.5
        cand = PromptCandidate(trial_id="synthetic", threshold_s=0.5,
                               deadline=deadline, scheduled_at=clock.now())
        player.arm(clip, cand)

        def speech(frames):
            return (np.ones((frames, 1), np.int16) * 6000)

        backend.pump_all(40, sources={mic: speech})      # 400 ms: before deadline
        early = cand.committed
        backend.pump_all(40, sources={mic: speech})      # past the deadline
        result = rec.finalize()
        player.close()

    out.append(_result("no_prompt_before_deadline", FAIL if early else PASS,
                       "candidate was committed before its deadline" if early
                       else "output stayed silent until the deadline"))
    committed = cand.committed and cand.committed_at is not None
    out.append(_result(
        "prompt_commits_after_deadline", PASS if committed else FAIL,
        f"committed_at - deadline = "
        f"{(cand.committed_at - deadline) * 1000:.2f} ms" if committed
        else "candidate never committed",
        commit_delay_ms=(cand.committed_at - deadline) * 1000 if committed else None,
        audible_onset=cand.audible_onset.as_record() if cand.audible_onset else None))
    out.append(_result(
        "recording_continuous_through_prompt",
        PASS if result.integrity["continuous"] and result.frames == 80 * block
        else FAIL,
        f"{result.frames} frames written, gaps={len(result.integrity['gaps'])}",
        integrity=result.integrity))
    out.append(_result(
        "recording_finalized_atomically", PASS if result.finalized else FAIL,
        f"published={result.finalized} sha256={result.sha256[:16]}..."))
    return out


# --- real device checks -------------------------------------------------------

def playback_check(*, seconds: float = 1.0, amplitude: float = 0.08,
                   device=None, blocksize: int = DEFAULT_BLOCKSIZE) -> list[dict]:
    """Open the real output device and play an audible quiet test tone."""
    out: list[dict] = []
    clock = MonotonicClock()
    ledger = TimingLedger(clock=clock)
    try:
        backend = SoundDeviceBackend(clock)
    except Exception as exc:
        return [_result("playback_stream", BLOCKED,
                        f"sounddevice unavailable: {type(exc).__name__}: {exc}")]

    entries: list[float] = []
    methods: set[str] = set()
    player = OutputPlayer(backend=backend, clock=clock, samplerate=CAPTURE_RATE,
                          blocksize=blocksize, device=device, ledger=ledger)
    original = player._callback

    def instrumented(outdata, timing, status):
        entries.append(timing.entry_time)
        methods.add(timing.method)
        original(outdata, timing, status)

    player._callback = instrumented
    try:
        player.open()
    except Exception as exc:
        return [_result("playback_stream", FAIL,
                        f"could not open output: {type(exc).__name__}: {exc}")]

    try:
        latency = player.latency_s
        clip = tone_clip(seconds, amplitude=amplitude, samplerate=CAPTURE_RATE,
                         clip_id="bench-tone")
        player.begin_attempt("bench")
        deadline = clock.now() + 0.30
        cand = PromptCandidate(trial_id="bench", threshold_s=0.5,
                               deadline=deadline, scheduled_at=clock.now())
        player.arm(clip, cand)
        t_end = clock.now() + 0.30 + seconds + 0.60
        while clock.now() < t_end:
            time.sleep(0.01)
        out.append(_result(
            "playback_stream", PASS,
            f"opened at {CAPTURE_RATE} Hz, blocksize {blocksize}, "
            f"device-reported output latency {latency * 1000:.1f} ms",
            reported_output_latency_ms=latency * 1000,
            block_timing_method=sorted(methods)))
        if cand.committed:
            delay_ms = (cand.committed_at - deadline) * 1000
            onset = cand.audible_onset
            out.append(_result(
                "commit_delay_after_deadline", PASS if delay_ms >= 0 else FAIL,
                f"commit {delay_ms:.2f} ms after the deadline; estimated audible "
                f"onset {(onset.seconds - deadline) * 1000:.2f} ms after it",
                commit_delay_ms=delay_ms,
                estimated_onset_delay_ms=(onset.seconds - deadline) * 1000,
                onset_method=onset.method,
                onset_uncertainty_ms=(onset.uncertainty_s or 0.0) * 1000))
        else:
            out.append(_result("commit_delay_after_deadline", FAIL,
                               "armed prompt never committed"))
        if len(entries) > 2:
            gaps = [b - a for a, b in zip(entries, entries[1:])]
            nominal = blocksize / CAPTURE_RATE
            out.append(_result(
                "callback_cadence", PASS,
                f"{len(entries)} callbacks; interval median "
                f"{statistics.median(gaps) * 1000:.2f} ms "
                f"(nominal {nominal * 1000:.2f} ms), max "
                f"{max(gaps) * 1000:.2f} ms",
                callbacks=len(entries),
                median_interval_ms=statistics.median(gaps) * 1000,
                max_interval_ms=max(gaps) * 1000,
                nominal_interval_ms=nominal * 1000,
                underruns=player.underruns))
        else:
            out.append(_result("callback_cadence", FAIL,
                               f"only {len(entries)} callbacks observed"))
        out.append(_result(
            "acoustic_onset", NOT_RUN,
            "no acoustic reference channel: audible onset is an estimate from "
            "the device latency report, not a measurement. Needs a microphone "
            "or loopback capture of the output (goal.md section 7)."))
    finally:
        player.stop("bench_complete")
        player.close()
    return out



def survey_outputs(*, blocksize: int = DEFAULT_BLOCKSIZE,
                   seconds: float = 1.0, host_apis=None) -> list[dict]:
    """Open each candidate output device briefly and compare its latency.

    Emits silence only - nothing audible, nothing recorded. The point is the
    device-reported output latency and the callback cadence, because those
    together bound how soon after an eligibility deadline a prompt can become
    audible. The MME default device is not necessarily the right one.
    """
    out: list[dict] = []
    clock = MonotonicClock()
    try:
        backend = SoundDeviceBackend(clock)
        import sounddevice as sd
    except Exception as exc:
        return [_result("output_survey", BLOCKED,
                        f"sounddevice unavailable: {type(exc).__name__}: {exc}")]

    hostapi_names = [a["name"] for a in sd.query_hostapis()]
    wanted = set(host_apis or hostapi_names)
    seen: set[str] = set()
    for index, dev in enumerate(sd.query_devices()):
        if dev["max_output_channels"] < 1:
            continue
        api = hostapi_names[dev["hostapi"]]
        if api not in wanted or api in seen:
            continue          # first output device per host API is enough
        seen.add(api)
        name = str(dev["name"]).replace("\n", " ").strip()
        entries: list[float] = []
        methods: set[str] = set()

        def record_block(outdata, timing, status, _e=entries, _m=methods):
            _e.append(timing.entry_time)
            _m.add(timing.method)

        stream = None
        try:
            stream = backend.open_output(samplerate=CAPTURE_RATE, channels=1,
                                         blocksize=blocksize, device=index,
                                         callback=record_block)
            stream.start()
            deadline = clock.now() + seconds
            while clock.now() < deadline:
                time.sleep(0.01)
            latency = stream.latency
            if isinstance(latency, (tuple, list)):
                latency = latency[-1]
            gaps = [b - a for a, b in zip(entries, entries[1:])]
            out.append(_result(
                f"output_survey[{api}]", PASS if entries else FAIL,
                f"device {index} {name!r}: reported latency "
                f"{float(latency) * 1000:.1f} ms, {len(entries)} callbacks, "
                f"max interval {max(gaps) * 1000:.2f} ms" if gaps else
                f"device {index} {name!r}: no callbacks",
                device_index=index, device_name=name, hostapi=api,
                reported_output_latency_ms=float(latency) * 1000,
                callbacks=len(entries),
                max_interval_ms=(max(gaps) * 1000) if gaps else None,
                median_interval_ms=(statistics.median(gaps) * 1000) if gaps else None,
                block_timing_method=sorted(methods)))
        except Exception as exc:
            out.append(_result(f"output_survey[{api}]", BLOCKED,
                               f"device {index} {name!r}: "
                               f"{type(exc).__name__}: {exc}",
                               device_index=index, hostapi=api))
        finally:
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
    return out



def _percentile(values, fraction):
    ordered = sorted(values)
    if not ordered:
        return None
    k = max(0, min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1)))))
    return ordered[k]


def commit_distribution(*, trials: int = 30, device=None,
                        blocksize: int = DEFAULT_BLOCKSIZE,
                        clip_s: float = 0.05) -> list[dict]:
    """Arm many prompts on the real output device and report the spread.

    The clips are silent, so this is inaudible. What it measures is the
    scheduling path: how long after an eligibility deadline the controller
    commits, and what audible onset the device's latency report implies. The
    candidate target in goal.md section 7 is a 95th-percentile onset delay of
    at most 100 ms - this check produces a number comparable to it, but from
    device-reported latency, not from sound. The acoustic figure still requires
    a recorded playback reference.
    """
    clock = MonotonicClock()
    try:
        backend = SoundDeviceBackend(clock)
    except Exception as exc:
        return [_result("commit_distribution", BLOCKED,
                        f"sounddevice unavailable: {type(exc).__name__}: {exc}")]
    player = OutputPlayer(backend=backend, clock=clock, samplerate=CAPTURE_RATE,
                          blocksize=blocksize, device=device)
    try:
        player.open()
    except Exception as exc:
        return [_result("commit_distribution", FAIL,
                        f"could not open output: {type(exc).__name__}: {exc}")]

    # A tone with a known leading silence, not a silent clip. A silent clip
    # has no audible onset at all, and an earlier version of this probe added
    # its whole length to every onset estimate as "leading silence" - inflating
    # the reported figures by exactly the clip length.
    # Faintly audible on purpose: a clip quiet enough to be silent has no
    # onset to estimate, so the probe must carry a real one. The 10 ms lead
    # also makes the clip-lead component non-zero and therefore checkable.
    clip = tone_clip(clip_s, amplitude=0.02, lead_silence=0.010,
                     samplerate=CAPTURE_RATE, clip_id="commit-probe")
    if not clip.has_audible_onset:
        return [_result("commit_distribution", FAIL,
                        "probe clip has no detectable onset")]
    commit_delays: list[float] = []
    onset_delays: list[float] = []
    device_offsets: list[float] = []
    leads: list[float] = []
    skipped_no_onset = 0
    early = timed_out = 0
    try:
        for i in range(trials):
            player.begin_attempt(f"probe-{i}")
            deadline = clock.now() + 0.08
            cand = PromptCandidate(trial_id=f"probe-{i}", threshold_s=0.5,
                                   deadline=deadline, scheduled_at=clock.now())
            player.arm(clip, cand)
            limit = deadline + clip_s + 0.5
            while not cand.committed and clock.now() < limit:
                time.sleep(0.002)
            if not cand.committed:
                # Release the slot; an armed leftover crashes the next probe's
                # begin_attempt() rather than failing cleanly (R04-F01).
                player.cancel_candidate("probe_timeout")
                timed_out += 1
                continue
            delay = (cand.committed_at - deadline) * 1000.0
            if delay < 0:
                early += 1
            commit_delays.append(delay)
            # A probe without an onset estimate is dropped from the onset
            # distribution and counted, never recorded as zero (R03-F10c).
            if (cand.onset_delay_s is None or cand.device_offset_s is None
                    or cand.clip_leading_silence_s is None):
                skipped_no_onset += 1
            else:
                device_offsets.append(cand.device_offset_s * 1000.0)
                leads.append(cand.clip_leading_silence_s * 1000.0)
                onset_delays.append(cand.onset_delay_s * 1000.0)
            # Let the clip finish before arming the next one.
            while player.state != "idle" and clock.now() < limit:
                time.sleep(0.002)
            outcome = player.cancel_candidate("probe_cleanup")
            if outcome.outcome not in ("too_late_committed", "nothing_armed"):
                return [_result("commit_distribution", FAIL,
                                f"probe {i} ended in state {outcome.outcome}")]
    finally:
        player.stop("probe_complete")
        player.close()

    if len(commit_delays) < trials:
        return [_result("commit_distribution", FAIL,
                        f"only {len(commit_delays)}/{trials} prompts committed "
                        f"({timed_out} timed out)",
                        committed=len(commit_delays), timed_out=timed_out)]
    out = [_result(
        "no_early_commitment", FAIL if early else PASS,
        f"{early} of {trials} commitments landed before their deadline",
        early=early, trials=trials)]
    out.append(_result(
        "commit_delay_distribution", PASS,
        f"n={trials} commit delay median "
        f"{statistics.median(commit_delays):.2f} ms, p95 "
        f"{_percentile(commit_delays, 0.95):.2f} ms, max "
        f"{max(commit_delays):.2f} ms",
        n=trials,
        median_ms=statistics.median(commit_delays),
        p95_ms=_percentile(commit_delays, 0.95),
        max_ms=max(commit_delays),
        min_ms=min(commit_delays)))
    p95 = _percentile(onset_delays, 0.95)
    if not onset_delays:
        out.append(_result(
            "estimated_onset_delay_distribution", NOT_RUN,
            f"no probe produced an onset estimate ({skipped_no_onset} skipped)",
            skipped=skipped_no_onset))
        return out
    out.append(_result(
        "device_offset_distribution", PASS,
        f"n={trials} device offset median "
        f"{statistics.median(device_offsets):.2f} ms, max "
        f"{max(device_offsets):.2f} ms (buffer time minus commit instant)",
        n=trials,
        median_ms=statistics.median(device_offsets),
        max_ms=max(device_offsets),
        method="estimated"))
    out.append(_result(
        "estimated_onset_delay_distribution", PASS,
        f"n={trials} estimated onset delay median "
        f"{statistics.median(onset_delays):.2f} ms, p95 {p95:.2f} ms, max "
        f"{max(onset_delays):.2f} ms = commit delay "
        f"{statistics.median(commit_delays):.2f} + device offset "
        f"{statistics.median(device_offsets):.2f} + clip lead "
        f"{statistics.median(leads):.2f} (medians) - device-latency estimate, "
        f"not acoustic",
        n=len(onset_delays),
        skipped_no_onset=skipped_no_onset,
        median_ms=statistics.median(onset_delays),
        p95_ms=p95,
        max_ms=max(onset_delays),
        components_median_ms={
            "commit_delay": statistics.median(commit_delays),
            "device_offset": statistics.median(device_offsets),
            "clip_leading_silence": statistics.median(leads),
        },
        method="estimated",
        caveat="sum of a scheduling delay, a device-reported latency and a "
               "property of the clip; the acoustic onset is unmeasured"))
    # Reported as its own check so a passing "we measured the spread" cannot be
    # read as "the device meets the target". The 100 ms figure is the candidate
    # engineering target in goal.md section 7, not an approved bound.
    out.append(_result(
        "meets_candidate_onset_target", PASS if p95 <= 100.0 else FAIL,
        f"estimated p95 onset delay {p95:.2f} ms vs the 100 ms candidate "
        f"target (a proposal, not a research-approved tolerance; the acoustic "
        f"onset is still unmeasured)",
        p95_ms=p95, candidate_target_ms=100.0,
        meets_candidate_target=bool(p95 <= 100.0),
        basis="estimated"))
    return out


def duplex_check(*, allow_microphone: bool, seconds: float = 2.0,
                 input_device=None) -> list[dict]:
    if not allow_microphone:
        return [_result("duplex_capture", BLOCKED,
                        "live microphone capture needs --allow-microphone; "
                        "not run")]
    info = inventory()
    if input_device is None and not info.get("default_capture_available"):
        return [_result("duplex_capture", BLOCKED,
                        "no default input device; pass --input-device to use "
                        "one of: " + ", ".join(info.get("input_devices", []))
                        if info.get("capture_possible") else
                        "no input-capable device: "
                        + "; ".join(info.get("warnings", [])))]
    clock = MonotonicClock()
    ledger = TimingLedger(clock=clock)
    backend = SoundDeviceBackend(clock)
    with tempfile.TemporaryDirectory() as tmp:
        rec = ContinuousRecorder(Path(tmp) / "duplex.wav", backend=backend,
                                 clock=clock, samplerate=CAPTURE_RATE,
                                 blocksize=DEFAULT_BLOCKSIZE, ledger=ledger,
                                 device=input_device)
        rec.start()
        time.sleep(seconds)
        result = rec.finalize()
    return [_result(
        "duplex_capture", PASS if result.frames else FAIL,
        f"{result.frames} frames captured, gaps="
        f"{len(result.integrity['gaps'])}, drift_ppm="
        f"{result.integrity['drift_ppm']}",
        integrity=result.integrity)]


# --- main ---------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--playback", action="store_true",
                    help="open the real output device and play an audible test tone")
    ap.add_argument("--commit-trials", type=int, default=0,
                    help="arm this many silent prompts on the real output "
                         "device and report the commit/onset-delay spread")
    ap.add_argument("--survey", action="store_true",
                    help="open one output device per host API (silence only) and "
                         "compare reported latency and callback cadence")
    ap.add_argument("--duplex", action="store_true",
                    help="open the microphone (also needs --allow-microphone)")
    ap.add_argument("--allow-microphone", action="store_true",
                    help="explicit consent to record from the live microphone")
    ap.add_argument("--seconds", type=float, default=1.0,
                    help="test tone length for --playback")
    ap.add_argument("--blocksize", type=int, default=DEFAULT_BLOCKSIZE)
    ap.add_argument("--device", default=None,
                    help="output device index or name for --playback")
    ap.add_argument("--input-device", default=None,
                    help="input device index for --duplex (needed when no "
                         "default input exists)")
    ap.add_argument("--out", default=None, help="write the JSON report here")
    args = ap.parse_args(argv)

    device = args.device
    if device is not None and str(device).lstrip("-").isdigit():
        device = int(device)

    report = {
        "tool": "tools/check_audio.py",
        "audio_io_module": str(Path(audio_io.__file__).name),
        "environment": environment(),
        "inventory": inventory(),
        "checks": [],
    }
    report["checks"].extend(synthetic_checks())
    if args.survey:
        report["checks"].extend(survey_outputs(blocksize=args.blocksize))
    if args.commit_trials:
        report["checks"].extend(commit_distribution(
            trials=args.commit_trials, device=device, blocksize=args.blocksize))
    if args.playback:
        report["checks"].extend(playback_check(
            seconds=args.seconds, device=device, blocksize=args.blocksize))
    else:
        report["checks"].append(_result(
            "playback_stream", NOT_RUN,
            "run with --playback to open the real output device"))
    input_device = args.input_device
    if input_device is not None and str(input_device).lstrip("-").isdigit():
        input_device = int(input_device)
    report["checks"].extend(duplex_check(allow_microphone=args.allow_microphone,
                                         input_device=input_device)
                            if args.duplex else
                            [_result("duplex_capture", NOT_RUN,
                                     "run with --duplex --allow-microphone")])

    counts: dict[str, int] = {}
    for check in report["checks"]:
        counts[check["status"]] = counts.get(check["status"], 0) + 1
    report["summary"] = counts
    # A report containing NOT_RUN or BLOCKED checks is not a pass. Stamping
    # "PASS" on one invites exactly the misreading EGM_WORKFLOW.md section 6
    # forbids: missing evidence is not evidence.
    if counts.get(FAIL):
        report["verdict"] = FAIL
    elif counts.get(BLOCKED):
        report["verdict"] = BLOCKED
    elif counts.get(NOT_RUN):
        report["verdict"] = INCOMPLETE
    else:
        report["verdict"] = PASS

    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")

    inv = report["inventory"]
    print(f"capture_available={inv.get('capture_available')} "
          f"playback_available={inv.get('playback_available')}")
    for warning in inv.get("warnings", []):
        print(f"  ! {warning}")
    for check in report["checks"]:
        print(f"{check['status']:<8} {check['check']}: {check['detail']}")
    print("summary:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print("verdict:", report["verdict"])
    if args.out:
        print("report:", args.out)
    return 1 if counts.get(FAIL) else 0


if __name__ == "__main__":
    raise SystemExit(main())
