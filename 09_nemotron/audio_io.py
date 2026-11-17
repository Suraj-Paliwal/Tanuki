"""Native audio capture and playback for the Tanuki experiment controller.

The controller owns the audio, not the browser (goal.md section 5). This module
holds the device layer:

* :func:`inventory` - device identities and defaults, without opening a stream.
* :class:`ContinuousRecorder` - one uninterrupted microphone file per attempt,
  written through a queue so the audio callback never touches the disk, with
  dropped input frames recorded as timeline gaps instead of being papered over.
* :class:`OutputPlayer` - one output stream that stays open for the whole
  session and plays silence when idle, so the device buffer depth (and with it
  the commit boundary) does not change between trials. Story and instruction
  clips start immediately; the encouragement is *armed* with a deadline and
  commits inside the callback, which is the last moment a queued clip can still
  be removed.
* :class:`FakeBackend` - a deterministic driver with no devices at all. Every
  boundary test in ``tests/`` runs on it, so the state machine is verifiable on
  a PC with no microphone attached.

Two rules that the goal states and the code therefore enforces:

* Playback never starts before the eligibility deadline. The audible onset is
  then ``deadline + output latency``, which is late by a measurable amount
  rather than early by an unmeasurable one.
* An audible onset reported here is an :class:`~timing.Estimate` with method
  ``estimated``, derived from the device's own latency report. Calling it a
  measurement requires an acoustic reference channel, which this module does
  not have.
"""

from __future__ import annotations

import hashlib
import math
import os
import queue
import threading
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

import numpy as np

from timing import (
    ESTIMATED,
    Estimate,
    CaptureTimeline,
    MonotonicClock,
    PlaybackPosition,
    PromptCandidate,
    TimingLedger,
)

__all__ = [
    "DeviceIdentity", "inventory", "AudioFault", "FaultRecord", "BlockTiming",
    "Clip", "load_clip", "silence_clip", "tone_clip",
    "ContinuousRecorder", "RecordingResult", "OutputPlayer", "WaveSink",
    "CancelOutcome", "CANCEL_REMOVED", "CANCEL_ALREADY_CANCELLED",
    "CANCEL_TOO_LATE", "CANCEL_NOTHING_ARMED",
    "SoundDeviceBackend", "FakeBackend", "FakeStream",
    "CAPTURE_RATE", "VAD_RATE", "DEFAULT_BLOCKSIZE",
]

CAPTURE_RATE = 48_000          # preserved recording rate
VAD_RATE = 16_000              # detector stream rate
DEFAULT_BLOCKSIZE = 480        # 10 ms at 48 kHz
CAPTURE_DTYPE = "int16"


# --- faults -------------------------------------------------------------------

class AudioFault(RuntimeError):
    """A device, clock or storage failure that must end the attempt."""


@dataclass(frozen=True)
class FaultRecord:
    kind: str
    detail: str
    at: float
    fatal: bool = True

    def as_record(self) -> dict:
        return {"kind": self.kind, "detail": self.detail,
                "at": self.at, "fatal": self.fatal}


# --- device identity ----------------------------------------------------------

@dataclass(frozen=True)
class DeviceIdentity:
    """Enough of a device's identity to detect that it changed between sessions.

    The PortAudio index alone is not an identity: it moves when a Bluetooth
    headset connects. The configuration pins ``key()``.
    """

    index: int
    name: str
    hostapi: int
    hostapi_name: str
    max_input_channels: int
    max_output_channels: int
    default_samplerate: float

    def key(self) -> str:
        return f"{self.hostapi_name}|{self.name}|{self.max_input_channels}in/{self.max_output_channels}out"

    def as_record(self) -> dict:
        return {
            "index": self.index,
            "name": self.name,
            "hostapi": self.hostapi,
            "hostapi_name": self.hostapi_name,
            "max_input_channels": self.max_input_channels,
            "max_output_channels": self.max_output_channels,
            "default_samplerate": self.default_samplerate,
            "key": self.key(),
        }


def inventory(sd=None) -> dict:
    """Device inventory. Opens no stream and captures nothing.

    Returns a JSON-serialisable report. Capture availability is reported as
    two separate facts, because they have different consequences:

    ``default_capture_available``
        A default input device exists, so ``device=None`` works.
    ``capture_possible``
        Some input-capable device exists, so a session that *pins* a device by
        identity can still record. On this PC the first is false while the
        second is true (two Bluetooth hands-free endpoints on WDM-KS), and a
        preflight that refused outright would be wrong about a pinned device -
        while one that only checked the second would be wrong about the
        default.
    """
    if sd is None:
        try:
            import sounddevice as sd  # noqa: PLC0415  (optional dependency)
        except Exception as exc:  # pragma: no cover - import failure path
            return {
                "available": False,
                "error": f"{type(exc).__name__}: {exc}",
                "capture_available": False,
                "playback_available": False,
            }

    hostapis = []
    for i, api in enumerate(sd.query_hostapis()):
        hostapis.append({
            "index": i,
            "name": api["name"],
            "default_input_device": api["default_input_device"],
            "default_output_device": api["default_output_device"],
        })

    devices = []
    for i, dev in enumerate(sd.query_devices()):
        devices.append(DeviceIdentity(
            index=i,
            name=str(dev["name"]).replace("\n", " ").replace("\r", " ").strip(),
            hostapi=dev["hostapi"],
            hostapi_name=hostapis[dev["hostapi"]]["name"],
            max_input_channels=dev["max_input_channels"],
            max_output_channels=dev["max_output_channels"],
            default_samplerate=dev["default_samplerate"],
        ).as_record())

    default_in, default_out = (None, None)
    try:
        default_in, default_out = sd.default.device
    except Exception:  # pragma: no cover - defensive
        pass

    inputs = [d for d in devices if d["max_input_channels"] > 0]
    outputs = [d for d in devices if d["max_output_channels"] > 0]
    has_default_in = default_in is not None and default_in >= 0
    has_default_out = default_out is not None and default_out >= 0
    warnings = []
    if not has_default_in:
        warnings.append(
            "no default input device: PortAudio reports default_input_device "
            "< 0 for the default host API, so recording requires an explicitly "
            "pinned device"
        )
    if not inputs:
        warnings.append("no input-capable device of any host API")
    elif not has_default_in:
        names = ", ".join(f"{d['index']} {d['name']!r} ({d['hostapi_name']})"
                          for d in inputs[:4])
        warnings.append(
            f"{len(inputs)} input-capable device(s) exist but none is the "
            f"default: {names}"
        )
    if not has_default_out:
        warnings.append("no default output device")

    return {
        "available": True,
        "portaudio": str(sd.get_portaudio_version()[1]),
        "sounddevice": getattr(sd, "__version__", "unknown"),
        "hostapis": hostapis,
        "devices": devices,
        "default_input_device": default_in,
        "default_output_device": default_out,
        "input_device_count": len(inputs),
        "output_device_count": len(outputs),
        # Kept for existing callers; equals default_capture_available.
        "capture_available": bool(inputs) and has_default_in,
        "default_capture_available": bool(inputs) and has_default_in,
        "capture_possible": bool(inputs),
        "playback_available": bool(outputs) and has_default_out,
        "default_playback_available": bool(outputs) and has_default_out,
        "playback_possible": bool(outputs),
        "input_devices": [d["key"] for d in inputs],
        "warnings": warnings,
    }


# --- clips --------------------------------------------------------------------

@dataclass(frozen=True)
class Clip:
    """A complete frozen WAV held in memory, int16, shape ``(frames, channels)``.

    ``leading_silence_s`` is where sound actually starts inside the file, or
    ``None`` when the clip has no detectable sound at all. The mouth track is
    indexed in file time, so the renderer must get file time; the protocol's
    "audible onset" of the prompt, in contrast, is the file start plus this
    offset - which is undefined for a silent clip.
    """

    @property
    def has_audible_onset(self) -> bool:
        return self.leading_silence_s is not None

    clip_id: str
    samples: np.ndarray
    samplerate: int
    sha256: str
    #: ``None`` when no sound was detected anywhere in the clip, which is not
    #: the same as zero.
    leading_silence_s: float | None = 0.0
    path: str | None = None

    def __post_init__(self) -> None:
        if self.samples.ndim != 2:
            raise ValueError("samples must be 2-D (frames, channels)")
        if self.samples.dtype != np.int16:
            raise ValueError("samples must be int16 to stay bit-exact with the file")

    @property
    def frames(self) -> int:
        return int(self.samples.shape[0])

    @property
    def channels(self) -> int:
        return int(self.samples.shape[1])

    @property
    def duration(self) -> float:
        return self.frames / self.samplerate

    def as_record(self) -> dict:
        return {
            "clip_id": self.clip_id,
            "path": self.path,
            "sha256": self.sha256,
            "samplerate": self.samplerate,
            "channels": self.channels,
            "frames": self.frames,
            "duration": self.duration,
            "leading_silence_s": self.leading_silence_s,
            "has_audible_onset": self.has_audible_onset,
        }


def _leading_silence_s(samples: np.ndarray, samplerate: int, *,
                       floor_db: float = -45.0,
                       frame_ms: float = 5.0) -> float | None:
    """Start of the first frame above ``floor_db``, or ``None`` if there is none.

    ``None`` matters: returning the clip's whole duration for a silent clip
    would be read as "this clip has N seconds of leading silence", and adding
    that to a buffer time produced an audible-onset estimate inflated by the
    entire clip length. A clip with no detectable onset has no audible onset to
    estimate, and the caller must say so rather than invent one.
    """
    mono = samples.astype(np.float32).mean(axis=1) / 32768.0
    step = max(1, int(samplerate * frame_ms / 1000.0))
    floor = 10.0 ** (floor_db / 20.0)
    for start in range(0, mono.size, step):
        block = mono[start:start + step]
        if block.size and float(np.max(np.abs(block))) >= floor:
            return start / samplerate
    return None


def load_clip(path: str | os.PathLike[str], *, clip_id: str | None = None,
              expect_samplerate: int | None = None,
              expect_sha256: str | None = None) -> Clip:
    """Load a frozen WAV and refuse anything that does not match the manifest.

    The experiment plays manifest-pinned audio only; the baseline's "fall back
    to the first available voice" behaviour is exactly what must not happen to a
    stimulus, so a hash or rate mismatch raises instead of adapting.
    """
    p = Path(path)
    raw = p.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if expect_sha256 and digest != expect_sha256:
        raise AudioFault(
            f"{p.name}: sha256 {digest} does not match manifest {expect_sha256}")
    with wave.open(str(p), "rb") as wav:
        if wav.getsampwidth() != 2:
            raise AudioFault(f"{p.name}: expected 16-bit PCM, got "
                             f"{wav.getsampwidth() * 8}-bit")
        channels = wav.getnchannels()
        samplerate = wav.getframerate()
        frames = wav.getnframes()
        data = wav.readframes(frames)
    if expect_samplerate and samplerate != expect_samplerate:
        raise AudioFault(f"{p.name}: sample rate {samplerate} != "
                         f"required {expect_samplerate}")
    samples = np.frombuffer(data, dtype="<i2").reshape(-1, channels).copy()
    return Clip(
        clip_id=clip_id or p.stem,
        samples=samples,
        samplerate=samplerate,
        sha256=digest,
        leading_silence_s=_leading_silence_s(samples, samplerate),
        path=str(p),
    )


def _clip_from_array(clip_id: str, samples: np.ndarray, samplerate: int) -> Clip:
    data = np.ascontiguousarray(samples.astype(np.int16))
    if data.ndim == 1:
        data = data.reshape(-1, 1)
    return Clip(
        clip_id=clip_id,
        samples=data,
        samplerate=samplerate,
        sha256=hashlib.sha256(data.tobytes()).hexdigest(),
        leading_silence_s=_leading_silence_s(data, samplerate),
    )


def silence_clip(duration: float, *, samplerate: int = CAPTURE_RATE,
                 channels: int = 1, clip_id: str = "silence") -> Clip:
    frames = int(round(duration * samplerate))
    return _clip_from_array(clip_id, np.zeros((frames, channels), np.int16),
                            samplerate)


def tone_clip(duration: float, *, freq: float = 1000.0, amplitude: float = 0.25,
              samplerate: int = CAPTURE_RATE, channels: int = 1,
              lead_silence: float = 0.0, clip_id: str = "tone") -> Clip:
    """Synthetic clip for bench checks. Not a stimulus and never a study asset."""
    lead = int(round(lead_silence * samplerate))
    body = int(round(duration * samplerate))
    t = np.arange(body, dtype=np.float64) / samplerate
    wave_f = np.sin(2 * math.pi * freq * t) * amplitude
    # Short fades keep a bench tone from clicking, which would otherwise show up
    # as a spurious energy onset in any later acoustic measurement.
    fade = min(int(0.005 * samplerate), body // 2)
    if fade > 0:
        ramp = np.linspace(0.0, 1.0, fade)
        wave_f[:fade] *= ramp
        wave_f[-fade:] *= ramp[::-1]
    samples = np.zeros((lead + body, channels), np.int16)
    samples[lead:, :] = np.repeat((wave_f * 32767).astype(np.int16)[:, None],
                                  channels, axis=1)
    return _clip_from_array(clip_id, samples, samplerate)


def write_wav(path: str | os.PathLike[str], samples: np.ndarray,
              samplerate: int) -> str:
    """Write int16 PCM and return the SHA-256 of the file."""
    data = np.ascontiguousarray(samples.astype(np.int16))
    if data.ndim == 1:
        data = data.reshape(-1, 1)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(p), "wb") as wav:
        wav.setnchannels(int(data.shape[1]))
        wav.setsampwidth(2)
        wav.setframerate(int(samplerate))
        wav.writeframes(data.tobytes())
    return hashlib.sha256(p.read_bytes()).hexdigest()


# --- backend protocol ---------------------------------------------------------

@dataclass(frozen=True)
class BlockTiming:
    """Timing of one callback's block, in both clock domains.

    ``first_frame_time`` is the controller-domain estimate of when the block's
    first frame reached the ADC (input) or will reach the DAC (output). It is
    read off ``perf_counter`` at callback entry, so it carries scheduling
    jitter - on this PC, callback intervals of 12-40 ms against a 10 ms
    nominal block.

    ``device_time`` is the same instant on PortAudio's own stream clock, which
    does not jitter. Differences between consecutive ``device_time`` values are
    therefore the authoritative inter-block interval, and that is what gap
    detection and the sample/time mapping are built on. It is ``None`` when the
    host API does not report block times.

    ``method`` says which of the two the controller estimate was derived from,
    because the quality of every derived interval depends on it.
    """

    entry_time: float
    first_frame_time: float
    method: str              # "device_time" | "fallback"
    latency_s: float = 0.0
    device_time: float | None = None


InputCallback = Callable[[np.ndarray, BlockTiming, str], None]
OutputCallback = Callable[[np.ndarray, BlockTiming, str], None]


class StreamHandle(Protocol):
    samplerate: float
    blocksize: int
    latency: float

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def close(self) -> None: ...


class Backend(Protocol):
    def open_input(self, *, samplerate: int, channels: int, blocksize: int,
                   device, callback: InputCallback) -> StreamHandle: ...
    def open_output(self, *, samplerate: int, channels: int, blocksize: int,
                    device, callback: OutputCallback) -> StreamHandle: ...


# --- real backend -------------------------------------------------------------

class SoundDeviceBackend:
    """PortAudio backend via ``sounddevice``.

    PortAudio reports block times on its own stream clock. Each callback
    converts that to controller time using the offset between
    ``time.currentTime`` and the ADC/DAC time of this block, measured against a
    ``perf_counter`` reading taken at callback entry. When a host API leaves
    those fields at zero, the conversion falls back to the nominal block
    duration and says so.
    """

    def __init__(self, clock: MonotonicClock | None = None, *,
                 dtype: str = CAPTURE_DTYPE) -> None:
        self.clock = clock or MonotonicClock()
        self.dtype = dtype
        import sounddevice as sd  # noqa: PLC0415 - optional dependency

        self._sd = sd

    def _timing(self, time_info, frames: int, samplerate: float,
                *, output: bool) -> BlockTiming:
        entry = self.clock.now()
        current = float(getattr(time_info, "currentTime", 0.0) or 0.0)
        target = float(getattr(
            time_info,
            "outputBufferDacTime" if output else "inputBufferAdcTime",
            0.0) or 0.0)
        if current > 0.0 and target > 0.0:
            offset = target - current
            return BlockTiming(entry_time=entry, first_frame_time=entry + offset,
                               method="device_time", latency_s=abs(offset),
                               device_time=target)
        nominal = frames / float(samplerate)
        # Without device timestamps: an input block has already been captured,
        # an output block is about to be played. There is no smooth clock to
        # fall back on, so device_time stays None and the consumer widens its
        # tolerances accordingly.
        first = entry + nominal if output else entry - nominal
        return BlockTiming(entry_time=entry, first_frame_time=first,
                           method="fallback", latency_s=nominal,
                           device_time=None)

    def open_input(self, *, samplerate, channels, blocksize, device,
                   callback) -> StreamHandle:
        sd = self._sd

        def _cb(indata, frames, time_info, status):
            timing = self._timing(time_info, frames, samplerate, output=False)
            callback(np.asarray(indata), timing, str(status) if status else "")

        return sd.InputStream(samplerate=samplerate, channels=channels,
                              blocksize=blocksize, device=device,
                              dtype=self.dtype, callback=_cb)

    def open_output(self, *, samplerate, channels, blocksize, device,
                    callback) -> StreamHandle:
        sd = self._sd

        def _cb(outdata, frames, time_info, status):
            timing = self._timing(time_info, frames, samplerate, output=True)
            callback(np.asarray(outdata), timing, str(status) if status else "")

        return sd.OutputStream(samplerate=samplerate, channels=channels,
                               blocksize=blocksize, device=device,
                               dtype=self.dtype, callback=_cb)


# --- fake backend -------------------------------------------------------------

class FakeStream:
    """A stream the test pumps by hand. No device, no thread, no real time."""

    def __init__(self, backend: "FakeBackend", *, samplerate: int, channels: int,
                 blocksize: int, callback, kind: str, latency: float) -> None:
        self.backend = backend
        self.samplerate = float(samplerate)
        self.channels = int(channels)
        self.blocksize = int(blocksize)
        self.latency = float(latency)
        self.kind = kind
        self._callback = callback
        self.active = False
        self.closed = False
        self.blocks = 0
        self.emitted: list[np.ndarray] = []   # output only
        # PortAudio's stream clock: starts at zero and advances by exactly one
        # block per block, regardless of when the callback actually runs.
        self._device_time = 0.0
        # Controller time at device time zero. On the real backend the block's
        # controller-domain time is ``device_time + (entry - currentTime)``,
        # i.e. the device clock plus an epoch offset in which callback
        # lateness cancels out; this models that. Set at start().
        self._epoch: float | None = None

    def start(self) -> None:
        if self.closed:
            raise AudioFault("stream already closed")
        self.active = True
        if self._epoch is None:
            now = self.backend.clock.now()
            # An input block's first frame reached the ADC one latency before
            # the stream clock says so; an output block reaches the DAC one
            # latency after.
            self._epoch = (now - self.latency if self.kind == "input"
                           else now + self.latency)

    def stop(self) -> None:
        self.active = False

    def close(self) -> None:
        self.active = False
        self.closed = True

    # -- test driver

    @property
    def block_s(self) -> float:
        return self.blocksize / self.samplerate

    def pump(self, blocks: int = 1, *, source=None, overflow: bool = False,
             status: str = "", gap_s: float = 0.0, jitter_s: float = 0.0,
             drop: bool = False, method: str = "device_time") -> None:
        """Deliver ``blocks`` callbacks, advancing the manual clock as it goes.

        ``gap_s`` inserts lost device time before the next block, which is how a
        dropped-input-frame case is produced deterministically. ``source`` is
        called as ``source(frames)`` for input streams and must return int16
        samples.

        Use :meth:`FakeBackend.pump_all` when an input and an output stream must
        run together: pumping them in turn would advance the shared clock twice
        per block, which the capture timeline would correctly read as dropped
        input frames.
        """
        clock = self.backend.clock
        for _ in range(blocks):
            if gap_s:
                # Lost device time: the device clock advances but no block is
                # delivered, which is what a dropped block actually looks like.
                clock.advance(gap_s)
                self._device_time += gap_s
                gap_s = 0.0
            if drop:
                # The block exists on the device but never reaches the callback.
                self._device_time += self.block_s
            else:
                self.deliver(source=source, overflow=overflow, status=status,
                             method=method, jitter_s=jitter_s)
            clock.advance(self.block_s)

    def deliver(self, *, source=None, overflow: bool = False, status: str = "",
                method: str = "device_time", jitter_s: float = 0.0) -> None:
        """One callback at the current clock time, without advancing the clock.

        ``jitter_s`` delays only the callback *entry*. In ``device_time`` mode
        that is exactly what the real backend sees: the controller estimate of
        the block is derived from the device clock plus a stable epoch offset,
        so lateness does not reach ``first_frame_time`` at all. In ``fallback``
        mode there is no device clock, the estimate is taken from entry time,
        and the lateness flows straight into it - which is why that basis
        cannot support a tight gap tolerance.
        """
        if not self.active:
            raise AudioFault("pump on an inactive stream")
        clock = self.backend.clock
        block_s = self.block_s
        device_time = self._device_time if method == "device_time" else None
        self._device_time += block_s
        entry = clock.now() + jitter_s
        if self.kind == "input":
            if device_time is not None:
                first = self._epoch + device_time
            else:
                # Fallback: the block just finished arriving, so its first
                # frame is one block in the past, further offset by latency.
                first = entry - block_s - self.latency
            data = (np.zeros((self.blocksize, self.channels), np.int16)
                    if source is None else np.asarray(source(self.blocksize)))
            if data.ndim == 1:
                data = data.reshape(-1, self.channels)
            if data.shape != (self.blocksize, self.channels):
                raise AudioFault(
                    f"source returned {data.shape}, expected "
                    f"{(self.blocksize, self.channels)}")
            timing = BlockTiming(entry, first, method, self.latency,
                                 device_time=device_time)
            self._callback(data.astype(np.int16), timing, status if not overflow
                           else (status or "input overflow"))
        else:
            first = (self._epoch + device_time if device_time is not None
                     else entry + self.latency)
            out = np.zeros((self.blocksize, self.channels), np.int16)
            timing = BlockTiming(entry, first, method, self.latency,
                                 device_time=device_time)
            self._callback(out, timing, status)
            self.emitted.append(out.copy())
        self.blocks += 1

    def emitted_samples(self) -> np.ndarray:
        if not self.emitted:
            return np.zeros((0, self.channels), np.int16)
        return np.concatenate(self.emitted, axis=0)


class FakeBackend:
    """Deterministic backend for tests: a manual clock drives everything."""

    def __init__(self, clock, *, input_latency: float = 0.010,
                 output_latency: float = 0.020) -> None:
        self.clock = clock
        self.input_latency = float(input_latency)
        self.output_latency = float(output_latency)
        self.streams: list[FakeStream] = []

    def pump_all(self, blocks: int = 1, *, sources=None, jitter=None,
                 status: str = "") -> None:
        """Advance every active stream together, one shared block at a time.

        This is what two real callbacks do: they see the same wall clock. The
        per-stream :meth:`FakeStream.pump` advances the clock itself, so calling
        it on two streams in turn would make each one look as if it had lost a
        block.
        """
        sources = sources or {}
        jitter = jitter or {}
        active = [s for s in self.streams if s.active]
        if not active:
            raise AudioFault("no active streams to pump")
        durations = {s.block_s for s in active}
        if len(durations) != 1:
            raise AudioFault(f"streams disagree on block duration: {durations}")
        step = next(iter(durations))
        for _ in range(blocks):
            for stream in active:
                stream.deliver(source=sources.get(stream), status=status,
                               jitter_s=jitter.get(stream, 0.0))
            self.clock.advance(step)

    def open_input(self, *, samplerate, channels, blocksize, device, callback):
        stream = FakeStream(self, samplerate=samplerate, channels=channels,
                            blocksize=blocksize, callback=callback,
                            kind="input", latency=self.input_latency)
        self.streams.append(stream)
        return stream

    def open_output(self, *, samplerate, channels, blocksize, device, callback):
        stream = FakeStream(self, samplerate=samplerate, channels=channels,
                            blocksize=blocksize, callback=callback,
                            kind="output", latency=self.output_latency)
        self.streams.append(stream)
        return stream


# --- incremental sink ---------------------------------------------------------

class WaveSink:
    """Incremental 16-bit PCM writer used by the recorder's writer thread.

    Kept behind a one-method interface so a test can inject a sink that fails
    mid-attempt: "the disk went away while recording" must be exercised, and
    reaching into a live ``wave`` object from the test thread would be a race
    rather than a deterministic check.
    """

    def __init__(self, path: str | os.PathLike[str], *, channels: int,
                 samplerate: int) -> None:
        self.path = Path(path)
        self._wave = wave.open(str(self.path), "wb")
        self._wave.setnchannels(int(channels))
        self._wave.setsampwidth(2)
        self._wave.setframerate(int(samplerate))

    def write(self, data: bytes) -> None:
        self._wave.writeframes(data)

    def close(self) -> None:
        if self._wave is not None:
            try:
                self._wave.close()
            finally:
                self._wave = None


# --- continuous recorder ------------------------------------------------------

@dataclass
class RecordingResult:
    path: str
    frames: int
    samplerate: int
    channels: int
    sha256: str
    finalized: bool
    integrity: dict = field(default_factory=dict)
    faults: list[dict] = field(default_factory=list)

    def as_record(self) -> dict:
        return {
            "path": self.path,
            "frames": self.frames,
            "samplerate": self.samplerate,
            "channels": self.channels,
            "sha256": self.sha256,
            "finalized": self.finalized,
            "duration": self.frames / self.samplerate if self.samplerate else 0.0,
            "integrity": self.integrity,
            "faults": self.faults,
        }


class ContinuousRecorder:
    """One microphone file per attempt, opened before the stimulus plays.

    The audio callback copies bytes into a queue and returns; a writer thread
    does the disk I/O. The file is written as ``<name>.partial`` and renamed on
    :meth:`finalize`, so a crash leaves a detectable incomplete attempt rather
    than a file that looks complete.
    """

    def __init__(self, path: str | os.PathLike[str], *, backend: Backend,
                 clock: MonotonicClock, samplerate: int = CAPTURE_RATE,
                 channels: int = 1, blocksize: int = DEFAULT_BLOCKSIZE,
                 device=None, name: str = "microphone",
                 ledger: TimingLedger | None = None,
                 max_queue_blocks: int = 512,
                 on_fault: Callable[[FaultRecord], None] | None = None,
                 sink_factory: Callable[..., "WaveSink"] = WaveSink) -> None:
        self.path = Path(path)
        self.partial_path = self.path.with_suffix(self.path.suffix + ".partial")
        self.backend = backend
        self.clock = clock
        self.samplerate = int(samplerate)
        self.channels = int(channels)
        self.blocksize = int(blocksize)
        self.device = device
        self.name = name
        self.ledger = ledger
        self.timeline = CaptureTimeline(self.samplerate, name=name)
        self.faults: list[FaultRecord] = []
        self._on_fault = on_fault
        self._queue: queue.Queue = queue.Queue(maxsize=int(max_queue_blocks))
        self._writer: threading.Thread | None = None
        self._stream: StreamHandle | None = None
        self._sink_factory = sink_factory
        self._sink: WaveSink | None = None
        self._lock = threading.Lock()
        self._stopping = threading.Event()
        self._writer_failed = threading.Event()
        self._timing_method: str | None = None
        self.frames_written = 0
        self.dropped_blocks = 0
        self.blocks_received = 0
        self.last_callback_at: float | None = None
        self.started_at: float | None = None
        self.finalized = False

    # -- lifecycle

    def start(self) -> None:
        if self._stream is not None:
            raise AudioFault("recorder already started")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.partial_path.exists():
            raise AudioFault(
                f"{self.partial_path.name} already exists: an earlier attempt "
                "did not finalize; resolve it before recording over it")
        self._sink = self._sink_factory(self.partial_path, channels=self.channels,
                                        samplerate=self.samplerate)
        self._writer = threading.Thread(target=self._drain, name=f"{self.name}-writer",
                                        daemon=True)
        self._writer.start()
        try:
            self._stream = self.backend.open_input(
                samplerate=self.samplerate, channels=self.channels,
                blocksize=self.blocksize, device=self.device,
                callback=self._callback)
            self._stream.start()
        except Exception:
            # The device never opened, so there is no attempt and nothing to
            # publish. Tear the sink down and remove the empty partial file
            # rather than leaving a zero-frame recording to be renamed later.
            self._queue.put(None)
            self._writer.join(timeout=5.0)
            self._writer = None
            with self._lock:
                if self._sink is not None:
                    try:
                        self._sink.close()
                    finally:
                        self._sink = None
            self.partial_path.unlink(missing_ok=True)
            raise
        self.started_at = self.clock.now()
        self._log("recording_started", path=str(self.partial_path),
                  samplerate=self.samplerate, channels=self.channels)

    @property
    def stream(self) -> StreamHandle:
        if self._stream is None:
            raise AudioFault("recorder not started")
        return self._stream

    def _log(self, kind: str, /, **fields) -> None:
        if self.ledger is not None:
            self.ledger.record(kind, at=self.clock.now(), stream=self.name, **fields)

    def _fault(self, kind: str, detail: str, *, fatal: bool = True) -> FaultRecord:
        """Record a fault and notify the controller.

        Audio-thread contract for ``on_fault`` (and for the ledger write
        here): this can run inside the PortAudio callback. The handler must
        not block, take a lock a slow holder might own, do I/O, or raise - it
        should set flags and return; the controller reads ``faults`` and the
        ledger on its own thread. The same applies to ``OutputPlayer``.
        """
        rec = FaultRecord(kind=kind, detail=detail, at=self.clock.now(), fatal=fatal)
        self.faults.append(rec)
        self._log("audio_fault", fault=rec.as_record())
        if self._on_fault is not None:
            try:
                self._on_fault(rec)
            except Exception:  # pragma: no cover - a fault handler must not mask the fault
                pass
        return rec

    # -- audio thread

    def _callback(self, indata: np.ndarray, timing: BlockTiming,
                  status: str) -> None:
        """PortAudio input callback. Must never raise and never touch the disk.

        Nothing here may propagate an exception: sounddevice stops delivering
        blocks after one, which would end the recording silently. Any failure
        becomes a fault record instead.
        """
        try:
            self._callback_body(indata, timing, status)
        except Exception as exc:          # pragma: no cover - defensive net
            self._fault("capture_callback_error",
                        f"{type(exc).__name__}: {exc}")

    def _callback_body(self, indata: np.ndarray, timing: BlockTiming,
                       status: str) -> None:
        frames = int(indata.shape[0])
        overflow = "overflow" in status.lower()
        self.last_callback_at = timing.entry_time
        self.blocks_received += 1

        if self._timing_method is None:
            self._timing_method = timing.method
        elif timing.method != self._timing_method:
            # A host API that changes its time source mid-stream invalidates
            # the basis of every interval measured so far; that is a fault, not
            # a silent downgrade.
            self._fault("block_timing_method_changed",
                        f"{self._timing_method} -> {timing.method}", fatal=False)
            self._timing_method = timing.method

        # The frames must be accepted for writing *before* the timeline counts
        # them. Counting first and dropping afterwards left the timeline
        # claiming frames the file does not contain, which shifted every later
        # sample index earlier in time with no gap recorded at all.
        if self._writer_failed.is_set():
            self.dropped_blocks += 1
            gap = self.timeline.note_not_persisted(
                frames, timing.first_frame_time, kind="writer_failed")
            self._log("capture_gap", gap=gap.as_record())
            return
        try:
            self._queue.put_nowait(indata.astype(np.int16, copy=True).tobytes())
        except queue.Full:
            # Disk cannot keep up. Losing audio is a fault, not a warning: the
            # attempt must be flagged rather than quietly short.
            self.dropped_blocks += 1
            gap = self.timeline.note_not_persisted(
                frames, timing.first_frame_time, kind="recorder_backlog")
            self._fault("recording_queue_full",
                        f"writer backlog full; {frames} frames not persisted")
            self._log("capture_gap", gap=gap.as_record())
            return

        gap = self.timeline.note_block(frames, timing.first_frame_time,
                                       device_time=timing.device_time,
                                       overflowed=overflow, status=status)
        if gap is not None:
            self._log("capture_gap", gap=gap.as_record())
        if overflow:
            self._log("input_overflow", status=status, frames=frames)

    def _drain(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                return
            frames = len(item) // (2 * self.channels)
            try:
                with self._lock:
                    if self._sink is not None:
                        self._sink.write(item)
                        self.frames_written += frames
                        self.timeline.note_persisted(frames)
            except Exception as exc:
                # The writer is done. Flag it so the callback stops counting
                # blocks as written and records them as lost instead.
                self._writer_failed.set()
                self._fault("recording_write_failed",
                            f"{type(exc).__name__}: {exc}")
                return

    # -- shutdown

    def check_liveness(self, now: float, *,
                       max_silence_s: float = 0.5) -> FaultRecord | None:
        """Fault an attempt whose capture callback has stopped arriving.

        A dead input stream is otherwise invisible until finalisation: the
        recorder still reports itself started while the participant speaks into
        nothing. goal.md section 6 requires a trial not to continue while
        recording is broken, so the controller polls this.
        """
        if self._stream is None or self.finalized:
            return None
        last = self.last_callback_at if self.last_callback_at is not None \
            else self.started_at
        if last is None or (now - last) <= max_silence_s:
            return None
        return self._fault(
            "capture_stalled",
            f"no input callback for {now - last:.3f}s "
            f"(limit {max_silence_s:.3f}s)")

    def finalize(self, *, reason: str = "normal") -> RecordingResult:
        """Stop the stream, flush the queue and publish the file.

        Always returns a result: a faulted attempt still yields whatever audio
        was recoverable, which is what the goal requires of finalization.
        """
        if self.finalized:
            raise AudioFault("recorder already finalized")
        self._stopping.set()
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as exc:
                self._fault("stream_close_failed", f"{type(exc).__name__}: {exc}",
                            fatal=False)
        if self._writer is not None:
            self._queue.put(None)
            self._writer.join(timeout=10.0)
            if self._writer.is_alive():
                self._fault("writer_stuck", "writer thread did not exit in 10s",
                            fatal=False)
        with self._lock:
            if self._sink is not None:
                try:
                    self._sink.close()
                except Exception as exc:
                    self._fault("recording_close_failed",
                                f"{type(exc).__name__}: {exc}", fatal=False)
                finally:
                    self._sink = None
        # Reconcile what the device delivered against what reached the file.
        # Blocks already queued when a writer dies are lost after the callback
        # has counted them, so the shortfall is only knowable here.
        shortfall = self.timeline.frames_written - self.timeline.frames_persisted
        if shortfall > 0:
            gap = self.timeline.note_tail_shortfall(shortfall, self.clock.now())
            self._fault("recording_shortfall",
                        f"{shortfall} frames were delivered but never written",
                        fatal=False)
            self._log("capture_gap", gap=gap.as_record())

        published = self.partial_path
        finalized = False
        if self.partial_path.exists():
            try:
                os.replace(self.partial_path, self.path)
                published = self.path
                finalized = True
            except Exception as exc:
                self._fault("recording_publish_failed",
                            f"{type(exc).__name__}: {exc}", fatal=False)
        digest = (hashlib.sha256(published.read_bytes()).hexdigest()
                  if published.exists() else "")
        if self.frames_written == 0:
            self._fault("recording_empty",
                        "the attempt finalized with no frames on disk",
                        fatal=False)
        self.finalized = True
        self._log("recording_finalized", path=str(published), reason=reason,
                  frames=self.frames_written, finalized=finalized)
        return RecordingResult(
            path=str(published),
            frames=self.frames_written,
            samplerate=self.samplerate,
            channels=self.channels,
            sha256=digest,
            finalized=finalized,
            integrity=self.timeline.integrity(),
            faults=[f.as_record() for f in self.faults],
        )


# --- output player ------------------------------------------------------------

_IDLE = "idle"
_PLAYING = "playing"

#: Outcomes of a cancellation request. A bare boolean conflated "nothing was
#: armed" with "too late, it is already audible", and the controller's
#: one-prompt allowance depends on telling those apart: only a committed
#: prompt consumes it.
CANCEL_REMOVED = "removed"                    # taken out before commitment
CANCEL_ALREADY_CANCELLED = "already_cancelled"  # a guard veto got there first
CANCEL_TOO_LATE = "too_late_committed"        # committed; allowance consumed
CANCEL_NOTHING_ARMED = "nothing_armed"        # no candidate in this attempt


@dataclass(frozen=True)
class CancelOutcome:
    """What a cancellation request actually did."""

    outcome: str
    candidate: PromptCandidate | None = None
    reason: str = ""

    @property
    def removed(self) -> bool:
        """True only when this call took an uncommitted clip out of the queue."""
        return self.outcome == CANCEL_REMOVED

    @property
    def allowance_consumed(self) -> bool:
        """Whether the trial's single encouragement has been spent.

        Only commitment spends it. A guard veto, a pre-commit cancellation and
        an empty slot all leave it intact, so the controller rearms from the
        next detected speech offset.
        """
        return self.outcome == CANCEL_TOO_LATE

    @property
    def spoke(self) -> bool:
        return self.outcome == CANCEL_TOO_LATE

    def as_record(self) -> dict:
        return {
            "outcome": self.outcome,
            "reason": self.reason,
            "allowance_consumed": self.allowance_consumed,
            "candidate": None if self.candidate is None else self.candidate.as_record(),
        }


class OutputPlayer:
    """Session-long output stream with a deadline-gated prompt slot.

    The stream stays open and emits silence when nothing is playing, so the
    device buffer depth is the same at the moment a prompt commits as it was
    during calibration.

    Commitment happens inside the audio callback, under the player lock, and
    only when (a) controller time has reached the deadline and (b) a guard
    supplied by the controller still returns ``None``. That guard is where
    Stop, fault, completion and timeout keep their precedence over an eligible
    encouragement (goal.md section 6). Before that instant
    :meth:`cancel_candidate` removes the clip and nothing is heard; after it,
    the allowance is spent even if the participant resumes speaking before the
    first sample is audible.
    """

    def __init__(self, *, backend: Backend, clock: MonotonicClock,
                 samplerate: int = CAPTURE_RATE, channels: int = 1,
                 blocksize: int = DEFAULT_BLOCKSIZE, device=None,
                 ledger: TimingLedger | None = None,
                 on_fault: Callable[[FaultRecord], None] | None = None) -> None:
        self.backend = backend
        self.clock = clock
        self.samplerate = int(samplerate)
        self.channels = int(channels)
        self.blocksize = int(blocksize)
        self.device = device
        self.ledger = ledger
        self._on_fault = on_fault
        self._lock = threading.RLock()
        self._stream: StreamHandle | None = None
        self.state = _IDLE
        self.generation = 0
        self.faults: list[FaultRecord] = []

        self._clip: Clip | None = None
        self._ended_reason: str | None = None
        self._playing_candidate: PromptCandidate | None = None
        self._pos = 0                      # frames of the active clip emitted
        self._started_at: float | None = None   # audible time of clip frame 0
        self._last_block: BlockTiming | None = None
        self._finished: list[dict] = []

        self._candidate: PromptCandidate | None = None
        self._candidate_clip: Clip | None = None
        self._committed: PromptCandidate | None = None
        self._vetoed: PromptCandidate | None = None
        self._guard: Callable[[], str | None] | None = None
        self.attempt: str | None = None
        self.underruns = 0

    # -- lifecycle

    def open(self) -> None:
        if self._stream is not None:
            raise AudioFault("output already open")
        self._stream = self.backend.open_output(
            samplerate=self.samplerate, channels=self.channels,
            blocksize=self.blocksize, device=self.device, callback=self._callback)
        self._stream.start()
        self._log("output_opened", samplerate=self.samplerate,
                  blocksize=self.blocksize,
                  latency_s=float(getattr(self._stream, "latency", 0.0) or 0.0))

    def close(self) -> None:
        with self._lock:
            stream, self._stream = self._stream, None
            self._clip = None
            self._candidate = None
            self._candidate_clip = None
            self.state = _IDLE
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception as exc:
                self._fault("output_close_failed", f"{type(exc).__name__}: {exc}",
                            fatal=False)
        self._log("output_closed")

    @property
    def stream(self) -> StreamHandle:
        if self._stream is None:
            raise AudioFault("output not open")
        return self._stream

    @property
    def latency_s(self) -> float:
        """Device output latency actually reported by the open stream."""
        if self._stream is None:
            return 0.0
        value = getattr(self._stream, "latency", 0.0)
        if isinstance(value, (tuple, list)):
            value = value[-1]
        return float(value or 0.0)

    def _log(self, kind: str, /, **fields) -> dict | None:
        if self.ledger is None:
            return None
        return self.ledger.record(kind, at=self.clock.now(), **fields)

    def _fault(self, kind: str, detail: str, *, fatal: bool = True) -> FaultRecord:
        rec = FaultRecord(kind=kind, detail=detail, at=self.clock.now(), fatal=fatal)
        self.faults.append(rec)
        self._log("audio_fault", fault=rec.as_record())
        if self._on_fault is not None:
            try:
                self._on_fault(rec)
            except Exception:  # pragma: no cover
                pass
        return rec

    def _check_clip(self, clip: Clip) -> None:
        if clip.samplerate != self.samplerate:
            raise AudioFault(
                f"clip {clip.clip_id}: {clip.samplerate} Hz does not match the "
                f"output stream at {self.samplerate} Hz; the released trial "
                "plays manifest-pinned audio and does not resample it")
        if clip.channels != self.channels:
            raise AudioFault(
                f"clip {clip.clip_id}: {clip.channels} channels does not match "
                f"the output stream's {self.channels}")

    def begin_attempt(self, attempt: str) -> None:
        """Scope the prompt slot to one trial attempt.

        The output stream lives for the whole session (D2), so without this the
        prompt bookkeeping would be session-scoped: a prompt committed in trial
        one would make trial five report a "too late" deviation naming trial
        one's candidate. Every attempt starts with an empty, unspent slot.
        """
        with self._lock:
            if self._candidate is not None and not (
                    self._candidate.cancelled or self._candidate.committed):
                raise AudioFault(
                    "cannot begin a new attempt with a prompt still armed")
            self.attempt = attempt
            self._candidate = None
            self._candidate_clip = None
            self._committed = None
            self._vetoed = None
            self._guard = None
        self._log("attempt_began", attempt=attempt)

    # -- immediate playback (story, instruction, bench tone)

    def _require_attempt(self, what: str) -> None:
        """Per-attempt scoping is not optional.

        C4's fix lives in ``begin_attempt``; a controller that forgot to call
        it would silently inherit the previous trial's prompt bookkeeping
        (R03-F07). So the slot cannot be used outside an attempt.
        """
        if self.attempt is None:
            raise AudioFault(
                f"cannot {what}: no attempt has begun; call begin_attempt() first")

    def play(self, clip: Clip, *, kind: str = "stimulus") -> int:
        """Start a clip at the next callback. Returns its generation number."""
        self._check_clip(clip)
        self._require_attempt("play")
        with self._lock:
            if self.state == _PLAYING:
                raise AudioFault(
                    f"output busy with {self._clip.clip_id if self._clip else '?'}")
            if self._candidate is not None and not self._candidate.cancelled:
                raise AudioFault("a prompt candidate is armed; cancel it first")
            self.generation += 1
            self._clip = clip
            self._pos = 0
            self._started_at = None
            self._ended_reason = None
            self.state = _PLAYING
            gen = self.generation
        self._log("output_play_requested", clip=clip.as_record(), purpose=kind,
                  generation=gen)
        return gen

    # -- deadline-gated prompt

    def arm(self, clip: Clip, candidate: PromptCandidate, *,
            guard: Callable[[], str | None] | None = None) -> PromptCandidate:
        """Queue the encouragement to commit at or after ``candidate.deadline``.

        Nothing is placed in the device buffer until a callback observes that
        controller time has reached the deadline, which keeps the no-early-
        trigger requirement structural rather than a matter of timer accuracy.
        """
        self._check_clip(clip)
        self._require_attempt("arm")
        if candidate.trial_id != self.attempt:
            raise AudioFault(
                f"candidate belongs to {candidate.trial_id!r} but the current "
                f"attempt is {self.attempt!r}")
        with self._lock:
            if self.state == _PLAYING:
                raise AudioFault("cannot arm a prompt while output is playing")
            if self._candidate is not None and not (
                    self._candidate.cancelled or self._candidate.committed):
                raise AudioFault("a prompt candidate is already armed")
            self._candidate = candidate
            self._candidate_clip = clip
            self._guard = guard
        self._log("prompt_armed", candidate=candidate.as_record(),
                  clip=clip.as_record())
        return candidate

    def cancel_candidate(self, reason: str) -> CancelOutcome:
        """Try to take an armed prompt out of the queue before it is audible.

        Every branch is logged, including the no-op, and the returned outcome
        says whether the trial's one encouragement has been consumed. Only a
        committed prompt consumes it: a guard veto or a pre-commit cancellation
        leaves the allowance intact and the controller rearms from the next
        detected speech offset (goal.md section 6).
        """
        with self._lock:
            cand = self._candidate
            vetoed = self._vetoed
            committed = self._committed
            if cand is not None:
                if cand.cancel(self.clock.now(), reason):
                    self._candidate = None
                    self._candidate_clip = None
                    self._guard = None
                    result = CancelOutcome(CANCEL_REMOVED, cand, reason)
                else:
                    result = CancelOutcome(
                        CANCEL_TOO_LATE if cand.committed
                        else CANCEL_ALREADY_CANCELLED, cand, reason)
            elif committed is not None and committed.committed:
                result = CancelOutcome(CANCEL_TOO_LATE, committed, reason)
            elif vetoed is not None:
                result = CancelOutcome(CANCEL_ALREADY_CANCELLED, vetoed, reason)
            else:
                result = CancelOutcome(CANCEL_NOTHING_ARMED, None, reason)
        self._log({
            CANCEL_REMOVED: "prompt_cancelled",
            CANCEL_TOO_LATE: "prompt_cancel_too_late",
            CANCEL_ALREADY_CANCELLED: "prompt_cancel_already_cancelled",
            CANCEL_NOTHING_ARMED: "prompt_cancel_nothing_armed",
        }[result.outcome], **result.as_record())
        return result

    @property
    def candidate(self) -> PromptCandidate | None:
        return self._candidate

    @property
    def committed_candidate(self) -> PromptCandidate | None:
        """The prompt that reached the device buffer, if any.

        Kept after the clip ends so the controller can report the consumed
        allowance and any overlap with resumed speech.
        """
        return self._committed

    def stop(self, reason: str = "stop") -> dict:
        """Halt output immediately and drop any armed candidate."""
        with self._lock:
            cand = self._candidate
            removed = False
            if cand is not None and not cand.committed:
                removed = cand.cancel(self.clock.now(), reason)
            clip_id = self._clip.clip_id if self._clip else None
            played = self._pos
            self._clip = None
            self._candidate = None
            self._candidate_clip = None
            self._guard = None
            self._pos = 0
            self._started_at = None
            self._ended_reason = reason
            self.state = _IDLE
            self.generation += 1
            # Only true when what was actually playing is this attempt's
            # committed prompt, not merely that some prompt committed earlier.
            interrupted = (self._playing_candidate is not None
                           and clip_id is not None)
            self._playing_candidate = None
        rec = {"reason": reason, "clip_id": clip_id, "frames_played": played,
               "candidate_removed": removed,
               "interrupted_committed_prompt": interrupted}
        self._log("output_stopped", **rec)
        return rec

    # -- audio thread

    def _callback(self, outdata: np.ndarray, timing: BlockTiming, status: str) -> None:
        frames = int(outdata.shape[0])
        outdata[:] = 0
        with self._lock:
            self._last_block = timing
            if status:
                lowered = status.lower()
                if "underflow" in lowered or "underrun" in lowered:
                    self.underruns += 1
                    self._fault("output_underrun", status, fatal=False)

            if self._clip is None and self._candidate is not None:
                self._maybe_commit(timing)

            clip = self._clip
            if clip is None:
                return
            if self._started_at is None:
                self._started_at = timing.first_frame_time
            take = min(frames, clip.frames - self._pos)
            if take > 0:
                outdata[:take] = clip.samples[self._pos:self._pos + take]
                self._pos += take
            if self._pos >= clip.frames:
                # The clip is done. Record it and go idle; the renderer's
                # external-clock track has no end event of its own, so the
                # position snapshot must flip to not-playing here.
                self._finished.append({
                    "clip_id": clip.clip_id,
                    "frames": clip.frames,
                    "generation": self.generation,
                    "end_block_time": timing.first_frame_time + take / self.samplerate,
                })
                self._clip = None
                self._playing_candidate = None
                self._pos = 0
                self._started_at = None
                self._ended_reason = "clip_end"
                self.state = _IDLE

    def _maybe_commit(self, timing: BlockTiming) -> None:
        """Commit the armed prompt if the deadline has passed and guards allow.

        Called with the lock held, from the audio thread. The guard must be
        non-blocking: it reads already-decided controller flags.
        """
        cand = self._candidate
        clip = self._candidate_clip
        if cand is None or clip is None or cand.cancelled or cand.committed:
            return
        now = timing.entry_time
        if now < cand.deadline:
            return
        if self._guard is not None:
            try:
                veto = self._guard()
            except Exception as exc:  # a broken guard must not speak
                veto = f"guard_error:{type(exc).__name__}"
            if veto:
                cand.cancel(now, veto)
                self._candidate = None
                self._candidate_clip = None
                self._guard = None
                # Remembered so a controller cancellation arriving in the same
                # instant is reported as "already cancelled, allowance intact"
                # rather than as an empty slot.
                self._vetoed = cand
                self._log("prompt_vetoed_at_commit", reason=veto, removed=True,
                          candidate=cand.as_record())
                return
        # Three separable quantities, never collapsed into one number:
        #   commit_delay   = now - deadline           (scheduling)
        #   device_offset  = buffer time - now        (device latency)
        #   clip lead      = silence inside the file  (a property of the asset)
        # An earlier version folded the clip lead into the estimate, which with
        # a silent probe clip inflated every reported onset by the clip length.
        device_offset = timing.first_frame_time - now
        lead = clip.leading_silence_s
        # Two estimators of the device latency exist and were seen to disagree
        # by ~12 ms on WASAPI: the stream's reported latency and the per-block
        # DAC offset. The recorded half-width must cover that disagreement,
        # not just the block quantisation (R03-F10a). Both readings travel in
        # the record so the calibration can later say which was right.
        reported = self.latency_s
        disagreement = abs(reported - device_offset) if reported else 0.0
        uncertainty = max(self.blocksize / self.samplerate, disagreement)
        lead = clip.leading_silence_s
        onset: Estimate | None = None
        if lead is not None:
            onset = Estimate(
                seconds=timing.first_frame_time + lead,
                method=ESTIMATED,
                uncertainty_s=uncertainty,
                source=f"device_latency:{timing.method};"
                       f"reported={reported:.4f};per_block={device_offset:.4f}",
            )
        self._ended_reason = None
        cand.commit(now, onset)
        cand.device_offset_s = device_offset
        cand.clip_leading_silence_s = lead
        self._committed = cand
        self._playing_candidate = cand
        self.generation += 1
        self._clip = clip
        self._pos = 0
        self._started_at = None
        self.state = _PLAYING
        self._candidate = None
        self._candidate_clip = None
        self._guard = None
        self._log("prompt_committed",
                  audible_onset=onset,
                  buffer_time=timing.first_frame_time,
                  device_offset_s=device_offset,
                  reported_latency_s=reported,
                  latency_disagreement_s=disagreement,
                  leading_silence_s=lead,
                  clip_has_audible_onset=clip.has_audible_onset,
                  timing_method=timing.method, candidate=cand.as_record())

    # -- renderer clock

    def position(self) -> PlaybackPosition:
        """Current audible position for ``playTrack``'s ``getTime``.

        ``file_time`` counts from the start of the complete WAV, including its
        leading silence, because the mouth track is indexed in file time.
        """
        with self._lock:
            clip = self._clip
            now = self.clock.now()
            if clip is None or self._started_at is None:
                return PlaybackPosition(file_time=0.0, controller_time=now,
                                        rate=0.0, playing=False, duration=0.0,
                                        generation=self.generation,
                                        ended_reason=self._ended_reason)
            # Frames handed to the device become audible at _started_at onward;
            # what is audible *now* is bounded by both the clip length and how
            # much has actually been written.
            audible = now - self._started_at
            written = self._pos / self.samplerate
            file_time = max(0.0, min(audible, written, clip.duration))
            # Frames already handed to the device are not audible until they
            # clear its buffer. While that is still ahead of us the audible
            # position is pinned at zero, and a consumer extrapolating from
            # this snapshot has to know not to advance through it.
            pre_roll = max(0.0, self._started_at - now)
            return PlaybackPosition(file_time=file_time, controller_time=now,
                                    rate=1.0, playing=True,
                                    duration=clip.duration,
                                    generation=self.generation,
                                    pre_roll_s=pre_roll)

    @property
    def finished(self) -> list[dict]:
        return list(self._finished)
