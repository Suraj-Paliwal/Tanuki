"""Boundary tests for timing.py. No devices, no audio, no real clock.

These check the protocol arithmetic the goal is specific about: where a speech
offset lands, that the configured waiting interval is added exactly once, that a
dropped input block does not corrupt the sample/time mapping, and that a
scheduling timestamp cannot be dressed up as an acoustic measurement.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from timing import (  # noqa: E402
    COUNTED,
    DEFAULT_PROFILE,
    ESTIMATED,
    MEASURED,
    ORIGIN_LAST_STRONG,
    ORIGIN_RUN_END,
    SPEECH_OFFSET,
    SPEECH_ONSET,
    CaptureTimeline,
    DetectorProfile,
    Estimate,
    ManualClock,
    PauseTimer,
    PlaybackPosition,
    PromptCandidate,
    ResampleMap,
    SpeechSegmenter,
    StalePositionFault,
    StreamTimebase,
    TimingLedger,
    interpolate,
    validate_detector_profile,
)

RATE = 48_000


class EstimateProvenanceTest(unittest.TestCase):
    def test_method_must_be_known(self):
        with self.assertRaises(ValueError):
            Estimate(0.1, "measured-ish")

    def test_measurement_flag_distinguishes_a_schedule_from_an_observation(self):
        scheduled = Estimate(1.0, "scheduled")
        measured = Estimate(1.0, MEASURED, uncertainty_s=0.001)
        self.assertFalse(scheduled.is_measurement)
        self.assertTrue(measured.is_measurement)

    def test_uncertainty_none_is_not_zero(self):
        self.assertIsNone(Estimate(1.0, ESTIMATED).uncertainty_s)
        self.assertEqual(Estimate(1.0, ESTIMATED, 0.0).uncertainty_s, 0.0)

    def test_rejects_nonfinite_and_negative_uncertainty(self):
        with self.assertRaises(ValueError):
            Estimate(float("nan"), ESTIMATED)
        with self.assertRaises(ValueError):
            Estimate(1.0, ESTIMATED, -0.1)


class ManualClockTest(unittest.TestCase):
    def test_cannot_move_backwards(self):
        clock = ManualClock(5.0)
        clock.advance(1.0)
        self.assertEqual(clock.now(), 6.0)
        with self.assertRaises(ValueError):
            clock.advance(-0.1)
        with self.assertRaises(ValueError):
            clock.set(1.0)


class StreamTimebaseTest(unittest.TestCase):
    def test_rate_is_unknown_until_the_baseline_is_long_enough(self):
        tb = StreamTimebase(RATE, min_span_s=1.0)
        tb.anchor(0, 0.0)
        tb.anchor(4800, 0.1)
        self.assertIsNone(tb.measured_rate())
        self.assertIsNone(tb.drift_ppm())
        self.assertEqual(tb.effective_rate(), RATE)

    def test_measured_rate_and_drift(self):
        tb = StreamTimebase(RATE, min_span_s=1.0)
        tb.anchor(0, 0.0)
        tb.anchor(96_096, 2.0)                   # device runs 1000 ppm fast
        self.assertAlmostEqual(tb.measured_rate(), 48_048.0, places=6)
        self.assertAlmostEqual(tb.drift_ppm(), 1000.0, places=6)

    def test_sample_time_roundtrip(self):
        tb = StreamTimebase(RATE)
        tb.anchor(RATE, 1.0)
        self.assertAlmostEqual(tb.time_of_sample(2 * RATE), 2.0, places=9)
        self.assertEqual(tb.sample_at_time(2.0), 2 * RATE)

    def test_clamps_a_backwards_anchor_and_reports_it(self):
        """A host API that switches time sources mid-stream must not kill capture.

        anchor() runs on the PortAudio thread, so a non-monotonic block time is
        reported as an anomaly and clamped, never raised.
        """
        tb = StreamTimebase(RATE)
        self.assertIsNone(tb.anchor(1000, 1.0))
        self.assertEqual(tb.anchor(500, 1.1), "sample_position_went_backwards")
        self.assertEqual(tb.anchors[-1][0], 1000)          # clamped forward
        self.assertEqual(tb.anchor(2000, 0.9), "clock_went_backwards")
        self.assertGreaterEqual(tb.anchors[-1][1], 1.1)    # clamped forward
        self.assertEqual(len(tb.anomalies), 2)

    def test_monotonic_anchors_report_no_anomaly(self):
        tb = StreamTimebase(RATE)
        tb.anchor(0, 0.0)
        self.assertIsNone(tb.anchor(480, 0.01))
        self.assertEqual(tb.anomalies, [])

    def test_needs_an_anchor_before_mapping(self):
        tb = StreamTimebase(RATE)
        with self.assertRaises(LookupError):
            tb.time_of_sample(0)


class CaptureTimelineTest(unittest.TestCase):
    EPOCH = 100.0   # controller time at device time zero

    def _contiguous(self, blocks=5, block=480, t0=0.0, tolerance=None):
        """Blocks on the device-clock basis, as a real PortAudio stream gives."""
        tl = CaptureTimeline(RATE, gap_tolerance_s=tolerance) if tolerance \
            else CaptureTimeline(RATE)
        for i in range(blocks):
            device_time = t0 + i * block / RATE
            tl.note_block(block, self.EPOCH + device_time, device_time=device_time)
            tl.note_persisted(block)       # the writer thread confirms the bytes
        return tl

    def test_contiguous_mapping_is_linear(self):
        tl = self._contiguous()
        self.assertEqual(tl.frames_written, 2400)
        self.assertAlmostEqual(tl.sample_to_time(0), self.EPOCH, places=9)
        self.assertAlmostEqual(tl.sample_to_time(2400), self.EPOCH + 0.05,
                               places=9)
        self.assertTrue(tl.integrity()["continuous"])
        self.assertEqual(tl.integrity()["gap_basis"], "device_clock")
        self.assertEqual(tl.frames_lost, 0)

    def test_continuity_is_not_asserted_on_the_callback_time_basis(self):
        """Without a device clock a lost block up to the tolerance is invisible.

        The code comment admitted this; the field a consumer reads did not
        (R03-F03a). "continuous" now requires a basis that could have seen a
        lost block, and the record says what it could not see.
        """
        tl = CaptureTimeline(RATE)
        for i in range(5):
            tl.note_block(480, i * 480 / RATE)      # no device_time
            tl.note_persisted(480)
        integrity = tl.integrity()
        self.assertEqual(integrity["gap_basis"], "callback_time")
        self.assertFalse(integrity["continuity_supported_by_basis"])
        self.assertAlmostEqual(integrity["undetectable_gap_s"], 0.080)
        self.assertEqual(integrity["gaps"], [])
        self.assertFalse(integrity["continuous"])

    def test_an_unknown_persisted_count_is_not_continuous(self):
        """A timeline that was never told what reached disk cannot claim continuity."""
        tl = CaptureTimeline(RATE)
        for i in range(5):
            tl.note_block(480, i * 480 / RATE)
        integrity = tl.integrity()
        self.assertEqual(integrity["frames_written"], 2400)
        self.assertEqual(integrity["frames_persisted"], 0)
        self.assertFalse(integrity["all_frames_persisted"])
        self.assertFalse(integrity["continuous"])

    def test_a_divergence_between_written_and_persisted_is_not_continuous(self):
        tl = self._contiguous(blocks=5)
        self.assertTrue(tl.integrity()["continuous"])
        tl.note_block(480, 5 * 480 / RATE)      # delivered but never confirmed
        integrity = tl.integrity()
        self.assertEqual(integrity["frames_written"], 2880)
        self.assertEqual(integrity["frames_persisted"], 2400)
        self.assertFalse(integrity["continuous"])

    def test_an_empty_recording_is_not_continuous(self):
        tl = CaptureTimeline(RATE)
        integrity = tl.integrity()
        self.assertTrue(integrity["empty"])
        self.assertFalse(integrity["continuous"])

    def test_a_late_block_records_a_gap_instead_of_inventing_silence(self):
        tl = self._contiguous(blocks=2)
        # Third block arrives 100 ms late: 4800 frames never reached the file.
        late = 2 * 480 / RATE + 0.1
        gap = tl.note_block(480, self.EPOCH + late, device_time=late)
        self.assertIsNotNone(gap)
        self.assertEqual(gap.file_sample, 960)
        self.assertEqual(gap.frames_lost, 4800)
        self.assertEqual(gap.method, ESTIMATED)
        # The file still holds only the frames the device actually delivered.
        self.assertEqual(tl.frames_written, 1440)
        self.assertEqual(tl.device_frames, 1440 + 4800)
        self.assertFalse(tl.integrity()["continuous"])

    def test_mapping_stays_correct_on_both_sides_of_a_gap(self):
        tl = self._contiguous(blocks=2)
        late = 2 * 480 / RATE + 0.1
        tl.note_block(480, self.EPOCH + late, device_time=late)
        e = self.EPOCH
        self.assertAlmostEqual(tl.sample_to_time(480), e + 0.01, places=9)
        self.assertAlmostEqual(tl.sample_to_time(960), e + 0.12, places=9)
        self.assertAlmostEqual(tl.sample_to_time(1440), e + 0.13, places=9)

    def test_time_inside_a_gap_is_flagged(self):
        tl = self._contiguous(blocks=2)
        late = 2 * 480 / RATE + 0.1
        tl.note_block(480, self.EPOCH + late, device_time=late)
        sample, in_gap = tl.time_to_sample(self.EPOCH + 0.05)
        self.assertTrue(in_gap)
        self.assertEqual(sample, 960)
        sample, in_gap = tl.time_to_sample(self.EPOCH + 0.005)
        self.assertFalse(in_gap)
        self.assertEqual(sample, 240)

    def test_overflow_status_opens_a_gap_even_without_a_time_jump(self):
        tl = self._contiguous(blocks=2)
        at = 2 * 480 / RATE
        gap = tl.note_block(480, self.EPOCH + at, device_time=at,
                            overflowed=True, status="input overflow")
        self.assertIsNotNone(gap)
        self.assertEqual(gap.kind, "input_overflow")
        self.assertEqual(tl.status_flags["input overflow"], 1)

    def test_small_jitter_is_not_a_gap(self):
        tl = self._contiguous(blocks=2)
        at = 2 * 480 / RATE
        gap = tl.note_block(480, self.EPOCH + at + 0.0005, device_time=at)
        self.assertIsNone(gap)
        self.assertEqual(len(tl.segments), 1)

    def test_realistic_callback_jitter_is_not_a_gap(self):
        """Measured worst-case callback intervals on this PC reached 40 ms.

        Those are scheduling delays, not lost audio. Gap detection runs on the
        device's own block clock, which does not jitter, so even 30 ms of
        callback lateness against a 10 ms block produces no gap and the tight
        2 ms device tolerance still catches a real single-block loss.
        """
        tl = CaptureTimeline(RATE)
        block = 480
        block_s = block / RATE
        # The first block is the *latest* one: the earlier minimum-biased
        # estimator dropped the offset by 30 ms on block two and labelled time
        # backwards (R03-F02). Note this models a perturbation of the observed
        # offset itself; on the real backend callback lateness cancels out of
        # that observation, so this is a robustness case, not the normal one.
        jitter = [0.030, 0.0, 0.0, 0.038, 0.0, 0.012, 0.0, 0.039]
        for i, j in enumerate(jitter):
            device_time = i * block_s
            tl.note_block(block, device_time + j, device_time=device_time)
            tl.note_persisted(block)
        self.assertEqual(tl.gaps, [])
        integrity = tl.integrity()
        self.assertEqual(integrity["clock_anomalies"], [])
        self.assertTrue(integrity["continuous"])
        self.assertEqual(integrity["gap_basis"], "device_clock")
        self.assertEqual(integrity["blocks_without_device_time"], 0)
        times = [tl.sample_to_time(n) for n in range(0, 8 * block + 1, 48)]
        self.assertEqual(times, sorted(times))    # never runs backwards

    def test_device_clock_drift_over_a_long_recording_is_not_a_gap(self):
        """A 1000 ppm fast device must not accumulate into fabricated losses.

        The first implementation extrapolated the nominal rate from the segment
        start, so any drift eventually crossed the tolerance and invented lost
        frames over a three-minute recall.
        """
        tl = CaptureTimeline(RATE)
        block = 480
        true_block_s = block / (RATE * 1.001)     # device runs 1000 ppm fast
        blocks = int(180 / true_block_s)          # three minutes of recall
        for i in range(blocks):
            device_time = i * true_block_s
            tl.note_block(block, device_time, device_time=device_time)
            tl.note_persisted(block)
        self.assertEqual(tl.gaps, [])
        self.assertTrue(tl.integrity()["continuous"])
        self.assertAlmostEqual(tl.integrity()["drift_ppm"], 1000.0, delta=5.0)

    def test_one_truly_omitted_block_is_exactly_one_gap(self):
        """A single lost 10 ms block is still caught on the device clock."""
        tl = CaptureTimeline(RATE)
        block = 480
        block_s = block / RATE
        for i in range(10):
            if i == 5:
                continue                       # this block never arrives
            device_time = i * block_s
            tl.note_block(block, device_time, device_time=device_time)
            tl.note_persisted(block)
        self.assertEqual(len(tl.gaps), 1)
        self.assertEqual(tl.gaps[0].file_sample, 5 * block)
        self.assertAlmostEqual(tl.gaps[0].frames_lost, block, delta=2)

    def test_jitter_alone_cannot_hide_a_lost_block_on_the_device_clock(self):
        """The two must stay distinguishable: that is the point of the fix."""
        tl = CaptureTimeline(RATE)
        block = 480
        block_s = block / RATE
        for i in range(8):
            if i == 4:
                continue
            device_time = i * block_s
            # Heavy callback lateness on every block, plus one real loss.
            tl.note_block(block, device_time + 0.035, device_time=device_time)
            tl.note_persisted(block)
        self.assertEqual(len(tl.gaps), 1)
        self.assertEqual(tl.gaps[0].file_sample, 4 * block)

    def test_without_device_timestamps_the_tolerance_widens(self):
        """A host API with no block times falls back, and says so."""
        tl = CaptureTimeline(RATE)
        block = 480
        block_s = block / RATE
        for i in range(5):
            tl.note_block(block, i * block_s + (0.03 if i % 2 else 0.0))
            tl.note_persisted(block)
        integrity = tl.integrity()
        self.assertEqual(integrity["gap_basis"], "callback_time")
        self.assertEqual(integrity["blocks_with_device_time"], 0)
        self.assertEqual(tl.gaps, [])
        # ...and therefore cannot claim continuity.
        self.assertFalse(integrity["continuous"])

    def test_the_mapping_follows_the_real_rate_not_the_nominal_one(self):
        """sample_to_time interpolates between device-time anchors.

        Extrapolating 48000 Hz across a minute of a drifting device would
        misplace a sample index by tens of milliseconds; the anchors remove it.
        """
        tl = CaptureTimeline(RATE, anchor_interval_s=1.0)
        block = 480
        true_block_s = block / (RATE * 1.001)
        blocks = int(60 / true_block_s)
        for i in range(blocks):
            device_time = i * true_block_s
            tl.note_block(block, device_time, device_time=device_time)
            tl.note_persisted(block)
        end_time = blocks * true_block_s
        last_sample = blocks * block
        self.assertAlmostEqual(tl.sample_to_time(last_sample), end_time,
                               delta=0.002)
        # The nominal-rate answer would be ~60 ms out over this interval.
        self.assertGreater(abs(last_sample / RATE - end_time), 0.030)

    def test_a_fallback_run_between_device_timed_blocks_is_not_a_gap(self):
        """R03-F01: the host API stops and resumes reporting block times.

        WDM-KS - the only host API with an input device on this PC - was seen
        doing this in the survey. The stale device-clock reference from before
        the fallback run must not be used to measure the first block after it,
        or the whole run reads as lost audio.
        """
        tl = CaptureTimeline(RATE)
        block = 480
        block_s = block / RATE
        k, m = 5, 7
        for i in range(k):
            tl.note_block(block, i * block_s, device_time=i * block_s)
            tl.note_persisted(block)
        for i in range(k, k + m):
            tl.note_block(block, i * block_s)          # no device time
            tl.note_persisted(block)
        for i in range(k + m, 2 * k + m):
            tl.note_block(block, i * block_s, device_time=i * block_s)
            tl.note_persisted(block)
        integrity = tl.integrity()
        self.assertEqual(tl.gaps, [])
        self.assertEqual(integrity["clock_anomalies"], [])
        self.assertEqual(integrity["gap_basis"], "mixed")
        self.assertEqual(tl.frames_written, (2 * k + m) * block)
        self.assertEqual(integrity["frames_lost_estimate"], 0)
        # Repeated flips must not accumulate either.
        for round_ in range(3):
            tl.note_block(block, 0.0)
            tl.note_persisted(block)
            tl.note_block(block, 0.0, device_time=(2 * k + m + round_) * block_s)
            tl.note_persisted(block)
        self.assertEqual(tl.gaps, [])

    def test_a_device_clock_jump_is_an_anomaly_not_a_fabricated_loss(self):
        """R03-F01 second case: a one-second forward step is not 48000 lost frames."""
        tl = CaptureTimeline(RATE)
        block = 480
        block_s = block / RATE
        for i in range(5):
            tl.note_block(block, i * block_s, device_time=i * block_s)
            tl.note_persisted(block)
        jumped = 5 * block_s + 1.5
        tl.note_block(block, jumped, device_time=jumped)
        tl.note_persisted(block)
        integrity = tl.integrity()
        self.assertEqual(tl.gaps, [])
        self.assertEqual(integrity["frames_lost_estimate"], 0)
        self.assertEqual(len(integrity["clock_anomalies"]), 1)
        self.assertEqual(integrity["clock_anomalies"][0]["kind"],
                         "device_time_discontinuity")
        self.assertFalse(integrity["continuous"])

    def test_a_device_clock_running_backwards_is_still_a_real_anomaly(self):
        """Estimator adjustments are clamped silently; a real clock fault is not."""
        tl = CaptureTimeline(RATE)
        block = 480
        block_s = block / RATE
        for i in range(5):
            tl.note_block(block, i * block_s, device_time=i * block_s)
            tl.note_persisted(block)
        tl.note_block(block, 5 * block_s, device_time=5 * block_s - 0.5)
        tl.note_persisted(block)
        kinds = [a["kind"] for a in tl.integrity()["clock_anomalies"]]
        self.assertIn("device_time_went_backwards", kinds)
        self.assertFalse(tl.integrity()["continuous"])

    def test_a_large_offset_correction_is_noted_but_is_not_a_clock_fault(self):
        tl = CaptureTimeline(RATE)
        block = 480
        block_s = block / RATE
        tl.note_block(block, 0.0 + 0.5, device_time=0.0)   # epoch observed 0.5
        tl.note_persisted(block)
        for i in range(1, 6):
            tl.note_block(block, i * block_s, device_time=i * block_s)  # epoch 0
            tl.note_persisted(block)
        integrity = tl.integrity()
        self.assertEqual(integrity["clock_anomalies"], [])
        self.assertTrue(len(integrity["offset_steps"]) >= 1)
        self.assertTrue(integrity["continuous"])

    def test_the_clamp_alone_keeps_the_mapping_monotonic(self):
        """Isolates the clamp added for R03-F02, per finding R04-F02.

        The offset tracker absorbs 1% of its error per block, so a correction
        larger than one block (10 ms) needs an initial observation off by more
        than a second. That is the only situation in which the clamp does any
        work, and no other anomaly path covers it: the device clock below is
        strictly monotonic and never steps backwards, so neither
        `device_time_went_backwards` nor `device_time_discontinuity` fires.
        Reverting the clamp makes `sample_to_time` decrease here.
        """
        tl = CaptureTimeline(RATE)
        block = 480
        block_s = block / RATE
        # First block observed with a 2 s epoch error: the tracker then pulls
        # the offset down by 0.01 * 2.0 = 20 ms on the next block, which is
        # twice the 10 ms block duration.
        tl.note_block(block, 2.0, device_time=0.0)
        tl.note_persisted(block)
        for i in range(1, 12):
            device_time = i * block_s
            tl.note_block(block, device_time, device_time=device_time)
            tl.note_persisted(block)
        integrity = tl.integrity()
        # The clamp is an estimator adjustment, not a clock fault.
        self.assertEqual(integrity["clock_anomalies"], [])
        self.assertTrue(integrity["offset_steps"])
        self.assertGreater(abs(integrity["offset_steps"][0]["step_s"]), block_s)
        # The mapping must still never run backwards.
        times = [tl.sample_to_time(n) for n in range(0, 12 * block + 1, 60)]
        self.assertEqual(times, sorted(times))
        self.assertTrue(integrity["continuous"])

    def test_frames_the_recorder_dropped_are_a_counted_gap_not_a_shift(self):
        """Losing audio to a writer backlog must not move every later sample.

        The frames never reach the file, so the timeline must not count them;
        otherwise sample_to_time would return a time earlier than the truth for
        the rest of the recording - a silent shift of the speech boundaries
        this study measures.
        """
        tl = self._contiguous(blocks=10)
        block = 480
        drop_at_time = self.EPOCH + 10 * block / RATE
        gap = tl.note_not_persisted(block, drop_at_time, kind="recorder_backlog")
        self.assertEqual(gap.file_sample, 10 * block)
        self.assertEqual(gap.frames_lost, block)
        self.assertEqual(gap.method, COUNTED)
        self.assertEqual(gap.kind, "recorder_backlog")
        # Nothing was added to the file for the dropped block.
        self.assertEqual(tl.frames_written, 10 * block)
        # The next delivered block resumes after the dropped interval.
        resume_device = 11 * block / RATE
        tl.note_block(block, self.EPOCH + resume_device, device_time=resume_device)
        tl.note_persisted(block)
        integrity = tl.integrity()
        self.assertFalse(integrity["continuous"])
        self.assertEqual(integrity["frames_written"], 11 * block)
        self.assertEqual(integrity["frames_persisted"], 11 * block)
        self.assertEqual(len(integrity["gaps"]), 1)
        # Mapping is right on both sides of the loss.
        self.assertAlmostEqual(tl.sample_to_time(10 * block - 1),
                               self.EPOCH + (10 * block - 1) / RATE, delta=0.001)
        self.assertAlmostEqual(tl.sample_to_time(10 * block),
                               drop_at_time + block / RATE, delta=0.001)

    def test_a_clock_anomaly_makes_the_attempt_not_continuous(self):
        tl = self._contiguous(blocks=5)
        # The device clock jumps back by half a second: a real anomaly.
        tl.note_block(480, self.EPOCH + 5 * 480 / RATE,
                      device_time=5 * 480 / RATE - 0.5)
        tl.note_persisted(480)
        integrity = tl.integrity()
        self.assertTrue(integrity["clock_anomalies"])
        self.assertFalse(integrity["continuous"])

    def test_mapping_before_any_frames_is_an_error_not_a_guess(self):
        tl = CaptureTimeline(RATE)
        with self.assertRaises(LookupError):
            tl.sample_to_time(0)
        with self.assertRaises(LookupError):
            tl.time_to_sample(0.0)


class ResampleMapTest(unittest.TestCase):
    def test_detector_index_maps_back_to_the_preserved_recording(self):
        m = ResampleMap(source_rate=48_000, target_rate=16_000, source_start=9600)
        self.assertEqual(m.source_sample(0), 9600)
        self.assertEqual(m.source_sample(16_000), 9600 + 48_000)
        self.assertEqual(m.target_index(9600 + 48_000), 16_000)
        start, end = m.source_span(1600, 160)
        self.assertEqual((start, end), (9600 + 4800, 9600 + 5280))


class DetectorProfileTest(unittest.TestCase):
    def test_thresholds_must_be_ordered(self):
        with self.assertRaises(ValueError):
            DetectorProfile(speech_threshold=0.4, exit_threshold=0.6)

    def test_frame_counts_round_up(self):
        p = DetectorProfile(frame_ms=32.0, min_speech_ms=120.0, hangover_ms=150.0)
        self.assertEqual(p.min_speech_frames, 4)   # ceil(120/32)
        self.assertEqual(p.hangover_frames, 5)     # ceil(150/32)

    def test_profile_that_cannot_serve_the_shortest_threshold_is_rejected(self):
        bad = DetectorProfile(hangover_ms=600.0)
        with self.assertRaises(ValueError):
            validate_detector_profile(bad, [0.5, 1.0, 2.0])
        ok = DetectorProfile(hangover_ms=150.0)
        validate_detector_profile(ok, [0.5, 1.0, 2.0], decision_budget_s=0.05)
        with self.assertRaises(ValueError):
            validate_detector_profile(ok, [0.5], decision_budget_s=0.4)


class SpeechSegmenterTest(unittest.TestCase):
    """Frame 0 starts at t=0; each frame is 32 ms."""

    def setUp(self):
        self.profile = DetectorProfile(frame_ms=32.0, min_speech_ms=96.0,
                                       hangover_ms=160.0, detector="synthetic")
        self.resample = ResampleMap(48_000, 16_000)
        self.seg = SpeechSegmenter(self.profile, self.resample,
                                   lambda i: i * self.profile.frame_s)

    def test_onset_is_the_start_of_the_run_not_the_confirmation(self):
        events = self.seg.push_all([0.0, 0.9, 0.9, 0.9])
        self.assertEqual(len(events), 1)
        onset = events[0]
        self.assertEqual(onset.kind, SPEECH_ONSET)
        self.assertEqual(onset.frame_index, 1)
        self.assertAlmostEqual(onset.event_time, 0.032, places=9)
        # Confirmed only at the end of frame 3.
        self.assertAlmostEqual(onset.confirmed_time, 0.128, places=9)
        self.assertAlmostEqual(onset.detector_delay_s, 0.096, places=9)

    def test_a_cough_shorter_than_min_speech_never_opens_speech(self):
        events = self.seg.push_all([0.0, 0.95, 0.95, 0.0, 0.0, 0.0])
        self.assertEqual(events, [])
        self.assertFalse(self.seg.in_speech)

    def test_offset_is_the_end_of_the_last_speech_frame(self):
        self.seg.push_all([0.9] * 4)                  # onset confirmed
        events = self.seg.push_all([0.0] * 5)         # hangover = 5 frames
        self.assertEqual(len(events), 1)
        off = events[0]
        self.assertEqual(off.kind, SPEECH_OFFSET)
        self.assertEqual(off.frame_index, 3)
        self.assertAlmostEqual(off.event_time, 0.128, places=9)   # end of frame 3
        self.assertAlmostEqual(off.confirmed_time, 0.288, places=9)
        self.assertAlmostEqual(off.detector_delay_s, self.profile.hangover_s,
                               places=9)

    def test_hysteresis_keeps_a_dip_inside_one_speech_run(self):
        self.seg.push_all([0.9] * 4)
        self.assertEqual(self.seg.push_all([0.4, 0.4, 0.9, 0.9]), [])
        self.assertTrue(self.seg.in_speech)

    def test_offset_sample_maps_into_the_preserved_recording(self):
        self.seg.push_all([0.9] * 4)
        off = self.seg.push_all([0.0] * 5)[0]
        # End of frame 3 == detector sample 4*512 == source sample 4*1536.
        self.assertEqual(off.source_sample, 4 * 512 * 3)


class PauseTimerTest(unittest.TestCase):
    def setUp(self):
        self.profile = DetectorProfile(frame_ms=32.0, min_speech_ms=96.0,
                                       hangover_ms=160.0, detector="synthetic")
        self.resample = ResampleMap(48_000, 16_000)

    def _segmenter(self):
        return SpeechSegmenter(self.profile, self.resample,
                               lambda i: i * self.profile.frame_s)

    def test_no_deadline_before_participant_speech(self):
        timer = PauseTimer(0.5, profile=self.profile)
        self.assertIsNone(timer.deadline)
        self.assertFalse(timer.eligible(1000.0))
        # Silence reported without a prior onset must not arm anything.
        timer.note_offset(0.0, 0.0)
        self.assertIsNone(timer.deadline)
        self.assertFalse(timer.armed)

    def test_threshold_is_added_once_to_the_real_speech_offset(self):
        """The hangover is detector latency, not part of the waiting interval."""
        timer = PauseTimer(0.5, profile=self.profile)
        seg = self._segmenter()
        for event in seg.push_all([0.9] * 4 + [0.0] * 5):
            timer.note_event(event)
        self.assertAlmostEqual(timer.silence_since, 0.128, places=9)
        self.assertAlmostEqual(timer.deadline, 0.628, places=9)
        # Had the hangover been added twice the deadline would be 0.788.
        self.assertNotAlmostEqual(timer.deadline, 0.628 + self.profile.hangover_s,
                                  places=6)
        self.assertFalse(timer.eligible(0.6279))
        self.assertTrue(timer.eligible(0.628))

    def test_deadline_can_be_known_only_after_confirmation(self):
        timer = PauseTimer(0.1, profile=self.profile)   # shorter than hangover
        seg = self._segmenter()
        for event in seg.push_all([0.9] * 4 + [0.0] * 5):
            timer.note_event(event)
        self.assertAlmostEqual(timer.deadline, 0.228, places=9)
        # Confirmation lands at 0.288, i.e. the deadline is already past: this
        # is exactly the configuration validate_detector_profile rejects.
        self.assertAlmostEqual(timer.known_at(), 0.288, places=9)
        self.assertGreater(timer.known_at(), timer.deadline)

    def test_resumed_speech_clears_the_deadline(self):
        timer = PauseTimer(0.5, profile=self.profile)
        timer.note_onset(0.0)
        timer.note_offset(1.0, 1.16)
        self.assertAlmostEqual(timer.deadline, 1.5, places=9)
        timer.note_onset(1.2)
        self.assertIsNone(timer.deadline)
        self.assertEqual(timer.speech_runs, 2)

    def test_rearm_computes_a_fresh_deadline_from_the_next_offset(self):
        timer = PauseTimer(0.5, profile=self.profile)
        timer.note_onset(0.0)
        timer.note_offset(1.0, 1.16)
        timer.reset_for_rearm()
        self.assertIsNone(timer.deadline)
        self.assertTrue(timer.armed)
        timer.note_offset(2.0, 2.16)
        self.assertAlmostEqual(timer.deadline, 2.5, places=9)

    def test_rejects_a_nonpositive_threshold(self):
        with self.assertRaises(ValueError):
            PauseTimer(0.0)


class PromptCandidateTest(unittest.TestCase):
    def _candidate(self):
        return PromptCandidate(trial_id="T1", threshold_s=0.5, deadline=10.0,
                               scheduled_at=9.5)

    def test_cancel_before_commit_removes_it(self):
        cand = self._candidate()
        self.assertTrue(cand.cancel(9.9, "speech_resumed"))
        self.assertTrue(cand.cancelled)
        self.assertFalse(cand.committed)

    def test_cancel_after_commit_fails_and_keeps_the_commitment(self):
        cand = self._candidate()
        cand.commit(10.004, Estimate(10.03, ESTIMATED, 0.01))
        self.assertFalse(cand.cancel(10.01, "speech_resumed"))
        self.assertTrue(cand.committed)
        self.assertFalse(cand.cancelled)

    def test_committing_a_cancelled_candidate_is_an_error(self):
        cand = self._candidate()
        cand.cancel(9.9, "stop")
        with self.assertRaises(RuntimeError):
            cand.commit(10.0)

    def test_double_commit_is_an_error(self):
        cand = self._candidate()
        cand.commit(10.0)
        with self.assertRaises(RuntimeError):
            cand.commit(10.1)

    def test_record_separates_commit_delay_from_audible_onset(self):
        cand = self._candidate()
        cand.commit(10.004, Estimate(10.03, ESTIMATED, 0.01, source="device"))
        rec = cand.as_record()
        self.assertAlmostEqual(rec["commit_delay_s"], 0.004, places=9)
        self.assertEqual(rec["audible_onset"]["method"], ESTIMATED)


class PlaybackPositionTest(unittest.TestCase):
    def _snapshot(self, **kw):
        base = dict(file_time=1.0, controller_time=100.0, rate=1.0,
                    playing=True, duration=3.0)
        base.update(kw)
        return PlaybackPosition(**base)

    def test_interpolates_within_the_clip(self):
        snap = self._snapshot()
        self.assertAlmostEqual(interpolate(snap, 100.1), 1.1, places=9)

    def test_clamps_to_the_clip_length(self):
        snap = self._snapshot(file_time=2.95)
        self.assertAlmostEqual(interpolate(snap, 100.2), 3.0, places=9)

    def test_stale_snapshot_raises_instead_of_extrapolating(self):
        snap = self._snapshot()
        with self.assertRaises(StalePositionFault):
            interpolate(snap, 100.5, stale_after_s=0.25)

    def test_future_snapshot_raises(self):
        snap = self._snapshot()
        with self.assertRaises(StalePositionFault):
            interpolate(snap, 99.9)

    def test_stopped_position_does_not_advance(self):
        snap = self._snapshot(rate=0.0, playing=False)
        self.assertAlmostEqual(interpolate(snap, 100.2), 1.0, places=9)


class TimingLedgerTest(unittest.TestCase):
    def test_records_are_ordered_and_estimates_keep_their_method(self):
        clock = ManualClock(10.0)
        ledger = TimingLedger(clock=clock)
        ledger.record("speech_onset", source_sample=4800)
        clock.advance(0.5)
        ledger.record("prompt_committed",
                      audible_onset=Estimate(11.0, ESTIMATED, 0.01))
        self.assertEqual([r["seq"] for r in ledger.records], [1, 2])
        self.assertEqual(ledger.records[0]["controller_time"], 10.0)
        self.assertEqual(ledger.records[1]["controller_time"], 10.5)
        self.assertEqual(
            ledger.of_kind("prompt_committed")[0]["audible_onset"]["method"],
            ESTIMATED)


class HysteresisOffsetOriginTest(unittest.TestCase):
    """The silence origin must not sit behind audio the detector called speech.

    Round-1 review finding R01-F06 / R02-F06. Frames in the hysteresis band
    [exit_threshold, speech_threshold) keep the run open and reset the quiet
    counter, so they are being treated as speech. If they did not also move the
    offset origin, a participant trailing off quietly would be dated as silent
    from the last loud frame - and the assigned 0.5/1.0/2.0 s threshold could
    already have expired by the time the controller was told. Since the
    threshold is the manipulation, that silently shortens the condition.
    """

    def setUp(self):
        self.profile = DetectorProfile(frame_ms=32.0, min_speech_ms=96.0,
                                       hangover_ms=160.0, exit_threshold=0.35,
                                       speech_threshold=0.5,
                                       detector="synthetic")
        self.seg = SpeechSegmenter(self.profile, ResampleMap(48_000, 16_000),
                                   lambda i: i * self.profile.frame_s)

    def test_band_frames_move_the_offset_origin(self):
        # Four loud frames, twenty band frames, then real silence.
        events = self.seg.push_all([0.9] * 4 + [0.4] * 20 + [0.0] * 5)
        offsets = [e for e in events if e.kind == SPEECH_OFFSET]
        self.assertEqual(len(offsets), 1)
        off = offsets[0]
        # The offset is the end of frame 23 (the last band frame), not frame 3.
        self.assertEqual(off.frame_index, 23)
        self.assertAlmostEqual(off.event_time, 24 * 0.032, places=9)
        self.assertEqual(off.last_strong_frame, 3)
        self.assertAlmostEqual(off.strong_event_time, 4 * 0.032, places=9)
        self.assertEqual(off.band_frames, 20)
        self.assertAlmostEqual(off.band_dwell_s, 20 * 0.032, places=9)

    def test_the_deadline_is_not_already_past_after_a_long_band_dwell(self):
        timer = PauseTimer(0.5, profile=self.profile)
        for event in self.seg.push_all([0.9] * 4 + [0.4] * 20 + [0.0] * 5):
            timer.note_event(event)
        # Offset at 0.768 s, confirmed at 0.928 s, so the 0.5 s deadline is
        # 1.268 s - comfortably in the future, as it must be.
        self.assertAlmostEqual(timer.deadline, 24 * 0.032 + 0.5, places=9)
        self.assertEqual(timer.discovery_lateness, 0.0)
        self.assertFalse(timer.too_late())
        self.assertFalse(timer.eligible(1.0))
        self.assertTrue(timer.eligible(1.268))


class StaleDeadlineTest(unittest.TestCase):
    """A deadline already long past must be flagged, not prompted through.

    With a valid detector profile and a healthy timeline this cannot happen
    through the segmenter: the offset is confirmed one hangover after it, and
    the validator requires the hangover to be shorter than the threshold. The
    reachable triggers are a capture-timeline gap between the last speech frame
    and the confirming frame, and a real detector that buffers more than its
    nominal hangover (R03-F08). The first is driven end-to-end below.
    """

    def setUp(self):
        self.profile = DEFAULT_PROFILE    # a profile the validator accepts
        validate_detector_profile(self.profile, [0.5, 1.0, 2.0])

    def test_a_timeline_gap_can_make_a_deadline_stale_through_the_segmenter(self):
        """Frame times come from the capture timeline; a gap stretches them."""
        tl = CaptureTimeline(RATE)
        frame_s = self.profile.frame_s
        frames_per_vad_frame = int(round(frame_s * RATE))
        # 20 contiguous frames, then the recorder drops 0.8 s, then 10 more.
        for i in range(20):
            dt = i * frame_s
            tl.note_block(frames_per_vad_frame, dt, device_time=dt)
            tl.note_persisted(frames_per_vad_frame)
        tl.note_not_persisted(int(0.8 * RATE), 20 * frame_s, kind="recorder_backlog")
        for i in range(20, 30):
            dt = i * frame_s + 0.8
            tl.note_block(frames_per_vad_frame, dt, device_time=dt)
            tl.note_persisted(frames_per_vad_frame)

        # Detector frames index the *file*; their times come from the timeline.
        resample = ResampleMap(RATE, self.profile.sample_rate)
        seg = SpeechSegmenter(
            self.profile, resample,
            lambda i: tl.sample_to_time(i * frames_per_vad_frame))
        timer = PauseTimer(0.5, profile=self.profile, lateness_budget_s=0.05)
        # Speech through frame 19, then quiet; the hangover frames land after
        # the 0.8 s hole, so the offset is confirmed far later than the
        # hangover alone would imply.
        for event in seg.push_all([0.9] * 20 + [0.0] * 8):
            timer.note_event(event)
        self.assertIsNotNone(timer.deadline)
        self.assertGreater(timer.discovery_lateness, 0.05)
        self.assertTrue(timer.too_late())
        self.assertFalse(timer.eligible(timer.known_at()))

    def test_a_deadline_discovered_too_late_is_not_eligible(self):
        """Direct form of the same guard, with hand-supplied times."""
        timer = PauseTimer(0.5, profile=self.profile, lateness_budget_s=0.05)
        timer.note_onset(0.0)
        timer.note_offset(1.0, 1.8)
        self.assertAlmostEqual(timer.deadline, 1.5, places=9)
        self.assertAlmostEqual(timer.discovery_lateness, 0.3, places=9)
        self.assertTrue(timer.too_late())
        self.assertFalse(timer.eligible(1.8))

    def test_a_deadline_within_the_budget_is_eligible(self):
        timer = PauseTimer(0.5, profile=self.profile, lateness_budget_s=0.05)
        timer.note_onset(0.0)
        timer.note_offset(1.0, 1.52)      # 20 ms late, inside the budget
        self.assertAlmostEqual(timer.discovery_lateness, 0.02, places=9)
        self.assertFalse(timer.too_late())
        self.assertTrue(timer.eligible(1.52))

    def test_a_valid_profile_on_a_healthy_timeline_is_never_late(self):
        resample = ResampleMap(RATE, self.profile.sample_rate)
        seg = SpeechSegmenter(self.profile, resample,
                              lambda i: i * self.profile.frame_s)
        timer = PauseTimer(0.5, profile=self.profile)
        for event in seg.push_all([0.9] * 10 + [0.0] * 8):
            timer.note_event(event)
        self.assertEqual(timer.discovery_lateness, 0.0)
        self.assertFalse(timer.too_late())

    def test_the_normal_case_has_no_lateness_at_all(self):
        profile = DetectorProfile(hangover_ms=150.0, detector="synthetic")
        timer = PauseTimer(0.5, profile=profile)
        timer.note_onset(0.0)
        timer.note_offset(1.0, 1.15)      # confirmed well before 1.5 s
        self.assertEqual(timer.discovery_lateness, 0.0)
        self.assertFalse(timer.too_late())


class SilenceOriginTest(unittest.TestCase):
    """The origin of the silence interval is configuration, not code (R03-F09).

    Both readings are recorded on every offset event; which one the live
    deadline counts from is a research decision about the manipulation.
    """

    def setUp(self):
        self.profile = DetectorProfile(frame_ms=32.0, min_speech_ms=96.0,
                                       hangover_ms=160.0, detector="synthetic")
        self.resample = ResampleMap(48_000, 16_000)
        # Four strong frames, twenty band frames, then real silence.
        self.sequence = [0.9] * 4 + [0.4] * 20 + [0.0] * 5

    def _deadline(self, origin):
        seg = SpeechSegmenter(self.profile, self.resample,
                              lambda i: i * self.profile.frame_s)
        timer = PauseTimer(0.5, profile=self.profile, origin=origin)
        for event in seg.push_all(self.sequence):
            timer.note_event(event)
        return timer

    def test_run_end_counts_from_the_end_of_the_band(self):
        timer = self._deadline(ORIGIN_RUN_END)
        self.assertAlmostEqual(timer.deadline, 24 * 0.032 + 0.5, places=9)

    def test_last_strong_counts_from_the_last_loud_frame(self):
        timer = self._deadline(ORIGIN_LAST_STRONG)
        self.assertAlmostEqual(timer.deadline, 4 * 0.032 + 0.5, places=9)

    def test_the_two_origins_differ_by_exactly_the_band_dwell(self):
        a = self._deadline(ORIGIN_RUN_END).deadline
        b = self._deadline(ORIGIN_LAST_STRONG).deadline
        self.assertAlmostEqual(a - b, 20 * 0.032, places=9)

    def test_the_origin_is_recorded_and_validated(self):
        timer = PauseTimer(0.5, origin=ORIGIN_LAST_STRONG)
        self.assertEqual(timer.as_record()["origin"], ORIGIN_LAST_STRONG)
        with self.assertRaises(ValueError):
            PauseTimer(0.5, origin="somewhere")


class DefaultProfileTest(unittest.TestCase):
    def test_one_documented_profile_is_the_library_default(self):
        """Three divergent profiles made "the detector settings" unanswerable."""
        self.assertEqual(DEFAULT_PROFILE.frame_ms, 32.0)
        self.assertEqual(DEFAULT_PROFILE.min_speech_ms, 96.0)
        self.assertEqual(DEFAULT_PROFILE.hangover_ms, 150.0)
        self.assertEqual(DEFAULT_PROFILE.speech_threshold, 0.5)
        self.assertEqual(DEFAULT_PROFILE.exit_threshold, 0.35)
        # The dataclass defaults must agree with the named profile.
        self.assertEqual(DetectorProfile().as_record(),
                         DEFAULT_PROFILE.as_record())

    def test_the_default_profile_serves_the_shortest_threshold(self):
        validate_detector_profile(DEFAULT_PROFILE, [0.5, 1.0, 2.0],
                                  decision_budget_s=0.01)


class LedgerConcurrencyTest(unittest.TestCase):
    def test_sequence_numbers_are_unique_under_concurrent_writers(self):
        """The ledger is written from the audio callback and the controller."""
        import threading

        ledger = TimingLedger()
        errors = []

        def writer():
            try:
                for _ in range(200):
                    ledger.record("block")
            except Exception as exc:        # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=writer) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(ledger.records), 1600)
        self.assertEqual(len({r["seq"] for r in ledger.records}), 1600)


if __name__ == "__main__":
    unittest.main(verbosity=2)
