# M1 audio and timing feasibility spike

Checkpoint `M1-audio-001`. Executed 2026-11-17 (Asia/Tokyo). The JSON reports
carry UTC timestamps: the two **superseded** single-shot files are from
2026-11-16T17:28-17:29Z, the current 40-trial and survey reports from
2026-11-16T22:18Z (re-run after round 2 of review on the corrected tool).

**Every device measurement below was taken over a TeamViewer remote session.**
A remote-desktop audio stack can redirect or claim endpoints, change which
device is the default and alter the latency a device reports, so this is the
largest single limitation on Findings 1-3. All of them must be repeated at the
physical machine with the final speakers and microphone attached before any
figure here is treated as describing the study configuration.

This records what was actually executed on this PC and what was not. A pass
here establishes that the controller's capture/playback/timing logic behaves as
`goal.md` sections 6 and 7 require **on a synthetic backend**, plus a small
number of real device measurements. It is not participant readiness, it is not
acoustic validation, and it does not settle any research-owned decision.

## Environment

| Item | Value |
|---|---|
| OS | Windows 11 Education 10.0.26300 (x64) |
| Python | 3.13.9 (Anaconda) |
| numpy | 2.3.5 |
| sounddevice | 0.5.5 |
| PortAudio | V19.7.0-devel |
| soundfile | 0.13.1 (installed, not imported by committed code) |
| onnxruntime | 1.24.4 (installed, not imported by committed code) |
| GPU | RTX 2080 Ti, 11 GB (irrelevant to this checkpoint; M7) |

Reproduce with, from `09_nemotron`:

```text
python -m unittest discover -s tests -p "test_*.py"
python tools/check_audio.py
python tools/check_audio.py --survey --out validation/audio_check_survey.json
python tools/check_audio.py --commit-trials 40 --device 8 \
    --out validation/audio_check_commit_wasapi.json
python tools/check_audio.py --commit-trials 40 \
    --out validation/audio_check_commit_default.json
python tools/check_audio.py --playback --device 8 \
    --out validation/audio_check_wasapi.json        # superseded, see Finding 3
python tools/check_audio.py --playback \
    --out validation/audio_check_playback.json      # superseded, default device
```

Each `validation/audio_check_*.json` is produced by exactly one command above.
The two superseded files carry `"superseded": true` and a reason at the top of
the JSON; their internal `"verdict": "PASS"` was stamped by the pre-fix tool
and would read `INCOMPLETE` under the current verdict ladder. (Round 1 claimed
the default-device command had been added to this list; it had not - R03-F05.)

`--playback` is the only command that makes sound (a quiet 1 kHz tone). No
command above opens the microphone; `--duplex --allow-microphone` would, and
has not been run.

## Finding 1 (blocking for any real session): this PC has no input device

PortAudio reports `default_input_device = -1` for MME, DirectSound and WASAPI.
The only input-capable devices are two Bluetooth hands-free headset endpoints
on WDM-KS (indices 13 and 15), and `sd.default.device` is `[-1, 1]`, so
`sd.query_devices(kind='input')` raises `PortAudioError: Error querying
device -1`.

Consequences, recorded rather than worked around:

* **Continuous recording cannot be opened on this configuration at all.** Every
  microphone-side claim in this checkpoint rests on the fake backend.
* `audio_io.inventory()` reports `default_capture_available: false` and
  `capture_possible: true` as separate facts, with the reason and the two
  non-default input devices named in `warnings`. The distinction matters: a
  session that pins a device by identity could still open one of them, so a
  preflight must not refuse outright on the default alone. `tools/check_audio.py
  --duplex` refuses with `BLOCKED` rather than producing an empty recording.
* A Bluetooth hands-free headset is not a suitable research microphone: it is
  typically 8-16 kHz with aggressive noise suppression and its own buffering,
  which would corrupt exactly the speech-offset boundary this study measures.
* Microphone selection, placement and calibration are a research/hardware
  decision (`goal.md` section 14, "device models, measured timing tolerance and
  calibration method"). That gate is **open**.

## Finding 2: the Windows default output device cannot meet the candidate target

One output device per host API was opened for one second, emitting silence
(`--survey`, `validation/audio_check_survey.json`):

| Host API | Device | Reported output latency | Callbacks in 1 s | Worst interval |
|---|---|---|---|---|
| MME (current default) | 0 Microsoft Sound Mapper - Output | 180.0 ms | 96 | 30.08 ms |
| DirectSound | 4 Primary Sound Driver | 240.0 ms | 97 | 16.55 ms |
| **WASAPI** | **8 VZ239 (NVIDIA High Definition Audio)** | **22.0 ms** | **103** | **14.13 ms** |
| WDM-KS | 11 SPDIF Out (HD Audio SPDIF out) | 40.7 ms | 108 | 40.28 ms |

Measured over a TeamViewer session (see the note at the top); worst intervals
vary by several milliseconds between runs.

Nominal interval at 48 kHz with a 480-frame block is 10.00 ms. Those worst-case
intervals are scheduling jitter, not lost audio, and they are why gap detection
runs on the device's own block clock rather than on callback-entry time: a time
threshold wide enough to tolerate 40 ms of lateness could never see a single
lost 10 ms block. WDM-KS also reported *both* block-timing methods within one
stream (`"block_timing_method": ["device_time", "fallback"]`), which the
recorder now treats as a fault rather than as a usable time source. Since
round 2 the timeline also drops its device-clock reference across such a
fallback run and re-anchors afterwards, so the run is no longer misread as
lost audio; on the callback-time basis a loss shorter than the 80 ms
tolerance is undetectable, and `integrity()` says so rather than reporting
`continuous: true` there.

## Finding 3: commit and estimated-onset delay, 40 prompts per device

**These figures were corrected after independent review.** The first version of
this record overstated every onset by exactly 50 ms: the probe used a silent
clip, and the leading-silence detector returned the whole clip duration when it
found no sound, which was then added to the onset estimate. Both reviewers
derived the artifact independently from the published JSON (the onset-minus-
commit difference was constant to four decimal places across all 40 trials,
which no device observation would be). The superseded numbers and the wrong
explanation are kept at the end of this section.

Each trial arms a clip with an eligibility deadline and records when the
controller committed it to the device and what audible onset the device's
per-block DAC time implies. The probe is a faint tone with a known 10 ms lead;
it is quietly audible, because a clip silent enough to be inaudible has no
onset to estimate at all. Nothing is recorded.

The estimate is now reported as three separate quantities that are summed
explicitly, so no single number mixes a scheduling delay with a device latency
or with a property of the audio file:

| Device | Early commits | Commit delay median / p95 / max | Device offset median | Clip lead | Onset delay median / p95 / max | Device-attributable p95 | Meets 100 ms candidate target |
|---|---|---|---|---|---|---|---|
| WASAPI, device 8 | 0 / 40 | 6.29 / 9.61 / 10.44 ms | 10.00 ms | 10.00 ms | 26.29 / 29.61 / 30.44 ms | ~19.6 ms | yes (estimated) |
| Default MME | 0 / 40 | 8.55 / 12.80 / 29.42 ms | 170.15 ms | 10.00 ms | 188.75 / 192.88 / 219.20 ms | ~183 ms | **no (estimated)** |

(Round-1 corrected run on the same tool before the round-2 fixes: WASAPI
30.32 ms p95, MME 190.90 ms p95 - within run-to-run variation of the figures
above.)

"Device-attributable" excludes the 10 ms lead belonging to the probe clip
itself. For a real stimulus the corresponding term is that clip's own leading
silence, which the frozen manifest records per asset.

Raw reports: `audio_check_commit_wasapi.json`,
`audio_check_commit_default.json`.

Four things this still does **not** say:

1. **It is not an acoustic measurement.** The device offset comes from
   PortAudio's own per-block DAC time. `goal.md` section 7 requires a recorded
   playback reference for a measured onset; there is no input device, so that
   check is `NOT_RUN`. Every onset figure produced by this code carries
   `method: "estimated"`, and the code has no path that can label one
   `measured`.
2. **The two available latency reports still disagree, on WASAPI.**
   `stream.latency` reports 22.0 ms while the per-block DAC offset is 10.00 ms.
   On MME they roughly agree (180.0 ms against 171.03 ms). Which is closer to
   the truth cannot be settled without the acoustic reference; the larger
   figure is the safer one for planning, and on WASAPI both clear the candidate
   target with margin either way.
3. **40 trials on an idle machine is not a distribution under load.** No
   concurrent rendering, synthesis or disk activity was running.
4. **It was measured through TeamViewer**, as noted at the top. Each committed
   onset record now carries both latency readings and an `uncertainty_s` no
   smaller than their disagreement (12 ms on WASAPI), so the machine-readable
   record is at least as cautious as this prose.

The 100 ms figure is the candidate engineering target in `goal.md` section 7. It
is a proposal, not a research-approved tolerance, and the tolerance freeze
remains an open gate.

### Superseded figures from the first version of this record

Kept so the correction is auditable, not deleted:

- Reported WASAPI onset p95 **70.13 ms** and MME **232.78 ms**. Both were
  inflated by 50 ms of probe-clip artifact; the remainder differed from the
  current numbers because the device offset was not separated out.
- The claim that "the steady-state per-block DAC offset implies about 60 ms"
  on WASAPI was wrong: it is 10.00 ms. The 60 ms figure was 50 ms of artifact
  plus that 10 ms.
- The justification that the reported number "uses the per-block figure, which
  is the larger and therefore the safer of the two" was therefore backwards.
  Once the artifact is removed the per-block figure is the *smaller* of the two
  available estimates, which is why the discrepancy is now stated plainly
  instead of being presented as conservatism.
- An earlier single-shot `--playback --device 8` run estimated a 10.37 ms onset
  delay. It was taken on the first commitment after the stream opened, before
  the device buffer had filled, and must not be quoted as the result. It is
  retained in `audio_check_wasapi.json`.

## Finding 4: synthetic behaviour checks

`python -m unittest discover -s tests -p "test_*.py"` - **153 tests, OK**,
0.40 s. Per file, verified by running each: `test_timing.py` 74,
`test_audio_io.py` 53, `test_preflight.py` 26. (80 at the first review; 33
added for the round-1 fixes; 26 with the session preflight; 14 for the round-2
fixes.) All run on `FakeBackend` with a `ManualClock`: no device is opened and
no microphone is used, so the suite runs on this PC despite Finding 1.

What the suite pins down, mapped to the requirement:

| Requirement (`goal.md`) | Check | Status |
|---|---|---|
| No prompt before participant speech is detected | `PauseTimerTest.test_no_deadline_before_participant_speech` | PASS |
| Configured interval added once, not hangover-plus-timer (§6) | `test_threshold_is_added_once_to_the_real_speech_offset` | PASS |
| Speech offset is the end of the last speech frame (§6) | `SpeechSegmenterTest.test_offset_is_the_end_of_the_last_speech_frame` | PASS |
| Detector delay logged separately from the interval (§7) | `test_onset_is_the_start_of_the_run_not_the_confirmation` | PASS |
| Coughs/clicks do not open a speech run | `test_a_cough_shorter_than_min_speech_never_opens_speech` | PASS |
| No unintended early trigger (§13) | `OutputPlayerTest.test_nothing_is_audible_before_the_deadline` | PASS |
| Cancellation before the commit boundary (§6) | `test_cancel_before_commit_leaves_the_output_silent` | PASS |
| Commitment consumes the allowance (§6) | `test_cancel_after_commit_fails_and_the_clip_keeps_playing` | PASS |
| Terminal conditions re-checked at commitment (§6) | `test_a_guard_veto_at_the_deadline_keeps_the_prompt_silent` | PASS |
| A fault in that re-check must not speak | `test_a_broken_guard_stays_silent_rather_than_speaking` | PASS |
| Rearming computes a fresh deadline (§6) | `test_rearm_computes_a_fresh_deadline_from_the_next_offset` | PASS |
| Recording continuous through prompt overlap (§13) | `RecordingContinuesThroughPromptTest` | PASS |
| Dropped frames detected, audio not padded (§13) | `test_a_dropped_block_becomes_a_flagged_gap_not_silent_padding` | PASS |
| Sample/time mapping correct across a gap (§6) | `test_mapping_stays_correct_on_both_sides_of_a_gap` | PASS |
| Detector index maps back to original samples (§6) | `ResampleMapTest`, `test_offset_sample_maps_into_the_preserved_recording` | PASS |
| Write failure yields a flagged recoverable attempt (§13) | `test_a_write_failure_is_a_fault_and_what_survived_is_published` | PASS |
| Incomplete attempt detectable after a crash (§10) | `test_refuses_to_start_over_an_unfinalized_attempt` | PASS |
| Manifest-pinned audio, no silent substitution (§4) | `test_load_refuses_a_hash_mismatch`, `..._a_rate_mismatch` | PASS |
| Avatar clock in file time, stale update is a fault (§7) | `AvatarClockTest` | PASS |
| Scheduling timestamp never labelled a measurement (§7) | `EstimateProvenanceTest`, `test_audible_onset_is_labelled_an_estimate_not_a_measurement` | PASS |
| Onset components kept separate; silent clip has no onset (§7) | `OnsetEstimateComponentsTest` | PASS |
| Hysteresis-band speech moves the silence origin (§6) | `HysteresisOffsetOriginTest` | PASS |
| A deadline discovered too late is flagged, not prompted (§6) | `StaleDeadlineTest` | PASS |
| Prompt bookkeeping is per attempt, not per session (§6) | `AttemptScopingTest` | PASS |
| A vetoed prompt does not consume the allowance (§6) | `test_a_vetoed_prompt_does_not_consume_the_allowance` | PASS |
| Recorder-side loss is counted, not a silent mapping shift (§13) | `RecorderLossAccountingTest` | PASS |
| Nothing raises on the audio thread; stalled capture is faulted (§6) | `CaptureFaultContainmentTest` | PASS |
| Jitter and drift do not fabricate gaps; a real loss still shows (§13) | `test_realistic_callback_jitter_is_not_a_gap`, `test_device_clock_drift_over_a_long_recording_is_not_a_gap`, `test_jitter_alone_cannot_hide_a_lost_block_on_the_device_clock` | PASS |
| A fallback run between device-timed blocks is not a gap; a clock jump is an anomaly, not a count (§13) | `test_a_fallback_run_between_device_timed_blocks_is_not_a_gap`, `test_a_device_clock_jump_is_an_anomaly_not_a_fabricated_loss` | PASS |
| The mapping never runs backwards; a real backwards device clock is still flagged (§6) | `test_realistic_callback_jitter_is_not_a_gap` (monotonic check), `test_a_device_clock_running_backwards_is_still_a_real_anomaly`, `test_a_large_offset_correction_is_noted_but_is_not_a_clock_fault` | PASS |
| Continuity is never asserted on a basis that cannot see a lost block (§13) | `test_continuity_is_not_asserted_on_the_callback_time_basis` | PASS |
| A tail shortfall is placed at the end of the file, never past it (§10) | `test_frames_after_a_writer_failure_are_recorded_as_lost` | PASS |
| Prompt slot cannot be used outside an attempt (§6) | `test_arming_outside_an_attempt_is_refused`, `test_a_candidate_from_another_trial_is_refused` | PASS |
| The silence origin is configuration; both readings produce their deadlines (§6, §14) | `SilenceOriginTest` | PASS |
| A stale deadline is reachable through a timeline gap and refused (§6) | `test_a_timeline_gap_can_make_a_deadline_stale_through_the_segmenter` | PASS |
| One documented detector profile (§6, §12) | `DefaultProfileTest` | PASS |
| Ledger ordering is thread-safe (§10) | `LedgerConcurrencyTest` | PASS |

Four defects were found by these checks during development and fixed before
the first review: a logging keyword collision that raised `TypeError` from
inside the audio path on every `play()` and on every capture gap; a
cancellation request after commitment returning a bare `False` so the
controller could not distinguish "nothing armed" from "too late, already
audible"; a fake-backend clock that advanced once per stream and so made two
concurrent streams look like one had dropped frames; and an unguarded event
payload that could silently relabel a ledger record.

Independent review then found eight further Major defects, all fixed in
round 1 and covered by the added tests. They are recorded in
[reviews/M1-audio-001/resolution.md](../reviews/M1-audio-001/resolution.md)
with both reviewers' original reports preserved. The most consequential were
the onset artifact above; a recorder that counted frames the file did not
contain, silently shifting the sample-to-time mapping; an exception raised on
the PortAudio thread that would have killed capture with no fault recorded;
and a silence origin that ignored hysteresis-band speech, which could have
shortened the assigned threshold without any record of it.

## What remains NOT_RUN or BLOCKED

| Item | Status | Why |
|---|---|---|
| Microphone capture on this PC | BLOCKED | No input device (Finding 1) |
| Acoustic onset measurement | NOT_RUN | Needs a recorded playback reference |
| Last-speech-to-audible-response measurement | NOT_RUN | Needs capture + acoustic reference |
| Detector boundary error against real speech | NOT_RUN | Silero VAD not integrated (M3); current tests drive synthetic probabilities |
| Echo / playback leakage behaviour | NOT_RUN | Needs simultaneous capture and output |
| Low-volume speech, breaths, coughs, background noise | NOT_RUN | Needs real audio; synthetic probabilities only exercise the state machine |
| Avatar clock against the real renderer | NOT_RUN | Browser adapter and renderer snapshot are a separate checkpoint |
| Completion-control suppression at 0.5 s | NOT_RUN | Needs the controller (M3) and an operator UI (M4) |
| Device drift over a full session | NOT_RUN | `StreamTimebase.measured_rate()` needs a >= 1 s baseline from a real stream; only 1 s survey runs exist |
| Behaviour under system load | NOT_RUN | Not exercised |

## Limitations to carry forward

* A fake-backend pass is not hardware validation. The device layer has been
  exercised on exactly one real output path, for seconds, with no load.
* `tools/check_audio.py` reaches into `OutputPlayer._callback` to instrument
  block timings in `--playback`. That is acceptable for a bench tool and must
  not become a production pattern.
* The 100 ms candidate target, the detector profile (`timing.DEFAULT_PROFILE`:
  32 ms frames, 96 ms minimum speech, 150 ms hangover, 0.5/0.35 thresholds) and
  the recall-cap origin are all proposals. The detector profile in particular
  shapes where a speech offset lands and must be part of the frozen
  manipulation before collection.
* Two readings of "where speech ended" are now recorded per event: the end of
  the in-speech run, which includes hysteresis-band frames, and the end of the
  last frame above the speech threshold. The deadline is computed from the
  first. Which one the analysis should use is a research decision, listed in
  `reviews/M1-audio-001/resolution.md`.
* A device-side gap's lost-frame count is still `estimated` from the block-time
  discrepancy, because PortAudio reports no exact lost count. A gap caused by
  the recorder itself is `counted` and exact. A device-clock jump of a second
  or more is not converted into a count at all; it is an anomaly with the loss
  left unknown.
* On the callback-time basis (a host API that reports no block times) a loss
  shorter than 80 ms is undetectable. `integrity()` reports the basis and the
  undetectable bound and never claims `continuous` there. This PC's only input
  endpoints are on WDM-KS, which was seen mixing bases, so a real recording on
  them would carry this limitation.
* Every device figure in this record was measured through a TeamViewer
  session and must be repeated at the physical machine.
* A recording killed abruptly leaves a `.partial` file that is detectable but
  reports zero frames, because the WAV header is written on close. Deferred to
  M3 (finding C12 in the resolution record), where the partial will become raw
  PCM with a sidecar so a killed attempt is fully recoverable.
