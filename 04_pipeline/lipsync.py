# -*- coding: utf-8 -*-
"""Tanuki Japanese lip-sync - command line entry point.

  # from Japanese text (kana or romaji)
  python lipsync.py --text "こんにちは、たぬきです" --out track.json

  # fit a phrase to a known duration
  python lipsync.py --text "ありがとう" --total 1.2 --out track.json

  # from a recording
  python lipsync.py --audio voice.wav --out track.json

  # inspect what it decided
  python lipsync.py --text "こんにちは" --preview
"""
import argparse, json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    p = argparse.ArgumentParser(description="Generate viseme tracks for the tanuki rig")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--text",  help="Japanese text: hiragana, katakana or romaji (not kanji)")
    g.add_argument("--audio", help="audio file; any format ffmpeg can read")
    p.add_argument("--out", help="write the track as JSON")
    p.add_argument("--mora", type=float, default=0.135, help="seconds per mora (text mode)")
    p.add_argument("--total", type=float, help="fit the phrase to this many seconds")
    p.add_argument("--intensity", type=float, default=1.0, help="0-1, how far the mouth opens")
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--preview", action="store_true", help="print the track as a timeline")
    p.add_argument("--blink", action="store_true", help="add an idle Blink track")
    p.add_argument("--blink-seed", type=int, default=0)
    a = p.parse_args()

    if a.text:
        from jp_lipsync import build
        data = build(a.text, mora_dur=a.mora, total=a.total,
                     intensity=a.intensity, fps=a.fps,
                     blink=a.blink, blink_seed=a.blink_seed)
    else:
        from audio_lipsync import analyse, to_tracks
        data = to_tracks(analyse(a.audio))
        data["source"] = a.audio
        if a.blink:
            from jp_lipsync import blink_track
            data["tracks"]["Blink"] = blink_track(data["duration"], a.blink_seed)
            data["extras"] = ["Blink"]

    if a.preview:
        from jp_lipsync import sample, VISEMES
        step = 1.0 / min(a.fps, 20)
        t = 0.0
        while t <= data["duration"]:
            s = sample(data["tracks"], t)
            row = "".join(f"{v}{'#' * int(s[v] * 8):<9}" if s[v] > 0.06 else " " * 10
                          for v in VISEMES)
            print(f"{t:5.2f}s  {row.rstrip() or '(closed)'}")
            t += step
    if a.out:
        json.dump(data, open(a.out, "w"), ensure_ascii=False, indent=1)
        print(f"wrote {a.out}  ({data['duration']:.2f}s)", file=sys.stderr)
    elif not a.preview:
        json.dump(data, sys.stdout, ensure_ascii=False)

if __name__ == "__main__":
    main()
