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
# Several engines speak VOICEVOX's HTTP API, and they are not equally good.
# They are tried in this order, first one that answers wins:
#
#   aivis      AivisSpeech - Style-Bert-VITS2 models behind a VOICEVOX-shaped
#              API. The most natural-sounding of the family. LGPL-3.0.
#   voicevox   VOICEVOX itself. Reliable, and its phoneme durations are real.
#   coeiroink / sharevox   same API family again.
#
# The one that matters downstream is /audio_query, because that is where the
# exact mora timing comes from. Whether a given engine's durations are REAL or
# just plausible-looking is checked against the audio it produced, in say() -
# so a new engine can be tried here without any risk of silently desyncing the
# mouth.
VV_ENGINES = [
    ("aivis",     "http://127.0.0.1:10101"),
    ("voicevox",  "http://127.0.0.1:50021"),
    ("coeiroink", "http://127.0.0.1:50032"),
    ("sharevox",  "http://127.0.0.1:50025"),
]
_ENV_VV = os.getenv("VOICEVOX_URL")
if _ENV_VV:
    VV_ENGINES = [("custom", _ENV_VV)] + VV_ENGINES

VOICEVOX_URL = VV_ENGINES[0][1]      # replaced by whichever answers
_vv_found = None                     # (name, url), cached for the process


def _find_vv(recheck=False):
    """First VOICEVOX-compatible engine that answers. Cached: this runs on
    every /api/status and we do not want four connection attempts each time."""
    global _vv_found, VOICEVOX_URL
    if _vv_found is not None and not recheck:
        return _vv_found
    for name, url in VV_ENGINES:
        try:
            urllib.request.urlopen(url + "/version", timeout=0.6).read()
            _vv_found = (name, url)
            VOICEVOX_URL = url
            return _vv_found
        except Exception:
            continue
    _vv_found = ()
    return _vv_found


def _have_voicevox():
    return bool(_find_vv())

# Per-engine default voices. These live here, not only in the signatures
# below, because a default argument does NOT apply when the caller passes the
# parameter explicitly as None - and that is exactly what happens when a page
# posts no "voice" field. Every backend coerces instead of relying on defaults.
VOICEVOX_SPEAKER = "1"
EDGE_VOICE       = "ja-JP-NanamiNeural"
DEFAULT_RATE     = "+0%"

def tts_voicevox(text, path, voice=VOICEVOX_SPEAKER, **kw):
    speaker = str(voice or VOICEVOX_SPEAKER)
    found = _find_vv()
    base = found[1] if found else VOICEVOX_URL
    q = urllib.request.Request(
        f"{base}/audio_query?speaker={speaker}&text={urllib.parse.quote(text)}",
        method="POST")
    query = json.loads(urllib.request.urlopen(q, timeout=30).read())
    r = urllib.request.Request(
        f"{base}/synthesis?speaker={speaker}",
        data=json.dumps(query).encode(), method="POST",
        headers={"Content-Type": "application/json"})
    with open(path, "wb") as f:
        f.write(urllib.request.urlopen(r, timeout=60).read())
    # Keep the query. It is not metadata - it is the exact plan the engine just
    # synthesised, mora by mora, with the duration of every consonant and
    # vowel. Estimating the timing and then warping it onto the audio is what
    # you do when you cannot have this.
    try:
        with open(os.path.splitext(path)[0] + ".query.json", "w",
                  encoding="utf-8") as f:
            json.dump(query, f, ensure_ascii=False)
    except OSError:
        pass
    return "wav"

def tts_edge(text, path, voice=EDGE_VOICE, rate=DEFAULT_RATE, **kw):
    import asyncio, edge_tts
    # edge_tts type-checks both of these and raises "TypeError: voice must be
    # str" on None. chatbot.html posts {text, blink} and no voice, so the
    # server filled it with its own default of None and handed that straight
    # through - the default in the signature above never got a chance.
    voice = voice or EDGE_VOICE
    rate = rate or DEFAULT_RATE
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

EDGE_VOICES = [
    {"id": "ja-JP-NanamiNeural", "name": "Nanami", "style": "female"},
    {"id": "ja-JP-KeitaNeural",  "name": "Keita",  "style": "male"},
    {"id": "ja-JP-AoiNeural",    "name": "Aoi",    "style": "female"},
    {"id": "ja-JP-DaichiNeural", "name": "Daichi", "style": "male"},
    {"id": "ja-JP-MayuNeural",   "name": "Mayu",   "style": "female"},
    {"id": "ja-JP-NaokiNeural",  "name": "Naoki",  "style": "male"},
    {"id": "ja-JP-ShioriNeural", "name": "Shiori", "style": "female"},
]


def list_voices(engine=None):
    """Every voice the active engine can produce, so a speaker id can be
    PINNED. A voice is only stable if you name it: the default is whatever the
    engine calls speaker 1, and that is not the same character across engines.
    """
    name = pick_backend(engine or "auto")
    if name == "voicevox":
        found = _find_vv()
        if not found:
            return name, []
        out = []
        try:
            data = json.loads(urllib.request.urlopen(
                found[1] + "/speakers", timeout=5).read())
            for sp in data:
                for st in sp.get("styles", []):
                    out.append({"id": str(st.get("id")),
                                "name": sp.get("name", "?"),
                                "style": st.get("name", "")})
        except Exception as e:
            sys.stderr.write(f"  [voices] {e}\n")
        return found[0], out
    if name == "edge":
        return name, EDGE_VOICES
    return name, []


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
def speech_span(path=None, floor_db=-40.0, pad=0.03, db=None, n_samples=None):
    """Where the speech actually starts and ends inside the clip.

    Every TTS engine pads its output with silence - typically 150-300 ms at the
    front and more at the back. Fitting the viseme track to the whole clip
    stretches the mouth over that silence: a 1.43 s phrase spread across a 2.0 s
    file runs 40% too slow, and the error accumulates, so the mouth is visibly
    behind by the end of a sentence. That is the lag.

    Returns (start, end) in seconds, or None if the analysis is unavailable.
    """
    try:
        import numpy as np
        from align import frame_db
        sr = 16000
        if db is None:
            from audio_lipsync import decode
            x = decode(path)
            db = frame_db(x, sr)
            n_samples = len(x)
        if n_samples is None or len(db) < 2:
            return None
        on = np.nonzero(db > floor_db)[0]
        if len(on) < 2:
            return None
        t0 = max(0.0, on[0] * 0.010 - pad)
        t1 = min(n_samples / sr, on[-1] * 0.010 + 0.025 + pad)
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


def wav_duration(path):
    """Duration straight from the WAV header - no process, no decode."""
    if not path.lower().endswith(".wav"):
        return None
    try:
        import wave
        with wave.open(path) as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return None


def analyse(path):
    """Decode the clip ONCE and return everything downstream needs.

    Before this, a single request decoded the same file three times through
    three separate processes: ffprobe for the duration, ffmpeg for the silence
    trim, ffmpeg again for the alignment envelope. Measured at ~145 ms of pure
    process-spawn and re-decode per request on Linux, and worse on Windows
    where creating a process costs more.

    Returns (duration_seconds, frame_db_array, sample_count) or (None,)*3.
    """
    try:
        from audio_lipsync import decode
        from align import frame_db
        x = decode(path)                     # 16 kHz mono
        if len(x) < 8:
            return None, None, None
        return len(x) / 16000.0, frame_db(x, 16000), len(x)
    except Exception:
        return duration_of(path), None, None


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
FALLBACK_ORDER = ["voicevox", "edge", "gtts", "offline"]

def _synthesise(name, text, kana, voice, rate):
    """Run one backend and return the path it wrote. Raises on failure."""
    fn, ext = BACKENDS[name]
    # Offline speech uses the same kana parser; parser fixes can change the
    # spoken sequence even if the original input string is unchanged.
    key_source = f"{name}|{voice}|{rate}|{text}"
    if name == "offline":
        key_source += f"|{TRACK_CACHE_VERSION}"
    key = hashlib.sha1(key_source.encode()).hexdigest()[:16]
    path = os.path.join(MEDIA, f"{key}.{ext}")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    # Real engines read kanji and pick the right readings themselves, so they
    # get the original text. The offline formant synth only knows kana - hand
    # it the converted string or it silently skips the kanji and produces a
    # clip far shorter than the sentence.
    spoken = kana if name == "offline" else text
    try:
        got = fn(spoken, path, voice=voice, rate=rate)
    except Exception:
        # A backend that died halfway can leave a truncated file behind, and
        # the size check above would then serve that corpse forever.
        for f in (path,) + tuple(os.path.join(MEDIA, f"{key}.{e}")
                                 for _, e in BACKENDS.values()):
            try:
                if os.path.exists(f) and os.path.getsize(f) < 512:
                    os.remove(f)
            except OSError:
                pass
        raise
    if got != ext:
        newp = os.path.join(MEDIA, f"{key}.{got}")
        os.rename(path, newp)
        path = newp
    return path


def _chain(name, engine):
    """Which backends to try, in order. An explicit --tts choice is honoured
    exactly; only "auto" is allowed to fall back."""
    if engine != "auto":
        return [name]
    out = [name]
    for n in FALLBACK_ORDER:
        if n == name:
            continue
        # Don't queue voicevox unless it is actually up - its HTTP timeout is
        # 30 s, which would turn every fallback into a half-minute stall.
        if n == "voicevox" and not _have_voicevox():
            continue
        out.append(n)
    return out


_RESP_CACHE = {}                       # key -> serialised response
_RESP_LOCK = threading.Lock()
# Timing and mouth-shape changes must not reuse an older persisted track.
TRACK_CACHE_VERSION = "vowel-holds-2"

def _resp_key(text, engine, voice, rate, blink, intensity, trim, align):
    raw = f"{TRACK_CACHE_VERSION}|{engine}|{voice}|{rate}|{blink}|{intensity}|{trim}|{align}|{text}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _cache_get(key):
    """A repeated line should cost nothing.

    The audio file was already cached, but everything downstream of it -
    probing, decoding, building the track, the DTW pass - was redone on every
    request, so saying the same greeting twice cost the same as the first time.
    """
    with _RESP_LOCK:
        hit = _RESP_CACHE.get(key)
    if hit is None:
        f = os.path.join(MEDIA, key + ".resp.json")
        if not os.path.exists(f):
            return None
        try:
            hit = open(f, encoding="utf-8").read()
        except OSError:
            return None
        with _RESP_LOCK:
            _RESP_CACHE[key] = hit
    try:
        out = json.loads(hit)               # fresh copy: callers may mutate
    except ValueError:
        return None
    # the audio may have been cleared out from under us
    name = os.path.basename(out.get("audio", ""))
    if not name or not os.path.exists(os.path.join(MEDIA, name)):
        return None
    out["cached"] = True
    return out


def _cache_put(key, out):
    blob = json.dumps(out, ensure_ascii=False)
    with _RESP_LOCK:
        _RESP_CACHE[key] = blob
    try:
        with open(os.path.join(MEDIA, key + ".resp.json"), "w",
                  encoding="utf-8") as f:
            f.write(blob)                   # survives a server restart too
    except OSError:
        pass


def say(text, engine="auto", voice=None, rate=DEFAULT_RATE, blink=True,
        intensity=1.0, trim=True, align=True):
    rate = rate or DEFAULT_RATE
    ck = _resp_key(text, engine, voice, rate, blink, intensity, trim, align)
    hit = _cache_get(ck)
    if hit is not None:
        return hit

    kana = to_kana(text)
    name = pick_backend(engine)

    # If the chosen engine throws - no network, a bad voice name, an upstream
    # 403 - drop to the next one rather than failing the whole reply. `offline`
    # needs nothing at all, so this chain always terminates in a voice. The
    # failure is reported back in `fallback_from`, not swallowed.
    chain = _chain(name, engine)
    path, fell_back = None, None
    for i, cand in enumerate(chain):
        try:
            path = _synthesise(cand, text, kana, voice, rate)
            if i:
                fell_back = {"from": name, "error": fell_back}
                name = cand
            break
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            sys.stderr.write(f"  [tts] {cand} failed: {err}\n")
            if i == 0:
                fell_back = err
            if cand == chain[-1]:
                raise

    # ── exact timing, when the engine will tell us ────────────────────────
    # VOICEVOX hands back the phoneme durations it used. Believe them only
    # after checking their total against the audio that actually came out -
    # the units are not documented, and an assumption that silently drifts is
    # worse than the estimate it replaced.
    #
    # This runs BEFORE the decode, because when it succeeds there is nothing
    # left to measure: no ffmpeg, no envelope, no DTW. A VOICEVOX request costs
    # a WAV header read and a dictionary walk.
    qf = os.path.splitext(path)[0] + ".query.json"
    if os.path.exists(qf):
        try:
            from vv_timing import track_from_query, kana_of
            with open(qf, encoding="utf-8") as f:
                query = json.load(f)
            wdur = wav_duration(path)
            exact, total = track_from_query(query, intensity=intensity,
                                            blink=blink, fps=30)
            if exact and wdur and abs(total - wdur) <= 0.2 * wdur:
                exact["duration"] = round(wdur, 4)
                pre = float(query.get("prePhonemeLength") or 0.0)
                post = float(query.get("postPhonemeLength") or 0.0)
                out = {
                    "engine": name, "cached": False,
                    "fallback_from": fell_back if isinstance(fell_back, dict) else None,
                    "voice": voice, "kana": kana_of(query) or kana,
                    "duration": round(wdur, 4), "timing": "voicevox-exact",
                    # the engine states its own padding, so no analysis needed
                    "speech": [round(pre, 3), round(max(wdur - post, pre + 0.05), 3)],
                    "align": {"aligned": False,
                              "reason": "not needed: exact phoneme timing"},
                    "audio": "/media/" + os.path.basename(path),
                    "track": exact,
                }
                _cache_put(ck, out)
                return out
            sys.stderr.write(
                f"  [timing] voicevox durations sum to {total:.2f}s but the "
                f"clip is {wdur}s - falling back to estimated timing\n")
        except Exception as e:
            sys.stderr.write(f"  [timing] voicevox query unusable: {e}\n")

    # ONE decode, shared by the duration, the silence trim and the alignment.
    dur, db, n_samples = analyse(path)

    # Fit the mouth to the SPEECH, not to the file. Mora timing alone is an
    # estimate; fitting it to a clip that is part silence is worse than not
    # fitting it at all.
    span = speech_span(db=db, n_samples=n_samples) if (trim and db is not None) else None
    if span:
        t0, t1 = span
        track = build_track(kana, total=t1 - t0, intensity=intensity,
                            blink=blink, fps=30)
        shift_track(track, t0)
        track["duration"] = round(dur or t1, 4)
    else:
        track = build_track(kana, total=dur, intensity=intensity,
                            blink=blink, fps=30)
    # Take the timing from the recording rather than assuming it. The mora
    # model gives every mora the same beat; real speech stretches phrase-final
    # morae, compresses unstressed ones and pauses at commas for as long as the
    # engine likes. Fitting to the clip duration only corrects the average, so
    # the mouth still drifts inside the sentence.
    report = None
    if align:
        try:
            from align import align as align_track, envelope_from_db
            if db is not None:
                track, report = align_track(track, env=envelope_from_db(db))
            else:
                track, report = align_track(track, path)
        except Exception as e:
            report = {"aligned": False, "reason": f"{type(e).__name__}: {e}"}

    out = {
        "engine": name,
        "cached": False,
        "timing": "estimated+aligned" if (report or {}).get("aligned") else "estimated",
        "fallback_from": fell_back if isinstance(fell_back, dict) else None,
        "voice": voice,
        "kana": kana,
        "duration": dur or track["duration"],
        "speech": [round(span[0], 3), round(span[1], 3)] if span else None,
        "align": report,
        "audio": "/media/" + os.path.basename(path),
        "track": track,
    }
    _cache_put(ck, out)
    return out

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
            vv = _find_vv()
            return self._json({"engine": pick_backend(self.engine),
                               "voicevox": bool(vv),
                               "local_engine": vv[0] if vv else None,
                               "local_engine_url": vv[1] if vv else None,
                               "root": ROOT})
        if p == "/api/voices":
            eng, voices = list_voices(self.engine)
            return self._json({"engine": eng, "pinned": self.default_voice,
                               "count": len(voices), "voices": voices})
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
                      rate=req.get("rate") or DEFAULT_RATE,
                      blink=req.get("blink", True),
                      intensity=float(req.get("intensity", 1.0)),
                      trim=req.get("trim", True),
                      align=req.get("align", True))
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
    vv = _find_vv()
    if vv:
        print(f"  local engine: {vv[0]} at {vv[1]}")
    if a.voice:
        print(f"  voice:      {a.voice}   (pinned - the same voice every time)")
    else:
        print("  voice:      engine default"
              + ("" if a.tts != "auto" else
                 "\n  NOTE: --tts auto picks whichever engine is running, so the"
                 "\n        voice can change if that changes. Pin both with"
                 "\n        --tts <engine> --voice <id>.  See /api/voices"))
    print(f"  serving:    {ROOT}\n  pipeline:   {PIPELINE}\n  ctrl-c to stop\n")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  bye")


if __name__ == "__main__":
    main()
