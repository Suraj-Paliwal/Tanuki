#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tanuki TTS server - type Japanese, hear it, watch the tanuki say it.

    pip install edge-tts pykakasi        # recommended
    python tanuki_tts_server.py
    -> open http://localhost:8080

One dependency-light stdlib server. It synthesises speech, measures the clip's
real duration, builds a viseme track fitted to that duration, and hands both to
the page.

TTS backends, tried in order unless you force one with --tts:

  voicevox  a local VOICEVOX engine on :50021. Best Japanese character voices.
  edge      edge-tts. Free, no API key, very good ja-JP voices. Needs internet.
  gtts      Google Translate TTS. Free, needs internet, flatter delivery.
  offline   the formant synthesiser from jp_synth.py. Robotic, but it always
            works - useful for wiring things up on a plane.

Why the duration matters: mora timing is an estimate. Measuring the audio and
passing `total` makes the mouth land exactly on the end of the clip instead of
drifting a few hundred milliseconds by the end of a sentence.
"""
import argparse, hashlib, json, mimetypes, os, re, subprocess, sys, threading, urllib.request
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
# Serve this folder. Everything the page needs - model, textures, JS, the
# Japanese pipeline - lives inside it, so 06_web can be copied into a project
# whole and still work.
ROOT = HERE

def _find_pipeline():
    """Locate the lip-sync modules. Checked rather than assumed so the script
    still runs if it has been moved out of 06_web/."""
    for c in (os.path.join(HERE, "lib"),
              os.path.join(HERE, "..", "04_pipeline"),
              os.path.join(HERE, "04_pipeline"),
              os.path.join(HERE, "pipeline"),
              HERE):
        if os.path.exists(os.path.join(c, "jp_lipsync.py")):
            return c
    sys.exit("could not find jp_lipsync.py - run this from inside the Tanuki folder")

PIPELINE = _find_pipeline()
sys.path.insert(0, PIPELINE)

from jp_lipsync import build as build_track                # noqa: E402
from jp_kana import to_hiragana                            # noqa: E402

MEDIA = os.path.join(HERE, ".media")
os.makedirs(MEDIA, exist_ok=True)

# --------------------------------------------------------------------------- #
#  kanji
# --------------------------------------------------------------------------- #
_KANJI = re.compile(r"[一-鿿]")
_kks = None

def to_kana(text):
    """The viseme generator works on kana. Convert kanji if pykakasi is here."""
    if not _KANJI.search(text):
        return to_hiragana(text)
    global _kks
    try:
        if _kks is None:
            import pykakasi
            _kks = pykakasi.kakasi()
        return "".join(w["hira"] for w in _kks.convert(text))
    except Exception:
        # Without pykakasi the kanji are simply dropped by the mora parser,
        # so the mouth would fall silent over them. Say so rather than
        # producing a track that quietly doesn't match the audio.
        raise RuntimeError(
            "text contains kanji and pykakasi is not installed "
            "(pip install pykakasi), or pass kana/romaji instead"
        )

# --------------------------------------------------------------------------- #
#  TTS backends
# --------------------------------------------------------------------------- #
VOICEVOX_URL = os.getenv("VOICEVOX_URL", "http://127.0.0.1:50021")

def _have_voicevox():
    try:
        urllib.request.urlopen(VOICEVOX_URL + "/version", timeout=1.0).read()
        return True
    except Exception:
        return False

def tts_voicevox(text, path, voice="1", **kw):
    speaker = str(voice or "1")
    q = urllib.request.Request(
        f"{VOICEVOX_URL}/audio_query?speaker={speaker}&text={urllib.parse.quote(text)}",
        method="POST")
    query = json.loads(urllib.request.urlopen(q, timeout=30).read())
    r = urllib.request.Request(
        f"{VOICEVOX_URL}/synthesis?speaker={speaker}",
        data=json.dumps(query).encode(), method="POST",
        headers={"Content-Type": "application/json"})
    with open(path, "wb") as f:
        f.write(urllib.request.urlopen(r, timeout=60).read())
    return "wav"

def tts_edge(text, path, voice="ja-JP-NanamiNeural", rate="+0%", **kw):
    import asyncio, edge_tts
    async def go():
        await edge_tts.Communicate(text, voice, rate=rate).save(path)
    asyncio.run(go())
    return "mp3"

def tts_gtts(text, path, **kw):
    from gtts import gTTS
    gTTS(text=text, lang="ja").save(path)
    return "mp3"

def tts_offline(text, path, **kw):
    """No network, no model - the formant synthesiser written to test the
    audio path. It sounds like a robot; it is here so nothing ever hard-fails."""
    from jp_synth import synth, write_wav
    y, sr = synth(text)
    write_wav(path, y, sr)
    return "wav"

BACKENDS = {
    "voicevox": (tts_voicevox, "wav"),
    "edge":     (tts_edge,     "mp3"),
    "gtts":     (tts_gtts,     "mp3"),
    "offline":  (tts_offline,  "wav"),
}

def pick_backend(pref="auto"):
    if pref != "auto":
        return pref
    if _have_voicevox():
        return "voicevox"
    try:
        import edge_tts  # noqa: F401
        return "edge"
    except ImportError:
        pass
    try:
        import gtts  # noqa: F401
        return "gtts"
    except ImportError:
        pass
    return "offline"

# --------------------------------------------------------------------------- #
#  duration
# --------------------------------------------------------------------------- #
def speech_span(path, floor_db=-40.0, pad=0.03):
    """Where the speech actually starts and ends inside the clip.

    Every TTS engine pads its output with silence - typically 150-300 ms at the
    front and more at the back. Fitting the viseme track to the whole clip
    stretches the mouth over that silence: a 1.43 s phrase spread across a 2.0 s
    file runs 40% too slow, and the error accumulates, so the mouth is visibly
    behind by the end of a sentence. That is the lag.

    Returns (start, end) in seconds, or None if the analysis is unavailable.
    """
    try:
        from audio_lipsync import decode
        import numpy as np
        x = decode(path)
        sr = 16000
        n_win, n_hop = int(0.025 * sr), int(0.010 * sr)
        if len(x) < n_win:
            return None
        rms = np.array([np.sqrt(np.mean(x[i:i+n_win] ** 2)) + 1e-12
                        for i in range(0, len(x) - n_win, n_hop)])
        db = 20 * np.log10(rms / max(rms.max(), 1e-12))
        on = np.nonzero(db > floor_db)[0]
        if len(on) < 2:
            return None
        t0 = max(0.0, on[0] * 0.010 - pad)
        t1 = min(len(x) / sr, on[-1] * 0.010 + 0.025 + pad)
        return (float(t0), float(t1)) if t1 - t0 > 0.05 else None
    except Exception:
        return None


def shift_track(track, dt):
    """Move every keyframe later by dt, and hold the mouth shut before it."""
    for v, keys in track["tracks"].items():
        for k in keys:
            k[0] = round(k[0] + dt, 4)
        if dt > 0:
            keys.insert(0, [0.0, 0.0])
    return track


def duration_of(path):
    """Measure the clip. ffprobe first, then a wav header, then give up."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=20)
        d = float(out.stdout.strip())
        if d > 0:
            return d
    except Exception:
        pass
    if path.lower().endswith(".wav"):
        try:
            import wave
            with wave.open(path) as w:
                return w.getnframes() / float(w.getframerate())
        except Exception:
            pass
    return None

# --------------------------------------------------------------------------- #
#  the one interesting function
# --------------------------------------------------------------------------- #
def say(text, engine="auto", voice=None, rate="+0%", blink=True, intensity=1.0,
        trim=True):
    kana = to_kana(text)
    name = pick_backend(engine)
    fn, ext = BACKENDS[name]
    key = hashlib.sha1(f"{name}|{voice}|{rate}|{text}".encode()).hexdigest()[:16]
    path = os.path.join(MEDIA, f"{key}.{ext}")

    if not os.path.exists(path) or os.path.getsize(path) == 0:
        # Real engines read kanji and pick the right readings themselves, so
        # they get the original text. The offline formant synth only knows
        # kana - hand it the converted string or it silently skips the kanji
        # and produces a clip far shorter than the sentence.
        spoken = kana if name == "offline" else text
        got = fn(spoken, path, voice=voice, rate=rate)
        if got != ext:
            os.rename(path, os.path.join(MEDIA, f"{key}.{got}"))
            path = os.path.join(MEDIA, f"{key}.{got}")

    dur = duration_of(path)
    # Fit the mouth to the SPEECH, not to the file. Mora timing alone is an
    # estimate; fitting it to a clip that is part silence is worse than not
    # fitting it at all.
    span = speech_span(path) if trim else None
    if span:
        t0, t1 = span
        track = build_track(kana, total=t1 - t0, intensity=intensity,
                            blink=blink, fps=30)
        shift_track(track, t0)
        track["duration"] = round(dur or t1, 4)
    else:
        track = build_track(kana, total=dur, intensity=intensity,
                            blink=blink, fps=30)
    return {
        "engine": name,
        "voice": voice,
        "kana": kana,
        "duration": dur or track["duration"],
        "speech": [round(span[0], 3), round(span[1], 3)] if span else None,
        "audio": "/media/" + os.path.basename(path),
        "track": track,
    }

# --------------------------------------------------------------------------- #
#  HTTP
# --------------------------------------------------------------------------- #
class Handler(SimpleHTTPRequestHandler):
    engine = "auto"
    default_voice = None
    # Keep-alive. With HTTP/1.0 the browser reopens a connection per request,
    # and while the 19 MB GLB is streaming the small /api calls beside it can
    # be left waiting long enough to look like the server is down.
    protocol_version = "HTTP/1.1"

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, fmt, *args):
        if "/api/" in (self.path or ""):
            sys.stderr.write("  %s\n" % (fmt % args))

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.end_headers()

    def do_GET(self):
        p = urlparse(self.path).path
        if p in ("/", "/index.html"):
            self.send_response(302)
            self.send_header("Location", "/chatbot.html")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if p == "/api/status":
            return self._json({"engine": pick_backend(self.engine),
                               "voicevox": _have_voicevox(),
                               "root": ROOT})
        if p.startswith("/media/"):
            f = os.path.join(MEDIA, os.path.basename(p))
            if not os.path.exists(f):
                return self._json({"error": "not found"}, 404)
            ctype = mimetypes.guess_type(f)[0] or "application/octet-stream"
            data = open(f, "rb").read()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
            return
        return super().do_GET()

    def do_POST(self):
        if urlparse(self.path).path != "/api/say":
            return self._json({"error": "unknown endpoint"}, 404)
        n = int(self.headers.get("Content-Length", 0))
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._json({"error": "bad json"}, 400)
        text = (req.get("text") or "").strip()
        if not text:
            return self._json({"error": "text is empty"}, 400)
        try:
            out = say(text,
                      engine=req.get("engine") or self.engine,
                      voice=req.get("voice") or self.default_voice,
                      rate=req.get("rate", "+0%"),
                      blink=req.get("blink", True),
                      intensity=float(req.get("intensity", 1.0)),
                      trim=req.get("trim", True))
        except Exception as e:
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)
        return self._json(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--tts", default="auto",
                    choices=["auto", "voicevox", "edge", "gtts", "offline"])
    ap.add_argument("--voice", default=None,
                    help="edge: ja-JP-NanamiNeural / ja-JP-KeitaNeural ; voicevox: speaker id")
    ap.add_argument("--say", default=None, help="synthesise one line and exit")
    a = ap.parse_args()

    Handler.engine = a.tts
    Handler.default_voice = a.voice

    if a.say:
        out = say(a.say, engine=a.tts, voice=a.voice)
        out_small = {k: v for k, v in out.items() if k != "track"}
        out_small["track_keys"] = {k: len(v) for k, v in out["track"]["tracks"].items()}
        print(json.dumps(out_small, ensure_ascii=False, indent=1))
        return

    chosen = pick_backend(a.tts)
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print(f"\n  tanuki  →  http://{a.host}:{a.port}/   (chatbot)")
    print(f"             http://{a.host}:{a.port}/player.html   (tuning bench)")
    print(f"  tts engine: {chosen}"
          + ("   (install edge-tts for a real voice)" if chosen == "offline" else ""))
    print(f"  serving:    {ROOT}\n  pipeline:   {PIPELINE}\n  ctrl-c to stop\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  bye")


if __name__ == "__main__":
    main()
