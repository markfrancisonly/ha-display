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


# --- Bradford chromatic adaptation ---------------------------------------
# Diagonal gains can only scale channels; at deep warmth that flips
# cyan-ish blues to green (B crushed, G kept). A full 3x3 adaptation mixes
# channels the way perception does, so hues track: blues dim toward
# violet-grey instead. Same feColorMatrix, same per-pixel cost.

_RGB2XYZ = (
    (0.4124564, 0.3575761, 0.1804375),
    (0.2126729, 0.7151522, 0.0721750),
    (0.0193339, 0.1191920, 0.9503041),
)
_XYZ2RGB = (
    (3.2404542, -1.5371385, -0.4985314),
    (-0.9692660, 1.8760108, 0.0415560),
    (0.0556434, -0.2040259, 1.0572252),
)
_BRADFORD = (
    (0.8951, 0.2664, -0.1614),
    (-0.7502, 1.7135, 0.0367),
    (0.0389, -0.0685, 1.0296),
)
_BRADFORD_INV = (
    (0.9869929, -0.1470543, 0.1599627),
    (0.4323053, 0.5183603, 0.0492912),
    (-0.0085287, 0.0400428, 0.9684867),
)


def _mat_mul(a, b):
    return [
        [sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)]
        for i in range(3)
    ]


def _mat_vec(m, v):
    return [sum(m[i][k] * v[k] for k in range(3)) for i in range(3)]


def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def adaptation_matrix(white: tuple[float, float, float]) -> list[float]:
    """Row-major 3x3 Bradford adaptation toward the target ``white``.

    ``white`` is the gamma-encoded RGB the display's white should render as
    (peak-normalized, attenuation only) — from the blackbody locus for a
    kelvin white point, or anywhere in the gamut for an hs tint. Rows are
    rescaled so WHITE renders exactly as the diagonal gains always have —
    neutrals are unchanged from the diagonal era; only saturated colors get
    the channel mixing that keeps hues tracking. A zero target channel zeroes
    its row (degenerates to the diagonal behavior). The matrix is applied to
    gamma-encoded values (display-LUT semantics), matching how the gains have
    always been applied.
    """
    w_lin = [_srgb_to_linear(g) for g in white]
    src = _mat_vec(_BRADFORD, _mat_vec(_RGB2XYZ, (1.0, 1.0, 1.0)))
    dst = _mat_vec(_BRADFORD, _mat_vec(_RGB2XYZ, w_lin))
    scale = [d / s if abs(s) > 1e-9 else 0.0 for d, s in zip(dst, src)]
    a_scaled = [[_BRADFORD[i][j] * scale[i] for j in range(3)] for i in range(3)]
    cat = _mat_mul(_BRADFORD_INV, a_scaled)
    m = _mat_mul(_XYZ2RGB, _mat_mul(cat, _RGB2XYZ))
    flat = []
    for i in range(3):
        row_white = sum(m[i])
        k = white[i] / row_white if abs(row_white) > 1e-6 else 0.0
        flat.extend(round(x * k, 4) for x in m[i])
    return flat


def rgb_matrix(kelvin: float) -> list[float]:
    """Bradford adaptation from 6500 K to ``kelvin`` (blackbody white)."""
    return adaptation_matrix(rgb_gains(kelvin))
