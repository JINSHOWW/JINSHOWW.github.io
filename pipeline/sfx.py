"""효과음·배경음. 기본은 numpy 로 직접 합성 (외부 음원 없음 → 저작권 문제 없음).
더 좋은 무료 음원을 쓰려면 assets/sfx/<이름>.wav 를 두고 assets/sfx/SOURCES.md 에
'- <이름>.wav: 출처 URL, 라이선스' 한 줄을 적는다. 출처 줄이 없으면 쓰지 않는다.

사용: python3 pipeline/sfx.py            # 전부 생성해 pipeline/.cache/sfx/ 에 저장
"""
import sys

import numpy as np

from common import CACHE, ROOT

SR = 48000
RNG = np.random.default_rng(7)
BEDS = {"wind", "night", "rain", "fire", "stream", "drone"}
SHOTS = {"footsteps", "heartbeat", "bell", "thud"}


def _brown(n):
    x = np.cumsum(RNG.standard_normal(n))
    x -= np.convolve(x, np.ones(4800) / 4800, mode="same")  # 직류 성분 제거
    return x / (np.abs(x).max() + 1e-9)


def _lowpass(x, a):
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):  # 짧은 음원만 만드므로 단순 루프로 충분
        acc += a * (x[i] - acc)
        y[i] = acc
    return y


def _onepole_scipy(x, a):
    from scipy.signal import lfilter  # 있으면 빠르게
    return lfilter([a], [1, a - 1], x)


def lp(x, a):
    try:
        return _onepole_scipy(x, a)
    except ImportError:
        return _lowpass(x, a)


def _loopable(x, fade=SR):
    """앞뒤를 겹쳐 이음매 없는 루프로 만든다."""
    head, tail = x[:fade], x[-fade:]
    r = np.linspace(0, 1, fade)
    x = x[fade:].copy()
    x[-fade:] = tail * (1 - r) + head * r
    return x


def synth(name, sec=20):
    n = SR * sec
    t = np.arange(n) / SR
    if name == "wind":
        lfo = 0.55 + 0.45 * np.sin(2 * np.pi * 0.07 * t) * np.sin(2 * np.pi * 0.023 * t + 1)
        x = _brown(n) * lfo + 0.15 * lp(RNG.standard_normal(n), 0.05) * lfo ** 2
    elif name == "night":
        x = 0.4 * _brown(n)
        for _ in range(sec * 2):  # 멀리서 우는 벌레
            s = RNG.integers(0, n - SR)
            k = np.arange(int(0.25 * SR))
            f = RNG.uniform(3800, 4600)
            chirp = np.sin(2 * np.pi * f * k / SR) * (np.sin(2 * np.pi * 28 * k / SR) > 0.3)
            x[s:s + len(k)] += 0.05 * chirp * np.hanning(len(k))
    elif name == "rain":
        hiss = RNG.standard_normal(n)
        x = 0.35 * (hiss - lp(hiss, 0.15)) + 0.25 * lp(RNG.standard_normal(n), 0.1)
        for s in RNG.integers(0, n - 400, sec * 60):  # 빗방울
            k = np.arange(300)
            x[s:s + 300] += RNG.uniform(0.05, 0.25) * RNG.standard_normal(300) * np.exp(-k / 40)
    elif name == "fire":
        x = 0.5 * lp(RNG.standard_normal(n), 0.02)
        for s in RNG.integers(0, n - 800, sec * 25):  # 장작 튀는 소리
            k = np.arange(600)
            x[s:s + 600] += RNG.uniform(0.1, 0.6) * RNG.standard_normal(600) * np.exp(-k / RNG.uniform(20, 80))
    elif name == "stream":
        x = 0.5 * lp(RNG.standard_normal(n), 0.3) * (0.7 + 0.3 * np.sin(2 * np.pi * 0.3 * t))
    elif name == "drone":
        x = (0.5 * np.sin(2 * np.pi * 55 * t) + 0.3 * np.sin(2 * np.pi * 82.7 * t + 0.4)
             + 0.25 * _brown(n)) * (0.8 + 0.2 * np.sin(2 * np.pi * 0.05 * t))
    elif name == "footsteps":
        n = SR * 5
        x = np.zeros(n)
        for i in range(7):
            s = int((0.3 + i * 0.62 + RNG.uniform(-0.04, 0.04)) * SR)
            k = np.arange(int(0.18 * SR))
            step = lp(RNG.standard_normal(len(k)), 0.04) * np.exp(-k / (0.035 * SR))
            x[s:s + len(k)] += step * (0.6 + 0.4 * i / 7)
    elif name == "heartbeat":
        n = SR * 5
        x = np.zeros(n)
        k = np.arange(int(0.15 * SR))
        beat = np.sin(2 * np.pi * 50 * k / SR) * np.exp(-k / (0.04 * SR))
        for i in range(6):
            s = int((0.2 + i * 0.8) * SR)
            x[s:s + len(k)] += beat
            x[s + int(0.25 * SR):s + int(0.25 * SR) + len(k)] += 0.7 * beat
    elif name == "bell":
        n = SR * 8
        t = np.arange(n) / SR
        x = sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t / d)
                for f, a, d in ((110, 1, 4), (221.5, .6, 3), (297, .4, 2.2), (412, .25, 1.5), (590, .15, 1)))
        x *= 1 + 0.1 * np.sin(2 * np.pi * 1.3 * t)  # 맥놀이
    elif name == "thud":
        n = SR * 2
        k = np.arange(n)
        x = np.sin(2 * np.pi * 45 * k / SR) * np.exp(-k / (0.12 * SR)) + 0.3 * lp(RNG.standard_normal(n), 0.03) * np.exp(-k / (0.05 * SR))
    else:
        raise ValueError(f"모르는 효과음: {name} (가능: {sorted(BEDS | SHOTS)})")
    if name in BEDS:
        x = _loopable(x)
    return 0.7 * x / (np.abs(x).max() + 1e-9)


def user_asset(name):
    """assets/sfx 에 출처가 기록된 파일이 있으면 그 경로와 출처를 돌려준다."""
    f = ROOT / "assets" / "sfx" / f"{name}.wav"
    src = ROOT / "assets" / "sfx" / "SOURCES.md"
    if f.exists() and src.exists():
        for line in src.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(f"- {name}.wav:"):
                return f, line.split(":", 1)[1].strip()
    return None, None


def get(name):
    """(경로, 출처 설명)"""
    f, credit = user_asset(name)
    if f:
        return f, credit
    out = CACHE / "sfx" / f"{name}.wav"
    if not out.exists():
        import wave
        out.parent.mkdir(parents=True, exist_ok=True)
        x = synth(name)
        with wave.open(str(out), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes((x * 32767).astype("<i2").tobytes())
    return out, "자체 합성 (pipeline/sfx.py, numpy 노이즈·사인파 합성, 외부 음원 미사용)"


if __name__ == "__main__":
    for nm in sorted(BEDS | SHOTS) if len(sys.argv) == 1 else sys.argv[1:]:
        print(nm, get(nm)[0])
