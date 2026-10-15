#!/usr/bin/env python3
"""דף קטן על פני הים — builds the finished film from Abba's video and the Suno playback.

Runs on the phone (Termux) or any Linux with ffmpeg + numpy + pillow.

  python daf.py                    # finds both files on the phone by name
  python daf.py VIDEO PLAYBACK     # explicit paths

Pipeline:
  1. analyse both tracks (tuning in cents, chroma, voice activity)
  2. find the key shift + tempo + offset that best match the playback to Abba's singing
  3. follow his timing through the song (piecewise tempo) and his pitch drift
  4. render the playback to fit him, clean his voice, mix with ducking
  5. intro/outro cards, lyric subtitles, final encode into the gallery
"""
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, features

HERE = os.path.dirname(os.path.abspath(__file__))
SR = 22050           # analysis rate
NFFT = 4096
HOP = 512
FPS = SR / HOP       # ~43 analysis frames per second
OUT_SR = 48000

TITLE = "דַּף קָטָן עַל פְּנֵי הַיָּם"
SUBTITLE = "דף היומי"
INTRO_LINES = ["לחן: הרב רפאל שוורץ", "הולחן לכבוד סיום מסכת חולין"]
OUTRO_LINES = [
    "בוצע בערב אזכרה",
    "לעילוי נשמת",
    "הרב עוזר ב״ר חיים שווארץ זצ״ל",
    "ג׳ דחול המועד סוכות",
    "תנצב״ה",
]

GOLD = (236, 204, 132, 255)
WHITE = (255, 255, 255, 255)


def log(*a):
    print(*a, flush=True)


def run(cmd):
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        sys.stderr.write(r.stderr.decode(errors="replace")[-3000:])
        raise SystemExit("ffmpeg failed: " + " ".join(cmd[:6]) + " ...")
    return r.stdout


# ---------------------------------------------------------------- files

VIDEO_EXT = (".mp4", ".mov", ".mkv", ".3gp", ".webm", ".m4v")
AUDIO_EXT = (".mp3", ".m4a", ".wav", ".aac", ".ogg", ".flac", ".opus")
MAIN_NAME = re.compile(r"סוכות|sukkot|sukot|abba|אבא", re.I)
SUNO_NAME = re.compile(r"סונו|suno|דף קטן|daf", re.I)


def storage_root():
    for p in ("~/storage/shared", "/sdcard", "/storage/emulated/0"):
        p = os.path.expanduser(p)
        if os.path.isdir(p) and os.access(p, os.R_OK):
            return p
    return None


def walk_media(root):
    dirs = ["DCIM", "Pictures", "Movies", "Download", "Downloads", "WhatsApp",
            "Android/media/com.whatsapp/WhatsApp/Media", "Music", "Recordings"]
    seen = set()
    for d in dirs:
        base = os.path.join(root, d)
        if not os.path.isdir(base):
            continue
        for dp, dn, fn in os.walk(base, onerror=lambda e: None):
            dn[:] = [x for x in dn if not x.startswith(".") and x != ".thumbnails"]
            for f in fn:
                p = os.path.join(dp, f)
                if p not in seen:
                    seen.add(p)
                    yield p


def find_inputs():
    root = storage_root()
    if not root:
        raise SystemExit("No phone storage. Run: termux-setup-storage   (and allow), then try again.")
    files = list(walk_media(root))
    vids = [p for p in files if p.lower().endswith(VIDEO_EXT) and MAIN_NAME.search(os.path.basename(p))]
    auds = [p for p in files if p.lower().endswith(AUDIO_EXT) and MAIN_NAME.search(os.path.basename(p))]
    suno = [p for p in files if p.lower().endswith(AUDIO_EXT) and SUNO_NAME.search(os.path.basename(p))]
    if not vids:
        raise SystemExit("Video not found (name with 'סוכות' / 'Abba_sukkot'). Pass the path: bash daf_katan/make.sh VIDEO PLAYBACK")
    ranked = sorted(vids, key=video_rank, reverse=True)
    log("video candidates (best first):")
    for p in ranked[:6]:
        log(f"   {os.path.getsize(p) / 1e6:7.1f}MB  {p}")
    video = ranked[0]
    newest = lambda ps: sorted(ps, key=lambda p: (not DERIVED.search(os.path.basename(p)), os.path.getsize(p) > 2e6,
                                                  os.path.getmtime(p)), reverse=True)
    cands = newest(auds) + [p for p in newest(suno) if p not in auds]
    if not cands:
        raise SystemExit("Playback mp3 not found. Pass the path: bash daf_katan/make.sh VIDEO PLAYBACK")
    return video, cands


# outputs of earlier attempts - never the original recording
DERIVED = re.compile(r"synced|instrumental|mix|final|output|render|edit|preview|proxy|copy|דף|daf|_out", re.I)
ORIGINAL_SIZE = 72364957  # "דף קטן סיום אבא מקור.mp4" as uploaded to Drive


def video_rank(p):
    name = os.path.basename(p)
    stem = re.sub(r"[\s_\-.]|\(\d+\)|-\d+$", "", os.path.splitext(name)[0]).lower()
    size = os.path.getsize(p)
    return (size == ORIGINAL_SIZE,
            not DERIVED.search(name),
            stem in ("abbasukkot", "אבאסוכות", "אבאסוכותמקור"),
            "/DCIM/" in p,
            size,
            os.path.getmtime(p))


def probe(path):
    out = run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path])
    return json.loads(out)


def duration(info):
    return float(info["format"]["duration"])


# ---------------------------------------------------------------- analysis

def load(path, sr=SR, ch=1, start=None, dur=None):
    cmd = ["ffmpeg", "-v", "error"]
    if start is not None:
        cmd += ["-ss", f"{start:.4f}"]
    if dur is not None:
        cmd += ["-t", f"{dur:.4f}"]
    cmd += ["-i", path, "-vn", "-ac", str(ch), "-ar", str(sr), "-f", "f32le", "-"]
    y = np.frombuffer(run(cmd), dtype=np.float32)
    return y.reshape(-1, ch) if ch > 1 else y.copy()


class Analysis:
    """Band-limited log spectrogram summarised into tuning, chroma and activity."""

    def __init__(self, y):
        y = y / (np.max(np.abs(y)) + 1e-9)
        self.freqs = np.fft.rfftfreq(NFFT, 1 / SR)
        self.band = np.where((self.freqs >= 70) & (self.freqs <= 4200))[0]
        nfr = max(1, 1 + (len(y) - NFFT) // HOP)
        win = np.hanning(NFFT).astype(np.float32)
        mags = np.empty((nfr, len(self.band)), dtype=np.float32)
        voc = (self.freqs[self.band] >= 100) & (self.freqs[self.band] <= 3000)
        energy = np.empty(nfr, dtype=np.float32)
        step = 512
        for s in range(0, nfr, step):
            e = min(nfr, s + step)
            idx = (np.arange(s, e)[:, None] * HOP) + np.arange(NFFT)[None, :]
            idx = np.minimum(idx, len(y) - 1)
            spec = np.abs(np.fft.rfft(y[idx] * win, axis=1))[:, self.band].astype(np.float32)
            mags[s:e] = spec
            energy[s:e] = 10 * np.log10(np.sum(spec[:, voc] ** 2, axis=1) + 1e-9)
        self.mag = mags
        self.n = nfr
        self.flux = self._onsets()
        self.energy = energy
        lo, hi = np.percentile(energy, 15), np.percentile(energy, 97)
        self.active = energy > lo + 0.38 * (hi - lo)
        self.tune_vec = self._tuning_vectors()
        self.tuning = self.tuning_at(0, self.n)
        self.tcurve = self._tuning_curve()
        self._chroma = None
        self._melody = None

    def _onsets(self):
        """Spectral-flux onset strength, z-scored, for millisecond timing."""
        f = self.freqs[self.band]
        sel = (f >= 150) & (f <= 4000)
        L = np.log1p(self.mag[:, sel] * 4.0)
        d = np.zeros(self.n, np.float32)
        d[1:] = np.maximum(0, np.diff(L, axis=0)).sum(axis=1)
        k = int(0.5 * FPS)
        d = np.maximum(0, d - np.convolve(d, np.ones(k) / k, mode="same"))
        return (d - d.mean()) / (d.std() + 1e-9)

    def _tuning_vectors(self):
        """Per frame weighted unit vectors of peak deviations from A440 grid."""
        m = self.mag
        f = self.freqs[self.band]
        out = np.zeros((self.n, 2), dtype=np.float64)
        a, b, c = m[:, :-2], m[:, 1:-1], m[:, 2:]
        peak = (b > a) & (b >= c) & (b > 0.08 * m.max(axis=1, keepdims=True))
        peak &= (f[1:-1] > 150)[None, :] & (f[1:-1] < 2500)[None, :]
        la, lb, lc = np.log(a + 1e-9), np.log(b + 1e-9), np.log(c + 1e-9)
        den = la - 2 * lb + lc
        delta = np.where(np.abs(den) > 1e-9, 0.5 * (la - lc) / np.where(den == 0, 1, den), 0)
        delta = np.clip(delta, -0.5, 0.5)
        fr = (self.band[1:-1][None, :] + delta) * SR / NFFT
        cents = 1200 * np.log2(np.maximum(fr, 1) / 440.0)
        ang = 2 * np.pi * cents / 100.0
        w = np.where(peak, b, 0)
        out[:, 0] = np.sum(w * np.cos(ang), axis=1)
        out[:, 1] = np.sum(w * np.sin(ang), axis=1)
        return np.cumsum(out, axis=0)

    def tuning_at(self, s, e):
        s, e = max(0, int(s)), min(self.n, int(e))
        if e <= s:
            return 0.0
        v = self.tune_vec[e - 1] - (self.tune_vec[s - 1] if s > 0 else 0)
        return float(np.angle(v[0] + 1j * v[1]) * 100 / (2 * np.pi))

    def _tuning_curve(self):
        """Continuous (unwrapped) tuning in cents per frame - follows a singer drifting flat/sharp."""
        step, half = int(FPS), int(8 * FPS)
        cs = np.arange(0, self.n, step)
        vals, mags = [], []
        for c in cs:
            s, e = max(0, c - half), min(self.n, c + half)
            v = self.tune_vec[e - 1] - (self.tune_vec[s - 1] if s > 0 else 0)
            vals.append(np.angle(v[0] + 1j * v[1]))
            mags.append(np.hypot(*v))
        vals, mags = np.array(vals), np.array(mags)
        good = mags > 0.05 * (mags.max() + 1e-9)
        if good.sum() < 2:
            return np.full(self.n, self.tuning)
        ang = np.unwrap(vals[good])
        cents = ang * 100 / (2 * np.pi)
        cents -= 100 * np.round((np.median(cents) - self.tuning) / 100)
        return np.interp(np.arange(self.n), cs[good], cents)

    def chroma(self):
        """12 x n pitch-class profile read against the local tuning (cached)."""
        if self._chroma is not None:
            return self._chroma
        f = self.freqs[self.band]
        base = 69 + 12 * np.log2(f / 440.0)
        lowf = np.where(f < 120, 0.4, 1.0)[None, :]
        L = np.log1p(self.mag * 4.0)
        C = np.empty((12, self.n), np.float32)
        blk = int(FPS)
        cols = np.arange(len(f))
        for s in range(0, self.n, blk):
            e = min(self.n, s + blk)
            pc = np.mod(base - float(np.mean(self.tcurve[s:e])) / 100.0, 12)
            lo = np.floor(pc).astype(int) % 12
            fr = pc - np.floor(pc)
            M = np.zeros((12, len(f)), dtype=np.float32)
            M[lo, cols] += (1 - fr)
            M[(lo + 1) % 12, cols] += fr
            C[:, s:e] = (L[s:e] @ (M * lowf).T).T
        self._chroma = C
        return C


    def melody(self):
        """Sung-note pitch classes from the fundamental (not the overtones), 12 x n, plus voiced mask.

        A single voice's overtones look like a fourth/fifth to plain chroma; tracking
        the fundamental is what makes the key decision reliable."""
        if self._melody is not None:
            return self._melody
        f = self.freqs[self.band]
        nb = len(f)
        cands = 55 * 2 ** (np.arange(0, 12 * 5 * 4) / 60.0)
        cands = cands[(cands >= 80) & (cands <= 900)]
        S = np.zeros((nb, len(cands)), np.float32)
        for j, c in enumerate(cands):
            for k in range(1, 7):
                p = c * k * NFFT / SR - self.band[0]
                i = int(p)
                if i >= nb - 1:
                    break
                if i >= 0:
                    S[i, j] += 0.84 ** (k - 1) * (1 - (p - i))
                    S[i + 1, j] += 0.84 ** (k - 1) * (p - i)
        sal = np.empty(self.n, np.float32)
        best = np.empty(self.n, int)
        for s0 in range(0, self.n, 2048):
            blk = np.log1p(self.mag[s0:s0 + 2048] * 4.0) @ S
            best[s0:s0 + 2048] = np.argmax(blk, axis=1)
            sal[s0:s0 + 2048] = blk[np.arange(len(blk)), best[s0:s0 + 2048]]
        cents = 1200 * np.log2(cands[best] / 440.0)
        pc = np.mod(69 + (cents - self.tcurve) / 100.0, 12)
        near = np.round(pc).astype(int) % 12
        voiced = self.active & (sal > np.percentile(sal[self.active], 30) if self.active.any() else False)
        C = np.zeros((12, self.n), np.float32)
        C[near, np.arange(self.n)] = np.exp(-(np.abs(pc - np.round(pc)) / 0.3) ** 2)
        C *= voiced[None, :]
        self._melody = (C, voiced)
        return self._melody


def harmony(pa):
    """Playback chroma sharpened so the strong chord tones dominate."""
    C = pa.chroma()
    return (C / (C.max(axis=0, keepdims=True) + 1e-6)) ** 2


def normalise(C, weight=None):
    C = C - C.mean(axis=0, keepdims=True)
    C = C / (np.linalg.norm(C, axis=0, keepdims=True) + 1e-6)
    if weight is not None:
        C = C * weight[None, :]
    return C


def downsample(x, k):
    n = x.shape[-1] // k
    return x[..., : n * k].reshape(*x.shape[:-1], n, k).mean(axis=-1)


def resample_cols(P, r, n_out=None):
    """Column j of the result is P at fractional column j*r."""
    n_out = n_out or int(P.shape[1] / r)
    src = np.arange(n_out) * r
    i0 = np.clip(np.floor(src).astype(int), 0, P.shape[1] - 1)
    i1 = np.clip(i0 + 1, 0, P.shape[1] - 1)
    fr = (src - np.floor(src))[None, :]
    out = P[:, i0] * (1 - fr) + P[:, i1] * fr
    out[:, src > P.shape[1] - 1] = 0
    return out


def xcorr(V, P):
    """score[lag] = sum_t V[:,t].P[:,t+lag]; returns (scores, lags)."""
    n = V.shape[1] + P.shape[1]
    nfft = 1 << (n - 1).bit_length()
    acc = np.zeros(nfft)
    for d in range(V.shape[0]):
        acc += np.fft.irfft(np.conj(np.fft.rfft(V[d], nfft)) * np.fft.rfft(P[d], nfft), nfft)
    lags = np.concatenate([np.arange(0, P.shape[1]), np.arange(-V.shape[1] + 1, 0)])
    vals = np.concatenate([acc[: P.shape[1]], acc[nfft - V.shape[1] + 1:]])
    return vals, lags


# ---------------------------------------------------------------- matching

def global_match(va, pa):
    """Search key shift k, tempo ratio r and offset so playback(off + r*t) fits voice(t)."""
    K = 4  # ~10.8 fps for the coarse search
    Mv, voiced = va.melody()
    wv = downsample(voiced.astype(np.float32), K)
    V = normalise(downsample(Mv, K), (wv > 0.25).astype(np.float32))
    Pc = downsample(harmony(pa), K)
    Pc[:, downsample(pa.active.astype(np.float32), K) < 0.3] *= 0.3
    F = FPS / K
    best = None
    for k in range(-6, 6):
        P = normalise(np.roll(Pc, k, axis=0))
        for r in np.arange(0.80, 1.2501, 0.005):
            s, lags = xcorr(V, resample_cols(P, r))
            i = int(np.argmax(s))
            if best is None or s[i] > best[0]:
                best = (float(s[i]), k, float(r), lags[i] * r / F)
    score, k, r, off = best
    # fine pass at full frame rate
    V = normalise(Mv, voiced.astype(np.float32))
    P = normalise(np.roll(harmony(pa), k, axis=0))
    fbest = None
    for rr in np.arange(r - 0.006, r + 0.0061, 0.0005):
        s, lags = xcorr(V, resample_cols(P, rr))
        target = off * FPS / rr
        near = np.abs(lags - target) <= 0.4 * FPS / rr
        i = np.flatnonzero(near)[np.argmax(s[near])]
        if fbest is None or s[i] > fbest[0]:
            fbest = (float(s[i]), float(rr), lags[i] * rr / FPS)
    norm = fbest[0] / max(1.0, float(voiced.sum()))
    return dict(shift=k, tempo=fbest[1], offset=fbest[2], score=norm)


def local_map(va, pa, g, pred=None, reach_s=3.0, half_s=6.0, step_s=3.0, onset_w=0.0, t_range=None):
    """Follow Abba's timing: per-window corrections around a predicted map.

    Returns (video_time, delta, confidence) where delta is the playback-time
    correction relative to the global line off + r*t."""
    Mv, voiced = va.melody()
    V = normalise(Mv, voiced.astype(np.float32))
    P = normalise(np.roll(harmony(pa), g["shift"], axis=0))
    r, off = g["tempo"], g["offset"]
    line = lambda t: off + r * t
    pred = pred or line
    half, step, reach = int(half_s * FPS), int(step_s * FPS), int(reach_s * FPS)
    cols = np.arange(P.shape[1])
    pts = []
    c_lo, c_hi = half // 2, va.n - half // 2
    if t_range:
        c_lo, c_hi = max(c_lo, int(t_range[0] * FPS)), min(c_hi, int(t_range[1] * FPS))
    for c in range(c_lo, c_hi, step):
        lo_, hi_ = max(0, c - half), min(va.n, c + half)
        if hi_ - lo_ < 2 * half:
            continue
        sl = slice(lo_, hi_)
        w = voiced[sl].astype(np.float32)
        if w.mean() < 0.25:
            continue
        t = np.arange(c - half - reach, c + half + reach) / FPS
        src = np.asarray(pred(t)) * FPS
        if src[-1] < 0 or src[0] > P.shape[1]:
            continue
        inside = (src >= 0) & (src <= P.shape[1] - 1)
        seg = np.stack([np.interp(src, cols, P[d]) for d in range(12)]) * inside[None, :]
        s, lags = xcorr(V[:, sl], seg)
        s = s / (w.sum() + 1e-6)
        if onset_w:
            fv = va.flux[sl][None, :]
            fp = (np.interp(src, cols, pa.flux) * inside)[None, :]
            fs, _ = xcorr(fv, fp)
            s = s + onset_w * fs / (2 * half)
        ok = (lags >= 0) & (lags <= 2 * reach)
        sv, lv = s[ok], lags[ok]
        j = int(np.argmax(sv))
        peak = sv[j]
        away = np.abs(lv - lv[j]) > min(0.4 * FPS, reach * 0.7)
        second = sv[away].max() if away.any() else 0
        if peak < 0.18 or (reach_s > 1 and peak - second < 0.04):
            continue
        frac = 0.0
        if 0 < j < len(sv) - 1:
            den = sv[j - 1] - 2 * sv[j] + sv[j + 1]
            if den < 0:
                frac = float(np.clip(0.5 * (sv[j - 1] - sv[j + 1]) / den, -0.5, 0.5))
        # the point sits where the singing in this window actually is
        tc = float(np.sum(w * np.arange(c - half, c + half)) / w.sum()) / FPS
        slope = float(pred(tc + 0.5) - pred(tc - 0.5))
        tp = float(pred(tc)) + (lv[j] + frac - reach) / FPS * slope
        pts.append((tc, tp - line(tc), peak))
    return pts


def cycle_period(pa, lo_s=8.0, hi_s=40.0):
    """Length of the playback's repeating harmonic cycle (one stanza), in seconds."""
    K = 4
    F = FPS / K
    H = normalise(downsample(harmony(pa), K))
    lags = np.arange(int(lo_s * F), int(hi_s * F))
    ac = np.array([float(np.mean(np.sum(H[:, :-L] * H[:, L:], axis=0))) for L in lags])
    L = int(lags[np.argmax(ac)])
    # refine to frame precision on the full-rate onset envelope (bars must line up)
    fl = pa.flux
    best, bestL = -1e9, L * K
    for Lf in range(L * K - 2 * K, L * K + 2 * K + 1):
        v = float(np.dot(fl[:-Lf], fl[Lf:]) / (len(fl) - Lf))
        if v > best:
            best, bestL = v, Lf
    return bestL / FPS, float(ac.max())


def offset_scores(va, pa, g):
    """Evidence (melody vs harmony) for every constant offset at the found tempo."""
    Mv, voiced = va.melody()
    V = normalise(Mv, voiced.astype(np.float32))
    P = normalise(np.roll(harmony(pa), g["shift"], axis=0))
    r = g["tempo"]
    s, lags = xcorr(V, resample_cols(P, r))
    order = np.argsort(lags)
    lags, s = lags[order], s[order]
    return lambda off: float(np.interp(off * FPS / r, lags, s))


def plan_structure(va, pa, g, m, play_len, intro_min=6.0, outro_s=15.0):
    """Place Abba's song on the playback's own intro and ending.

    Returns [(t_from, t_to, shift_s)]: playback time = m(t) + shift. Shifts are
    whole harmonic cycles, so the chords stay exactly right."""
    _, voiced = va.melody()
    dens = np.convolve(voiced.astype(np.float32), np.ones(int(FPS)) / int(FPS), mode="same")
    sung_idx = np.flatnonzero(dens > 0.3)
    if len(sung_idx) < FPS * 5:
        return [(-np.inf, np.inf, 0.0)], None
    t_first, t_last = sung_idx[0] / FPS, sung_idx[-1] / FPS
    C, strength = cycle_period(pa)
    if strength < 0.3:
        return [(-np.inf, np.inf, 0.0)], None
    score = offset_scores(va, pa, g)
    base = score(g["offset"])
    p_first = float(m(t_first))
    # earliest stanza start that still leaves the playback's intro in front of him,
    # among positions the evidence supports nearly as well as the best one
    feasible = [k for k in range(-12, 13)
                if intro_min <= p_first + k * C < play_len and score(g["offset"] + k * C) >= 0.75 * base]
    k_best = min(feasible, key=lambda k: p_first + k * C) if feasible else 0
    shift = k_best * C
    remaining = play_len - (float(m(t_last)) + shift)
    n = 0
    if remaining < 4.0:
        n = -int(math.ceil((outro_s - remaining) / C))
    elif remaining > outro_s + 0.6 * C:
        n = int(math.floor((remaining - outro_s) / C + 0.4))
    plan = {"cycle": C, "start_cycles": k_best, "jump_cycles": n, "t_first": t_first, "t_last": t_last}
    if n == 0:
        return [(-np.inf, np.inf, shift)], plan
    # jump in the longest breath in the middle of the song (between stanzas)
    span = t_last - t_first
    lo, hi = int((t_first + 0.3 * span) * FPS), int((t_first + 0.7 * span) * FPS)
    quiet = dens[lo:hi] < 0.15
    best_len, best_mid, run = 0, (lo + hi) // 2, 0
    for i, q in enumerate(quiet):
        run = run + 1 if q else 0
        if run > best_len:
            best_len, best_mid = run, lo + i - run // 2
    if best_len == 0:
        best_mid = lo + int(np.argmin(dens[lo:hi]))
    tg = best_mid / FPS
    plan["jump_at"] = tg
    return [(-np.inf, tg, shift), (tg, np.inf, shift + n * C)], plan


def refine_shift(pa, shift, p_lo, p_hi, reach=0.4):
    """Exact jump size: where the playback repeats itself beat-for-beat.

    Compares the playback with itself (music vs identical music - far sharper
    than voice vs music) around `shift`, over the playback region [p_lo, p_hi]."""
    if shift == 0:
        return 0.0
    n = pa.n
    R = int(reach * FPS)
    base = int(round(shift * FPS))
    # both the region and every shifted copy of it must lie inside the playback
    a = max(int(p_lo * FPS), 0, -(base - R))
    b = min(int(p_hi * FPS), n, n - (base + R))
    if b - a < 4 * FPS:
        return shift
    fl = pa.flux
    H = normalise(harmony(pa))
    scores = []
    for L in range(base - R, base + R + 1):
        x, y = fl[a:b], fl[a + L:b + L]
        c1 = float(np.dot(x - x.mean(), y - y.mean()) / (np.std(x) * np.std(y) * len(x) + 1e-9))
        c2 = float(np.mean(np.sum(H[:, a:b] * H[:, a + L:b + L], axis=0)))
        scores.append(c1 + c2)
    sc = np.array(scores)
    j = int(np.argmax(sc))
    frac = 0.0
    if 0 < j < len(sc) - 1:
        den = sc[j - 1] - 2 * sc[j] + sc[j + 1]
        if den < 0:
            frac = float(np.clip(0.5 * (sc[j - 1] - sc[j + 1]) / den, -0.5, 0.5))
    return (base - R + j + frac) / FPS


def local_shift_curve(pa, shift, q_lo, q_hi, half_s=4.0, step_s=1.5, reach=0.3):
    """Suno's AI audio drifts slightly in tempo, so a whole-cycle jump is not the
    same everywhere. For each playback position q, find the beat-equivalent
    position in the target cycle (music vs music), then smooth."""
    fl, F = pa.flux, FPS
    H = normalise(harmony(pa))
    h, R = int(half_s * F), int(reach * F)
    qs, ds, ws = [], [], []
    for q in np.arange(q_lo, q_hi + 1e-6, step_s):
        a, b = int(q * F) - h, int(q * F) + h
        base = int(round(shift * F))
        if a < 0 or b > pa.n or a + base - R < 0 or b + base + R > pa.n:
            continue
        x = fl[a:b] - fl[a:b].mean()
        sc = []
        for L in range(base - R, base + R + 1):
            y = fl[a + L:b + L] - fl[a + L:b + L].mean()
            c1 = float(np.dot(x, y) / (np.linalg.norm(x) * np.linalg.norm(y) + 1e-9))
            c2 = float(np.mean(np.sum(H[:, a:b] * H[:, a + L:b + L], axis=0)))
            sc.append(c1 + 0.5 * c2)
        sc = np.array(sc)
        j = int(np.argmax(sc))
        frac = 0.0
        if 0 < j < len(sc) - 1:
            den = sc[j - 1] - 2 * sc[j] + sc[j + 1]
            if den < 0:
                frac = float(np.clip(0.5 * (sc[j - 1] - sc[j + 1]) / den, -0.5, 0.5))
        qs.append(q)
        ds.append((base - R + j + frac) / F - shift)
        ws.append(max(1e-3, float(sc[j] - np.median(sc))))
    if len(qs) < 3:
        return lambda q: shift + 0 * np.asarray(q, float)
    qs, ds, ws = np.array(qs), np.array(ds), np.array(ws)
    grid = np.arange(qs[0], qs[-1] + 1e-6, 1.0)
    fit = robust_fit(qs, ds, ws, grid, span=10.0)
    return lambda q: shift + np.interp(q, grid, fit)


def section_knots(pa, knots0, m0, shift, t_lo, t_hi):
    """Abba's timing from the main pass, moved to the equivalent place in another stanza."""
    if shift == 0:
        return knots0, 0.0
    exact = refine_shift(pa, shift, float(m0(max(t_lo, 0.0))), float(m0(t_hi)))
    curve = local_shift_curve(pa, exact, float(m0(max(t_lo, 0.0))) - 5, float(m0(t_hi)) + 5)
    knots = [(t, m + float(curve(m))) for t, m in knots0]
    # denser knots inside the section so the local correction is followed
    lo, hi = max(t_lo, knots0[0][0]), min(t_hi, knots0[-1][0])
    extra = [(t, float(m0(t)) + float(curve(float(m0(t))))) for t in np.arange(lo, hi, 1.0)]
    knots = sorted(set(knots + extra))
    return knots, exact


def mapping_fn(knots):
    kt = np.array([k[0] for k in knots])
    km = np.array([k[1] for k in knots])

    def f(t):
        t = np.asarray(t, dtype=float)
        y = np.interp(t, kt, km)
        lo, hi = t < kt[0], t > kt[-1]
        if np.any(lo):
            y = np.where(lo, km[0] + (t - kt[0]) * (km[1] - km[0]) / (kt[1] - kt[0]), y)
        if np.any(hi):
            y = np.where(hi, km[-1] + (t - kt[-1]) * (km[-1] - km[-2]) / (kt[-1] - kt[-2]), y)
        return y
    return f


def robust_fit(t, d, conf, at, span=8.0):
    """Robust local-linear regression (LOWESS with bisquare reweighting) of d(t), evaluated at `at`."""

    def local(x, rob):
        u = np.abs(t - x) / span
        w = np.where(u < 1, (1 - u ** 3) ** 3, 0) * conf * rob
        if w.sum() < 1.5 * np.max(w, initial=0) or w.sum() < 1e-6:
            u = np.abs(t - x) / (2 * span)
            w = np.where(u < 1, (1 - u ** 3) ** 3, 0) * conf * rob + 1e-9
        dx = t - x
        sw, sx, sxx = w.sum(), (w * dx).sum(), (w * dx * dx).sum() + 1e-3 * w.sum()
        sy, sxy = (w * d).sum(), (w * dx * d).sum()
        det = sw * sxx - sx * sx
        return (sxx * sy - sx * sxy) / det if det > 1e-12 else sy / sw

    rob = np.ones_like(d)
    for _ in range(3):
        fit = np.array([local(x, rob) for x in t])
        res = d - fit
        mad = np.median(np.abs(res)) + 0.005
        u = res / (6 * mad)
        rob = np.where(np.abs(u) < 1, (1 - u ** 2) ** 2, 0.0)
    return np.array([local(x, rob) for x in at])


def build_mapping(g, pts, t_from, t_to, step=4.0, span=8.0):
    """Piecewise-linear map video time -> playback time from timing points."""
    r, off = g["tempo"], g["offset"]
    line = lambda t: off + r * t
    if len(pts) < 4:
        return [(t_from, line(t_from)), (t_to, line(t_to))], 0.0
    t = np.array([p[0] for p in pts])
    d = np.array([p[1] for p in pts])
    conf = np.array([p[2] for p in pts])
    order = np.argsort(t)
    t, d, conf = t[order], d[order], conf[order]
    knots_t = np.arange(t[0], t[-1] + 1e-6, step)
    if t[-1] - knots_t[-1] > 0.5:
        knots_t = np.append(knots_t, t[-1])
    kd = robust_fit(t, d, conf, knots_t, span=span)
    spread = float(np.max(np.abs(kd - np.median(kd))))
    if spread < 0.03:
        off += float(np.median(kd))
        return [(t_from, off + r * t_from), (t_to, off + r * t_to)], spread
    knots = [(float(a), float(off + r * a + b)) for a, b in zip(knots_t, kd)]
    # keep the tempo musical: no segment more than 12% from the song tempo
    fixed = [knots[0]]
    for a, b in knots[1:]:
        pa_, pb_ = fixed[-1]
        slope = min(max((b - pb_) / (a - pa_), r * 0.88), r * 1.12)
        fixed.append((a, pb_ + slope * (a - pa_)))
    # before the first / after the last timing point: continue at the song's tempo
    first, last = fixed[0], fixed[-1]
    out = [(t_from, first[1] - r * (first[0] - t_from))] + fixed + [(t_to, last[1] + r * (t_to - last[0]))]
    return out, spread


def robust_line(t, d, w):
    """Weighted straight-line fit with bisquare outlier rejection -> (intercept, slope)."""
    rob = np.ones_like(d)
    a, b = float(np.median(d)), 0.0
    for _ in range(5):
        ww = w * rob
        A = np.stack([np.ones_like(t), t], axis=1) * np.sqrt(ww)[:, None]
        a, b = np.linalg.lstsq(A, d * np.sqrt(ww), rcond=None)[0]
        res = d - (a + b * t)
        u = res / (6 * (np.median(np.abs(res)) + 0.004))
        rob = np.where(np.abs(u) < 1, (1 - u ** 2) ** 2, 0.0)
    return float(a), float(b)


# (search reach s, window half-width s, step s, onset weight, knot step s, smoothing span s)
FOLLOW_PASSES = ((0.6, 5.0, 2.0, 0.5, 4.0, 8.0), (0.25, 3.5, 1.0, 1.0, 2.0, 4.0), (0.12, 3.0, 0.75, 1.0, 1.5, 4.0))


def follow_timing(va, pa, g, t_from, t_to):
    """Map video time -> playback time.

    Coarse pass decides whether Abba really changed tempo along the way; if not,
    one straight line is refined to the millisecond (noise must not become
    wobble). If he did, the map follows him, narrowing the search pass by pass."""
    pts = local_map(va, pa, g)
    knots, spread = build_mapping(g, pts, t_from, t_to)
    if spread < 0.07 or len(pts) < 4:
        line = mapping_fn([(t_from, g["offset"] + g["tempo"] * t_from), (t_to, g["offset"] + g["tempo"] * t_to)])
        fine = local_map(va, pa, g, pred=line, reach_s=0.25, half_s=3.5, step_s=1.5, onset_w=1.0)
        if len(fine) >= 4:
            t = np.array([p[0] for p in fine])
            d = np.array([p[1] for p in fine])
            a, b = robust_line(t, d, np.array([p[2] for p in fine]))
            g = dict(g, offset=g["offset"] + a, tempo=g["tempo"] + b)
        m = lambda x: g["offset"] + g["tempo"] * x
        return [(t_from, m(t_from)), (t_to, m(t_to))], 0.0, fine or pts, "steady"
    for reach, half, step, ow, kstep, span in FOLLOW_PASSES:
        fine = local_map(va, pa, g, pred=mapping_fn(knots), reach_s=reach, half_s=half, step_s=step, onset_w=ow)
        if len(fine) >= max(4, len(pts) // 2):
            knots, spread = build_mapping(g, fine, t_from, t_to, step=kstep, span=span)
            pts = fine
    return knots, spread, pts, "following"


def pitch_curve(va, pa, g, knots):
    """Cents to shift the playback per segment: key shift + Abba's (drifting) tuning."""
    pt = float(np.median(pa.tcurve))
    cents = []
    for (a, _), (b, _) in zip(knots[:-1], knots[1:]):
        # intro/outro sit outside the singing: hold the nearest sung tuning
        lo = int(np.clip(a * FPS, 0, va.n - 1))
        hi = int(np.clip(b * FPS, lo + 1, va.n))
        cents.append(float(np.mean(va.tcurve[lo:hi])) - pt)
    cents = np.array(cents) + g["shift"] * 100
    if len(cents) > 2:
        cents = np.convolve(np.pad(cents, 1, mode="edge"), [0.25, 0.5, 0.25], mode="valid")
    if np.ptp(cents) < 12:
        cents[:] = np.median(cents)
    return cents


# ---------------------------------------------------------------- audio render

def has_filter(name):
    out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.decode()
    return re.search(r"\s" + re.escape(name) + r"\s", out) is not None


def render_segment(src, a, b, tempo, cents, out_len, rubber):
    """Playback [a,b) seconds, stretched by tempo and shifted by cents -> out_len seconds stereo."""
    p = 2 ** (cents / 1200.0)
    if rubber:
        af = f"rubberband=tempo={tempo:.6f}:pitch={p:.6f}:transients=mixed:pitchq=quality"
    else:
        af = f"asetrate={OUT_SR * p:.3f},aresample={OUT_SR},atempo={tempo / p:.6f}"
    y = load_filtered(src, a, b - a, af)
    n = int(round(out_len * OUT_SR))
    if len(y) < n:
        y = np.vstack([y, np.zeros((n - len(y), 2), np.float32)])
    return y[:n]


def load_filtered(path, start, dur, af):
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{max(0, start):.5f}", "-t", f"{dur:.5f}", "-i", path,
           "-vn", "-af", f"aresample={OUT_SR},{af}", "-ac", "2", "-ar", str(OUT_SR), "-f", "f32le", "-"]
    return np.frombuffer(run(cmd), dtype=np.float32).reshape(-1, 2).copy()


def render_playback(src, knots, cents, total_from, total_to, play_len, rubber):
    """Warped playback on the video timeline [total_from, total_to)."""
    if rubber:
        return render_continuous(src, knots, cents, total_from, total_to, play_len)
    return render_pieces(src, knots, cents, total_from, total_to, play_len)


def render_continuous(src, knots, cents, total_from, total_to, play_len):
    """One rubberband pass whose tempo/pitch change on the fly at each knot - no seams."""
    segs = merge_segments(knots, cents)
    m = mapping_fn(knots)
    a = max(0.0, float(m(total_from)))
    b = min(play_len, float(m(total_to)))
    n_total = int(round((total_to - total_from) * OUT_SR))
    out = np.zeros((n_total, 2), np.float32)
    if b - a < 0.5:
        return out
    # timeline moment where the source region starts
    kt = np.array([k[0] for k in knots])
    km = np.array([k[1] for k in knots])
    t_a = float(np.interp(a, km, kt)) if a > km[0] else total_from
    tempo_of = lambda sg: (sg[3] - sg[2]) / (sg[1] - sg[0])
    first = next((sg for sg in segs if sg[3] > a), segs[0])
    lines = []
    for sg in segs:
        at = sg[2] - a
        if at <= 0 or sg[2] >= b:
            continue
        lines.append(f"{at:.4f} rubberband tempo {tempo_of(sg):.6f}, rubberband pitch {2 ** (sg[4] / 1200):.6f};")
    cmdfile = os.path.join(tempfile.gettempdir(), f"daf_cmd_{os.getpid()}.txt")
    with open(cmdfile, "w") as f:
        f.write("\n".join(lines) + "\n")
    cmds = f"asetnsamples=n=256:p=0,asendcmd=f={cmdfile}," if lines else ""
    af = (f"{cmds}rubberband=tempo={tempo_of(first):.6f}:"
          f"pitch={2 ** (first[4] / 1200):.6f}:transients=mixed:pitchq=quality")
    y = load_filtered(src, a, b - a, af)
    os.remove(cmdfile)
    s = int(round((t_a - total_from) * OUT_SR))
    s0, s1 = max(0, s), min(n_total, s + len(y))
    if s1 > s0:
        out[s0:s1] = y[s0 - s: s1 - s]
    return out


def render_pieces(src, knots, cents, total_from, total_to, play_len):
    """Fallback without rubberband: per-segment stretch joined with crossfades."""
    n_total = int(round((total_to - total_from) * OUT_SR))
    out = np.zeros((n_total, 2), np.float32)
    xf = 0.06
    segs = merge_segments(knots, cents)
    for i, (t0, t1, m0, m1, c) in enumerate(segs):
        tempo = (m1 - m0) / (t1 - t0)
        e0 = t0 - (xf if i > 0 else 0)
        e1 = t1 + (xf if i < len(segs) - 1 else 0)
        a, b = m0 - (t0 - e0) * tempo, m1 + (e1 - t1) * tempo
        if b <= 0 or a >= play_len:
            continue
        if a < 0:
            e0 += -a / tempo
            a = 0.0
        if b > play_len:
            e1 -= (b - play_len) / tempo
            b = play_len
        if e1 - e0 < 0.05:
            continue
        y = render_segment(src, a, b, tempo, c, e1 - e0, False)
        s = int(round((e0 - total_from) * OUT_SR))
        ramp = int(xf * 2 * OUT_SR)
        env = np.ones(len(y), np.float32)
        if i > 0 and ramp < len(y):
            env[:ramp] = np.sin(np.linspace(0, np.pi / 2, ramp)) ** 2
        if i < len(segs) - 1 and ramp < len(y):
            env[-ramp:] = np.cos(np.linspace(0, np.pi / 2, ramp)) ** 2
        y = y * env[:, None]
        s0, s1 = max(0, s), min(n_total, s + len(y))
        if s1 > s0:
            out[s0:s1] += y[s0 - s: s1 - s]
    return out


def merge_segments(knots, cents):
    segs = []
    for (t0, m0), (t1, m1), c in zip(knots[:-1], knots[1:], cents):
        if segs:
            pt0, pt1, pm0, pm1, pc = segs[-1]
            tempo_prev = (pm1 - pm0) / (pt1 - pt0)
            tempo = (m1 - m0) / (t1 - t0)
            if abs(tempo / tempo_prev - 1) < 0.004 and abs(c - pc) < 3:
                segs[-1] = (pt0, t1, pm0, m1, pc)
                continue
        segs.append((t0, t1, m0, m1, c))
    return segs


def write_wav(path, y):
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(OUT_SR), "-ac", "2", "-i", "-",
                          "-c:a", "pcm_f32le", path], stdin=subprocess.PIPE)
    p.stdin.write(np.ascontiguousarray(y, dtype=np.float32).tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise SystemExit("could not write " + path)


VOICE_CHAIN = ("highpass=f=85,afftdn=nf=-28:nr=10:tn=1,"
               "equalizer=f=220:t=q:w=1.1:g=-2.5,equalizer=f=3200:t=q:w=1.2:g=2.5,"
               "equalizer=f=9000:t=h:w=0.7:g=1.5,deesser=i=0.35,"
               "acompressor=threshold=0.09:ratio=3:attack=12:release=180:makeup=1.6,"
               "aecho=0.85:0.82:47|83|131:0.16|0.11|0.07")


def rms_db(y, mask=None):
    y = y.mean(axis=1) if y.ndim > 1 else y
    if mask is not None and mask.any():
        y = y[mask]
    return 20 * np.log10(np.sqrt(np.mean(y ** 2)) + 1e-9)


# ---------------------------------------------------------------- graphics

RAQM = features.check("raqm")
NIQQUD = re.compile(r"[֑-ׇ]")


def font(path, size, weight=700):
    eng = ImageFont.Layout.RAQM if RAQM else ImageFont.Layout.BASIC
    f = ImageFont.truetype(path, size, layout_engine=eng)
    try:
        f.set_variation_by_axes([weight])
    except (OSError, ValueError):
        pass
    f.weight = weight
    return f


def shape(text):
    """Text and draw kwargs for correct RTL rendering with or without libraqm."""
    if RAQM:
        return text, dict(direction="rtl", language="he")
    plain = NIQQUD.sub("", text)
    return plain[::-1], {}


def text_size(draw, text, fnt):
    t, kw = shape(text)
    x0, y0, x1, y1 = draw.textbbox((0, 0), t, font=fnt, **kw)
    return x1 - x0, y1 - y0, x0, y0


def draw_centered(img, y, text, fnt, fill, shadow=0.55, max_w=None):
    d = ImageDraw.Draw(img)
    W = img.width
    if max_w:
        while text_size(d, text, fnt)[0] > max_w and fnt.size > 12:
            fnt = font(fnt.path, int(fnt.size * 0.94), fnt.weight)
    w, h, ox, oy = text_size(d, text, fnt)
    x = (W - w) / 2 - ox
    t, kw = shape(text)
    if shadow:
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        sd = ImageDraw.Draw(sh)
        off = max(2, fnt.size // 18)
        sd.text((x + off, y - oy + off), t, font=fnt, fill=(0, 0, 0, int(255 * shadow)), **kw)
        sh = sh.filter(ImageFilter.GaussianBlur(max(2, fnt.size // 10)))
        img.alpha_composite(sh)
    ImageDraw.Draw(img).text((x, y - oy), t, font=fnt, fill=fill, **kw)
    return y + h


def card(W, H, lines, path):
    """lines: (text, font, color, gap_after) stacked and vertically centred."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    heights = [(text_size(d, t, f)[1] if f else 0) + g for t, f, c, g in lines]
    y = (H - sum(heights)) / 2
    for (t, f, c, g), h in zip(lines, heights):
        if t == "—":
            lw = int(W * 0.18)
            ImageDraw.Draw(img).line([(W / 2 - lw, y + h / 2), (W / 2 + lw, y + h / 2)], fill=GOLD, width=max(2, W // 400))
        else:
            draw_centered(img, y, t, f, c, max_w=W * 0.88)
        y += h
    img.save(path)


def lyric_png(W, H, text, fpath, path):
    base = min(W, H)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fnt = font(fpath, int(base * 0.06), 700)
    d = ImageDraw.Draw(img)
    _, h, _, _ = text_size(d, text, fnt)
    y = H - int(H * (0.11 if H > W else 0.09)) - h
    draw_centered(img, y, text, fnt, WHITE, shadow=0.85, max_w=W * 0.9)
    top = max(0, int(y - h * 0.9))
    bottom = min(H, int(y + h * 1.9))
    img.crop((0, top, W, bottom)).save(path)
    return top


def blurred_bg(src, dst, W, H):
    im = Image.open(src).convert("RGB").resize((W, H))
    im = im.filter(ImageFilter.GaussianBlur(max(14, min(W, H) // 36)))
    im = ImageEnhance.Color(im).enhance(0.75)
    im = ImageEnhance.Brightness(im).enhance(0.62)
    im.save(dst)


def gradient_png(W, H, path):
    h0 = int(H * 0.68)
    a = np.zeros((H - h0, W, 4), np.uint8)
    a[:, :, 3] = (np.linspace(0, 1, H - h0) ** 1.6 * 150).astype(np.uint8)[:, None]
    Image.fromarray(a, "RGBA").save(path)
    return h0


# ---------------------------------------------------------------- lyrics timing

def load_lyrics():
    with open(os.path.join(HERE, "lyrics.txt"), encoding="utf-8") as f:
        return [ln.strip().rstrip(",.:") for ln in f if ln.strip()]


def lyric_times(va, n_lines, t_from, t_to):
    """Group voiced phrases inside [t_from,t_to] into n_lines lines."""
    act = va.melody()[1].copy()
    gap_fill = int(0.22 * FPS)
    idx = np.flatnonzero(act)
    for a, b in zip(idx[:-1], idx[1:]):
        if 1 < b - a <= gap_fill:
            act[a:b] = True
    segs, start = [], None
    for j, v in enumerate(np.append(act, False)):
        if v and start is None:
            start = j
        elif not v and start is not None:
            s, e = start / FPS, j / FPS
            if e - s >= 0.25 and e > t_from and s < t_to:
                segs.append([max(s, t_from), min(e, t_to)])
            start = None
    if not segs:
        return None
    # too few phrases: split the longest at its quietest point
    while len(segs) < n_lines:
        k = int(np.argmax([e - s for s, e in segs]))
        s, e = segs[k]
        if e - s < 1.0:
            break
        a, b = int((s + 0.35 * (e - s)) * FPS), int((s + 0.65 * (e - s)) * FPS)
        m = (a + int(np.argmin(va.energy[a:b]))) / FPS
        segs[k: k + 1] = [[s, m], [m, e]]
    n = len(segs)
    if n < n_lines:
        return None
    gaps = np.array([segs[i + 1][0] - segs[i][1] for i in range(n - 1)])
    sung = sum(e - s for s, e in segs)
    mu = sung / n_lines
    # DP: choose n_lines contiguous groups, rewarding big gaps and even line lengths
    INF = 1e18
    cost = np.full((n_lines + 1, n + 1), INF)
    back = np.zeros((n_lines + 1, n + 1), int)
    cost[0, 0] = 0
    cum = np.concatenate([[0], np.cumsum([e - s for s, e in segs])])
    for g in range(1, n_lines + 1):
        for j in range(g, n - (n_lines - g) + 1):
            best, arg = INF, 0
            for i in range(g - 1, j):
                if cost[g - 1, i] >= INF:
                    continue
                dur = cum[j] - cum[i]
                c = cost[g - 1, i] + 1.2 * math.log(max(dur, 0.2) / mu) ** 2
                if j < n:
                    c -= math.log(gaps[j - 1] + 0.05) * 1.0
                if c < best:
                    best, arg = c, i
            cost[g, j], back[g, j] = best, arg
    bounds, j = [], n
    for g in range(n_lines, 0, -1):
        i = back[g, j]
        bounds.append((segs[i][0], segs[j - 1][1]))
        j = i
    return bounds[::-1]


# ---------------------------------------------------------------- main

def same_recording(video, audio, vd, ad):
    if abs(vd - ad) > 1.5:
        return False
    a = load(video, sr=4000)
    b = load(audio, sr=4000)
    n = min(len(a), len(b), 4000 * 60)
    a, b = np.abs(a[:n]), np.abs(b[:n])
    a, b = a - a.mean(), b - b.mean()
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9)) > 0.6


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    opts = {a.split("=")[0]: (a.split("=", 1)[1] if "=" in a else "1") for a in sys.argv[1:] if a.startswith("--")}
    if len(args) >= 2:
        video, cands = args[0], [args[1]]
    else:
        video, cands = find_inputs()
    vinfo = probe(video)
    vdur = duration(vinfo)
    playback = None
    for c in cands:
        cd = duration(probe(c))
        if same_recording(video, c, vdur, cd):
            log("skip (same as video audio):", os.path.basename(c))
            continue
        playback, pdur = c, cd
        break
    if not playback:
        raise SystemExit("No separate playback found next to the video.")
    log("VIDEO   :", video, f"({vdur:.1f}s)")
    log("PLAYBACK:", playback, f"({pdur:.1f}s)")

    work = tempfile.mkdtemp(prefix="daf_")
    out_dir = opts.get("--out") or os.path.join(storage_root() or os.path.expanduser("~"), "Movies")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "דף קטן על פני הים.mp4")

    log("[1/6] listening to Abba ...")
    va = Analysis(load(video))
    log("[2/6] listening to the playback ...")
    pa = Analysis(load(playback))
    log(f"      tuning: Abba {np.median(va.tcurve):+.0f} cents (moves {np.ptp(va.tcurve):.0f}), playback {np.median(pa.tcurve):+.0f}")

    log("[3/6] matching key + tempo + timing ...")
    g = global_match(va, pa)
    knots0, spread, pts, mode = follow_timing(va, pa, g, -60.0, vdur + 60.0)
    m0 = mapping_fn(knots0)
    plan, info = plan_structure(va, pa, g, m0, pdur)
    sections = []
    for a, b, shift in plan:
        try:
            knots, exact = section_knots(pa, knots0, m0, shift, max(a, 0.0), min(b, vdur))
        except Exception as e:  # never lose the film over a refinement
            log(f"      note: section refinement skipped ({e})")
            knots = [(t, m + shift) for t, m in knots0]
        sections.append((a, b, knots))
    m_first, m_last = mapping_fn(sections[0][2]), mapping_fn(sections[-1][2])
    # open on the playback's own beginning and close on its own ending
    intro = float(min(max(float(m_first(0.0)) / g["tempo"], 6.0), 24.0))
    slope_end = float(m_last(vdur + 1) - m_last(vdur))
    outro = float(min(max((pdur - float(m_last(vdur))) / slope_end, 6.0), 25.0))
    total = intro + vdur + outro
    all_cents = []
    for a, b, knots in sections:
        all_cents.extend(pitch_curve(va, pa, g, knots))
    log(f"      key shift {g['shift']:+d} semitones, fine {np.median(all_cents) - g['shift'] * 100:+.0f} cents"
        f" (range {np.ptp(all_cents):.0f})")
    log(f"      tempo x{g['tempo']:.3f}, match {g['score']:.2f}, timing points {len(pts)}, {mode}"
        f" (drift {spread * 1000:.0f}ms)")
    if info:
        log(f"      stanza cycle {info['cycle']:.2f}s, first note at {float(m_first(info['t_first'])):.1f}s of the playback"
            + (f", jump {info['jump_cycles']:+d} cycles at {info['jump_at']:.1f}s" if info.get("jump_cycles") else ""))
    if g["score"] < 0.12:
        log("      WARNING: weak match - check the result carefully")

    log("[4/6] rendering playback to Abba's key and timing ...")
    rubber = has_filter("rubberband") and "--no-rubberband" not in opts
    n_total = int(round(total * OUT_SR))
    music = np.zeros((n_total, 2), np.float32)
    xf = 0.3
    for i, (a, b, knots) in enumerate(sections):
        w0 = max(a - (xf if i > 0 else 0), -intro)
        w1 = min(b + (xf if i < len(sections) - 1 else 0), vdur + outro)
        y = render_playback(playback, knots, pitch_curve(va, pa, g, knots), w0, w1, pdur, rubber)
        env = np.ones(len(y), np.float32)
        ramp = int(2 * xf * OUT_SR)
        if i > 0:
            env[:ramp] = np.sin(np.linspace(0, np.pi / 2, ramp)) ** 2
        if i < len(sections) - 1:
            env[-ramp:] = np.cos(np.linspace(0, np.pi / 2, ramp)) ** 2
        s0 = int(round((w0 + intro) * OUT_SR))
        n = min(len(y), n_total - s0)
        music[s0:s0 + n] += (y * env[:, None])[:n]
    vfile = os.path.join(work, "voice.wav")
    run(["ffmpeg", "-v", "error", "-y", "-i", video, "-vn", "-af",
         f"aresample={OUT_SR},{VOICE_CHAIN},adelay={int(intro * 1000)}:all=1,apad=whole_dur={total:.3f}",
         "-ac", "2", "-ar", str(OUT_SR), "-c:a", "pcm_f32le", vfile])
    voice = np.frombuffer(run(["ffmpeg", "-v", "error", "-i", vfile, "-f", "f32le", "-"]), np.float32).reshape(-1, 2)
    n = min(len(voice), len(music))
    win = int(0.4 * OUT_SR)
    env = np.sqrt(np.convolve(voice[:n, 0] ** 2, np.ones(win) / win, mode="same"))
    vmask = env > np.percentile(env, 60)
    mmask = np.abs(music[:n, 0]) > 1e-4
    gain_db = (rms_db(voice[:n], vmask) - 6.0) - rms_db(music[:n], mmask)
    gain_db += float(opts.get("--music-db", 0))
    # musical fades: in under the title, out under the dedication
    fi, fo = int(2.0 * OUT_SR), int(5.0 * OUT_SR)
    music[:fi] *= np.linspace(0, 1, fi)[:, None] ** 2
    music[-fo:] *= np.linspace(1, 0, fo)[:, None] ** 1.5
    mfile = os.path.join(work, "music.wav")
    write_wav(mfile, music)
    mix = os.path.join(work, "mix.wav")
    run(["ffmpeg", "-v", "error", "-y", "-i", vfile, "-i", mfile, "-filter_complex",
         f"[1:a]volume={gain_db:.2f}dB[m];[0:a]asplit[v][sc];"
         f"[m][sc]sidechaincompress=threshold=0.04:ratio=2.2:attack=40:release=450:makeup=1[md];"
         f"[v][md]amix=inputs=2:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11,"
         f"afade=t=out:st={total - 2.5:.3f}:d=2.5,atrim=0:{total:.3f}[a]",
         "-map", "[a]", "-ar", str(OUT_SR), "-c:a", "pcm_s16le", mix])

    log("[5/6] titles and lyrics ...")
    frame = os.path.join(work, "f.png")
    run(["ffmpeg", "-v", "error", "-y", "-i", video, "-frames:v", "1", frame])
    last = os.path.join(work, "last.png")
    run(["ffmpeg", "-v", "error", "-y", "-sseof", "-1.5", "-i", video, "-update", "1", "-frames:v", "999", last])
    W, H = Image.open(frame).size
    if max(W, H) > 1920:  # 4K phone video: render at 1080p (sharp, and hours faster on a phone)
        k = 1920 / max(W, H)
        W, H = int(W * k) // 2 * 2, int(H * k) // 2 * 2
    for src, dst in ((frame, "blur_in.png"), (last, "blur_out.png")):
        blurred_bg(src, os.path.join(work, dst), W, H)
    serif = os.path.join(HERE, "fonts", "FrankRuhlLibre.ttf")
    sans = os.path.join(HERE, "fonts", "Heebo.ttf")
    b = min(W, H)
    card(W, H, [
        ("בס״ד", font(sans, int(b * 0.03), 400), (255, 255, 255, 200), int(b * 0.07)),
        (TITLE, font(serif, int(b * 0.104), 800), GOLD, int(b * 0.03)),
        (SUBTITLE, font(serif, int(b * 0.064), 600), WHITE, int(b * 0.035)),
        ("—", None, GOLD, int(b * 0.04)),
        (INTRO_LINES[0], font(serif, int(b * 0.05), 600), WHITE, int(b * 0.022)),
        (INTRO_LINES[1], font(sans, int(b * 0.034), 400), (235, 235, 235, 255), 0),
    ], os.path.join(work, "intro.png"))
    card(W, H, [
        (OUTRO_LINES[0], font(sans, int(b * 0.036), 400), (235, 235, 235, 255), int(b * 0.05)),
        (OUTRO_LINES[1], font(serif, int(b * 0.046), 600), WHITE, int(b * 0.014)),
        (OUTRO_LINES[2], font(serif, int(b * 0.066), 800), GOLD, int(b * 0.045)),
        ("—", None, GOLD, int(b * 0.04)),
        (OUTRO_LINES[3], font(sans, int(b * 0.038), 500), WHITE, int(b * 0.035)),
        (OUTRO_LINES[4], font(serif, int(b * 0.054), 700), GOLD, 0),
    ], os.path.join(work, "outro.png"))
    grad_y = gradient_png(W, H, os.path.join(work, "grad.png"))

    lyrics = load_lyrics()
    subs = []
    if "--no-subs" not in opts and pts:
        sung_from = max(0.0, pts[0][0] - 8)
        sung_to = min(vdur, pts[-1][0] + 8)
        times = lyric_times(va, len(lyrics), sung_from, sung_to)
        if times:
            for i, ((s, e), text) in enumerate(zip(times, lyrics)):
                nxt = times[i + 1][0] if i + 1 < len(times) else e + 2.0
                st = max(0.0, s - 0.25)
                en = min(nxt - 0.1, e + 1.6)
                subs.append((st + intro, en + intro, text))
    sub_y = [lyric_png(W, H, text, serif, os.path.join(work, f"l{i:02d}.png")) for i, (s, e, text) in enumerate(subs)]
    with open(os.path.join(out_dir, "דף קטן - כתוביות.srt"), "w", encoding="utf-8") as f:
        for i, (s, e, text) in enumerate(subs, 1):
            ts = lambda x: f"{int(x // 3600):02d}:{int(x % 3600 // 60):02d}:{int(x % 60):02d},{int(x * 1000 % 1000):03d}"
            f.write(f"{i}\n{ts(s)} --> {ts(e)}\n{text}\n\n")

    log("[6/6] rendering the film (this takes a while on a phone) ...")
    fps = 30
    vs = [s for s in vinfo["streams"] if s.get("codec_type") == "video"][0]
    try:
        num, den = vs.get("avg_frame_rate", "30/1").split("/")
        fps = min(60, max(24, round(float(num) / float(den))))
    except (ValueError, ZeroDivisionError):
        pass
    # input order: 0 video, 1 mix, 2 intro, 3 outro, 4 gradient, 5 blur in, 6 blur out, 7.. lyric lines
    inputs = ["-i", video, "-i", mix]
    T_end = intro + vdur
    g0, g1 = (subs[0][0] - 1.0, subs[-1][1] + 1.0) if subs else (0, 1)
    # each still starts at its moment on the timeline, so nothing is buffered ahead of time
    stills = [(os.path.join(work, "intro.png"), 0.0, intro), (os.path.join(work, "outro.png"), T_end, outro),
              (os.path.join(work, "grad.png"), g0, g1 - g0),
              (os.path.join(work, "blur_in.png"), 0.0, intro + 1.4),
              (os.path.join(work, "blur_out.png"), T_end - 1.2, outro + 1.2)]
    stills += [(os.path.join(work, f"l{i:02d}.png"), s, e - s) for i, (s, e, _) in enumerate(subs)]
    for p, at, dur in stills:
        inputs.extend(["-itsoffset", f"{at:.3f}", "-loop", "1", "-framerate", str(fps), "-t", f"{dur:.3f}", "-i", p])
    fc = [
        f"[0:v]fps={fps},scale={W}:{H}:flags=lanczos,setsar=1,tpad=start_mode=clone:start_duration={intro:.3f}:"
        f"stop_mode=clone:stop_duration={outro:.3f},format=yuv420p[base]",
        f"[5:v]format=rgba,fade=t=out:st={intro - 0.3:.3f}:d=1.6:alpha=1[blin]",
        f"[6:v]format=rgba,fade=t=in:st={T_end - 1.2:.3f}:d=1.6:alpha=1[blout]",
        "[base][blin]overlay=eof_action=pass[x0]",
        "[x0][blout]overlay=eof_action=pass[x1]",
        f"[2:v]format=rgba,fade=t=in:st=0.8:d=1.4:alpha=1,fade=t=out:st={intro - 1.4:.3f}:d=1.2:alpha=1[ti]",
        "[x1][ti]overlay=eof_action=pass[x2]",
        f"[3:v]format=rgba,fade=t=in:st={T_end + 1.0:.3f}:d=1.6:alpha=1[to]",
        "[x2][to]overlay=eof_action=pass[x3]",
    ]
    cur = "x3"
    if subs:
        fc.append(f"[4:v]format=rgba,fade=t=in:st={g0:.3f}:d=1.0:alpha=1,"
                  f"fade=t=out:st={g1 - 1.0:.3f}:d=1.0:alpha=1[gr]")
        fc.append(f"[{cur}][gr]overlay=x=0:y={grad_y}:eof_action=pass[y0]")
        cur = "y0"
        for i, (s, e, _) in enumerate(subs):
            d = e - s
            fd = min(0.3, d / 4)
            fc.append(f"[{7 + i}:v]format=rgba,fade=t=in:st={s:.3f}:d={fd:.3f}:alpha=1,"
                      f"fade=t=out:st={e - fd:.3f}:d={fd:.3f}:alpha=1[s{i}]")
            fc.append(f"[{cur}][s{i}]overlay=x=0:y={sub_y[i]}:eof_action=pass[z{i}]")
            cur = f"z{i}"
    fc.append(f"[{cur}]fade=t=in:st=0:d=1.5,fade=t=out:st={total - 2.2:.3f}:d=2.2,format=yuv420p[v]")
    script = os.path.join(work, "graph.txt")
    with open(script, "w") as f:
        f.write(";\n".join(fc))
    enc = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.decode()
    venc = ["-c:v", "libx264", "-preset", opts.get("--preset", "faster"), "-crf", "18", "-profile:v", "high"] \
        if "libx264" in enc else ["-c:v", "mpeg4", "-q:v", "2"]
    ver = re.search(r"ffmpeg version n?(\d+)", subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE).stdout.decode())
    graph_opt = ["-/filter_complex", script] if ver and int(ver.group(1)) >= 7 else ["-filter_complex_script", script]
    cmd = ["ffmpeg", "-v", "error", "-stats", "-y"] + inputs + [
        *graph_opt, "-map", "[v]", "-map", "1:a", *venc,
        "-c:a", "aac", "-b:a", "256k", "-t", f"{total:.3f}", "-movflags", "+faststart", out_path]
    with open(os.path.join(work, "cmd.json"), "w") as f:
        json.dump(cmd, f, ensure_ascii=False)
    r = subprocess.run(cmd, stderr=subprocess.PIPE)
    if r.returncode != 0:
        err = r.stderr.decode(errors="replace").replace("\r", "\n").splitlines()
        sys.stderr.write("\n".join([ln for ln in err if not ln.startswith("frame=")][-15:]) + "\n")
        raise SystemExit(f"final render failed (code {r.returncode})")
    report = dict(video=video, playback=playback, shift=g["shift"], tempo=g["tempo"], offset=g["offset"],
                  match=g["score"], drift_ms=spread * 1000, cents=[round(float(c), 1) for c in all_cents],
                  structure=info, sections=[(None if math.isinf(a) else a, None if math.isinf(b) else b)
                                            for a, b, _ in sections],
                  intro=intro, outro=outro, subtitles=len(subs), rubberband=rubber)
    with open(os.path.join(work, "report.json"), "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    shutil.copy(os.path.join(work, "report.json"), os.path.join(out_dir, "daf_report.json"))
    log("")
    log("DONE ->", out_path)
    log(f"key {g['shift']:+d} | tempo x{g['tempo']:.3f} | match {g['score']:.2f} | lyrics {len(subs)}/{len(lyrics)}")
    if "--keep" not in opts:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
