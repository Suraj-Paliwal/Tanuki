# -*- coding: utf-8 -*-
"""Japanese text -> viseme keyframes for the tanuki's A/I/U/E/O morph targets."""
import json
from jp_kana import moras

VISEMES = ["A", "I", "U", "E", "O"]
V_OF = {"a": "A", "i": "I", "u": "U", "e": "E", "o": "O"}

# Japanese is mora-timed: every mora takes roughly the same beat, unlike the
# stress-timed rhythm of English. One duration per mora is therefore a much
# better first approximation here than it would be for English.
MORA = 0.135
BLEND = 0.025      # brief transitions leave the vowel's actual shape visible

def plan(text, mora_dur=MORA, total=None, intensity=1.0):
    ms = moras(text)
    if not ms:
        return [], 0.0
    if total:
        beats = sum(1.0 if m.kind != "pause" else 0.6 for m in ms)
        mora_dur = total / max(beats, 1e-6)
    ev = [(0.0, None, 0.0)]
    t = 0.0
    for i, m in enumerate(ms):
        d = mora_dur * (0.6 if m.kind == "pause" else 1.0)
        if m.kind == "pause":
            ev.append((t, None, 0.0)); ev.append((t + d, None, 0.0))
        elif m.kind == "stop":
            # sokuon: the mouth holds the shape of the coming consonant, closed
            ev.append((t, None, 0.0)); ev.append((t + d, None, 0.0))
        elif m.kind == "nasal":
            # ん is a beat with the lips together or nearly so
            ev.append((t, None, 0.0)); ev.append((t + d, None, 0.0))
        else:
            w = intensity
            if m.kind == "long":
                w *= 0.95                      # a held vowel, not a new attack
            # Text alone does not establish whether /i/ or /u/ is devoiced.
            # Keep its recognisable mouth shape: vocal-fold activity is not
            # equivalent to morph-target strength, especially for rounded U.
            attack = min(BLEND, d * 0.2)
            if m.bilabial:
                # lips must physically meet before /m/, /b/, /p/
                ev.append((t, None, 0.0))
                closure_end = t + d * 0.22
                ev.append((closure_end, None, 0.0))
                attack += closure_end - t
            # A single peak per mora crossfaded for the entire syllable, so
            # most frames showed an in-between mouth instead of A/I/U/E/O.
            ev.append((t + attack, V_OF[m.vowel], round(w, 3)))
            ev.append((t + d - min(BLEND, d * 0.2), V_OF[m.vowel], round(w, 3)))
        t += d
    ev.append((t, None, 0.0))
    ev.sort(key=lambda e: e[0])
    return ev, t

def tracks(events):
    """Events -> one sparse keyframe list per viseme.

    At every event exactly one viseme is driven and the rest are pinned to 0,
    so a linear interpolator crossfades cleanly instead of stacking two open
    mouths on top of each other."""
    tr = {v: [] for v in VISEMES}
    for t, name, w in events:
        for v in VISEMES:
            tr[v].append([round(max(t, 0.0), 4), round(w if v == name else 0.0, 4)])
    for v in tr:                                  # drop redundant flat keys
        out = []
        for k in tr[v]:
            if len(out) >= 2 and out[-1][1] == k[1] and out[-2][1] == k[1]:
                out[-1] = k
            else:
                out.append(k)
        tr[v] = out
    return tr

def blink_track(duration, seed=0, first=0.35, gap=(2.2, 5.5),
                down=0.055, hold=0.030, up=0.075):
    """Idle blinks: keyframes for the Blink morph.

    A blink is fast down, a short hold, and a slower opening - symmetric
    timing reads as a twitch. Spacing is randomised because a perfectly
    regular blink is one of the clearest tells that something is animated
    rather than alive.
    """
    import random
    rng = random.Random(seed)
    keys, t = [[0.0, 0.0]], first
    while t < duration - (down + hold + up):
        keys += [[round(t, 4), 0.0],
                 [round(t + down, 4), 1.0],
                 [round(t + down + hold, 4), 1.0],
                 [round(t + down + hold + up, 4), 0.0]]
        t += rng.uniform(*gap)
    keys.append([round(max(duration, keys[-1][0]), 4), 0.0])
    return keys

def build(text, mora_dur=MORA, total=None, intensity=1.0, fps=30,
          blink=False, blink_seed=0):
    ev, dur = plan(text, mora_dur, total, intensity)
    tr = tracks(ev)
    out = {"text": text, "duration": round(dur, 4), "fps": fps,
           "visemes": VISEMES, "tracks": tr,
           "moras": [m.kana for m in moras(text)]}
    if blink:
        tr["Blink"] = blink_track(dur, blink_seed)
        out["extras"] = ["Blink"]
    return out

def sample(tr, t):
    """Linear interpolation, for previewing a track without an engine."""
    out = {}
    for v, ks in tr.items():
        if t <= ks[0][0]: out[v] = ks[0][1]; continue
        if t >= ks[-1][0]: out[v] = ks[-1][1]; continue
        for i in range(1, len(ks)):
            if ks[i][0] >= t:
                (t0, w0), (t1, w1) = ks[i-1], ks[i]
                f = 0 if t1 == t0 else (t - t0) / (t1 - t0)
                out[v] = w0 + (w1 - w0) * f
                break
    return out

if __name__ == "__main__":
    import sys
    txt = sys.argv[1] if len(sys.argv) > 1 else "こんにちは、たぬきです"
    d = build(txt)
    print(json.dumps(d, ensure_ascii=False, indent=1)[:1200])
