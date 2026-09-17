# -*- coding: utf-8 -*-
"""Warp a viseme track onto the rhythm of the actual audio.

The mora model assumes every mora takes the same beat. Real speech does not:
TTS engines stretch phrase-final morae, compress unstressed ones, and pause at
commas for however long they feel like. Fitting a uniform track to the clip's
duration only fixes the average - the mouth still drifts inside the sentence
and snaps back at the end.

So instead of guessing the timing, take it from the audio. Both signals say the
same thing in different units: the track predicts how open the mouth should be,
and the recording's energy envelope shows how open it actually was. Dynamic
time warping finds the monotonic mapping between them, and the track is
retimed along that path.

This needs no model and no calibration - it works with any TTS voice, any
language the mora parser handles, and adapts per utterance.
"""
import numpy as np

FRAME, HOP = 0.025, 0.010


def frame_db(x, sr=16000):
    """Per-frame energy in dB, relative to the loudest frame.

    This is the one measurement the server needs from the audio, and both
    things that consume it - the silence trim and the alignment - want exactly
    the same frames. Computing it once and passing the array around removes a
    whole decode + analysis pass per request.
    """
    n_win, n_hop = int(FRAME * sr), int(HOP * sr)
    if len(x) < n_win:
        return np.zeros(1)
    # sliding window instead of a Python loop over frames
    win = np.lib.stride_tricks.sliding_window_view(x, n_win)[::n_hop]
    rms = np.sqrt((win * win).mean(axis=1)) + 1e-12
    return 20 * np.log10(rms / max(rms.max(), 1e-12))


def envelope_from_db(db):
    """dB -> 0..1 with a -45 dB floor."""
    return np.clip((db + 45.0) / 45.0, 0, 1)


def envelope(path, sr=16000, x=None):
    """Speech energy over time, normalised to 0..1 at `HOP` resolution."""
    if x is None:
        from audio_lipsync import decode
        x = decode(path, sr)
    return envelope_from_db(frame_db(x, sr))


def predicted(track, n_frames):
    """How open the track says the mouth should be, on the same time grid."""
    from jp_lipsync import sample, VISEMES
    out = np.zeros(n_frames)
    for i in range(n_frames):
        s = sample(track["tracks"], i * HOP)
        out[i] = min(1.0, sum(s.get(v, 0.0) for v in VISEMES))
    return out


def _dtw_path(a, b, band=0.25):
    """Monotonic alignment of a onto b.

    Constrained to a Sakoe-Chiba band: without it, DTW happily maps a whole
    phrase onto one loud syllable, which is a perfect score and a useless
    result. The band caps how far the warp can wander from the diagonal.
    """
    na, nb = len(a), len(b)
    w = max(int(band * max(na, nb)), 10)
    INF = 1e18
    D = np.full((na + 1, nb + 1), INF)
    D[0, 0] = 0.0
    cost = np.abs(a[:, None] - b[None, :])
    for i in range(1, na + 1):
        lo = max(1, int((i - 1) * nb / na) - w)
        hi = min(nb, int((i - 1) * nb / na) + w) + 1
        c = cost[i - 1, lo - 1:hi - 1]
        prev = np.minimum(np.minimum(D[i - 1, lo - 1:hi - 1], D[i - 1, lo:hi]),
                          D[i, lo - 1:hi - 1])
        # D[i, lo:hi] depends on D[i, lo-1:hi-1] within the same row, so the
        # row has to be filled left to right rather than vectorised outright.
        for k in range(lo, hi):
            j = k - lo
            best = min(D[i - 1, k - 1], D[i - 1, k], D[i, k - 1])
            D[i, k] = c[j] + best
    # backtrack
    i, j, path = na, nb, []
    while i > 0 and j > 0:
        path.append((i - 1, j - 1))
        step = np.argmin([D[i - 1, j - 1], D[i - 1, j], D[i, j - 1]])
        if step == 0: i, j = i - 1, j - 1
        elif step == 1: i -= 1
        else: j -= 1
    return path[::-1]


def align(track, audio_path=None, band=0.25, strength=1.0, min_corr=0.15,
          env=None):
    """Retime `track` onto the rhythm of `audio_path`.

    `strength` blends between the original timing (0) and the warped one (1).
    If the alignment does not improve the correlation it is discarded - a bad
    warp is worse than uniform timing, and a track can fail to align for honest
    reasons like a voice that whispers a whole clause.
    Returns (track, report).
    """
    if env is None:
        env = envelope(audio_path)
    # Nothing meaningful to warp in a very short clip, and DTW is the most
    # expensive step here - skip it rather than spend 50 ms proving it.
    if len(env) < 40:
        return track, {"aligned": False, "reason": "clip too short to align"}
    pred = predicted(track, len(env))
    if env.std() < 1e-6 or pred.std() < 1e-6:
        return track, {"aligned": False, "reason": "flat signal"}

    before = float(np.corrcoef(pred, env)[0, 1])
    path = _dtw_path(pred, env, band)
    # path maps predicted-frame -> audio-frame; make it a function of time
    pi = np.array([p[0] for p in path], float)
    ai = np.array([p[1] for p in path], float)
    # collapse duplicates so np.interp gets a strictly increasing x
    keep = np.concatenate([[True], np.diff(pi) > 0])
    pi, ai = pi[keep], ai[keep]

    def remap(t):
        f = t / HOP
        g = np.interp(f, pi, ai)
        return float((g * (1 - 0) * strength + f * (1 - strength)) * HOP)

    warped = {"duration": track["duration"], "fps": track.get("fps", 30),
              "visemes": track.get("visemes"), "tracks": {}}
    for v, keys in track["tracks"].items():
        warped["tracks"][v] = [[round(remap(t), 4), w] for t, w in keys]
        warped["tracks"][v].sort(key=lambda k: k[0])

    after = float(np.corrcoef(predicted(warped, len(env)), env)[0, 1])
    if after < before or after < min_corr:
        return track, {"aligned": False, "before": round(before, 3),
                       "after": round(after, 3), "reason": "no improvement"}
    for k in ("visemes",):
        if warped[k] is None: warped.pop(k)
    return warped, {"aligned": True, "before": round(before, 3),
                    "after": round(after, 3)}
