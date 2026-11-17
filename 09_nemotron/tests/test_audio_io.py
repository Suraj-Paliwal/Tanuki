"""Behaviour tests for audio_io.py on the deterministic fake backend.

No device is opened and no microphone is used: ``FakeBackend`` is pumped by the
test, so these cases run on a PC with no input device at all. They cover what
the goal makes protocol-critical at the device layer - continuous recording
through prompt playback, dropped input frames surfacing as flagged gaps, the
output commit boundary, and refusal to play a clip that does not match what was
pinned.

What they do not cover: real device latency, acoustic onset, echo, and PortAudio
behaviour under load. Those need the hardware spike in validation/audio_spike.md.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audio_io import (  # noqa: E402
    CANCEL_ALREADY_CANCELLED,
    CANCEL_NOTHING_ARMED,
    CANCEL_REMOVED,
    CANCEL_TOO_LATE,
    AudioFault,
    ContinuousRecorder,
    FakeBackend,
    OutputPlayer,
    WaveSink,
    load_clip,
    silence_clip,
    tone_clip,
    write_wav,
)
from timing import (  # noqa: E402
    ESTIMATED,
    ManualClock,
    PromptCandidate,
    TimingLedger,
    interpolate,
)

RATE = 48_000
BLOCK = 480            # 10 ms
BLOCK_S = BLOCK / RATE


def speech_source(amplitude=8000):
    def source(frames):
        return (np.ones((frames, 1), np.int16) * amplitude)
    return source


class ClipTest(unittest.TestCase):
    def test_leading_silence_is_found(self):
        clip = tone_clip(0.2, lead_silence=0.5, samplerate=RATE)
        self.assertAlmostEqual(clip.leading_silence_s, 0.5, delta=0.006)
        self.assertAlmostEqual(clip.duration, 0.7, places=6)

    def test_a_tone_with_no_lead_starts_immediately(self):
        clip = tone_clip(0.2, samplerate=RATE)
        self.assertEqual(clip.leading_silence_s, 0.0)

    def test_a_silent_clip_has_no_audible_onset_rather_than_a_full_one(self):
        """A silent clip must not claim its whole length as "leading silence".

        It used to, and the onset estimate added that figure to the buffer
        time - so a 50 ms silent probe clip inflated every reported audible
        onset by 50 ms.
        """
        clip = silence_clip(0.1, samplerate=RATE)
        self.assertIsNone(clip.leading_silence_s)
        self.assertFalse(clip.has_audible_onset)

    def test_load_refuses_a_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stim.wav"
            write_wav(path, tone_clip(0.05, samplerate=RATE).samples, RATE)
            with self.assertRaises(AudioFault):
                load_clip(path, expect_sha256="0" * 64)

    def test_load_refuses_a_rate_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stim.wav"
            write_wav(path, tone_clip(0.05, samplerate=16_000).samples, 16_000)
            with self.assertRaises(AudioFault):
                load_clip(path, expect_samplerate=RATE)

    def test_roundtrip_is_bit_exact_and_hash_matches_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stim.wav"
            original = tone_clip(0.05, samplerate=RATE)
            digest = write_wav(path, original.samples, RATE)
            loaded = load_clip(path, expect_sha256=digest,
                               expect_samplerate=RATE)
            np.testing.assert_array_equal(loaded.samples, original.samples)
            self.assertEqual(loaded.sha256, digest)


class RecorderTest(unittest.TestCase):
    def setUp(self):
        self.clock = ManualClock(100.0)
        self.backend = FakeBackend(self.clock)
        self.ledger = TimingLedger(clock=self.clock)
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.path = Path(self.tmp.name) / "microphone.wav"
        self.recorders = []

    def tearDown(self):
        # A failing test can leave the sink open; release it before cleanup so
        # the real assertion is reported instead of a Windows file lock.
        for rec in self.recorders:
            if not rec.finalized:
                try:
                    rec.finalize(reason="teardown")
                except Exception:
                    pass
        self.tmp.cleanup()

    def _recorder(self, **kw):
        rec = ContinuousRecorder(self.path, backend=self.backend,
                                 clock=self.clock, samplerate=RATE,
                                 blocksize=BLOCK, ledger=self.ledger, **kw)
        self.recorders.append(rec)
        return rec

    def test_writes_every_pumped_frame_and_publishes_atomically(self):
        rec = self._recorder()
        rec.start()
        self.assertTrue(rec.partial_path.exists())
        self.assertFalse(self.path.exists())
        rec.stream.pump(50, source=speech_source())
        result = rec.finalize()
        self.assertTrue(result.finalized)
        self.assertEqual(result.frames, 50 * BLOCK)
        self.assertFalse(rec.partial_path.exists())
        with wave.open(str(self.path), "rb") as wav:
            self.assertEqual(wav.getnframes(), 50 * BLOCK)
            self.assertEqual(wav.getframerate(), RATE)
            self.assertEqual(wav.getnchannels(), 1)
        self.assertTrue(result.integrity["continuous"])
        self.assertEqual(result.sha256, result.sha256.lower())
        self.assertEqual(len(result.sha256), 64)

    def test_recorded_samples_are_the_samples_the_device_delivered(self):
        rec = self._recorder()
        rec.start()
        rec.stream.pump(3, source=speech_source(1234))
        rec.finalize()
        with wave.open(str(self.path), "rb") as wav:
            data = np.frombuffer(wav.readframes(wav.getnframes()), "<i2")
        self.assertTrue(np.all(data == 1234))

    def test_a_dropped_block_becomes_a_flagged_gap_not_silent_padding(self):
        rec = self._recorder()
        rec.start()
        rec.stream.pump(10, source=speech_source())
        rec.stream.pump(10, source=speech_source(), gap_s=0.25)
        result = rec.finalize()
        self.assertEqual(result.frames, 20 * BLOCK)       # no invented samples
        self.assertFalse(result.integrity["continuous"])
        gaps = result.integrity["gaps"]
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["file_sample"], 10 * BLOCK)
        self.assertAlmostEqual(gaps[0]["frames_lost"], 0.25 * RATE, delta=2)
        self.assertEqual(gaps[0]["frames_lost_method"], ESTIMATED)
        self.assertTrue(self.ledger.of_kind("capture_gap"))

    def test_overflow_status_is_recorded_as_a_gap_and_logged(self):
        rec = self._recorder()
        rec.start()
        rec.stream.pump(5, source=speech_source())
        rec.stream.pump(1, source=speech_source(), overflow=True)
        result = rec.finalize()
        self.assertEqual(result.integrity["gaps"][0]["kind"], "input_overflow")
        self.assertTrue(self.ledger.of_kind("input_overflow"))

    def test_sample_index_maps_back_to_controller_time(self):
        rec = self._recorder()
        rec.start()
        rec.stream.pump(10, source=speech_source())
        t0 = rec.timeline.sample_to_time(0)
        t_end = rec.timeline.sample_to_time(10 * BLOCK)
        self.assertAlmostEqual(t_end - t0, 10 * BLOCK_S, places=9)
        rec.finalize()

    def test_refuses_to_start_over_an_unfinalized_attempt(self):
        rec = self._recorder()
        rec.start()
        rec.stream.pump(1, source=speech_source())
        other = self._recorder()
        with self.assertRaises(AudioFault):
            other.start()
        rec.finalize()

    def test_finalize_twice_is_an_error(self):
        rec = self._recorder()
        rec.start()
        rec.finalize()
        with self.assertRaises(AudioFault):
            rec.finalize()

    def test_a_write_failure_is_a_fault_and_what_survived_is_published(self):
        """The disk goes away mid-attempt: keep the audio, flag the attempt."""
        failures = []

        class FailingSink(WaveSink):
            def write(self, data):
                if len(failures) >= 2:
                    failures.append("raised")
                    raise OSError("device not ready")
                failures.append("ok")
                super().write(data)

        rec = self._recorder(sink_factory=FailingSink)
        rec.start()
        rec.stream.pump(5, source=speech_source())
        result = rec.finalize(reason="fault")
        # Two blocks reached the file before the sink started failing; the
        # attempt is published with what survived and carries the fault.
        self.assertEqual(result.frames, 2 * BLOCK)
        self.assertTrue(result.finalized)
        self.assertTrue(any(f["kind"] == "recording_write_failed"
                            for f in result.faults))
        self.assertTrue(self.ledger.of_kind("audio_fault"))

    def test_a_queue_overrun_is_reported_as_a_fault_not_a_silent_short_file(self):
        rec = self._recorder(max_queue_blocks=1)
        rec.start()
        # The writer is alive, so fill the queue from the callback faster than
        # it can drain by holding the write lock.
        with rec._lock:
            for _ in range(40):
                rec.stream.pump(1, source=speech_source())
        result = rec.finalize(reason="fault")
        self.assertGreater(rec.dropped_blocks, 0)
        self.assertTrue(any(f["kind"] == "recording_queue_full"
                            for f in result.faults))


class OutputPlayerTest(unittest.TestCase):
    def setUp(self):
        self.clock = ManualClock(200.0)
        self.backend = FakeBackend(self.clock, output_latency=0.020)
        self.ledger = TimingLedger(clock=self.clock)
        self.player = OutputPlayer(backend=self.backend, clock=self.clock,
                                   samplerate=RATE, blocksize=BLOCK,
                                   ledger=self.ledger)
        self.player.open()
        self.player.begin_attempt("T1")
        self.stream = self.backend.streams[-1]

    def tearDown(self):
        self.player.close()

    def _candidate(self, deadline, **kw):
        return PromptCandidate(trial_id="T1", threshold_s=0.5, deadline=deadline,
                               scheduled_at=self.clock.now(), **kw)

    def test_arming_outside_an_attempt_is_refused(self):
        """Per-attempt scoping is not opt-in (R03-F07)."""
        player = OutputPlayer(backend=self.backend, clock=self.clock,
                              samplerate=RATE, blocksize=BLOCK)
        player.open()
        try:
            clip = tone_clip(0.02, samplerate=RATE)
            with self.assertRaises(AudioFault):
                player.arm(clip, self._candidate(self.clock.now() + 1.0))
            with self.assertRaises(AudioFault):
                player.play(clip)
        finally:
            player.close()

    def test_an_armed_candidate_must_be_released_before_the_next_attempt(self):
        """The shape of R04-F01.

        A probe or trial that times out without committing has to cancel its
        candidate; otherwise the next begin_attempt() raises, turning a
        timed-out measurement into a crash. This pins the contract that the
        preflight and the bench tool now honour.
        """
        clip = tone_clip(0.02, samplerate=RATE)
        cand = self._candidate(self.clock.now() + 10.0)      # never reached
        self.player.arm(clip, cand)
        with self.assertRaises(AudioFault):
            self.player.begin_attempt("T2")
        # Releasing the slot makes the next attempt possible again.
        outcome = self.player.cancel_candidate("probe_timeout")
        self.assertEqual(outcome.outcome, CANCEL_REMOVED)
        self.assertFalse(outcome.allowance_consumed)
        self.player.begin_attempt("T2")
        self.assertEqual(self.player.attempt, "T2")

    def test_a_candidate_from_another_trial_is_refused(self):
        clip = tone_clip(0.02, samplerate=RATE)
        other = PromptCandidate(trial_id="T9", threshold_s=0.5,
                                deadline=self.clock.now() + 1.0,
                                scheduled_at=self.clock.now())
        with self.assertRaises(AudioFault):
            self.player.arm(clip, other)

    def test_idle_output_is_silence(self):
        self.stream.pump(5)
        self.assertFalse(np.any(self.stream.emitted_samples()))

    def test_immediate_playback_emits_the_clip_bit_exactly(self):
        clip = tone_clip(0.03, samplerate=RATE)      # 1440 frames == 3 blocks
        self.player.play(clip, kind="instruction")
        self.stream.pump(4)
        emitted = self.stream.emitted_samples()
        np.testing.assert_array_equal(emitted[:clip.frames], clip.samples)
        self.assertFalse(np.any(emitted[clip.frames:]))
        self.assertEqual(len(self.player.finished), 1)
        self.assertEqual(self.player.finished[0]["clip_id"], clip.clip_id)

    def test_nothing_is_audible_before_the_deadline(self):
        clip = tone_clip(0.02, samplerate=RATE)
        cand = self._candidate(self.clock.now() + 0.5)
        self.player.arm(clip, cand)
        self.stream.pump(10)                          # 100 ms of callbacks
        self.assertFalse(np.any(self.stream.emitted_samples()))
        self.assertFalse(cand.committed)

    def test_commits_at_the_first_callback_at_or_after_the_deadline(self):
        clip = tone_clip(0.02, samplerate=RATE)
        deadline = self.clock.now() + 0.1
        cand = self._candidate(deadline)
        self.player.arm(clip, cand)
        self.stream.pump(20)
        self.assertTrue(cand.committed)
        self.assertGreaterEqual(cand.committed_at, deadline)
        # Late by at most one block: the commit waits for a callback.
        self.assertLess(cand.committed_at - deadline, BLOCK_S + 1e-9)
        self.assertTrue(np.any(self.stream.emitted_samples()))

    def test_audible_onset_is_labelled_an_estimate_not_a_measurement(self):
        clip = tone_clip(0.02, lead_silence=0.05, samplerate=RATE)
        cand = self._candidate(self.clock.now() + 0.02)
        self.player.arm(clip, cand)
        self.stream.pump(10)
        onset = cand.audible_onset
        self.assertIsNotNone(onset)
        self.assertEqual(onset.method, ESTIMATED)
        self.assertFalse(onset.is_measurement)
        # Onset = buffer time + device latency + the clip's own leading silence.
        self.assertAlmostEqual(
            onset.seconds,
            cand.committed_at + self.backend.output_latency + clip.leading_silence_s,
            delta=0.002)
        self.assertIsNotNone(onset.uncertainty_s)

    def test_cancel_before_commit_leaves_the_output_silent(self):
        clip = tone_clip(0.02, samplerate=RATE)
        cand = self._candidate(self.clock.now() + 0.5)
        self.player.arm(clip, cand)
        self.stream.pump(5)
        outcome = self.player.cancel_candidate("speech_resumed")
        self.assertEqual(outcome.outcome, CANCEL_REMOVED)
        self.assertTrue(outcome.removed)
        self.assertFalse(outcome.allowance_consumed)
        self.stream.pump(60)                          # well past the deadline
        self.assertFalse(np.any(self.stream.emitted_samples()))
        self.assertEqual(cand.cancel_reason, "speech_resumed")
        self.assertIsNone(self.player.candidate)

    def test_cancel_after_commit_consumes_the_allowance_and_keeps_playing(self):
        clip = tone_clip(0.05, samplerate=RATE)
        cand = self._candidate(self.clock.now() + 0.01)
        self.player.arm(clip, cand)
        self.stream.pump(3)
        self.assertTrue(cand.committed)
        result = self.player.cancel_candidate("speech_resumed")
        self.assertEqual(result.outcome, CANCEL_TOO_LATE)
        self.assertTrue(result.allowance_consumed)
        self.assertFalse(result.removed)
        self.stream.pump(3)
        self.assertTrue(np.any(self.stream.emitted_samples()))
        self.assertTrue(self.ledger.of_kind("prompt_cancel_too_late"))

    def test_a_guard_veto_at_the_deadline_keeps_the_prompt_silent(self):
        clip = tone_clip(0.02, samplerate=RATE)
        cand = self._candidate(self.clock.now() + 0.02)
        self.player.arm(clip, cand, guard=lambda: "completion_marked")
        self.stream.pump(10)
        self.assertFalse(cand.committed)
        self.assertTrue(cand.cancelled)
        self.assertEqual(cand.cancel_reason, "completion_marked")
        self.assertFalse(np.any(self.stream.emitted_samples()))

    def test_a_broken_guard_stays_silent_rather_than_speaking(self):
        clip = tone_clip(0.02, samplerate=RATE)
        cand = self._candidate(self.clock.now() + 0.02)

        def guard():
            raise RuntimeError("controller state unreadable")

        self.player.arm(clip, cand, guard=guard)
        self.stream.pump(10)
        self.assertFalse(cand.committed)
        self.assertIn("guard_error", cand.cancel_reason)
        self.assertFalse(np.any(self.stream.emitted_samples()))

    def test_a_passing_guard_commits_once_and_clears_the_armed_slot(self):
        clip = tone_clip(0.05, samplerate=RATE)
        cand = self._candidate(self.clock.now() + 0.02)
        self.player.arm(clip, cand, guard=lambda: None)
        self.stream.pump(5)
        self.assertTrue(cand.committed)
        self.assertIsNone(self.player.candidate)
        self.assertIs(self.player.committed_candidate, cand)
        # While the committed clip is still playing nothing else can be armed.
        # The one-prompt-per-trial allowance itself is a controller rule (M3);
        # this is only the device layer refusing to double-speak.
        with self.assertRaises(AudioFault):
            self.player.arm(clip, self._candidate(self.clock.now(),
                                                  candidate_index=1))

    def test_a_committed_prompt_stays_reportable_after_the_clip_ends(self):
        """The consumed allowance must remain visible to the controller."""
        clip = tone_clip(0.02, samplerate=RATE)
        cand = self._candidate(self.clock.now() + 0.01)
        self.player.arm(clip, cand)
        self.stream.pump(10)
        self.assertIsNone(self.player.candidate)
        self.assertIs(self.player.committed_candidate, cand)
        # A late cancellation request is logged as too-late rather than being
        # silently treated as "nothing was armed".
        result = self.player.cancel_candidate("speech_resumed")
        self.assertEqual(result.outcome, CANCEL_TOO_LATE)
        self.assertTrue(result.allowance_consumed)
        self.assertTrue(self.ledger.of_kind("prompt_cancel_too_late"))

    def test_stop_halts_output_and_drops_an_armed_candidate(self):
        clip = tone_clip(0.2, samplerate=RATE)
        self.player.play(clip)
        self.stream.pump(2)
        rec = self.player.stop("participant_stop")
        self.assertEqual(rec["reason"], "participant_stop")
        before = self.stream.emitted_samples().shape[0]
        self.stream.pump(5)
        after = self.stream.emitted_samples()
        self.assertFalse(np.any(after[before:]))

    def test_rejects_a_clip_whose_rate_does_not_match_the_stream(self):
        with self.assertRaises(AudioFault):
            self.player.play(tone_clip(0.02, samplerate=16_000))

    def test_rejects_a_clip_whose_channel_count_does_not_match(self):
        with self.assertRaises(AudioFault):
            self.player.play(tone_clip(0.02, samplerate=RATE, channels=2))

    def test_refuses_to_play_over_a_playing_clip(self):
        clip = tone_clip(0.2, samplerate=RATE)
        self.player.play(clip)
        self.stream.pump(1)
        with self.assertRaises(AudioFault):
            self.player.play(clip)

    def test_refuses_to_arm_while_a_clip_is_playing(self):
        clip = tone_clip(0.2, samplerate=RATE)
        self.player.play(clip)
        self.stream.pump(1)
        with self.assertRaises(AudioFault):
            self.player.arm(clip, self._candidate(self.clock.now()))


class AvatarClockTest(unittest.TestCase):
    """The position source behind TanukiLipSync.playTrack(track, getTime)."""

    def setUp(self):
        self.clock = ManualClock(300.0)
        self.backend = FakeBackend(self.clock, output_latency=0.020)
        self.player = OutputPlayer(backend=self.backend, clock=self.clock,
                                   samplerate=RATE, blocksize=BLOCK)
        self.player.open()
        self.player.begin_attempt("avatar")
        self.stream = self.backend.streams[-1]

    def tearDown(self):
        self.player.close()

    def test_idle_position_is_not_playing(self):
        snap = self.player.position()
        self.assertFalse(snap.playing)
        self.assertEqual(snap.rate, 0.0)
        self.assertEqual(snap.file_time, 0.0)

    def test_position_advances_with_the_clip_and_stays_in_file_time(self):
        clip = tone_clip(0.5, lead_silence=0.1, samplerate=RATE)
        self.player.play(clip)
        self.stream.pump(20)                       # 200 ms of output
        snap = self.player.position()
        self.assertTrue(snap.playing)
        self.assertEqual(snap.rate, 1.0)
        self.assertAlmostEqual(snap.duration, clip.duration, places=6)
        # File time includes the clip's leading silence: the mouth track is
        # indexed from the start of the complete WAV.
        self.assertGreater(snap.file_time, 0.1)
        self.assertLessEqual(snap.file_time, 20 * BLOCK_S)

    def test_position_never_runs_past_what_has_been_written(self):
        clip = tone_clip(1.0, samplerate=RATE)
        self.player.play(clip)
        self.stream.pump(5)
        snap = self.player.position()
        self.assertLessEqual(snap.file_time, 5 * BLOCK_S + 1e-9)

    def test_clip_end_flips_the_position_to_stopped_so_the_mouth_closes(self):
        clip = tone_clip(0.02, samplerate=RATE)
        self.player.play(clip)
        self.stream.pump(5)
        snap = self.player.position()
        self.assertFalse(snap.playing)
        self.assertEqual(snap.rate, 0.0)

    def test_a_stale_snapshot_is_a_fault_for_the_renderer(self):
        clip = tone_clip(1.0, samplerate=RATE)
        self.player.play(clip)
        self.stream.pump(5)
        snap = self.player.position()
        self.assertAlmostEqual(interpolate(snap, snap.controller_time + 0.1),
                               snap.file_time + 0.1, places=9)
        with self.assertRaises(Exception):
            interpolate(snap, snap.controller_time + 0.5, stale_after_s=0.25)


class RecordingContinuesThroughPromptTest(unittest.TestCase):
    """The participant must stay recorded while the encouragement plays."""

    def test_capture_is_continuous_across_prompt_commitment_and_overlap(self):
        clock = ManualClock(400.0)
        backend = FakeBackend(clock, output_latency=0.020)
        ledger = TimingLedger(clock=clock)
        with tempfile.TemporaryDirectory() as tmp:
            rec = ContinuousRecorder(Path(tmp) / "microphone.wav",
                                     backend=backend, clock=clock,
                                     samplerate=RATE, blocksize=BLOCK,
                                     ledger=ledger)
            player = OutputPlayer(backend=backend, clock=clock, samplerate=RATE,
                                  blocksize=BLOCK, ledger=ledger)
            rec.start()
            player.open()
            player.begin_attempt("T1")
            mic, out = backend.streams[0], backend.streams[1]

            clip = tone_clip(0.05, samplerate=RATE)
            deadline = clock.now() + 0.05
            cand = PromptCandidate(trial_id="T1", threshold_s=0.5,
                                   deadline=deadline, scheduled_at=clock.now())
            player.arm(clip, cand)

            # Both callbacks see the same clock, so both streams advance one
            # shared block at a time.
            backend.pump_all(20, sources={mic: speech_source(5000)})
            self.assertEqual(out.blocks, 20)

            result = rec.finalize()
            player.close()

            self.assertTrue(cand.committed)
            self.assertEqual(result.frames, 20 * BLOCK)
            self.assertTrue(result.integrity["continuous"])
            # Participant speech is still in the file over the prompt's interval.
            with wave.open(result.path, "rb") as wav:
                data = np.frombuffer(wav.readframes(wav.getnframes()), "<i2")

        commit_sample, in_gap = rec.timeline.time_to_sample(cand.committed_at)
        self.assertFalse(in_gap)
        self.assertGreater(commit_sample, 0)
        self.assertTrue(np.all(data[commit_sample:] == 5000))


class OnsetEstimateComponentsTest(unittest.TestCase):
    """The onset estimate must keep its three parts separate.

    Round-1 review finding R01-F01 / R02-F01: commit delay (scheduling),
    device offset (latency) and the clip's own leading silence are different
    quantities. Folding them into one number, with a silent probe clip whose
    "leading silence" was its whole length, inflated every reported onset by
    the clip length.
    """

    def setUp(self):
        self.clock = ManualClock(500.0)
        self.backend = FakeBackend(self.clock, output_latency=0.020)
        self.player = OutputPlayer(backend=self.backend, clock=self.clock,
                                   samplerate=RATE, blocksize=BLOCK)
        self.player.open()
        self.player.begin_attempt("T1")
        self.stream = self.backend.streams[-1]

    def tearDown(self):
        self.player.close()

    def _commit(self, clip):
        cand = PromptCandidate(trial_id=self.player.attempt, threshold_s=0.5,
                               deadline=self.clock.now() + 0.02,
                               scheduled_at=self.clock.now())
        self.player.arm(clip, cand)
        self.stream.pump(10)
        return cand

    def test_uncertainty_covers_the_disagreement_between_latency_sources(self):
        """R03-F10a: the half-width must not be smaller than what is known."""
        clip = tone_clip(0.05, samplerate=RATE)
        # FakeStream reports the configured latency as stream.latency; the
        # per-block offset equals it, so here they agree and the floor is one
        # block.
        cand = self._commit(clip)
        self.assertGreaterEqual(cand.audible_onset.uncertainty_s, BLOCK / RATE)
        self.assertIn("reported=", cand.audible_onset.source)
        self.assertIn("per_block=", cand.audible_onset.source)

    def test_components_are_recorded_separately_and_sum_to_the_onset(self):
        clip = tone_clip(0.05, lead_silence=0.030, samplerate=RATE)
        cand = self._commit(clip)
        self.assertTrue(cand.committed)
        self.assertAlmostEqual(cand.device_offset_s,
                               self.backend.output_latency, delta=0.001)
        self.assertAlmostEqual(cand.clip_leading_silence_s, 0.030, delta=0.006)
        rec = cand.as_record()
        total = (rec["commit_delay_s"] + rec["device_offset_s"]
                 + rec["clip_leading_silence_s"])
        self.assertAlmostEqual(cand.onset_delay_s, total, places=9)

    def test_a_silent_clip_yields_no_onset_estimate_rather_than_an_inflated_one(self):
        clip = silence_clip(0.05, samplerate=RATE)
        cand = self._commit(clip)
        self.assertTrue(cand.committed)
        self.assertIsNone(cand.audible_onset)
        self.assertIsNone(cand.clip_leading_silence_s)
        self.assertIsNone(cand.onset_delay_s)
        # The scheduling figure is still available and still honest.
        self.assertIsNotNone(cand.as_record()["commit_delay_s"])

    def test_the_onset_estimate_is_not_the_commit_delay_plus_a_clip_length(self):
        """Regression guard for the exact 50 ms artifact that was reported."""
        clip = silence_clip(0.05, samplerate=RATE)
        cand = self._commit(clip)
        self.assertIsNone(cand.onset_delay_s)
        tone = tone_clip(0.05, samplerate=RATE)
        self.player.stop("next")
        self.player.begin_attempt("a2")
        cand2 = self._commit(tone)
        # A clip that starts immediately adds nothing beyond the device offset.
        self.assertAlmostEqual(
            cand2.onset_delay_s,
            (cand2.committed_at - cand2.deadline) + self.backend.output_latency,
            delta=0.002)


class AttemptScopingTest(unittest.TestCase):
    """Prompt bookkeeping is per attempt, not per session.

    Round-1 review finding R01-F03 / R02-F04: the output stream lives for the
    whole session, so a prompt committed in trial one otherwise made trial five
    report a "too late" deviation naming trial one's candidate.
    """

    def setUp(self):
        self.clock = ManualClock(600.0)
        self.backend = FakeBackend(self.clock, output_latency=0.020)
        self.ledger = TimingLedger(clock=self.clock)
        self.player = OutputPlayer(backend=self.backend, clock=self.clock,
                                   samplerate=RATE, blocksize=BLOCK,
                                   ledger=self.ledger)
        self.player.open()
        self.stream = self.backend.streams[-1]

    def tearDown(self):
        self.player.close()

    def test_a_later_attempt_does_not_inherit_an_earlier_commitment(self):
        clip = tone_clip(0.02, samplerate=RATE)
        self.player.begin_attempt("trial-1")
        cand = PromptCandidate(trial_id="trial-1", threshold_s=0.5,
                               deadline=self.clock.now() + 0.01,
                               scheduled_at=self.clock.now())
        self.player.arm(clip, cand)
        self.stream.pump(10)
        self.assertTrue(cand.committed)

        self.player.begin_attempt("trial-5")
        self.assertIsNone(self.player.committed_candidate)
        outcome = self.player.cancel_candidate("speech_resumed")
        self.assertEqual(outcome.outcome, CANCEL_NOTHING_ARMED)
        self.assertFalse(outcome.allowance_consumed)
        self.assertTrue(self.ledger.of_kind("prompt_cancel_nothing_armed"))
        self.assertFalse(self.ledger.of_kind("prompt_cancel_too_late"))

    def test_beginning_an_attempt_with_a_prompt_still_armed_is_refused(self):
        clip = tone_clip(0.02, samplerate=RATE)
        self.player.begin_attempt("trial-1")
        self.player.arm(clip, PromptCandidate(
            trial_id="trial-1", threshold_s=0.5,
            deadline=self.clock.now() + 5.0, scheduled_at=self.clock.now()))
        with self.assertRaises(AudioFault):
            self.player.begin_attempt("trial-2")

    def test_a_vetoed_prompt_does_not_consume_the_allowance(self):
        """Round-1 finding R02-F05: the veto-then-cancel race.

        Resumed speech and the deadline callback can land in the same instant.
        The guard vetoes and clears the slot; the controller's own cancellation
        then arrives to find it empty. Reporting that as "too late" would spend
        the one encouragement on a prompt nobody heard.
        """
        clip = tone_clip(0.02, samplerate=RATE)
        self.player.begin_attempt("trial-1")
        cand = PromptCandidate(trial_id="trial-1", threshold_s=0.5,
                               deadline=self.clock.now() + 0.01,
                               scheduled_at=self.clock.now())
        self.player.arm(clip, cand, guard=lambda: "speech_resumed")
        self.stream.pump(5)
        self.assertFalse(cand.committed)
        self.assertFalse(np.any(self.stream.emitted_samples()))
        outcome = self.player.cancel_candidate("speech_resumed")
        self.assertEqual(outcome.outcome, CANCEL_ALREADY_CANCELLED)
        self.assertFalse(outcome.allowance_consumed)
        self.assertFalse(self.ledger.of_kind("prompt_cancel_too_late"))
        self.assertTrue(self.ledger.of_kind("prompt_vetoed_at_commit"))


class RecorderLossAccountingTest(unittest.TestCase):
    """Audio the recorder could not keep must not be counted as written.

    Round-1 review finding R01-F02 / R02-F02.
    """

    def setUp(self):
        self.clock = ManualClock(700.0)
        self.backend = FakeBackend(self.clock)
        self.ledger = TimingLedger(clock=self.clock)
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.path = Path(self.tmp.name) / "microphone.wav"
        self.recorders = []

    def tearDown(self):
        for rec in self.recorders:
            if not rec.finalized:
                try:
                    rec.finalize(reason="teardown")
                except Exception:
                    pass
        self.tmp.cleanup()

    def _recorder(self, **kw):
        rec = ContinuousRecorder(self.path, backend=self.backend,
                                 clock=self.clock, samplerate=RATE,
                                 blocksize=BLOCK, ledger=self.ledger, **kw)
        self.recorders.append(rec)
        return rec

    def test_a_backlog_drop_is_a_counted_gap_and_not_continuous(self):
        rec = self._recorder(max_queue_blocks=1)
        rec.start()
        with rec._lock:                      # stall the writer
            for _ in range(40):
                rec.stream.pump(1, source=speech_source())
        result = rec.finalize(reason="fault")
        self.assertGreater(rec.dropped_blocks, 0)
        self.assertFalse(result.integrity["continuous"])
        self.assertTrue(result.integrity["gaps"])
        # Frames handed to the recorder equal frames confirmed on disk: the
        # dropped blocks were never counted as written.
        self.assertEqual(result.integrity["frames_written"],
                         result.integrity["frames_persisted"])
        self.assertEqual(result.frames, result.integrity["frames_written"])
        dropped = sum(g["frames_lost"] for g in result.integrity["gaps"])
        self.assertEqual(dropped, rec.dropped_blocks * BLOCK)

    def test_frames_after_a_writer_failure_are_recorded_as_lost(self):
        failures = []

        class FailingSink(WaveSink):
            def write(self, data):
                if len(failures) >= 2:
                    raise OSError("device not ready")
                failures.append("ok")
                super().write(data)

        rec = self._recorder(sink_factory=FailingSink)
        rec.start()
        rec.stream.pump(2, source=speech_source())
        # Let the writer process those two and die on the third.
        rec.stream.pump(1, source=speech_source())
        while not rec._writer_failed.is_set() and rec._writer.is_alive():
            rec.stream.pump(1, source=speech_source())
            if rec.timeline.frames_written > 20 * BLOCK:
                break
        rec.stream.pump(5, source=speech_source())
        result = rec.finalize(reason="fault")
        self.assertFalse(result.integrity["continuous"])
        self.assertTrue(any(f["kind"] == "recording_write_failed"
                            for f in result.faults))
        self.assertTrue(result.integrity["gaps"])
        # The file length is what the writer confirmed, and the difference
        # between delivered and written frames is reconciled at finalisation
        # rather than left as a silent shortfall.
        self.assertEqual(result.frames, result.integrity["frames_persisted"])
        self.assertTrue(any(f["kind"] == "recording_shortfall"
                            for f in result.faults))
        shortfall = next(g for g in result.integrity["gaps"]
                         if g["kind"] == "writer_shortfall")
        self.assertEqual(shortfall["frames_lost"],
                         result.integrity["frames_written"]
                         - result.integrity["frames_persisted"])
        # The gap sits at the real end of the file, not past it (R03-F03b).
        self.assertEqual(shortfall["file_sample"], result.frames)
        for gap in result.integrity["gaps"]:
            self.assertLessEqual(gap["file_sample"], result.frames)

    def test_the_mapping_is_right_on_both_sides_of_a_recorder_drop(self):
        rec = self._recorder(max_queue_blocks=1)
        rec.start()
        rec.stream.pump(5, source=speech_source())
        with rec._lock:
            for _ in range(5):
                rec.stream.pump(1, source=speech_source())
        rec.stream.pump(5, source=speech_source())
        rec.finalize()
        written = rec.timeline.frames_written
        # Every sample index still maps to a time inside the recording.
        self.assertGreater(written, 0)
        t_first = rec.timeline.sample_to_time(0)
        t_last = rec.timeline.sample_to_time(written)
        self.assertGreater(t_last, t_first)


class DeviceClockIntegrationTest(unittest.TestCase):
    """The two-clock model end to end through the recorder (R04-F04).

    `CaptureTimeline` is unit-tested directly; these drive the same paths
    through `FakeStream` and `ContinuousRecorder`, which is where the epoch
    model and the fallback round-trip actually have to hold.
    """

    def setUp(self):
        self.clock = ManualClock(900.0)
        self.backend = FakeBackend(self.clock)
        self.ledger = TimingLedger(clock=self.clock)
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.path = Path(self.tmp.name) / "microphone.wav"
        self.recorders = []

    def tearDown(self):
        for rec in self.recorders:
            if not rec.finalized:
                try:
                    rec.finalize(reason="teardown")
                except Exception:
                    pass
        self.tmp.cleanup()

    def _recorder(self, **kw):
        rec = ContinuousRecorder(self.path, backend=self.backend,
                                 clock=self.clock, samplerate=RATE,
                                 blocksize=BLOCK, ledger=self.ledger, **kw)
        self.recorders.append(rec)
        return rec

    def test_callback_lateness_does_not_reach_the_mapping(self):
        """In device-time mode jitter lands in entry_time, not first_frame_time.

        That is what the real backend does: both terms of the offset
        observation are sampled at callback entry, so lateness cancels.
        """
        rec = self._recorder()
        rec.start()
        for i in range(20):
            rec.stream.pump(1, source=speech_source(),
                            jitter_s=0.030 if i % 2 else 0.0)
        result = rec.finalize()
        integrity = result.integrity
        self.assertEqual(integrity["gap_basis"], "device_clock")
        self.assertEqual(integrity["gaps"], [])
        self.assertEqual(integrity["clock_anomalies"], [])
        self.assertTrue(integrity["continuous"])
        self.assertEqual(result.frames, 20 * BLOCK)

    def test_a_fallback_run_through_the_recorder_is_not_lost_audio(self):
        """The F01 round-trip, driven through the real recorder path."""
        rec = self._recorder()
        rec.start()
        rec.stream.pump(5, source=speech_source())
        rec.stream.pump(7, source=speech_source(), method="fallback")
        rec.stream.pump(5, source=speech_source())
        result = rec.finalize()
        integrity = result.integrity
        self.assertEqual(result.frames, 17 * BLOCK)
        self.assertEqual(integrity["gaps"], [])
        self.assertEqual(integrity["frames_lost_estimate"], 0)
        self.assertEqual(integrity["gap_basis"], "mixed")
        # A mixed basis cannot support a continuity claim.
        self.assertFalse(integrity["continuous"])


class CaptureFaultContainmentTest(unittest.TestCase):
    """Nothing in the input callback may propagate an exception.

    Round-1 review finding R02-F03: sounddevice stops delivering blocks after
    one raised callback, which would end the recording silently.
    """

    def setUp(self):
        self.clock = ManualClock(800.0)
        self.backend = FakeBackend(self.clock)
        self.ledger = TimingLedger(clock=self.clock)
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.path = Path(self.tmp.name) / "microphone.wav"

    def tearDown(self):
        self.tmp.cleanup()

    def _recorder(self):
        return ContinuousRecorder(self.path, backend=self.backend,
                                  clock=self.clock, samplerate=RATE,
                                  blocksize=BLOCK, ledger=self.ledger)

    def test_a_backwards_device_time_does_not_kill_the_stream(self):
        rec = self._recorder()
        rec.start()
        rec.stream.pump(5, source=speech_source())
        # Force the device clock backwards, as a host API switching time
        # sources mid-stream can.
        rec.stream._device_time -= 1.0
        rec.stream.pump(1, source=speech_source())
        rec.stream.pump(5, source=speech_source())
        result = rec.finalize()
        self.assertEqual(rec.blocks_received, 11)      # all blocks delivered
        self.assertGreater(result.frames, 0)
        self.assertFalse(result.integrity["continuous"])

    def test_a_host_api_changing_its_time_source_is_a_fault(self):
        rec = self._recorder()
        rec.start()
        rec.stream.pump(3, source=speech_source())
        rec.stream.pump(3, source=speech_source(), method="fallback")
        result = rec.finalize()
        self.assertTrue(any(f["kind"] == "block_timing_method_changed"
                            for f in result.faults))
        self.assertEqual(result.integrity["gap_basis"], "mixed")

    def test_a_stalled_capture_callback_is_faulted_while_the_trial_runs(self):
        rec = self._recorder()
        rec.start()
        rec.stream.pump(5, source=speech_source())
        self.assertIsNone(rec.check_liveness(self.clock.now()))
        self.clock.advance(2.0)                 # callbacks stop arriving
        fault = rec.check_liveness(self.clock.now(), max_silence_s=0.5)
        self.assertIsNotNone(fault)
        self.assertEqual(fault.kind, "capture_stalled")
        rec.finalize(reason="fault")

    def test_a_device_that_never_opens_publishes_nothing(self):
        class RefusingBackend(FakeBackend):
            def open_input(self, **kw):
                raise AudioFault("device busy")

        rec = ContinuousRecorder(self.path, backend=RefusingBackend(self.clock),
                                 clock=self.clock, samplerate=RATE,
                                 blocksize=BLOCK, ledger=self.ledger)
        with self.assertRaises(AudioFault):
            rec.start()
        self.assertFalse(self.path.exists())
        self.assertFalse(rec.partial_path.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
