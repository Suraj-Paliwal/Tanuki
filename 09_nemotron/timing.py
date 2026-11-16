"""Timing core for the Tanuki experiment controller.

Everything the protocol measures in seconds is derived here from a monotonic
controller clock plus device sample positions. Wall-clock time names files; it
never computes a waiting interval (goal.md section 7).

Three ideas carry most of the weight:

* An :class:`Estimate` carries how a number was obtained. A scheduling
  timestamp and a measured acoustic onset are both floats, and the goal
  forbids presenting one as the other, so the method travels with the value.
* A :class:`CaptureTimeline` maps a sample index in the written recording back
  to controller time *piecewise*. When the input stream drops frames the
  recording is short by an unknown amount; inventing silence to keep one
  linear mapping would corrupt the audio, so the timeline grows a new segment
  and keeps the gap as evidence.
* A :class:`PauseTimer` is the single authority for the silence deadline, and
  it counts from the end of the last detected speech frame - not from the
  moment the detector finished confirming that silence. Confirming an offset
  takes a hangover; adding the configured threshold to the confirmation time
  would charge the participant the hangover twice (goal.md section 6).

This module performs no I/O and opens no devices, so it is testable with a
manual clock.
"""

from __future__ import annotations

import bisect
import itertools
import math
import threading
from dataclasses import dataclass, field, replace
from typing import Callable, Iterable, Sequence

__all__ = [
    "MEASURED", "ESTIMATED", "SCHEDULED", "UNKNOWN",
    "Estimate", "MonotonicClock", "ManualClock",
    "StreamTimebase", "TimelineGap", "TimelineSegment", "CaptureTimeline",
    "ResampleMap", "DetectorProfile", "SpeechEvent", "SpeechSegmenter",
    "SPEECH_ONSET", "SPEECH_OFFSET",
    "PauseTimer", "PromptCandidate", "PlaybackPosition", "interpolate",
    "StalePositionFault", "TimingLedger", "validate_detector_profile",
    "DEFAULT_PROFILE", "DEFAULT_LATENESS_BUDGET_S", "COUNTED",
    "ORIGIN_RUN_END", "ORIGIN_LAST_STRONG",
]


# --- how a number was obtained ------------------------------------------------

MEASURED = "measured"       # observed in the acoustic/electrical signal
ESTIMATED = "estimated"     # derived from a calibrated model of the device
SCHEDULED = "scheduled"     # a controller decision time, not an observation
UNKNOWN = "unknown"

_METHODS = (MEASURED, ESTIMATED, SCHEDULED, UNKNOWN)


@dataclass(frozen=True)
class Estimate:
    """A time or interval together with the provenance of the number.

    ``uncertainty_s`` is a half-width; ``None`` means "not characterised",
    which is deliberately different from zero.
    """

    seconds: float
    method: str
    uncertainty_s: float | None = None
    source: str = ""

    def __post_init__(self) -> None:
        if self.method not in _METHODS:
            raise ValueError(
                f"unknown method {self.method!r}; expected one of {_METHODS}")
        if not math.isfinite(self.seconds):
            raise ValueError(f"non-finite seconds {self.seconds!r}")
        if self.uncertainty_s is not None:
            if not math.isfinite(self.uncertainty_s) or self.uncertainty_s < 0:
                raise ValueError(f"bad uncertainty {self.uncertainty_s!r}")

    @property
    def is_measurement(self) -> bool:
        return self.method == MEASURED

    def as_record(self) -> dict:
        return {
            "seconds": self.seconds,
            "method": self.method,
            "uncertainty_s": self.uncertainty_s,
            "source": self.source,
        }


# --- clocks -------------------------------------------------------------------

class MonotonicClock:
    """Controller clock. ``perf_counter`` so it cannot step backwards."""

    __slots__ = ()

    def now(self) -> float:
        import time

        return time.perf_counter()


class ManualClock(MonotonicClock):
    """Deterministic clock for tests and fake audio backends."""

    __slots__ = ("_t",)

    def __init__(self, start: float = 0.0) -> None:
        self._t = float(start)

    def now(self) -> float:
        return self._t

    def advance(self, dt: float) -> float:
        if dt < 0:
            raise ValueError("a monotonic clock cannot move backwards")
        self._t += float(dt)
        return self._t

    def set(self, t: float) -> float:
        if t < self._t:
            raise ValueError("a monotonic clock cannot move backwards")
        self._t = float(t)
        return self._t


# --- device sample position <-> controller time -------------------------------

class StreamTimebase:
    """Relates a device stream's sample counter to controller time.

    Anchors arrive from the audio callback: "sample ``pos`` of this stream was
    at (or will be at) controller time ``t``". The slope between the oldest and
    newest anchor gives the stream's actual rate, which differs from the
    nominal rate by device clock drift.
    """

    def __init__(self, nominal_rate: float, *, name: str = "stream",
                 min_span_s: float = 1.0, max_anchors: int = 256) -> None:
        if nominal_rate <= 0:
            raise ValueError("nominal_rate must be positive")
        self.nominal_rate = float(nominal_rate)
        self.name = name
        self.min_span_s = float(min_span_s)
        self._max_anchors = int(max_anchors)
        self._anchors: list[tuple[int, float]] = []
        self.anomalies: list[tuple[str, float]] = []

    def anchor(self, sample_pos: int, controller_time: float) -> str | None:
        """Add an anchor, clamping a non-monotonic one.

        This is called from the audio callback, so it must never raise: a host
        API that switches between device timestamps and a fallback estimate
        mid-stream can legitimately hand us a block whose computed time
        precedes the previous one, and killing the capture thread over it would
        lose the recording with no fault recorded. The anomaly is returned
        instead, for the caller to turn into a fault, and the anchor is clamped
        so the timebase stays monotonic.
        """
        anomaly: str | None = None
        if self._anchors:
            last_pos, last_t = self._anchors[-1]
            if sample_pos < last_pos:
                anomaly = "sample_position_went_backwards"
                sample_pos = last_pos
            if controller_time < last_t:
                anomaly = ("clock_went_backwards" if anomaly is None
                           else "sample_position_and_clock_went_backwards")
                controller_time = last_t
        if anomaly is not None:
            self.anomalies.append((anomaly, float(controller_time)))
        self._anchors.append((int(sample_pos), float(controller_time)))
        if len(self._anchors) > self._max_anchors:
            # Keep the first anchor: the long baseline is what makes the rate
            # estimate meaningful. Drop from the middle instead.
            del self._anchors[1]
        return anomaly

    @property
    def anchors(self) -> Sequence[tuple[int, float]]:
        return tuple(self._anchors)

    def measured_rate(self) -> float | None:
        """Observed samples per second, or ``None`` before the baseline is long
        enough for the figure to mean anything."""
        if len(self._anchors) < 2:
            return None
        (p0, t0), (p1, t1) = self._anchors[0], self._anchors[-1]
        span = t1 - t0
        if span < self.min_span_s or p1 == p0:
            return None
        return (p1 - p0) / span

    def effective_rate(self) -> float:
        return self.measured_rate() or self.nominal_rate

    def drift_ppm(self) -> float | None:
        rate = self.measured_rate()
        if rate is None:
            return None
        return (rate - self.nominal_rate) / self.nominal_rate * 1e6

    def time_of_sample(self, sample_pos: int) -> float:
        if not self._anchors:
            raise LookupError(f"{self.name}: no anchor yet")
        pos, t = self._anchors[-1]
        return t + (sample_pos - pos) / self.effective_rate()

    def sample_at_time(self, controller_time: float) -> int:
        if not self._anchors:
            raise LookupError(f"{self.name}: no anchor yet")
        pos, t = self._anchors[-1]
        return int(round(pos + (controller_time - t) * self.effective_rate()))


# --- capture timeline ---------------------------------------------------------

@dataclass(frozen=True)
class TimelineSegment:
    """A contiguous run of recorded samples with a single linear time mapping."""

    file_start: int        # sample index in the written file
    device_start: int      # device frame counter, including frames lost earlier
    start_time: float      # controller time of ``file_start``
    rate: float
    frames: int = 0

    def time_of(self, file_sample: int) -> float:
        return self.start_time + (file_sample - self.file_start) / self.rate


#: How a gap's lost-frame count was obtained. ``ESTIMATED`` means it was
#: derived from the callback time discrepancy (the device does not report an
#: exact lost count); ``COUNTED`` means the recorder dropped a block itself and
#: knows the exact number.
COUNTED = "counted"


@dataclass(frozen=True)
class TimelineGap:
    """Samples the device produced (or should have) that never reached the file."""

    file_sample: int          # where the discontinuity sits in the written file
    frames_lost: int          # see ``method`` for how this number was obtained
    controller_time: float
    kind: str                 # "input_overflow" | "discontinuity" | recorder drop
    method: str = ESTIMATED

    def as_record(self) -> dict:
        return {
            "file_sample": self.file_sample,
            "frames_lost": self.frames_lost,
            "frames_lost_method": self.method,
            "controller_time": self.controller_time,
            "kind": self.kind,
        }


class CaptureTimeline:
    """Sample-index <-> controller-time mapping for one continuous recording.

    ``note_block`` is called once per input callback with the controller time of
    the block's *first* frame. A block that arrives later than the previous
    segment predicts means frames were lost: the timeline closes the segment,
    records a :class:`TimelineGap`, and starts a new segment. The written file
    therefore stays byte-identical to what the device delivered.
    """

    #: Tolerance when only callback-entry time is available. It has to clear
    #: real callback jitter: measured worst-case callback intervals on this PC
    #: ranged from 12 ms (WASAPI) to 40 ms (WDM-KS) against a 10 ms nominal
    #: block, and the criterion compares consecutive blocks, so the usable
    #: threshold is about twice the worst jitter. At that width a single lost
    #: 10 ms block is invisible - which is exactly why the device clock is
    #: preferred whenever the host API provides it.
    DEFAULT_GAP_TOLERANCE_S = 0.080

    #: Tolerance when the device's own block timestamps are available. The
    #: device clock does not jitter, so a single dropped block stands out.
    DEFAULT_DEVICE_GAP_TOLERANCE_S = 0.002

    def __init__(self, sample_rate: float, *, name: str = "microphone",
                 gap_tolerance_s: float | None = None,
                 device_gap_tolerance_s: float | None = None,
                 anchor_interval_s: float = 1.0) -> None:
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        self.sample_rate = float(sample_rate)
        self.name = name
        self.gap_tolerance_s = float(self.DEFAULT_GAP_TOLERANCE_S
                                     if gap_tolerance_s is None
                                     else gap_tolerance_s)
        self.device_gap_tolerance_s = float(
            self.DEFAULT_DEVICE_GAP_TOLERANCE_S
            if device_gap_tolerance_s is None else device_gap_tolerance_s)
        self.anchor_interval_s = float(anchor_interval_s)
        self.timebase = StreamTimebase(sample_rate, name=name)
        self.segments: list[TimelineSegment] = []
        self.gaps: list[TimelineGap] = []
        self.frames_written = 0         # frames handed to the recorder
        self.frames_persisted = 0       # frames the sink confirmed on disk
        self.device_frames = 0          # written + estimated lost
        self.status_flags: dict[str, int] = {}
        self.anomalies: list[dict] = []
        self._lock = threading.Lock()
        self._starts: list[int] = []    # segment file_start values, for bisect
        # Sub-anchors inside the current segment: (file_sample, time). They let
        # sample_to_time follow the device's actual rate instead of
        # extrapolating the nominal rate across minutes of recording.
        self._marks: list[tuple[int, float]] = []
        self._last_block_end: tuple[int, float] | None = None
        # Device-clock bookkeeping. ``_offset`` converts the device's stream
        # clock into controller time. On the real backend the observation is
        # ``first_frame_time - device_time == entry - currentTime`` - both
        # sampled at the same callback entry, so scheduling lateness cancels
        # out and what remains is the epoch difference between perf_counter
        # and PortAudio's stream clock: essentially constant, drifting slowly.
        # (An earlier version described it as "late-only" and tracked its
        # minimum; review R03-F02 showed that model matched only the fake
        # backend, and that an immediate downward step could label time
        # backwards.) It is therefore tracked symmetrically and slowly, and the
        # block time derived from it is clamped so the mapping never runs
        # backwards; a large correction is noted, not treated as a clock fault.
        self._offset: float | None = None
        self._last_device_end: float | None = None
        self._last_block_time: float | None = None
        self.offset_steps: list[dict] = []
        self.blocks_with_device_time = 0
        self.blocks_without_device_time = 0

    #: Fraction of the observed offset error absorbed per block. At 100
    #: blocks/s this follows a slow epoch drift within seconds while a single
    #: outlying observation moves the mapping by a negligible amount.
    OFFSET_TRACK_RATE = 0.01
    #: A single-block offset correction larger than this is recorded as an
    #: ``offset_steps`` entry so the evidence shows where the mapping was
    #: pulled. It does not make the recording non-continuous.
    OFFSET_STEP_NOTE_S = 0.005
    #: A device-clock jump beyond this is not a credible lost-frame interval.
    #: It is recorded as a ``device_time_discontinuity`` anomaly with the lost
    #: count left unknown, rather than converted into a fabricated number.
    DEVICE_GAP_SANITY_S = 1.0

    # -- ingestion

    def note_block(self, frames: int, first_frame_time: float, *,
                   device_time: float | None = None,
                   overflowed: bool = False,
                   status: str = "") -> TimelineGap | None:
        """Record one callback's worth of captured frames.

        ``first_frame_time`` is the controller-domain estimate for the block's
        first frame, which carries callback-entry jitter. ``device_time``, when
        the host API supplies it, is the same instant on the device's own
        stream clock: smooth, so it is what gap detection and the sample/time
        mapping are built on. Without it both fall back to the jittery
        estimate and a much wider tolerance, and the block is counted in
        ``blocks_without_device_time`` so the evidence says which was used.

        Call this only once the block is known to have reached the recording
        path; use :meth:`note_not_persisted` for a block that was dropped,
        otherwise the timeline would count frames the file does not contain.

        Returns the gap detected immediately before this block, if any.
        """
        if frames < 0:
            raise ValueError("frames must be >= 0")
        with self._lock:
            if status:
                self.status_flags[status] = self.status_flags.get(status, 0) + 1

            if device_time is None:
                self.blocks_without_device_time += 1
                block_time = first_frame_time
                # The device clock is no longer a usable reference until the
                # host API resumes reporting it. Measuring the next
                # device-timed block against the end of the last one before
                # this fallback run would read the whole run as lost audio
                # (R03-F01), so the reference is dropped here and re-anchored
                # by the next block that carries a device time.
                self._last_device_end = None
            else:
                self.blocks_with_device_time += 1
                observed = first_frame_time - device_time
                if self._offset is None:
                    self._offset = observed
                else:
                    previous = self._offset
                    self._offset += (observed - previous) * self.OFFSET_TRACK_RATE
                    step = self._offset - previous
                    if abs(step) > self.OFFSET_STEP_NOTE_S:
                        self.offset_steps.append({
                            "file_sample": self.frames_written,
                            "device_time": device_time,
                            "step_s": step,
                        })
                block_time = device_time + self._offset

            # The mapping must never run backwards. A downward offset
            # correction is an estimator adjustment, not a clock fault, so it
            # is absorbed by clamping to the previous block's *start* rather
            # than reported as ``clock_went_backwards``. (Clamping to the
            # previous block's nominal end would be wrong: a device running
            # fast legitimately starts the next block before that instant, and
            # the clamp would push every block later and erase the drift.)
            if self._last_block_time is not None and block_time < self._last_block_time:
                block_time = self._last_block_time

            # A device clock that genuinely runs backwards is a real anomaly
            # and must stay distinguishable from estimator adjustments. The
            # tolerance leaves room for a fast device, whose blocks each start
            # a few microseconds before the previous block's nominal end.
            if (device_time is not None and self._last_device_end is not None
                    and device_time < self._last_device_end - self.device_gap_tolerance_s):
                self.anomalies.append({
                    "kind": "device_time_went_backwards",
                    "controller_time": block_time,
                    "file_sample": self.frames_written,
                    "jump_s": device_time - self._last_device_end,
                })
                self._last_device_end = None     # re-anchor on this block

            gap: TimelineGap | None = None
            if not self.segments:
                self._open_segment(block_time)
            else:
                if device_time is not None and self._last_device_end is not None:
                    late_by = device_time - self._last_device_end
                    tolerance = self.device_gap_tolerance_s
                    at = self._last_device_end + (self._offset or 0.0)
                    basis = "device_clock"
                else:
                    at = self._predicted_next_time()
                    late_by = block_time - at
                    tolerance = self.gap_tolerance_s
                    basis = "callback_time"
                if late_by >= self.DEVICE_GAP_SANITY_S:
                    # Not a credible lost-frame interval: a device-clock step,
                    # a suspended process, or a stream that was paused. The
                    # count is unknown and is not invented.
                    self.anomalies.append({
                        "kind": "device_time_discontinuity",
                        "controller_time": at,
                        "file_sample": self.frames_written,
                        "jump_s": late_by,
                        "basis": basis,
                    })
                    self._open_segment(block_time)
                elif overflowed or late_by > tolerance:
                    lost = int(round(late_by * self.sample_rate))
                    gap = TimelineGap(
                        file_sample=self.frames_written,
                        frames_lost=max(lost, 0),
                        controller_time=at,
                        kind="input_overflow" if overflowed else "discontinuity",
                    )
                    self.gaps.append(gap)
                    self.device_frames += gap.frames_lost
                    self._open_segment(block_time)

            if frames:
                seg = self.segments[-1]
                self.segments[-1] = replace(seg, frames=seg.frames + frames)
                self.frames_written += frames
                self.device_frames += frames
                end_time = block_time + frames / self.sample_rate
                self._last_block_end = (self.frames_written, end_time)
                self._last_block_time = block_time
                if device_time is not None:
                    self._last_device_end = device_time + frames / self.sample_rate
                self._mark(self.frames_written, end_time)
                anomaly = self.timebase.anchor(self.device_frames, end_time)
                if anomaly:
                    self.anomalies.append({
                        "kind": anomaly,
                        "controller_time": block_time,
                        "file_sample": self.frames_written,
                    })
            return gap

    def note_not_persisted(self, frames: int, first_frame_time: float, *,
                           kind: str = "not_persisted") -> TimelineGap:
        """Record audio the device delivered but the recorder could not keep.

        A writer backlog or a dead writer thread loses real audio. Counting
        those frames as written would leave the file short while every later
        sample index mapped to a time earlier than the truth - a silent shift
        of exactly the speech boundaries this study measures. So the frames are
        never added to the timeline; a gap is recorded instead and the next
        block starts a new segment.
        """
        if frames < 0:
            raise ValueError("frames must be >= 0")
        with self._lock:
            if not self.segments:
                self._open_segment(first_frame_time)
            gap = TimelineGap(
                file_sample=self.frames_written,
                frames_lost=int(frames),
                controller_time=first_frame_time,
                # Unlike a device-side drop, the recorder knows exactly how
                # many frames it threw away, so this count is not an estimate.
                kind=kind,
                method=COUNTED,
            )
            self.gaps.append(gap)
            self.device_frames += int(frames)
            # The file is now discontinuous in time at this sample index: the
            # next delivered frames belong after the dropped interval, so open
            # their segment at the far side of it.
            resume_at = first_frame_time + frames / self.sample_rate
            self._last_block_end = (self.frames_written, resume_at)
            if self._last_device_end is not None:
                self._last_device_end += frames / self.sample_rate
            self._open_segment(resume_at)
            return gap

    def note_persisted(self, frames: int) -> None:
        """Confirm frames actually written to storage, from the writer thread."""
        with self._lock:
            self.frames_persisted += int(frames)

    def note_tail_shortfall(self, frames: int, at: float) -> TimelineGap:
        """Record frames that were delivered but never reached the file's end.

        Used at finalisation for blocks still queued when the writer died.
        Those frames are necessarily the tail of the file, so the gap sits at
        ``frames_persisted`` - the real end of the published audio - and no
        empty trailing segment is opened. (The first version placed it at the
        delivered count, which is past the end of the file; R03-F03b.)
        """
        if frames < 0:
            raise ValueError("frames must be >= 0")
        with self._lock:
            gap = TimelineGap(
                file_sample=self.frames_persisted,
                frames_lost=int(frames),
                controller_time=at,
                kind="writer_shortfall",
                method=COUNTED,
            )
            self.gaps.append(gap)
            return gap

    def _open_segment(self, start_time: float) -> None:
        self.segments.append(TimelineSegment(
            file_start=self.frames_written,
            device_start=self.device_frames,
            start_time=start_time,
            rate=self.sample_rate,
        ))
        self._starts.append(self.frames_written)
        self._marks = [(self.frames_written, start_time)]

    def _mark(self, file_sample: int, at: float) -> None:
        """Keep a periodic (sample, time) anchor inside the current segment."""
        if not self._marks:
            self._marks = [(file_sample, at)]
            return
        last_sample, last_time = self._marks[-1]
        if at - last_time >= self.anchor_interval_s:
            self._marks.append((file_sample, at))

    def _predicted_next_time(self) -> float:
        """When the next block's first frame is due.

        Predicted from the end of the previous block rather than extrapolated
        from the segment start, so accumulated device-clock drift cannot build
        up into a fabricated gap.
        """
        if self._last_block_end is not None:
            return self._last_block_end[1]
        seg = self.segments[-1]
        return seg.time_of(self.frames_written)

    def predicted_time_of_next_sample(self) -> float:
        with self._lock:
            return self._predicted_next_time()

    # -- mapping

    def _segment_for_sample(self, file_sample: int) -> TimelineSegment:
        if not self.segments:
            raise LookupError(f"{self.name}: recording has no frames yet")
        idx = bisect.bisect_right(self._starts, file_sample) - 1
        return self.segments[max(idx, 0)]

    def sample_to_time(self, file_sample: int) -> float:
        """Controller time of a sample index in the written file.

        Inside the current segment this interpolates between periodic anchors
        taken from the device's own block times, so the mapping follows the
        real sample rate instead of accumulating nominal-rate drift.
        """
        if file_sample < 0:
            raise ValueError("file_sample must be >= 0")
        with self._lock:
            seg = self._segment_for_sample(file_sample)
            if seg is self.segments[-1] and len(self._marks) >= 2 and \
                    file_sample >= self._marks[0][0]:
                marks = self._marks
                i = bisect.bisect_right([m[0] for m in marks], file_sample) - 1
                i = min(max(i, 0), len(marks) - 2)
                (s0, t0), (s1, t1) = marks[i], marks[i + 1]
                if s1 > s0:
                    return t0 + (file_sample - s0) * (t1 - t0) / (s1 - s0)
            return seg.time_of(file_sample)

    def time_to_sample(self, controller_time: float) -> tuple[int, bool]:
        """Sample index for a controller time.

        The second element is ``True`` when the requested time falls inside a
        gap (or outside the recording), i.e. no sample actually exists there and
        the returned index is the nearest boundary.
        """
        if not self.segments:
            raise LookupError(f"{self.name}: recording has no frames yet")
        first = self.segments[0]
        if controller_time < first.start_time:
            return 0, True
        for seg in reversed(self.segments):
            if controller_time >= seg.start_time:
                offset = int(round((controller_time - seg.start_time) * seg.rate))
                if offset <= seg.frames:
                    return seg.file_start + offset, False
                # Past the end of this segment: either inside the following gap
                # or past the end of the whole recording.
                return seg.file_start + seg.frames, True
        return 0, True

    @property
    def duration_s(self) -> float:
        return self.frames_written / self.sample_rate

    @property
    def frames_lost(self) -> int:
        return sum(g.frames_lost for g in self.gaps)

    def integrity(self) -> dict:
        """Everything a consumer needs to decide whether to trust this audio.

        ``continuous`` is deliberately conservative: an empty recording, a gap,
        a clock anomaly, any divergence between frames handed to the recorder
        and frames confirmed on disk, or a timing basis that could not have
        seen a lost block all make it false. A reader must never see
        ``continuous: true`` for audio that is actually short.
        """
        persisted_known = self.frames_persisted > 0 or self.frames_written == 0
        complete = (self.frames_persisted == self.frames_written
                    if persisted_known else False)
        if self.blocks_without_device_time == 0 and self.blocks_with_device_time:
            basis = "device_clock"
            undetectable = self.device_gap_tolerance_s
        elif self.blocks_with_device_time == 0:
            basis = "callback_time"
            undetectable = self.gap_tolerance_s
        else:
            basis = "mixed"
            undetectable = self.gap_tolerance_s
        # On the callback-time basis a loss shorter than the tolerance is
        # invisible, so "continuous" cannot honestly be asserted there: the
        # field says what the evidence can support, and ``undetectable_gap_s``
        # says what it cannot (R03-F03a).
        continuity_supported = basis == "device_clock"
        return {
            "name": self.name,
            "sample_rate": self.sample_rate,
            "frames_written": self.frames_written,
            "frames_persisted": self.frames_persisted,
            "device_frames": self.device_frames,
            "frames_lost_estimate": self.frames_lost,
            "gaps": [g.as_record() for g in self.gaps],
            "segments": len(self.segments),
            "status_flags": dict(self.status_flags),
            "clock_anomalies": list(self.anomalies),
            "measured_rate": self.timebase.measured_rate(),
            "drift_ppm": self.timebase.drift_ppm(),
            "empty": self.frames_written == 0,
            "all_frames_persisted": complete,
            "blocks_with_device_time": self.blocks_with_device_time,
            "blocks_without_device_time": self.blocks_without_device_time,
            "device_to_controller_offset_s": self._offset,
            "offset_steps": list(self.offset_steps),
            "gap_basis": basis,
            "undetectable_gap_s": undetectable,
            "continuity_supported_by_basis": continuity_supported,
            "continuous": bool(self.frames_written > 0 and not self.gaps
                               and not self.anomalies and complete
                               and continuity_supported),
        }


# --- resampled analysis stream ------------------------------------------------

@dataclass(frozen=True)
class ResampleMap:
    """Index mapping between the preserved recording and the VAD stream.

    The detector runs on a normalised, resampled copy (goal.md section 6); every
    detector index must map back to an original sample index for evidence.
    """

    source_rate: float
    target_rate: float
    source_start: int = 0

    def __post_init__(self) -> None:
        if self.source_rate <= 0 or self.target_rate <= 0:
            raise ValueError("rates must be positive")

    @property
    def ratio(self) -> float:
        return self.source_rate / self.target_rate

    def source_sample(self, target_index: int) -> int:
        return self.source_start + int(round(target_index * self.ratio))

    def target_index(self, source_sample: int) -> int:
        return int(round((source_sample - self.source_start) / self.ratio))

    def source_span(self, target_index: int, target_frames: int) -> tuple[int, int]:
        start = self.source_sample(target_index)
        end = self.source_sample(target_index + target_frames)
        return start, end


# --- speech segmentation ------------------------------------------------------

@dataclass(frozen=True)
class DetectorProfile:
    """Voice-activity detector settings that affect protocol boundaries.

    Every field changes where a speech offset lands, so the profile is part of
    the frozen configuration and is recorded with each trial.
    """

    frame_ms: float = 32.0
    speech_threshold: float = 0.5
    exit_threshold: float = 0.35
    min_speech_ms: float = 96.0
    hangover_ms: float = 150.0
    detector: str = "unset"          # e.g. "silero-vad-5.1-onnx"
    sample_rate: float = 16000.0

    def __post_init__(self) -> None:
        if self.frame_ms <= 0:
            raise ValueError("frame_ms must be positive")
        if not 0.0 < self.exit_threshold <= self.speech_threshold <= 1.0:
            raise ValueError("need 0 < exit_threshold <= speech_threshold <= 1")
        if self.min_speech_ms < 0 or self.hangover_ms < 0:
            raise ValueError("durations must be >= 0")

    @property
    def frame_s(self) -> float:
        return self.frame_ms / 1000.0

    @property
    def hangover_s(self) -> float:
        return self.hangover_ms / 1000.0

    @property
    def min_speech_s(self) -> float:
        return self.min_speech_ms / 1000.0

    @property
    def hangover_frames(self) -> int:
        return int(math.ceil(self.hangover_ms / self.frame_ms))

    @property
    def min_speech_frames(self) -> int:
        return max(1, int(math.ceil(self.min_speech_ms / self.frame_ms)))

    def as_record(self) -> dict:
        return {
            "detector": self.detector,
            "sample_rate": self.sample_rate,
            "frame_ms": self.frame_ms,
            "speech_threshold": self.speech_threshold,
            "exit_threshold": self.exit_threshold,
            "min_speech_ms": self.min_speech_ms,
            "hangover_ms": self.hangover_ms,
        }


#: The single engineering default. The bench tool, the documented profile in
#: validation/audio_spike.md and the library default must all be this object;
#: three different profiles in three places would make "the detector settings"
#: unanswerable, and goal.md section 14 makes the profile part of the frozen
#: manipulation. These values are an engineering starting point chosen so the
#: shortest 0.5 s threshold stays servable - not a research decision.
DEFAULT_PROFILE = DetectorProfile(
    frame_ms=32.0,
    speech_threshold=0.5,
    exit_threshold=0.35,
    min_speech_ms=96.0,
    hangover_ms=150.0,
    detector="unset",
    sample_rate=16000.0,
)

#: How late a deadline may be when the controller first learns of it before the
#: attempt is flagged instead of prompted. See PauseTimer.discovery_lateness.
DEFAULT_LATENESS_BUDGET_S = 0.050


def validate_detector_profile(profile: DetectorProfile,
                              thresholds: Iterable[float],
                              *, decision_budget_s: float = 0.0) -> None:
    """Reject a detector profile that cannot serve the shortest threshold.

    The detector confirms a speech offset ``hangover_ms`` after it happened. If
    that confirmation (plus whatever the controller needs to commit output)
    reaches or exceeds the shortest configured threshold, the eligibility
    deadline is already in the past when the controller learns about it, and the
    prompt can only ever be late. That is a configuration error, not something
    to compensate for by starting the prompt early.
    """
    values = [float(t) for t in thresholds]
    if not values:
        raise ValueError("no thresholds given")
    shortest = min(values)
    if shortest <= 0:
        raise ValueError("thresholds must be positive")
    need = profile.hangover_s + float(decision_budget_s)
    if need >= shortest:
        raise ValueError(
            f"detector hangover {profile.hangover_s:.3f}s + decision budget "
            f"{float(decision_budget_s):.3f}s >= shortest threshold "
            f"{shortest:.3f}s: the deadline would pass before the offset is "
            "confirmed"
        )
    # This bounds only the *fixed* part of the detector's reporting delay. How
    # long the detector sits in the hysteresis band before giving up on a run
    # is data-dependent and cannot be bounded from the profile alone, so a
    # static check cannot guarantee a timely deadline on its own; that is what
    # PauseTimer.discovery_lateness and the lateness budget are for.


SPEECH_ONSET = "speech_onset"
SPEECH_OFFSET = "speech_offset"


@dataclass(frozen=True)
class SpeechEvent:
    """A participant speech boundary, with the detector's own delay exposed."""

    kind: str
    frame_index: int          # detector frame where the boundary actually is
    event_time: float         # controller time of the boundary
    confirmed_time: float     # controller time the detector could report it
    source_sample: int        # index in the preserved recording
    frames_considered: int = 0
    #: Frames of this run that were only in the hysteresis band. Recorded
    #: because the band is the difference between "the detector still calls
    #: this speech" and "this is clearly speech", and that difference moves the
    #: silence origin.
    band_frames: int = 0
    #: Last frame at or above the speech threshold, and the time it ended.
    #: Kept alongside the offset so an analyst can see both readings of "where
    #: speech ended" without re-running the detector.
    last_strong_frame: int | None = None
    strong_event_time: float | None = None

    @property
    def detector_delay_s(self) -> float:
        return self.confirmed_time - self.event_time

    @property
    def band_dwell_s(self) -> float | None:
        """Seconds of this run spent only in the hysteresis band."""
        if self.strong_event_time is None:
            return None
        return self.event_time - self.strong_event_time

    def as_record(self) -> dict:
        return {
            "kind": self.kind,
            "frame_index": self.frame_index,
            "event_time": self.event_time,
            "confirmed_time": self.confirmed_time,
            "detector_delay_s": self.detector_delay_s,
            "source_sample": self.source_sample,
            "band_frames": self.band_frames,
            "band_dwell_s": self.band_dwell_s,
            "last_strong_frame": self.last_strong_frame,
            "strong_event_time": self.strong_event_time,
        }


class SpeechSegmenter:
    """Turns per-frame speech probabilities into onset/offset events.

    Boundaries are reported where they happened, with the confirmation time
    alongside:

    * an onset is the start of the first frame of a run that reached
      ``min_speech_ms`` - short coughs and clicks never open a run;
    * an offset is the *end of the last frame above the speech threshold*,
      confirmed only after ``hangover_ms`` of quiet.

    A frame's controller time comes from the capture timeline, so the reported
    boundary survives dropped input frames.
    """

    def __init__(self, profile: DetectorProfile, resample: ResampleMap,
                 frame_time: Callable[[int], float]) -> None:
        self.profile = profile
        self.resample = resample
        self._frame_time = frame_time
        self._next_frame = 0
        self.in_speech = False
        self._run_start: int | None = None      # candidate onset frame
        self._run_frames = 0
        self._last_speech_frame: int | None = None
        self._last_strong_frame: int | None = None
        self._band_frames = 0
        self._quiet_frames = 0
        self.events: list[SpeechEvent] = []

    # -- helpers

    def _frame_start(self, frame_index: int) -> float:
        return self._frame_time(frame_index)

    def _frame_end(self, frame_index: int) -> float:
        return self._frame_time(frame_index) + self.profile.frame_s

    def _source_sample(self, frame_index: int) -> int:
        samples_per_frame = self.profile.frame_s * self.profile.sample_rate
        return self.resample.source_sample(
            int(round(frame_index * samples_per_frame)))

    # -- ingestion

    def push(self, probability: float) -> list[SpeechEvent]:
        """Feed the next detector frame. Returns events emitted by this frame."""
        idx = self._next_frame
        self._next_frame += 1
        p = float(probability)
        out: list[SpeechEvent] = []
        prof = self.profile

        if not self.in_speech:
            if p >= prof.speech_threshold:
                if self._run_start is None:
                    self._run_start = idx
                    self._run_frames = 0
                self._run_frames += 1
                if self._run_frames >= prof.min_speech_frames:
                    event = SpeechEvent(
                        kind=SPEECH_ONSET,
                        frame_index=self._run_start,
                        event_time=self._frame_start(self._run_start),
                        confirmed_time=self._frame_end(idx),
                        source_sample=self._source_sample(self._run_start),
                        frames_considered=self._run_frames,
                    )
                    self.in_speech = True
                    self._last_speech_frame = idx
                    self._last_strong_frame = idx
                    self._band_frames = 0
                    self._quiet_frames = 0
                    self._run_start = None
                    self._run_frames = 0
                    self.events.append(event)
                    out.append(event)
            elif p < prof.exit_threshold:
                # Hysteresis applies to a candidate run too: a frame below the
                # exit threshold breaks it, which is why a cough shorter than
                # min_speech_ms never opens speech.
                self._run_start = None
                self._run_frames = 0
            return out

        # In speech. A frame in the hysteresis band
        # [exit_threshold, speech_threshold) keeps the run open and resets the
        # quiet counter, so it is being treated as speech - and it must
        # therefore also move the offset origin. Leaving the origin behind
        # would date the silence from before audio the detector itself counted
        # as speech: an unbounded band dwell would then produce a deadline
        # already long past when the controller first hears about it, and the
        # participant would be prompted after materially less silence than the
        # assigned 0.5/1.0/2.0 s threshold. The threshold is the manipulation,
        # so that shortening is a protocol defect, not a rounding detail.
        if p >= prof.exit_threshold:
            self._last_speech_frame = idx
            if p >= prof.speech_threshold:
                self._last_strong_frame = idx
            else:
                self._band_frames += 1
            self._quiet_frames = 0
            return out

        self._quiet_frames += 1
        if self._quiet_frames >= prof.hangover_frames:
            last = (self._last_speech_frame
                    if self._last_speech_frame is not None else idx)
            strong = self._last_strong_frame
            event = SpeechEvent(
                kind=SPEECH_OFFSET,
                frame_index=last,
                event_time=self._frame_end(last),
                confirmed_time=self._frame_end(idx),
                source_sample=self._source_sample(last + 1),
                frames_considered=self._quiet_frames,
                band_frames=self._band_frames,
                last_strong_frame=strong,
                strong_event_time=(None if strong is None
                                   else self._frame_end(strong)),
            )
            self.in_speech = False
            self._quiet_frames = 0
            self._band_frames = 0
            self._last_speech_frame = None
            self._last_strong_frame = None
            self.events.append(event)
            out.append(event)
        return out

    def push_all(self, probabilities: Iterable[float]) -> list[SpeechEvent]:
        out: list[SpeechEvent] = []
        for p in probabilities:
            out.extend(self.push(p))
        return out


# --- pause timer and prompt eligibility ---------------------------------------

#: Where the silence interval starts counting. ``run_end`` is the end of the
#: in-speech run, which includes frames the detector kept in its hysteresis
#: band; ``last_strong`` is the end of the last frame at or above the speech
#: threshold. They differ by the band dwell, which is time the participant may
#: or may not have been audibly speaking - so the choice changes how much real
#: silence precedes the prompt and is a research decision (goal.md section
#: 14), applied here as configuration rather than as a code change.
ORIGIN_RUN_END = "run_end"
ORIGIN_LAST_STRONG = "last_strong"
_ORIGINS = (ORIGIN_RUN_END, ORIGIN_LAST_STRONG)


class PauseTimer:
    """The one place a silence deadline is computed.

    ``arm`` happens only when participant speech has been detected, so no
    pre-speech silence can ever qualify. The deadline is
    ``speech offset + threshold``, where the offset is read from the event
    according to the configured ``origin``; the detector's confirmation delay
    is recorded separately and never added to the interval.

    ``too_late`` guards a different hazard from the origin choice. With a
    profile that passes ``validate_detector_profile`` and a healthy capture
    timeline, an offset is always confirmed before its deadline. It can still
    be discovered late when the frame times come from a capture timeline that
    contains a gap between the last speech frame and the confirming frame, or
    when a real detector buffers more than its nominal hangover. Those are the
    cases the budget bounds (R03-F08).
    """

    def __init__(self, threshold_s: float, *,
                 profile: DetectorProfile | None = None,
                 lateness_budget_s: float = DEFAULT_LATENESS_BUDGET_S,
                 origin: str = ORIGIN_RUN_END) -> None:
        if threshold_s <= 0:
            raise ValueError("threshold_s must be positive")
        if lateness_budget_s < 0:
            raise ValueError("lateness_budget_s must be >= 0")
        if origin not in _ORIGINS:
            raise ValueError(f"origin must be one of {_ORIGINS}, not {origin!r}")
        self.threshold_s = float(threshold_s)
        self.profile = profile
        self.lateness_budget_s = float(lateness_budget_s)
        self.origin = origin
        self.armed = False
        self.silence_since: float | None = None
        self.silence_confirmed_at: float | None = None
        self.speech_runs = 0

    def origin_time(self, event: SpeechEvent) -> float:
        """The instant the configured origin reads off an offset event."""
        if self.origin == ORIGIN_LAST_STRONG and event.strong_event_time is not None:
            return event.strong_event_time
        return event.event_time

    def note_event(self, event: SpeechEvent) -> None:
        if event.kind == SPEECH_ONSET:
            self.note_onset(event.event_time)
        elif event.kind == SPEECH_OFFSET:
            self.note_offset(self.origin_time(event), event.confirmed_time)
        else:
            raise ValueError(f"unexpected event kind {event.kind!r}")

    def as_record(self) -> dict:
        return {
            "threshold_s": self.threshold_s,
            "origin": self.origin,
            "lateness_budget_s": self.lateness_budget_s,
            "profile": None if self.profile is None else self.profile.as_record(),
        }

    def note_onset(self, event_time: float) -> None:
        self.armed = True
        self.speech_runs += 1
        self.silence_since = None
        self.silence_confirmed_at = None

    def note_offset(self, event_time: float,
                    confirmed_time: float | None = None) -> None:
        if not self.armed:
            # An offset without a prior onset cannot arm the timer; the goal
            # requires participant speech first.
            return
        self.silence_since = float(event_time)
        self.silence_confirmed_at = (
            None if confirmed_time is None else float(confirmed_time))

    @property
    def deadline(self) -> float | None:
        if not self.armed or self.silence_since is None:
            return None
        return self.silence_since + self.threshold_s

    def known_at(self) -> float | None:
        """When the controller could first act on the current deadline."""
        deadline = self.deadline
        if deadline is None:
            return None
        if self.silence_confirmed_at is None:
            return deadline
        return max(deadline, self.silence_confirmed_at)

    @property
    def discovery_lateness(self) -> float | None:
        """How far past the deadline already was when it became knowable.

        Zero in the normal case: the detector confirms the offset well before
        ``offset + threshold``. It grows when the detector took a long time to
        decide the participant had stopped - and a large value means the
        participant received less actual silence than their condition
        specifies, which must be flagged rather than prompted through.
        """
        deadline = self.deadline
        known = self.known_at()
        if deadline is None or known is None:
            return None
        return max(0.0, known - deadline)

    def too_late(self, now: float | None = None) -> bool:
        """True when this deadline is too stale to act on.

        The controller must treat this as a ``deadline_already_past``
        deviation - record it, rearm, and do not speak - rather than firing a
        prompt that would land after a fraction of the assigned threshold.
        """
        lateness = self.discovery_lateness
        if lateness is None:
            return False
        return lateness > self.lateness_budget_s

    def eligible(self, now: float) -> bool:
        """Deadline reached *and* not stale.

        Both conditions live here so a caller cannot accidentally act on a
        deadline that was already long past when first learned.
        """
        deadline = self.deadline
        if deadline is None or now < deadline:
            return False
        return not self.too_late(now)

    def reset_for_rearm(self) -> None:
        """Return to listening after a cancellation, keeping the armed state.

        A fresh deadline is computed from the *next* detected speech offset; the
        cancelled candidate's deadline is discarded rather than reused.
        """
        self.silence_since = None
        self.silence_confirmed_at = None


@dataclass
class PromptCandidate:
    """One scheduled encouragement attempt.

    ``committed`` is the protocol-relevant boundary: before it the clip can
    still be removed from the queue, after it the allowance is consumed even if
    the participant resumes speaking before the clip is audible.
    """

    trial_id: str
    threshold_s: float
    deadline: float
    scheduled_at: float
    candidate_index: int = 0
    committed_at: float | None = None
    cancelled_at: float | None = None
    cancel_reason: str = ""
    #: Audible onset estimate, or ``None`` when the clip has no detectable
    #: sound and therefore no onset to estimate.
    audible_onset: Estimate | None = None
    #: The three components of the onset, kept separately so no single number
    #: mixes a scheduling delay with a device latency or a property of the
    #: audio file. Folding them together once inflated every reported onset by
    #: the length of a silent probe clip.
    device_offset_s: float | None = None
    clip_leading_silence_s: float | None = None

    @property
    def committed(self) -> bool:
        return self.committed_at is not None

    @property
    def onset_delay_s(self) -> float | None:
        """Estimated audible onset relative to the eligibility deadline.

        This is the quantity the candidate engineering target in goal.md
        section 7 talks about. It is the sum of the commit delay, the device
        offset and the clip's own leading silence; ``None`` when any part is
        unknown, rather than a number with a missing term silently treated as
        zero.
        """
        if self.audible_onset is None:
            return None
        return self.audible_onset.seconds - self.deadline

    @property
    def cancelled(self) -> bool:
        return self.cancelled_at is not None

    def commit(self, at: float, audible_onset: Estimate | None = None) -> None:
        if self.cancelled:
            raise RuntimeError("cannot commit a cancelled candidate")
        if self.committed:
            raise RuntimeError("candidate already committed")
        self.committed_at = float(at)
        self.audible_onset = audible_onset

    def cancel(self, at: float, reason: str) -> bool:
        """Cancel if still uncommitted. Returns ``True`` when it was removed."""
        if self.committed or self.cancelled:
            return False
        self.cancelled_at = float(at)
        self.cancel_reason = reason
        return True

    def as_record(self) -> dict:
        return {
            "trial_id": self.trial_id,
            "candidate_index": self.candidate_index,
            "threshold_s": self.threshold_s,
            "deadline": self.deadline,
            "scheduled_at": self.scheduled_at,
            "committed_at": self.committed_at,
            "cancelled_at": self.cancelled_at,
            "cancel_reason": self.cancel_reason,
            "audible_onset": (None if self.audible_onset is None
                              else self.audible_onset.as_record()),
            "commit_delay_s": (None if self.committed_at is None
                               else self.committed_at - self.deadline),
            "device_offset_s": self.device_offset_s,
            "clip_leading_silence_s": self.clip_leading_silence_s,
            "onset_delay_s": self.onset_delay_s,
        }


# --- playback position for the avatar -----------------------------------------

class StalePositionFault(RuntimeError):
    """The avatar clock went stale; the renderer must stop rather than guess."""


@dataclass(frozen=True)
class PlaybackPosition:
    """A timestamped playback position for ``TanukiLipSync.playTrack``.

    ``file_time`` is seconds from the start of the complete frozen WAV,
    including any leading silence, which is what the mouth track is indexed by.
    """

    file_time: float
    controller_time: float
    rate: float            # 1.0 while playing, 0.0 when stopped/paused
    playing: bool
    duration: float
    generation: int = 0
    method: str = ESTIMATED

    def as_record(self) -> dict:
        return {
            "file_time": self.file_time,
            "controller_time": self.controller_time,
            "rate": self.rate,
            "playing": self.playing,
            "duration": self.duration,
            "generation": self.generation,
            "method": self.method,
        }


def interpolate(snapshot: PlaybackPosition, now: float, *,
                stale_after_s: float = 0.25) -> float:
    """Bounded interpolation of a playback position.

    Mirrors what the browser adapter must do: extrapolate from the last
    snapshot, clamp to the clip, and raise instead of extrapolating across a
    stale update. An external-clock track has no end event of its own, so a
    silently frozen clock would otherwise hold the mouth open indefinitely.
    """
    age = now - snapshot.controller_time
    if age < -1e-9:
        raise StalePositionFault(
            f"position snapshot is {-age:.3f}s in the future; clocks disagree")
    if age > stale_after_s:
        raise StalePositionFault(
            f"position snapshot is {age:.3f}s old (limit {stale_after_s:.3f}s)")
    t = snapshot.file_time + age * snapshot.rate
    if t < 0.0:
        return 0.0
    if t > snapshot.duration:
        return snapshot.duration
    return t


# --- event ledger -------------------------------------------------------------

@dataclass
class TimingLedger:
    """Ordered in-memory timing events.

    Durable append-only storage is M3's job; this keeps the records that the
    audio layer produces so a checkpoint can assert on them.
    """

    clock: MonotonicClock = field(default_factory=MonotonicClock)
    records: list[dict] = field(default_factory=list)
    # Written from the PortAudio callback and from the controller thread, so
    # the sequence counter and the append are taken under one lock. seq is the
    # ordering authority for audio events; a duplicate would make the order
    # ambiguous.
    _counter: "itertools.count" = field(
        default_factory=lambda: itertools.count(1), repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    #: Envelope keys a payload may not overwrite.
    RESERVED = ("seq", "kind", "controller_time")

    def record(self, kind: str, /, *, at: float | None = None, **fields) -> dict:
        """Append one event.

        ``kind`` is positional-only so a payload may carry its own ``kind``
        field, and a payload key that would overwrite the envelope is rejected
        rather than silently relabelling the event.
        """
        clashes = sorted(set(fields) & set(self.RESERVED))
        if clashes:
            raise ValueError(
                f"payload keys {clashes} would overwrite the event envelope; "
                "nest them (for example fault=record) instead")
        now = self.clock.now() if at is None else float(at)
        payload = {
            key: (value.as_record() if isinstance(value, Estimate) else value)
            for key, value in fields.items()
        }
        with self._lock:
            rec = {"seq": next(self._counter), "kind": kind,
                   "controller_time": now, **payload}
            self.records.append(rec)
        return rec

    def of_kind(self, kind: str) -> list[dict]:
        return [r for r in self.records if r["kind"] == kind]

    def __len__(self) -> int:
        return len(self.records)
