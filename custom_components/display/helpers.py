"""Kelvin -> per-channel RGB gains (Tanner Helland blackbody fit)."""
from __future__ import annotations

import math

REFERENCE_KELVIN = 6500.0


def _clamp255(v: float) -> float:
    return max(0.0, min(255.0, v))


def _kelvin_to_rgb(kelvin: float) -> tuple[float, float, float]:
    t = max(1000.0, min(40000.0, kelvin)) / 100.0
    if t <= 66:
        r = 255.0
        g = 99.4708025861 * math.log(t) - 161.1195681661
    else:
        r = 329.698727446 * (t - 60) ** -0.1332047592
        g = 288.1221695283 * (t - 60) ** -0.0755148492
    if t >= 66:
        b = 255.0
    elif t <= 19:
        b = 0.0
    else:
        b = 138.5177312231 * math.log(t - 10) - 305.0447927307
    return _clamp255(r), _clamp255(g), _clamp255(b)


def rgb_gains(kelvin: float) -> tuple[float, float, float]:
    """Multipliers that move the white point from 6500 K to ``kelvin``.

    Normalized so the largest gain is 1.0 — channels are only ever attenuated,
    so white never clips: bluer dims red/green, warmer dims green/blue.
    """
    ref = _kelvin_to_rgb(REFERENCE_KELVIN)
    cur = _kelvin_to_rgb(kelvin)
    gains = [c / r for c, r in zip(cur, ref)]
    peak = max(gains)
    r, g, b = (round(x / peak, 4) for x in gains)
    return r, g, b
