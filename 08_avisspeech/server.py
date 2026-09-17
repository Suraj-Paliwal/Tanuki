"""Local AivisSpeech voice and audio-aligned Tanuki mouth animation."""
import argparse
import hashlib
import io
import json
import math
import os
from pathlib import Path
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import wave
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))
from jp_kana import to_hiragana
from jp_lipsync import build, VISEMES
from align import frame_db, envelope_from_db, align, HOP


class EngineUnavailable(RuntimeError):
    pass


class AivisClient:
    def __init__(self, base):
        self.base = base.rstrip("/")
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, endpoint, params=None, body=None, post=False, timeout=180):
        url = self.base + endpoint
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method="POST" if post else "GET",
                                     headers={"Content-Type": "application/json"})
        try:
            with self.opener.open(req, timeout=timeout) as response:
                result = response.read()
        except urllib.error.HTTPError as e:
            raise EngineUnavailable(f"AivisSpeech returned HTTP {e.code}. Check the selected voice and engine log.") from e
        except (OSError, urllib.error.URLError) as e:
            raise EngineUnavailable("AivisSpeech is not ready. Start AivisSpeech (port 10101), then click Reconnect.") from e
        return result if endpoint == "/synthesis" else json.loads(result)

    def voices(self):
        speakers = self.request("/speakers", timeout=5)
        return [{"id": str(style["id"]), "name": speaker["name"], "style": style["name"]}
                for speaker in speakers for style in speaker.get("styles", [])]


def query_reading(query):
    """Use engine readings, including kanji/dictionary pronunciations.

    AivisSpeech's top-level kana is ordinary input text, not VOICEVOX notation.
    Its duration fields are dummy zeroes: never label these as exact timing.
    """
    parts = []
    for phrase in query.get("accent_phrases", []):
        for mora in phrase.get("moras", []):
            parts.append("、" if mora.get("vowel") == "pau" else mora.get("text", ""))
        if phrase.get("pause_mora"):
            parts.append("、")
    reading = to_hiragana("".join(parts))
    if not reading.strip("、 。！？!?"):
        raise ValueError("The engine returned no pronounceable Japanese reading.")
    return reading


def decode_wav(data):
    with wave.open(io.BytesIO(data), "rb") as audio:
        rate, channels, width = audio.getframerate(), audio.getnchannels(), audio.getsampwidth()
        count = audio.getnframes()
        raw = audio.readframes(count)
    if width not in (1, 2, 4) or len(raw) != count * channels * width or not count:
        raise ValueError("AivisSpeech returned an incomplete or unsupported PCM WAV.")
    dtype = {1: "u1", 2: "<i2", 4: "<i4"}[width]
    samples = np.frombuffer(raw, dtype=dtype).astype(np.float64)
    samples = (samples - 128) / 128 if width == 1 else samples / (2 ** (width * 8 - 1))
    samples = samples.reshape(-1, channels).mean(axis=1)
    duration = count / rate
    if duration > 45:
        raise ValueError("Please split this text into shorter sentences (audio exceeds 45 seconds).")
    if rate != 16000:
        samples = np.interp(np.arange(round(duration * 16000)) / 16000,
                            np.arange(count) / rate, samples)
    return samples, duration


def make_track(data, query):
    samples, duration = decode_wav(data)
    if np.max(np.abs(samples)) < 1e-5:
        raise ValueError("The engine returned silent audio; try a different phrase or voice.")
    db = frame_db(samples)
    active = np.flatnonzero(db > -40)
    start = max(0, float(active[0]) * HOP - 0.03)
    end = min(duration, float(active[-1]) * HOP + 0.055)
    reading = query_reading(query)
    track = build(reading, total=end - start, blink=False, fps=30)
    for keys in track["tracks"].values():
        for key in keys:
            key[0] = round(key[0] + start, 4)
        keys.insert(0, [0.0, 0.0])
        keys.append([round(duration, 4), 0.0])
    track["duration"] = round(duration, 4)
    track, report = align(track, env=envelope_from_db(db), band=0.18)

    # Close the mouth through actual silence, including internal pauses. Keep
    # vowel identity from the engine reading; energy only gates mouth strength.
    times = np.unique(np.r_[np.arange(0, duration, HOP), duration])
    gate = np.interp(times, np.arange(len(db)) * HOP + 0.0125,
                     np.clip((db + 42) / 18, 0, 1), left=0, right=0)
    gate[(times < start) | (times > end)] = 0
    for name in VISEMES:
        keys = np.asarray(track["tracks"][name])
        weights = np.interp(times, keys[:, 0], keys[:, 1]) * gate
        weights[0] = weights[-1] = 0
        track["tracks"][name] = [[round(float(t), 4), round(float(w), 4)]
                                  for t, w in zip(times, weights)]
    return track, reading, [round(start, 4), round(end, 4)], report


class Service:
    def __init__(self, engine, media):
        self.engine, self.media = engine, Path(media)
        self.media.mkdir(exist_ok=True)
        self.lock = threading.Lock()
        self.cache = {}

    def say(self, payload):
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > 160:
            raise ValueError("Enter 1–160 characters of Japanese text.")
        speed = payload.get("speed", 1.0)
        if isinstance(speed, bool) or not isinstance(speed, (int, float)) or not math.isfinite(speed) or not 0.5 <= speed <= 2:
            raise ValueError("Speed must be between 0.5 and 2.0.")
        with self.lock:
            voices = self.engine.voices()
            if not voices:
                raise EngineUnavailable("No AivisSpeech voice models found. Add a model in AivisSpeech first.")
            voice = str(payload.get("voice") or voices[0]["id"])
            if voice not in {v["id"] for v in voices}:
                raise ValueError("This voice is no longer installed. Click Reconnect and select a voice.")
            params = {"speaker": voice}
            query = self.engine.request("/audio_query", {**params, "text": text.strip()}, post=True)
            query["speedScale"] = float(speed)
            # Include the actual query so dictionary or voice-setting edits do
            # not reuse an old reading. Cache only within this server process.
            key = hashlib.sha256(json.dumps([self.engine.base, voice, query], sort_keys=True,
                                          ensure_ascii=False).encode()).hexdigest()[:24]
            if key in self.cache and (self.media / f"{key}.wav").exists():
                return {**self.cache[key], "cached": True}
            audio = self.engine.request("/synthesis", params, body=query, post=True)
            track, reading, span, report = make_track(audio, query)
            result = {"engine": "aivisspeech", "voice": voice, "kana": reading,
                      "timing": "audio-aligned-estimate", "align": report,
                      "duration": track["duration"], "speech": span,
                      "track": track, "audio": f"/media/{key}.wav", "cached": False}
            path = self.media / f"{key}.wav"
            temp = path.with_suffix(".tmp")
            temp.write_bytes(audio)
            temp.replace(path)
            path.with_suffix(".json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
            if len(self.cache) >= 64:
                self.cache.pop(next(iter(self.cache)))
            self.cache[key] = result
            return result


class Handler(SimpleHTTPRequestHandler):
    service = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE), **kwargs)

    def respond(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        if path in ("/api/status", "/api/voices"):
            try:
                voices = self.service.engine.voices()
                self.respond({"engine": "aivisspeech", "ready": bool(voices), "voices": voices,
                              "message": "Connected" if voices else "No voice models installed"})
            except EngineUnavailable as e:
                self.respond({"engine": "aivisspeech", "ready": False, "voices": [], "message": str(e)}, 503)
            return
        clean = urllib.parse.unquote(path)
        if ".." in clean or "\\" in clean:
            self.send_error(404)
            return
        if clean.startswith("/media/"):
            if not __import__("re").fullmatch(r"/media/[a-f0-9]{24}\.(wav|json)", clean):
                self.send_error(404)
                return
            self.path = "/.media/" + clean.rsplit("/", 1)[1]
        elif clean in ("/", "/index.html"):
            self.path = "/index.html"
        elif not clean.startswith(("/model/", "/src/", "/vendor/")):
            self.send_error(404)
            return
        super().do_GET()

    def do_HEAD(self):
        self.send_error(405)

    def list_directory(self, path):
        self.send_error(404)

    def do_POST(self):
        if self.path != "/api/say":
            self.send_error(404)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 8192:
                raise ValueError("Invalid request size.")
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError("Expected a JSON object.")
            self.respond(self.service.say(payload))
        except (ValueError, UnicodeError) as e:
            self.respond({"error": str(e)}, 400)
        except EngineUnavailable as e:
            self.respond({"error": str(e)}, 503)
        except Exception as e:
            print(f"Speech failed: {e}", file=sys.stderr)
            self.respond({"error": "Could not generate speech. Check the server log."}, 500)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8088)
    parser.add_argument("--engine-url", default=os.getenv("AIVISSPEECH_URL", "http://127.0.0.1:10101"))
    args = parser.parse_args()
    Handler.service = Service(AivisClient(args.engine_url), HERE / ".media")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Tanuki + AivisSpeech: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
