# -*- coding: utf-8 -*-
"""Exact viseme timing from VOICEVOX's own phoneme durations.

Everywhere else in this project the mouth timing is ESTIMATED - every mora gets
the same beat - and then corrected after the fact by warping the track onto the
recording's energy envelope. That works with any engine, and it took the
measured correlation from 0.686 to 0.881. It is still an inference.

VOICEVOX does not require the inference. Its /audio_query endpoint returns the
exact plan it is about to synthesise: every mora, its consonant and vowel, and
how long each will last. Reading that is ground truth, not an estimate - the
mouth is driven by the same numbers that generated the sound.

    accent_phrases: [
      { moras: [ {text, consonant, consonant_length, vowel, vowel_length, pitch} ],
        accent: int, pause_mora: {...} | null, is_interrogative: bool }
    ],
    speedScale, prePhonemeLength, postPhonemeLength, ...

The vowel field carries more than identity. VOICEVOX writes a DEVOICED vowel in
upper case - the /u/ of です comes back as "U", not "u" - which is exactly the
distinction jp_lipsync has to guess at from the surrounding consonants. And
"N" (ん), "cl" (っ) and "pau" are marked as themselves rather than having to be
inferred from kana.

The lengths are believed to be in seconds, but nothing here assumes that:
`track_from_query` reports the total it computed, and the caller compares it
against the real duration of the audio and falls back to the estimating path if
they disagree. Never trust an undocumented unit; check it against the artifact.
"""

import math

VISEMES = ["A", "I", "U", "E", "O"]
V_OF = {"a": "A", "i": "I", "u": "U", "e": "E", "o": "O"}

# Lips have to be together before these, so the mouth must be shut through the
# consonant rather than already open on the vowel.
BILABIAL = {"m", "b", "p", "my", "by", "py"}

DEVOICED_W = 0.90      # retain the lip shape even when vocal-fold activity drops
BLEND = 0.025          # short blends; hold the identifiable vowel in between


def _moras(query):
    """Flatten the query into (consonant, consonant_len, vowel, vowel_len)."""
    out = []
    for ph in query.get("accent_phrases") or []:
        for m in ph.get("moras") or []:
            out.append((m.get("consonant"), float(m.get("consonant_length") or 0.0),
                        m.get("vowel") or "", float(m.get("vowel_length") or 0.0)))
        pm = ph.get("pause_mora")
        if pm:
            out.append((None, 0.0, "pau", float(pm.get("vowel_length") or 0.0)))
    return out


def track_from_query(query, intensity=1.0, fps=30, blink=False, blink_seed=0):
    """AudioQuery -> viseme track. Returns (track, total_seconds) or (None, 0)."""
    ms = _moras(query)
    if not ms:
        return None, 0.0

    speed = float(query.get("speedScale", 1.0))
    pre = float(query.get("prePhonemeLength") or 0.0)
    post = float(query.get("postPhonemeLength") or 0.0)
    # API-compatible engines can return dummy zero durations. Their presence
    # is not evidence of phoneme timing, even if padding matches a short clip.
    if (not math.isfinite(speed) or speed <= 0
            or any(not math.isfinite(x) or x < 0 for x in (pre, post))
            or any(not math.isfinite(c) or not math.isfinite(v) or c < 0 or v < 0
                   or (name.lower() in V_OF and v <= 0)
                   for _, c, name, v in ms)
            or not any(name.lower() in V_OF and v > 0 for _, _, name, v in ms)):
        return None, 0.0
    t = pre / speed

    ev = [(0.0, None, 0.0), (t, None, 0.0)]
    previous = (None, 0.0)
    for cons, clen, vowel, vlen in ms:
        clen, vlen = clen / speed, vlen / speed
        if cons and cons.lower() in BILABIAL:
            # hold the lips shut for the closure itself
            ev.append((t, None, 0.0))
            ev.append((t + clen, None, 0.0))
            previous = (None, 0.0)
        elif clen > 0:
            # Keep the previous pose until a short transition into the vowel;
            # long consonants must not stretch the crossfade over a whole mora.
            ev.append((max(t, t + clen - BLEND), *previous))
        t += clen
        v = vowel
        if v in ("pau", "cl", "N", "n"):
            # a beat with no vowel: silence, the sokuon's held closure, or ん
            ev.append((t, None, 0.0))
            ev.append((t + vlen, None, 0.0))
            previous = (None, 0.0)
        elif v.lower() in V_OF:
            w = intensity * (DEVOICED_W if v.isupper() else 1.0)
            blend = min(BLEND, vlen * 0.2)
            previous = (V_OF[v.lower()], round(w, 3))
            ev.append((t + blend, *previous))
            ev.append((t + vlen - blend, *previous))
        t += vlen
    # Close at the speech boundary and hold through the engine's trailing
    # padding. Previously the final vowel faded throughout that silence.
    ev.append((t, None, 0.0))
    t += post / speed
    ev.append((t, None, 0.0))
    ev.sort(key=lambda e: e[0])

    from jp_lipsync import tracks, blink_track
    tr = tracks(ev)
    out = {"duration": round(t, 4), "fps": fps, "visemes": VISEMES,
           "tracks": tr, "source": "voicevox"}
    if blink:
        tr["Blink"] = blink_track(t, blink_seed)
        out["extras"] = ["Blink"]
    return out, t


def kana_of(query):
    """The reading VOICEVOX chose, for display. Katakana, as it returns it."""
    parts = []
    for ph in query.get("accent_phrases") or []:
        parts.append("".join(m.get("text", "") for m in ph.get("moras") or []))
        if ph.get("pause_mora"):
            parts.append("、")
    return "".join(parts)
