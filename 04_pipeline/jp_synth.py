# -*- coding: utf-8 -*-
"""A small formant synthesiser for Japanese kana.

Not a text-to-speech system - it exists so the audio path can be tested and
demoed without shipping a voice model. Source-filter: a glottal pulse train
through three resonators tuned to each vowel, with crude consonant onsets.
"""
import numpy as np
from jp_kana import moras

try:
    from scipy.signal import lfilter as _lfilter
except ImportError:
    # This backend exists so the demo never hard-fails with no network and no
    # voice model - so it must not hard-fail on a missing SciPy either. The
    # only filter used here is a 2-pole resonator, which is four lines of
    # recursion. Slower than SciPy and identical in output.
    def _lfilter(b, a, x):
        b = np.asarray(b, float) / a[0]
        a = np.asarray(a, float) / a[0]
        x = np.asarray(x, float)
        y = np.zeros_like(x)
        nb, na = len(b), len(a)
        for n in range(len(x)):
            acc = 0.0
            for i in range(nb):
                if n - i >= 0:
                    acc += b[i] * x[n - i]
            for j in range(1, na):
                if n - j >= 0:
                    acc -= a[j] * y[n - j]
            y[n] = acc
        return y

SR = 22050
VOWEL_F = {"a": (750, 1200, 2600), "i": (300, 2300, 3000),
           "u": (350, 1300, 2200), "e": (500, 1900, 2600),
           "o": (500,  900, 2500)}
FRIC   = set("さしすせそざじずぜぞはひふへほ")
PLOS   = set("かきくけこがぎぐげごたちつてとだぢづでど぀ぱぴぷぺぽばびぶべぼ")
NASAL  = set("まみむめもなにぬねの")

def _reson(x, f, bw, sr=SR):
    r = np.exp(-np.pi * bw / sr)
    th = 2 * np.pi * f / sr
    return _lfilter([1 - r], [1, -2 * r * np.cos(th), r * r], x)

def _glottal(n, f0, sr=SR):
    t = np.arange(n) / sr
    ph = 2 * np.pi * np.cumsum(f0) / sr
    return np.where(np.diff(np.r_[0, ph % (2 * np.pi)]) < 0, 1.0, 0.0) - 0.02

def vowel(v, dur, f0=118.0, sr=SR):
    n = max(int(dur * sr), 8)
    f0c = f0 * (1 + 0.06 * np.linspace(0, -1, n))
    src = _glottal(n, f0c, sr)
    F1, F2, F3 = VOWEL_F[v]
    y = _reson(src, F1, 80) + 0.6 * _reson(src, F2, 110) + 0.25 * _reson(src, F3, 160)
    env = np.ones(n)
    a = max(int(0.012 * sr), 1); d = max(int(0.020 * sr), 1)
    env[:a] = np.linspace(0, 1, a); env[-d:] = np.linspace(1, 0, d)
    return y * env

def noise(dur, lo, hi, amp=0.25, sr=SR):
    n = max(int(dur * sr), 4)
    x = np.random.randn(n)
    y = _reson(x, (lo + hi) / 2, (hi - lo))
    e = np.ones(n); k = max(int(0.006 * sr), 1)
    e[:k] = np.linspace(0, 1, k); e[-k:] = np.linspace(1, 0, k)
    return y * e * amp

def synth(text, mora_dur=0.135, sr=SR):
    out = []
    for m in moras(text):
        d = mora_dur
        if m.kind == "pause":
            out.append(np.zeros(int(d * 0.6 * sr))); continue
        if m.kind == "stop":
            out.append(np.zeros(int(d * sr))); continue
        if m.kind == "nasal":
            n = int(d * sr)
            src = _glottal(n, np.full(n, 110.0), sr)
            out.append(0.5 * _reson(src, 280, 120)); continue
        head = m.kana[0]
        if m.kind == "long":
            out.append(vowel(m.vowel, d)); continue
        c = []
        if head in PLOS:
            c.append(np.zeros(int(0.028 * sr)))
            c.append(noise(0.014, 1200, 4200, 0.30))
            vd = d - 0.042
        elif head in FRIC:
            hi = 6500 if head in "しじ" else 5200
            c.append(noise(0.055, 2500, hi, 0.22)); vd = d - 0.055
        elif head in NASAL:
            n = int(0.035 * sr)
            src = _glottal(n, np.full(n, 112.0), sr)
            c.append(0.45 * _reson(src, 270, 110)); vd = d - 0.035
        else:
            vd = d
        c.append(vowel(m.vowel, max(vd, 0.03)))
        out.append(np.concatenate(c))
    y = np.concatenate(out) if out else np.zeros(1)
    y = y / max(np.abs(y).max(), 1e-9) * 0.85
    return y.astype(np.float32), sr

def write_wav(path, y, sr=SR):
    import wave
    d = (np.clip(y, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(d.tobytes())
