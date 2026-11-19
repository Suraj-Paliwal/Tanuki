"""Record a real OutputPlayer position trace for the JS adapter tests.

    python tools/make_position_trace.py

Writes `tests/fixtures/position_trace.json`.

Why this exists. The browser adapter and the controller are two
implementations of one contract: the controller publishes
`timing.PlaybackPosition` snapshots, and the adapter extrapolates between them
to drive the mouth. Hand-writing fixtures on both sides would verify each
against its author's assumptions rather than against each other.

So this drives the actual `OutputPlayer` on the fake backend, samples its
position every 10 ms of playback, and emits a trace in which only every fifth
sample is *delivered* to the adapter. The remaining four are assertions: the
adapter has to extrapolate to them, and the expected value is the controller's
own position at that instant - ground truth from the Python side, not the
adapter's formula restated. If the two drift apart, the JS test fails.

Frame 0 is sampled before any callback (the clip-starting snapshot) and the
assertion window runs through the audible tail of the clip, so both ends of
the clip are inside the cross-check.

No device is opened and nothing is recorded.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audio_io import (  # noqa: E402
    CAPTURE_RATE,
    DEFAULT_BLOCKSIZE,
    FakeBackend,
    OutputPlayer,
    tone_clip,
)
from timing import ManualClock  # noqa: E402

RATE = CAPTURE_RATE
BLOCK = DEFAULT_BLOCKSIZE
BLOCK_MS = BLOCK / RATE * 1000.0
#: Deliver one snapshot in this many samples; the rest are assertions the
#: adapter must reach by extrapolating.
DELIVER_EVERY = 5


FIXTURE = (Path(__file__).resolve().parents[1] / "tests" / "fixtures"
           / "position_trace.json")


def render(trace: dict) -> str:
    """The exact bytes written to the fixture.

    ``tests/test_timing.py`` regenerates the trace and compares it with the
    committed file through this function, so a code change that alters what
    the controller publishes fails the suite until the fixture is regenerated
    (R05-F07): the fixture is a standing guard, not a one-time discovery.
    """
    return json.dumps(trace, indent=2, ensure_ascii=False) + "\n"


def build_trace(clip_s: float = 0.40, lead_s: float = 0.05,
                output_latency: float = 0.020) -> dict:
    clock = ManualClock(0.0)
    backend = FakeBackend(clock, output_latency=output_latency)
    player = OutputPlayer(backend=backend, clock=clock, samplerate=RATE,
                          blocksize=BLOCK)
    player.open()
    stream = backend.streams[-1]
    player.begin_attempt("trace")

    clip = tone_clip(clip_s, lead_silence=lead_s, samplerate=RATE,
                     clip_id="trace-clip")
    player.play(clip, kind="instruction")

    frames: list[dict] = []
    expect_stops: list[str] = []
    # Frame 0 is sampled the instant play() returns, before any callback has
    # carried the clip: the moment a publisher naturally takes its first
    # snapshot. The controller used to publish that as "not playing", which
    # the adapter read as a stop for the whole clip (R05-F05), and a trace
    # that pumped before its first sample could not see it.
    pending = player.position().as_record()
    frames.append({"advance_ms": 0.0, "snapshot": pending,
                   "expect_file_time": round(pending["file_time"], 9)})
    # Enough blocks to cover the clip, its audible tail (one output latency
    # after the last block is written) and a few idle blocks after that.
    blocks = int(round((clip_s + lead_s + output_latency)
                       / (BLOCK / RATE))) + 4
    for i in range(1, blocks + 1):
        stream.pump(1)
        position = player.position()
        record = position.as_record()
        frame: dict = {"advance_ms": round(BLOCK_MS, 6)}
        if i % DELIVER_EVERY == 0:
            frame["snapshot"] = record
        # The controller's own position at this instant is the expectation.
        # While it is playing - which now includes the audible tail after the
        # last block is written (R05-F06) - the adapter must match it; once
        # the controller reports stopped, the adapter holds its last position
        # instead, so only the playing frames are asserted.
        if record["playing"]:
            frame["expect_file_time"] = round(record["file_time"], 9)
        frames.append(frame)

    # One final snapshot carrying playing=False, which is the only clip-end
    # signal an externally clocked track ever receives.
    final = player.position().as_record()
    frames.append({"advance_ms": 0.0, "snapshot": final})
    if not final["playing"]:
        # Read the reason the controller states rather than re-deriving it:
        # the point of the trace is to check the two sides agree on what the
        # controller publishes.
        expect_stops.append(
            "clip_end" if final["ended_reason"] == "clip_end" else "requested")

    player.close()
    delivered = sum(1 for f in frames if "snapshot" in f)
    asserted = sum(1 for f in frames if "expect_file_time" in f)
    return {
        "$comment": [
            "Generated by tools/make_position_trace.py from a real",
            "audio_io.OutputPlayer on the fake backend. Do not hand-edit:",
            "regenerate it, so the fixture keeps describing what the",
            "controller actually publishes.",
            "",
            f"Only every {DELIVER_EVERY}th sample is delivered as a snapshot;",
            "the rest are positions the JS adapter must reach by",
            "extrapolating, with the controller's own position as the",
            "expected value.",
        ],
        "generated_by": "tools/make_position_trace.py",
        "clip": clip.as_record(),
        "output_latency_s": output_latency,
        "block_ms": BLOCK_MS,
        "deliver_every": DELIVER_EVERY,
        "delivered_snapshots": delivered,
        "asserted_frames": asserted,
        "expect_stops": expect_stops,
        "frames": frames,
    }


def main() -> int:
    trace = build_trace()
    out = FIXTURE
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(trace), encoding="utf-8")
    print(f"wrote {out}")
    print(f"  {len(trace['frames'])} frames, "
          f"{trace['delivered_snapshots']} snapshots delivered, "
          f"{trace['asserted_frames']} positions asserted")
    print(f"  expected stops: {trace['expect_stops'] or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
