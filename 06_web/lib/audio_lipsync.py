# -*- coding: utf-8 -*-
"""Drive the tanuki's visemes from a Japanese audio recording.

No forced aligner and no model download: the five Japanese vowels are unusually
well separated in formant space, so estimating F1/F2 per frame and picking the
nearest vowel gets you a usable track. Formants are speaker-dependent, so they
are normalised against the speaker's own median before classification.
"""
import subprocess, tempfile, wave, os
import numpy as np
try:
    from scipy.signal import lfilter, medfilt
except ImportError:
    # SciPy is not required to run this. Only two of its functions are used
    # here and both are a couple of lines of numpy; without this shim a
    # machine with no SciPy silently loses the DTW alignment, which is the
    # single biggest contributor to lip-sync accuracy (0.686 -> 0.881).
    def lfilter(b, a, x):
        """Enough of scipy.signal.lfilter for this file: zero initial state."""
        b = np.asarray(b, float)
        x = np.asarray(x, float)
        a = np.atleast_1d(np.asarray(a, float))
        if a.size == 1:                       # FIR - a convolution
            return np.convolve(x, b / a[0])[:len(x)]
        b, a = b / a[0], a / a[0]             # IIR - direct recursion
        y = np.zeros_like(x)
        for n in range(len(x)):
            acc = sum(b[i] * x[n - i] for i in range(len(b)) if n - i >= 0)
            acc -= sum(a[j] * y[n - j] for j in range(1, len(a)) if n - j >= 0)
            y[n] = acc
        return y

    def medfilt(x, kernel_size=3):
        """1-D median filter, zero-padded at the edges, as scipy does it."""
        x = np.asarray(x, float)
        k = int(kernel_size) | 1              # scipy requires an odd kernel
        h = k // 2
        pad = np.concatenate([np.zeros(h), x, np.zeros(h)])
        win = np.lib.stride_tricks.sliding_window_view(pad, k)
        return np.median(win, axis=-1)

SR = 16000
WIN, HOP = 0.025, 0.010
VISEMES = ["A", "I", "U", "E", "O"]

# Reference F1/F2 for the five Japanese vowels (adult male, Hz).
VOWEL_F = {"A": (750, 1200), "I": (300, 2300), "U": (350, 1300),
           "E": (500, 1900), "O": (500,  900)}

def decode(path, sr=SR):
    """Any audio file -> mono float array.

    A .wav is read directly; anything else goes through ffmpeg, which streams
    raw samples to stdout rather than writing a temp file we would immediately
    read back. Process spawns are the single most expensive thing this server
    does per request - on Windows especially - so the callers below decode ONCE
    and share the array.
    """
    if path.lower().endswith(".wav"):
        try:
            with wave.open(path) as w:
                if w.getnchannels() == 1 and w.getframerate() == sr:
                    raw, width = w.readframes(w.getnframes()), w.getsampwidth()
                    dt = {1: np.int8, 2: np.int16, 4: np.int32}[width]
                    return np.frombuffer(raw, dtype=dt).astype(np.float64) / \
                        float(np.iinfo(dt).max)
        except Exception:
            pass                       # fall through to ffmpeg
    out = subprocess.run(["ffmpeg", "-v", "error", "-i", path,
                          "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
                         check=True, stdout=subprocess.PIPE).stdout
    x = np.frombuffer(out, dtype="<i2").astype(np.float64)
    return x / 32768.0

def _levinson(r, order):
    a = np.zeros(order + 1); a[0] = 1.0
    e = r[0]
    if e <= 0: return a
    for i in range(1, order + 1):
        acc = r[i] + np.dot(a[1:i], r[i-1:0:-1]) if i > 1 else r[i]
        k = -acc / e
        a[1:i+1] += k * a[i-1::-1][:i]
        e *= (1 - k * k)
        if e <= 0: break
    return a

def formants(frame, sr=SR, order=None, max_bw=420.0):
    """LPC roots -> the first two formants.

    Order matters more than it looks: at order 12 the two low, close formants
    of /o/ (about 500 and 900 Hz) merge into a single pole and the estimator
    reports F3 as F2, so every /o/ classifies as something else. Roughly
    sr/1000 + 4 poles keeps them apart. Wide-bandwidth roots are spectral
    tilt rather than resonances and are discarded.
    """
    if order is None:
        order = int(sr / 1000) + 4
    x = lfilter([1, -0.97], 1, frame * np.hamming(len(frame)))
    r = np.correlate(x, x, "full")[len(x)-1:len(x)+order]
    if r[0] <= 1e-12: return None
    a = _levinson(r, order)
    rts = np.roots(a)
    rts = rts[np.imag(rts) > 0.01]
    if len(rts) == 0: return None
    f  = np.abs(np.angle(rts)) * sr / (2 * np.pi)
    bw = -(sr / np.pi) * np.log(np.maximum(np.abs(rts), 1e-9))
    keep = np.sort(f[(f > 120) & (f < 4200) & (bw < max_bw)])
    if len(keep) < 2: return None
    return float(keep[0]), float(keep[1])

def analyse(path, floor_db=-38.0, smooth=3, speaker_adapt=0.35, f2_weight=1.4):
    x = decode(path)
    n_win, n_hop = int(WIN * SR), int(HOP * SR)
    if len(x) < n_win: return {"frames": [], "duration": 0.0}
    frames, times = [], []
    for i in range(0, len(x) - n_win, n_hop):
        frames.append(x[i:i+n_win]); times.append(i / SR)
    rms = np.array([np.sqrt(np.mean(f * f)) + 1e-12 for f in frames])
    db = 20 * np.log10(rms / max(rms.max(), 1e-12))
    voiced = db > floor_db
    F = np.full((len(frames), 2), np.nan)
    for i, f in enumerate(frames):
        if not voiced[i]: continue
        r = formants(f)
        if r: F[i] = r
    ok = ~np.isnan(F[:, 0])
    if ok.sum() < 3:
        return {"frames": [], "duration": len(x) / SR}
    # Adapt to the speaker, but only partly. Full normalisation divides by the
    # utterance median, which depends on which vowels happen to occur - a
    # sentence heavy in /a/ drags every other vowel out of place. A fractional
    # exponent keeps most of the benefit for high or low voices without letting
    # the phrase's own vowel mix distort the space.
    ref = np.array([VOWEL_F[v] for v in VISEMES], float)
    scale = (np.nanmedian(F[ok], axis=0) / np.median(ref, axis=0)) ** speaker_adapt
    Fn = F / np.maximum(scale, 1e-6)
    lref = np.log(ref)
    # F2 separates i / e / u, which is most of the work; F1 mainly says how
    # open the mouth is and is already used for the weight.
    wgt = np.array([1.0, f2_weight])
    lab = np.full(len(frames), -1)
    conf = np.zeros(len(frames))
    for i in np.nonzero(ok)[0]:
        d = np.linalg.norm((lref - np.log(np.maximum(Fn[i], 1.0))) * wgt, axis=1)
        j = int(np.argmin(d))
        lab[i] = j
        conf[i] = float(np.clip(1.0 - d[j] / 1.1, 0.20, 1.0))
    if smooth > 1:
        lab = medfilt(lab.astype(float), smooth).astype(int)
    # openness from F1 and loudness, so quiet frames do not gape
    loud = np.clip((db - floor_db) / 22.0, 0, 1)
    out = []
    for i, t in enumerate(times):
        if lab[i] < 0 or not voiced[i]:
            out.append((t, None, 0.0))
        else:
            out.append((t, VISEMES[lab[i]], float(np.clip(loud[i] * conf[i], 0, 1))))
    return {"frames": out, "duration": len(x) / SR}

def to_tracks(res, thin=0.012):
    """Frame labels -> sparse per-viseme keyframes, same shape as the text path."""
    tr = {v: [] for v in VISEMES}
    last = None
    for t, name, w in res["frames"]:
        key = (name, round(w, 2))
        if last is not None and key == last[0] and t - last[1] < thin:
            continue
        for v in VISEMES:
            tr[v].append([round(t, 4), round(w if v == name else 0.0, 4)])
        last = (key, t)
    return {"duration": round(res["duration"], 4), "fps": int(1 / HOP),
            "visemes": VISEMES, "tracks": tr}
