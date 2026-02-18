"""Color model conversions — RGB, HSV, HSL, CMYK, Lab, Oklab."""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..core.color import Color


# ============================================================================
# Extended Color Models
# ============================================================================

@dataclass(frozen=True)
class HSV:
    """Hue [0-360], Saturation [0-1], Value [0-1], Alpha [0-1]."""
    h: float = 0.0
    s: float = 0.0
    v: float = 0.0
    a: float = 1.0


@dataclass(frozen=True)
class HSL:
    """Hue [0-360], Saturation [0-1], Lightness [0-1], Alpha [0-1]."""
    h: float = 0.0
    s: float = 0.0
    l: float = 0.0
    a: float = 1.0


@dataclass(frozen=True)
class CMYK:
    """Cyan, Magenta, Yellow, Key(Black) all in [0-1]."""
    c: float = 0.0
    m: float = 0.0
    y: float = 0.0
    k: float = 1.0


@dataclass(frozen=True)
class LabColor:
    """CIE Lab — L [0-100], a [-128,127], b [-128,127]."""
    L: float = 0.0
    a: float = 0.0
    b: float = 0.0


@dataclass(frozen=True)
class OklabColor:
    """Oklab perceptual color — L [0-1], a ~[-0.4,0.4], b ~[-0.4,0.4]."""
    L: float = 0.0
    a: float = 0.0
    b: float = 0.0


# ============================================================================
# Conversion Functions
# ============================================================================

def rgb_to_hsv(r: float, g: float, b: float) -> tuple[float, float, float]:
    """RGB [0-1] → HSV (H in 0-360, S/V in 0-1)."""
    mx = max(r, g, b)
    mn = min(r, g, b)
    d = mx - mn
    v = mx
    s = d / mx if mx > 0 else 0.0
    if d == 0:
        h = 0.0
    elif mx == r:
        h = 60.0 * (((g - b) / d) % 6)
    elif mx == g:
        h = 60.0 * (((b - r) / d) + 2)
    else:
        h = 60.0 * (((r - g) / d) + 4)
    if h < 0:
        h += 360.0
    return h, s, v


def hsv_to_rgb(h: float, s: float, v: float) -> tuple[float, float, float]:
    """HSV (H 0-360, S/V 0-1) → RGB [0-1]."""
    h = h % 360
    c = v * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = v - c
    if h < 60:
        r, g, b = c, x, 0
    elif h < 120:
        r, g, b = x, c, 0
    elif h < 180:
        r, g, b = 0, c, x
    elif h < 240:
        r, g, b = 0, x, c
    elif h < 300:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x
    return r + m, g + m, b + m


def rgb_to_hsl(r: float, g: float, b: float) -> tuple[float, float, float]:
    """RGB [0-1] → HSL (H 0-360, S/L 0-1)."""
    mx = max(r, g, b)
    mn = min(r, g, b)
    l = (mx + mn) / 2.0
    d = mx - mn
    if d == 0:
        return 0.0, 0.0, l
    s = d / (1 - abs(2 * l - 1)) if (1 - abs(2 * l - 1)) > 0 else 0
    if mx == r:
        h = 60.0 * (((g - b) / d) % 6)
    elif mx == g:
        h = 60.0 * (((b - r) / d) + 2)
    else:
        h = 60.0 * (((r - g) / d) + 4)
    if h < 0:
        h += 360.0
    return h, s, l


def hsl_to_rgb(h: float, s: float, l: float) -> tuple[float, float, float]:
    """HSL (H 0-360, S/L 0-1) → RGB [0-1]."""
    c = (1 - abs(2 * l - 1)) * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = l - c / 2
    h = h % 360
    if h < 60:
        r, g, b = c, x, 0
    elif h < 120:
        r, g, b = x, c, 0
    elif h < 180:
        r, g, b = 0, c, x
    elif h < 240:
        r, g, b = 0, x, c
    elif h < 300:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x
    return r + m, g + m, b + m


def rgb_to_cmyk(r: float, g: float, b: float) -> tuple[float, float, float, float]:
    """RGB [0-1] → CMYK [0-1]."""
    k = 1.0 - max(r, g, b)
    if k >= 1.0:
        return 0.0, 0.0, 0.0, 1.0
    inv = 1.0 / (1.0 - k)
    c = (1.0 - r - k) * inv
    m = (1.0 - g - k) * inv
    y = (1.0 - b - k) * inv
    return c, m, y, k


def cmyk_to_rgb(c: float, m: float, y: float, k: float) -> tuple[float, float, float]:
    """CMYK [0-1] → RGB [0-1]."""
    inv = 1.0 - k
    return (1.0 - c) * inv, (1.0 - m) * inv, (1.0 - y) * inv


# ---------- CIE Lab (D65) ---------------------------------------------------

_D65_X, _D65_Y, _D65_Z = 0.95047, 1.0, 1.08883


def _linear_to_xyz_mat(r: float, g: float, b: float) -> tuple[float, float, float]:
    """sRGB linear → CIE XYZ."""
    x = 0.4124564 * r + 0.3575761 * g + 0.1804375 * b
    y = 0.2126729 * r + 0.7151522 * g + 0.0721750 * b
    z = 0.0193339 * r + 0.1191920 * g + 0.9503041 * b
    return x, y, z


def _srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1.0 / 2.4)) - 0.055


def _lab_f(t: float) -> float:
    d = 6.0 / 29.0
    return t ** (1.0 / 3.0) if t > d ** 3 else t / (3 * d * d) + 4.0 / 29.0


def _lab_f_inv(t: float) -> float:
    d = 6.0 / 29.0
    return t ** 3 if t > d else 3 * d * d * (t - 4.0 / 29.0)


def rgb_to_lab(r: float, g: float, b: float) -> tuple[float, float, float]:
    """sRGB [0-1] → CIE Lab."""
    rl = _srgb_to_linear(r)
    gl = _srgb_to_linear(g)
    bl = _srgb_to_linear(b)
    x, y, z = _linear_to_xyz_mat(rl, gl, bl)
    fx = _lab_f(x / _D65_X)
    fy = _lab_f(y / _D65_Y)
    fz = _lab_f(z / _D65_Z)
    L = 116 * fy - 16
    a = 500 * (fx - fy)
    bv = 200 * (fy - fz)
    return L, a, bv


def lab_to_rgb(L: float, a: float, bv: float) -> tuple[float, float, float]:
    """CIE Lab → sRGB [0-1] (clamped)."""
    fy = (L + 16) / 116
    fx = a / 500 + fy
    fz = fy - bv / 200
    x = _D65_X * _lab_f_inv(fx)
    y = _D65_Y * _lab_f_inv(fy)
    z = _D65_Z * _lab_f_inv(fz)
    rl = 3.2404542 * x - 1.5371385 * y - 0.4985314 * z
    gl = -0.9692660 * x + 1.8760108 * y + 0.0415560 * z
    bl = 0.0556434 * x - 0.2040259 * y + 1.0572252 * z
    return (
        max(0.0, min(1.0, _linear_to_srgb(rl))),
        max(0.0, min(1.0, _linear_to_srgb(gl))),
        max(0.0, min(1.0, _linear_to_srgb(bl))),
    )


# ---------- Oklab (perceptual) -----------------------------------------------

def rgb_to_oklab(r: float, g: float, b: float) -> tuple[float, float, float]:
    """sRGB [0-1] → Oklab."""
    rl = _srgb_to_linear(r)
    gl = _srgb_to_linear(g)
    bl = _srgb_to_linear(b)
    l_ = 0.4122214708 * rl + 0.5363325363 * gl + 0.0514459929 * bl
    m_ = 0.2119034982 * rl + 0.6806995451 * gl + 0.1073969566 * bl
    s_ = 0.0883024619 * rl + 0.2817188376 * gl + 0.6299787005 * bl
    l_ = l_ ** (1.0 / 3.0) if l_ >= 0 else -((-l_) ** (1.0 / 3.0))
    m_ = m_ ** (1.0 / 3.0) if m_ >= 0 else -((-m_) ** (1.0 / 3.0))
    s_ = s_ ** (1.0 / 3.0) if s_ >= 0 else -((-s_) ** (1.0 / 3.0))
    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    bv = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    return L, a, bv


def oklab_to_rgb(L: float, a: float, bv: float) -> tuple[float, float, float]:
    """Oklab → sRGB [0-1] (clamped)."""
    l_ = L + 0.3963377774 * a + 0.2158037573 * bv
    m_ = L - 0.1055613458 * a - 0.0638541728 * bv
    s_ = L - 0.0894841775 * a - 1.2914855480 * bv
    l_ = l_ * l_ * l_
    m_ = m_ * m_ * m_
    s_ = s_ * s_ * s_
    rl = 4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_
    gl = -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_
    bl = -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_
    return (
        max(0.0, min(1.0, _linear_to_srgb(max(0, rl)))),
        max(0.0, min(1.0, _linear_to_srgb(max(0, gl)))),
        max(0.0, min(1.0, _linear_to_srgb(max(0, bl)))),
    )


# ---------- Convenience helpers on Color ------------------------------------

def color_to_hsv(c: Color) -> HSV:
    h, s, v = rgb_to_hsv(c.r, c.g, c.b)
    return HSV(h, s, v, c.a)


def hsv_to_color(hsv: HSV) -> Color:
    r, g, b = hsv_to_rgb(hsv.h, hsv.s, hsv.v)
    return Color(r, g, b, hsv.a)


def color_to_hsl(c: Color) -> HSL:
    h, s, l = rgb_to_hsl(c.r, c.g, c.b)
    return HSL(h, s, l, c.a)


def hsl_to_color(hsl: HSL) -> Color:
    r, g, b = hsl_to_rgb(hsl.h, hsl.s, hsl.l)
    return Color(r, g, b, hsl.a)


def color_to_cmyk(c: Color) -> CMYK:
    return CMYK(*rgb_to_cmyk(c.r, c.g, c.b))


def cmyk_to_color(cmyk: CMYK) -> Color:
    r, g, b = cmyk_to_rgb(cmyk.c, cmyk.m, cmyk.y, cmyk.k)
    return Color(r, g, b)


def color_to_lab(c: Color) -> LabColor:
    return LabColor(*rgb_to_lab(c.r, c.g, c.b))


def lab_to_color(lab: LabColor) -> Color:
    r, g, b = lab_to_rgb(lab.L, lab.a, lab.b)
    return Color(r, g, b)


def color_to_oklab(c: Color) -> OklabColor:
    return OklabColor(*rgb_to_oklab(c.r, c.g, c.b))


def oklab_to_color(ok: OklabColor) -> Color:
    r, g, b = oklab_to_rgb(ok.L, ok.a, ok.b)
    return Color(r, g, b)


# ============================================================================
# Perceptual interpolation (Oklab)
# ============================================================================

def perceptual_lerp(c1: Color, c2: Color, t: float) -> Color:
    """Interpolate two colours in Oklab for perceptually-uniform blending."""
    L1, a1, b1 = rgb_to_oklab(c1.r, c1.g, c1.b)
    L2, a2, b2 = rgb_to_oklab(c2.r, c2.g, c2.b)
    s = 1.0 - t
    r, g, b = oklab_to_rgb(L1 * s + L2 * t, a1 * s + a2 * t, b1 * s + b2 * t)
    alpha = c1.a * s + c2.a * t
    return Color(r, g, b, alpha)


# ============================================================================
# Contrast / Accessibility
# ============================================================================

def relative_luminance(c: Color) -> float:
    """WCAG 2.1 relative luminance."""
    def _c(v: float) -> float:
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * _c(c.r) + 0.7152 * _c(c.g) + 0.0722 * _c(c.b)


def contrast_ratio(c1: Color, c2: Color) -> float:
    """WCAG 2.1 contrast ratio (1 – 21)."""
    l1 = relative_luminance(c1)
    l2 = relative_luminance(c2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


# ============================================================================
# Color Temperature
# ============================================================================

def kelvin_to_color(kelvin: float) -> Color:
    """Approximate a blackbody colour temperature (1000-40000K)."""
    t = max(1000.0, min(40000.0, kelvin)) / 100.0
    if t <= 66:
        r = 1.0
    else:
        r = max(0.0, min(1.0, 1.29293618606 * ((t - 60) ** -0.1332047592)))
    if t <= 66:
        g = max(0.0, min(1.0, 0.39008157876 * math.log(t) - 0.63184144378))
    else:
        g = max(0.0, min(1.0, 1.12989086090 * ((t - 60) ** -0.0755148492)))
    if t >= 66:
        b = 1.0
    elif t <= 19:
        b = 0.0
    else:
        b = max(0.0, min(1.0, 0.54320678911 * math.log(t - 10) - 1.19625408914))
    return Color(r, g, b)
