"""Tests for the session preflight. No devices; everything is injected.

The preflight is what decides whether a session may start and what evidence
that session carries about the hardware it ran on, so the cases that matter are
the refusals and the honest-reporting ones: a pinned device that is no longer
present, timing outside the target, a microphone check that was never run.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audio_io import FakeBackend, write_wav, tone_clip  # noqa: E402
from preflight import (  # noqa: E402
    BLOCKED,
    FAIL,
    NOT_RUN,
    PASS,
    WARN,
    PreflightConfig,
    SessionPreflight,
    load_config,
)
from timing import DEFAULT_PROFILE, DetectorProfile, ManualClock  # noqa: E402

RATE = 48_000
BLOCK = 480

WASAPI_KEY = "Windows WASAPI|Speakers|0in/2out"
MIC_KEY = "Windows WASAPI|Microphone|1in/0out"


def fake_inventory(*, with_input=True, default_input=True,
                   default_output=True) -> dict:
    devices = [
        {"index": 0, "name": "Speakers", "hostapi": 0,
         "hostapi_name": "Windows WASAPI", "max_input_channels": 0,
         "max_output_channels": 2, "default_samplerate": 48000.0,
         "key": WASAPI_KEY},
    ]
    if with_input:
        devices.append(
            {"index": 1, "name": "Microphone", "hostapi": 0,
             "hostapi_name": "Windows WASAPI", "max_input_channels": 1,
             "max_output_channels": 0, "default_samplerate": 48000.0,
             "key": MIC_KEY})
    inputs = [d for d in devices if d["max_input_channels"] > 0]
    warnings = []
    if inputs and not default_input:
        warnings.append("input devices exist but none is the default")
    if not inputs:
        warnings.append("no input-capable device of any host API")
    return {
        "available": True,
        "portaudio": "fake",
        "devices": devices,
        "hostapis": [{"index": 0, "name": "Windows WASAPI",
                      "default_input_device": 1 if default_input else -1,
                      "default_output_device": 0 if default_output else -1}],
        "default_input_device": 1 if (default_input and inputs) else -1,
        "default_output_device": 0 if default_output else -1,
        "input_device_count": len(inputs),
        "output_device_count": 1,
        "capture_available": bool(inputs) and default_input,
        "default_capture_available": bool(inputs) and default_input,
        "capture_possible": bool(inputs),
        "playback_available": default_output,
        "default_playback_available": default_output,
        "playback_possible": True,
        "input_devices": [d["key"] for d in inputs],
        "warnings": warnings,
    }


class PreflightHarness(unittest.TestCase):
    """Drives the preflight against FakeBackend with a manual clock.

    The real preflight sleeps while the device streams; here ``sleep`` pumps
    the fake streams instead, so a whole preflight runs deterministically in
    microseconds with no audio hardware.
    """

    def _run(self, config, inventory=None, output_latency=0.020):
        clock = ManualClock(1000.0)
        backend = FakeBackend(clock, output_latency=output_latency)

        def sleep(seconds):
            blocks = max(1, int(round(seconds / (BLOCK / RATE))))
            active = [s for s in backend.streams if s.active]
            if not active:
                clock.advance(seconds)
                return
            backend.pump_all(blocks)

        pre = SessionPreflight(
            config, clock=clock,
            backend_factory=lambda c: backend,
            inventory_fn=lambda: inventory or fake_inventory(),
            sleep=sleep)
        return pre.run()

    def _check(self, report, name):
        for check in report.checks:
            if check.name == name:
                return check
        self.fail(f"no check named {name!r} in "
                  f"{[c.name for c in report.checks]}")


class DeviceResolutionTest(PreflightHarness):
    def test_a_pinned_device_that_is_present_resolves(self):
        cfg = PreflightConfig(session_id="s1", output_device_key=WASAPI_KEY,
                              commit_trials=3, samplerate=RATE, blocksize=BLOCK)
        report = self._run(cfg)
        check = self._check(report, "output_device")
        self.assertEqual(check.status, PASS)
        self.assertTrue(check.data["pinned"])
        self.assertEqual(check.data["device_index"], 0)

    def test_a_pinned_device_that_is_gone_blocks_the_session(self):
        """The timing of a session is a property of its devices.

        Falling back to whatever happens to be present would make the recorded
        measurements describe different hardware than the configuration claims.
        """
        cfg = PreflightConfig(session_id="s2",
                              output_device_key="Windows WASAPI|Gone|0in/2out",
                              commit_trials=3)
        report = self._run(cfg)
        check = self._check(report, "output_device")
        self.assertEqual(check.status, FAIL)
        self.assertTrue(check.blocks_session)
        self.assertFalse(report.may_start)
        self.assertEqual(report.verdict(), "BLOCKED")
        # The stream must not have been opened at all.
        self.assertEqual(self._check(report, "output_stream").status, BLOCKED)

    def test_an_ambiguous_pinned_identity_blocks_the_session(self):
        inventory = fake_inventory()
        duplicate = dict(inventory["devices"][0])
        duplicate["index"] = 7
        inventory["devices"].append(duplicate)
        cfg = PreflightConfig(session_id="s3", output_device_key=WASAPI_KEY,
                              commit_trials=3)
        report = self._run(cfg, inventory=inventory)
        check = self._check(report, "output_device")
        self.assertEqual(check.status, FAIL)
        self.assertTrue(check.blocks_session)

    def test_no_default_output_and_no_pin_is_a_blocking_failure(self):
        cfg = PreflightConfig(session_id="s4", commit_trials=3)
        report = self._run(cfg, inventory=fake_inventory(default_output=False))
        self.assertEqual(self._check(report, "output_device").status, FAIL)
        self.assertFalse(report.may_start)

    def test_input_devices_that_exist_but_are_not_default_are_warned_about(self):
        cfg = PreflightConfig(session_id="s5", output_device_key=WASAPI_KEY,
                              commit_trials=3)
        report = self._run(cfg, inventory=fake_inventory(default_input=False))
        check = self._check(report, "device_inventory")
        self.assertEqual(check.status, WARN)
        self.assertTrue(check.data["capture_possible"])
        self.assertFalse(check.data["default_capture_available"])
        # A warning must not stop the session.
        self.assertTrue(report.may_start)


class TimingPolicyTest(PreflightHarness):
    def test_timing_inside_the_target_passes(self):
        cfg = PreflightConfig(session_id="t1", output_device_key=WASAPI_KEY,
                              commit_trials=5, samplerate=RATE, blocksize=BLOCK,
                              max_onset_delay_ms=200.0)
        report = self._run(cfg)
        check = self._check(report, "onset_delay_target")
        self.assertEqual(check.status, PASS)
        self.assertTrue(check.data["meets_target"])

    def test_timing_outside_the_target_warns_and_still_allows_the_session(self):
        """The recorded decision: measure it, warn, let the session start.

        A session run on a slow configuration must be identifiable afterwards
        rather than silently equivalent to a good one.
        """
        cfg = PreflightConfig(session_id="t2", output_device_key=WASAPI_KEY,
                              commit_trials=5, samplerate=RATE, blocksize=BLOCK,
                              max_onset_delay_ms=5.0, timing_blocking=False)
        report = self._run(cfg, output_latency=0.180)
        check = self._check(report, "onset_delay_target")
        self.assertEqual(check.status, WARN)
        self.assertFalse(check.data["meets_target"])
        self.assertTrue(report.may_start)
        self.assertIn("onset_delay_target", [c.name for c in report.warnings])
        # A warning does not stop the session, but it also does not let the
        # report call itself a pass.
        self.assertFalse(report.is_pass)
        self.assertIn("WARNINGS", report.verdict())

    def test_timing_outside_the_target_blocks_when_configured_to(self):
        cfg = PreflightConfig(session_id="t3", output_device_key=WASAPI_KEY,
                              commit_trials=5, samplerate=RATE, blocksize=BLOCK,
                              max_onset_delay_ms=5.0, timing_blocking=True)
        report = self._run(cfg, output_latency=0.180)
        check = self._check(report, "onset_delay_target")
        self.assertEqual(check.status, FAIL)
        self.assertTrue(check.blocks_session)
        self.assertFalse(report.may_start)

    def test_the_onset_figure_is_reported_with_its_components(self):
        cfg = PreflightConfig(session_id="t4", output_device_key=WASAPI_KEY,
                              commit_trials=5, samplerate=RATE, blocksize=BLOCK,
                              probe_lead_ms=10.0)
        report = self._run(cfg)
        data = self._check(report, "onset_delay_target").data
        parts = data["components_median_ms"]
        self.assertIn("commit_delay", parts)
        self.assertIn("device_offset", parts)
        self.assertIn("clip_leading_silence", parts)
        self.assertEqual(data["method"], "estimated")
        self.assertAlmostEqual(parts["device_offset"], 20.0, delta=2.0)

    def test_no_early_output_is_checked_and_blocking(self):
        cfg = PreflightConfig(session_id="t5", output_device_key=WASAPI_KEY,
                              commit_trials=5, samplerate=RATE, blocksize=BLOCK)
        report = self._run(cfg)
        check = self._check(report, "no_early_output")
        self.assertEqual(check.status, PASS)
        self.assertEqual(check.data["early"], 0)
        self.assertTrue(check.blocking)

    def test_acoustic_onset_is_always_reported_as_not_run(self):
        """No configuration can make this code claim an acoustic measurement."""
        cfg = PreflightConfig(session_id="t6", output_device_key=WASAPI_KEY,
                              commit_trials=3, samplerate=RATE, blocksize=BLOCK)
        report = self._run(cfg)
        self.assertEqual(self._check(report, "acoustic_onset").status, NOT_RUN)
        self.assertNotEqual(report.verdict(), "PASS")
        self.assertFalse(report.is_pass)

    def test_a_report_with_unrun_checks_never_calls_itself_a_pass(self):
        """"Incomplete" outranks "passed with warnings".

        A preflight that skipped the microphone, the manifest and the acoustic
        reference has not established that the session is sound, whether or not
        anything warned.
        """
        cfg = PreflightConfig(session_id="t6b", output_device_key=WASAPI_KEY,
                              commit_trials=3, samplerate=RATE, blocksize=BLOCK)
        report = self._run(cfg)
        self.assertGreater(report.summary.get(NOT_RUN, 0), 0)
        self.assertIn("INCOMPLETE", report.verdict())
        self.assertFalse(report.is_pass)
        self.assertTrue(report.may_start)

    def test_a_detector_profile_that_cannot_serve_the_threshold_blocks(self):
        cfg = PreflightConfig(
            session_id="t7", output_device_key=WASAPI_KEY, commit_trials=3,
            detector_profile=DetectorProfile(hangover_ms=600.0),
            thresholds=(0.5, 1.0, 2.0))
        report = self._run(cfg)
        check = self._check(report, "detector_profile")
        self.assertEqual(check.status, FAIL)
        self.assertTrue(check.blocks_session)


class CaptureCheckTest(PreflightHarness):
    def test_the_microphone_is_not_opened_unless_explicitly_enabled(self):
        cfg = PreflightConfig(session_id="c1", output_device_key=WASAPI_KEY,
                              commit_trials=3, check_capture=False)
        report = self._run(cfg)
        check = self._check(report, "capture_stream")
        self.assertEqual(check.status, NOT_RUN)
        self.assertIn("not opened", check.detail)
        # A disabled check is never a pass.
        self.assertEqual(self._check(report, "input_device").status, NOT_RUN)
        self.assertNotEqual(report.verdict(), "PASS")

    def test_an_enabled_capture_check_with_no_input_device_is_blocked(self):
        cfg = PreflightConfig(session_id="c2", output_device_key=WASAPI_KEY,
                              commit_trials=3, check_capture=True,
                              capture_blocking=True)
        report = self._run(cfg, inventory=fake_inventory(with_input=False))
        check = self._check(report, "capture_stream")
        self.assertEqual(check.status, BLOCKED)
        self.assertTrue(check.blocks_session)
        self.assertFalse(report.may_start)


class StimulusAndStorageTest(PreflightHarness):
    def test_a_missing_manifest_and_data_root_are_not_run_not_pass(self):
        cfg = PreflightConfig(session_id="m1", output_device_key=WASAPI_KEY,
                              commit_trials=3)
        report = self._run(cfg)
        self.assertEqual(self._check(report, "stimulus_hashes").status, NOT_RUN)
        self.assertEqual(self._check(report, "disk_space").status, NOT_RUN)

    def test_a_manifest_hash_mismatch_blocks_the_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clip = tone_clip(0.05, samplerate=RATE)
            write_wav(root / "story.wav", clip.samples, RATE)
            (root / "manifest.json").write_text(json.dumps({
                "version": "test",
                "assets": [{"id": "story-1", "audio": "story.wav",
                            "sha256": "0" * 64}],
            }), encoding="utf-8")
            cfg = PreflightConfig(session_id="m2",
                                  output_device_key=WASAPI_KEY,
                                  commit_trials=3, samplerate=RATE,
                                  stimulus_manifest=str(root / "manifest.json"))
            report = self._run(cfg)
        check = self._check(report, "stimulus_hashes")
        self.assertEqual(check.status, FAIL)
        self.assertTrue(check.blocks_session)

    def test_matching_manifest_hashes_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clip = tone_clip(0.05, samplerate=RATE)
            digest = write_wav(root / "story.wav", clip.samples, RATE)
            (root / "manifest.json").write_text(json.dumps({
                "version": "test",
                "assets": [{"id": "story-1", "audio": "story.wav",
                            "sha256": digest}],
            }), encoding="utf-8")
            cfg = PreflightConfig(session_id="m3",
                                  output_device_key=WASAPI_KEY,
                                  commit_trials=3, samplerate=RATE,
                                  stimulus_manifest=str(root / "manifest.json"))
            report = self._run(cfg)
        check = self._check(report, "stimulus_hashes")
        self.assertEqual(check.status, PASS)
        self.assertEqual(check.data["verified"], 1)

    def test_a_configured_data_root_is_checked_for_space(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = PreflightConfig(session_id="m4",
                                  output_device_key=WASAPI_KEY,
                                  commit_trials=3, data_root=tmp,
                                  min_free_gb=0.0001)
            report = self._run(cfg)
        check = self._check(report, "disk_space")
        self.assertEqual(check.status, PASS)
        self.assertGreater(check.data["free_gb"], 0)

    def test_a_missing_data_root_blocks_the_session(self):
        cfg = PreflightConfig(session_id="m5", output_device_key=WASAPI_KEY,
                              commit_trials=3,
                              data_root="Z:/does/not/exist/research-data")
        report = self._run(cfg)
        check = self._check(report, "disk_space")
        self.assertEqual(check.status, FAIL)
        self.assertTrue(check.blocks_session)


class ReportRecordTest(PreflightHarness):
    def test_the_report_is_storable_and_records_the_configuration(self):
        cfg = PreflightConfig(session_id="r1", output_device_key=WASAPI_KEY,
                              commit_trials=3, samplerate=RATE, blocksize=BLOCK)
        report = self._run(cfg)
        record = report.as_record()
        self.assertEqual(record["session_id"], "r1")
        self.assertIn("config", record["environment"])
        self.assertFalse(
            record["environment"]["config"]["max_onset_delay_is_frozen_tolerance"])
        self.assertIn("verdict", record)
        with tempfile.TemporaryDirectory() as tmp:
            path = report.to_json(Path(tmp) / "preflight.json")
            loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(loaded["session_id"], "r1")
        self.assertEqual(loaded["verdict"], record["verdict"])

    def test_operator_lines_name_every_check(self):
        cfg = PreflightConfig(session_id="r2", output_device_key=WASAPI_KEY,
                              commit_trials=3)
        report = self._run(cfg)
        lines = report.operator_lines()
        self.assertIn("r2", lines[0])
        for check in report.checks:
            self.assertTrue(any(check.name in line for line in lines),
                            f"{check.name} missing from the operator view")


class ConfigLoadingTest(unittest.TestCase):
    def test_the_project_configuration_loads_and_pins_what_it_claims(self):
        cfg = load_config(Path(__file__).resolve().parents[1]
                          / "config" / "experiment.json")
        self.assertEqual(cfg.samplerate, 48_000)
        self.assertEqual(cfg.blocksize, 480)
        self.assertFalse(cfg.check_capture)
        self.assertFalse(cfg.timing_blocking)
        self.assertEqual(cfg.max_onset_delay_ms, 100.0)
        self.assertIn("WASAPI", cfg.output_device_key)
        self.assertIsNone(cfg.input_device_key)
        self.assertIsNone(cfg.data_root)
        self.assertIsNone(cfg.stimulus_manifest)

    def test_the_configured_detector_profile_matches_the_library_default(self):
        """A second copy of the profile is a second chance to disagree."""
        cfg = load_config(Path(__file__).resolve().parents[1]
                          / "config" / "experiment.json")
        self.assertEqual(cfg.detector_profile.as_record(),
                         DEFAULT_PROFILE.as_record())

    def test_unknown_configuration_keys_are_refused(self):
        with self.assertRaises(ValueError):
            PreflightConfig.from_dict({"not_a_setting": 1})

    def test_comment_keys_are_allowed(self):
        cfg = PreflightConfig.from_dict({"$comment": "hello", "session_id": "x"})
        self.assertEqual(cfg.session_id, "x")


if __name__ == "__main__":
    unittest.main(verbosity=2)
