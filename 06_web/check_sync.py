#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Measure lip-sync accuracy on YOUR voice engine.

    python check_sync.py                      # uses whichever engine is available
    python check_sync.py --tts edge --voice ja-JP-NanamiNeural

For each test phrase it synthesises the audio, builds the viseme track, and
reports how well the mouth matches the recording's own energy envelope -
before and after the track is warped onto the audio's rhythm.

Correlation is the number to watch. Roughly:

    < 0.2   the mouth is not tracking the speech
    0.3-0.5 normal for a real voice; the mouth follows the phrase
    > 0.6   tight

The offline formant synth scores high on the "before" column and gains little,
because it was generated from the same uniform mora model the track assumes -
it agrees with itself. A real TTS voice does not, which is where the alignment
earns its keep. Run this with edge-tts or VOICEVOX to see the real numbers.
"""
import argparse, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PHRASES = [
    "こんにちは、たぬきです",
    "きょうはいいてんきですね",
    "ありがとうございます",
    "しゃべってみましょう、いっしょに",
    "がんばってください",
]

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tts", default="auto",
                   choices=["auto", "voicevox", "edge", "gtts", "offline"])
    p.add_argument("--voice", default=None)
    p.add_argument("--phrases", nargs="*", default=PHRASES)
    a = p.parse_args()

    import numpy as np
    import tanuki_tts_server as S
    import align as A

    engine = S.pick_backend(a.tts)
    print(f"\n  engine: {engine}\n")
    print(f"  {'phrase':<26} {'dur':>6} {'uniform':>8} {'aligned':>8} {'lag ms':>7}")
    print("  " + "-" * 60)

    gains = []
    for text in a.phrases:
        try:
            out = S.say(text, engine=a.tts, voice=a.voice, align=False)
        except Exception as e:
            print(f"  {text[:24]:<26} failed: {type(e).__name__}: {e}")
            continue
        path = os.path.join(S.MEDIA, os.path.basename(out["audio"]))
        env = A.envelope(path)
        before = A.predicted(out["track"], len(env))
        aligned, rep = A.align(out["track"], path)
        after = A.predicted(aligned, len(env))

        def corr(m):
            return 0.0 if m.std() < 1e-9 or env.std() < 1e-9 else float(np.corrcoef(m, env)[0, 1])
        def lag(m):
            mm = m - m.mean(); ee = env - env.mean()
            c = np.correlate(mm, ee, "full")
            return (int(np.argmax(c)) - (len(ee) - 1)) * A.HOP * 1000

        cb, ca = corr(before), corr(after)
        gains.append(ca - cb)
        # A cross-correlation peak is meaningless when the curves barely match:
        # on a nearly all-vowel phrase it lands anywhere and reports a full
        # second of lag that is not real. Only quote it once there is a match.
        lag_s = f"{lag(after):>+7.0f}" if ca > 0.25 else "      -"
        print(f"  {text[:24]:<26} {out['duration']:>5.2f}s {cb:>8.3f} {ca:>8.3f} {lag_s}")

    if gains:
        print("  " + "-" * 60)
        print(f"  mean gain from alignment: {sum(gains)/len(gains):+.3f}\n")
        print("  'lag ms' is how far the mouth sits from the audio after aligning.")
        print("  Anything inside +/-45 ms is below the threshold most people can see")
        print("  (ITU-R BT.1359). Negative means the mouth is early, which is the")
        print("  safer direction - the tolerance for a late mouth is much tighter.\n")

if __name__ == "__main__":
    main()
