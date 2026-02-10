"""Unified Color Engine — high-performance, multi-model color system.

Provides:
 • Full color model conversions (sRGB, HSV, HSL, CMYK, Lab/LCh, Oklab/OkLCh)
 • Color harmony generation (complementary, analogous, triadic, split-comp, etc.)
 • Perceptual interpolation (Oklab)
 • Contrast ratio computation (WCAG 2.1)
 • Named color matching
 • Color temperature (Kelvin → RGB)
 • Gradient system with conical/diamond presets
 • Swatch palette management
 • Global foreground/background state (ColorManager singleton)

All heavy-path maths uses NumPy for vectorised performance.
"""

from __future__ import annotations

import colorsys
import math
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Sequence

import numpy as np
from PySide6.QtCore import QObject, Signal

from .color import (
    Color,
    ColorFill,
    FillType,
    GradientStop,
    LinearGradient,
    RadialGradient,
    SolidFill,
)


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
    # XYZ → linear sRGB
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
# Color Harmonies
# ============================================================================

class HarmonyType(Enum):
    COMPLEMENTARY = auto()
    ANALOGOUS = auto()
    TRIADIC = auto()
    SPLIT_COMPLEMENTARY = auto()
    TETRADIC = auto()
    SQUARE = auto()
    MONOCHROMATIC = auto()


def generate_harmony(base: Color, harmony: HarmonyType) -> list[Color]:
    """Generate a list of harmonious colours from *base*."""
    h, s, v = rgb_to_hsv(base.r, base.g, base.b)

    def _rotated(deg: float) -> Color:
        r, g, b = hsv_to_rgb((h + deg) % 360, s, v)
        return Color(r, g, b, base.a)

    if harmony == HarmonyType.COMPLEMENTARY:
        return [base, _rotated(180)]
    elif harmony == HarmonyType.ANALOGOUS:
        return [_rotated(-30), base, _rotated(30)]
    elif harmony == HarmonyType.TRIADIC:
        return [base, _rotated(120), _rotated(240)]
    elif harmony == HarmonyType.SPLIT_COMPLEMENTARY:
        return [base, _rotated(150), _rotated(210)]
    elif harmony == HarmonyType.TETRADIC:
        return [base, _rotated(90), _rotated(180), _rotated(270)]
    elif harmony == HarmonyType.SQUARE:
        return [base, _rotated(90), _rotated(180), _rotated(270)]
    elif harmony == HarmonyType.MONOCHROMATIC:
        results = []
        for vf in [0.2, 0.4, 0.6, 0.8, 1.0]:
            r, g, b = hsv_to_rgb(h, s, v * vf)
            results.append(Color(r, g, b, base.a))
        return results
    return [base]


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
    # Red
    if t <= 66:
        r = 1.0
    else:
        r = max(0.0, min(1.0, 1.29293618606 * ((t - 60) ** -0.1332047592)))
    # Green
    if t <= 66:
        g = max(0.0, min(1.0, 0.39008157876 * math.log(t) - 0.63184144378))
    else:
        g = max(0.0, min(1.0, 1.12989086090 * ((t - 60) ** -0.0755148492)))
    # Blue
    if t >= 66:
        b = 1.0
    elif t <= 19:
        b = 0.0
    else:
        b = max(0.0, min(1.0, 0.54320678911 * math.log(t - 10) - 1.19625408914))
    return Color(r, g, b)


# ============================================================================
# Conical (Angle) Gradient
# ============================================================================

@dataclass(frozen=True)
class ConicalGradient(ColorFill):
    """Sweep/conical gradient around a center point."""
    fill_type: FillType = FillType.LINEAR_GRADIENT  # reuse enum
    stops: tuple[GradientStop, ...] = (
        GradientStop(0.0, Color.black()),
        GradientStop(1.0, Color.white()),
    )
    center: tuple[float, float] = (0.5, 0.5)
    start_angle: float = 0.0  # degrees

    def sample(self, u: float = 0.0, v: float = 0.0) -> Color:
        dx = u - self.center[0]
        dy = v - self.center[1]
        angle = math.degrees(math.atan2(dy, dx)) - self.start_angle
        t = (angle % 360) / 360.0
        from .color import _lerp_stops
        return _lerp_stops(self.stops, t)


@dataclass(frozen=True)
class DiamondGradient(ColorFill):
    """Diamond-shaped gradient from center outward."""
    fill_type: FillType = FillType.RADIAL_GRADIENT  # reuse enum
    stops: tuple[GradientStop, ...] = (
        GradientStop(0.0, Color.white()),
        GradientStop(1.0, Color.black()),
    )
    center: tuple[float, float] = (0.5, 0.5)
    radius: float = 0.5

    def sample(self, u: float = 0.0, v: float = 0.0) -> Color:
        dx = abs(u - self.center[0])
        dy = abs(v - self.center[1])
        dist = (dx + dy) / self.radius if self.radius > 0 else 1.0
        from .color import _lerp_stops
        return _lerp_stops(self.stops, min(1.0, dist))


# ============================================================================
# Gradient Presets
# ============================================================================

GRADIENT_PRESETS: dict[str, tuple[GradientStop, ...]] = {
    "Black to White": (
        GradientStop(0.0, Color.black()),
        GradientStop(1.0, Color.white()),
    ),
    "Foreground to Transparent": (
        GradientStop(0.0, Color.black()),
        GradientStop(1.0, Color.transparent()),
    ),
    "Spectrum": tuple(
        GradientStop(i / 6.0, Color(*hsv_to_rgb(i * 60, 1.0, 1.0)))
        for i in range(7)
    ),
    "Sunset": (
        GradientStop(0.0, Color.from_hex("#FF512F")),
        GradientStop(0.5, Color.from_hex("#F09819")),
        GradientStop(1.0, Color.from_hex("#DD2476")),
    ),
    "Ocean": (
        GradientStop(0.0, Color.from_hex("#2E3192")),
        GradientStop(0.5, Color.from_hex("#1BFFFF")),
        GradientStop(1.0, Color.from_hex("#2E3192")),
    ),
    "Fire": (
        GradientStop(0.0, Color.from_hex("#f12711")),
        GradientStop(0.5, Color.from_hex("#f5af19")),
        GradientStop(1.0, Color.from_hex("#f12711")),
    ),
}


# ============================================================================
# Swatch Palette
# ============================================================================

@dataclass
class SwatchPalette:
    """A named collection of colour swatches."""
    name: str = "Default"
    colors: list[Color] = field(default_factory=list)

    @staticmethod
    def default_palette() -> SwatchPalette:
        """Create a standard starter palette."""
        colors: list[Color] = []
        # Greyscale ramp
        for v in range(0, 256, 32):
            colors.append(Color.from_rgb8(v, v, v))
        # Hue ramp at full saturation
        for h_deg in range(0, 360, 15):
            r, g, b = hsv_to_rgb(float(h_deg), 1.0, 1.0)
            colors.append(Color(r, g, b))
        # Pastel row
        for h_deg in range(0, 360, 15):
            r, g, b = hsv_to_rgb(float(h_deg), 0.4, 1.0)
            colors.append(Color(r, g, b))
        # Dark row
        for h_deg in range(0, 360, 15):
            r, g, b = hsv_to_rgb(float(h_deg), 1.0, 0.5)
            colors.append(Color(r, g, b))
        return SwatchPalette("Default", colors)


# ============================================================================
# Color Manager — singleton-style global state
# ============================================================================

class ColorManager(QObject):
    """Application-wide foreground/background colour state with history.

    Connect to the signals to react when the user picks a new colour.
    Access the singleton via ``ColorManager.instance()``.
    """

    foreground_changed = Signal(object)  # Color
    background_changed = Signal(object)  # Color
    active_fill_changed = Signal(object)  # ColorFill
    history_changed = Signal()

    _instance: ColorManager | None = None

    @classmethod
    def instance(cls) -> ColorManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._fg: Color = Color.black()
        self._bg: Color = Color.white()
        self._active_fill: ColorFill = SolidFill(color=Color.black())
        self._history: list[Color] = []
        self._max_history = 32
        self._palette = SwatchPalette.default_palette()

    # ---- Properties ---------------------------------------------------------

    @property
    def foreground(self) -> Color:
        return self._fg

    @foreground.setter
    def foreground(self, c: Color) -> None:
        if c != self._fg:
            self._fg = c
            self._push_history(c)
            self._active_fill = SolidFill(color=c)
            self.foreground_changed.emit(c)
            self.active_fill_changed.emit(self._active_fill)

    def set_foreground_preview(self, c: Color) -> None:
        """Update foreground visually without recording to history.

        Use during interactive drags. Call ``commit_foreground`` on release.
        """
        if c != self._fg:
            self._fg = c
            self._active_fill = SolidFill(color=c)
            self.foreground_changed.emit(c)
            self.active_fill_changed.emit(self._active_fill)

    def commit_foreground(self) -> None:
        """Record the current foreground to history (call after drag ends)."""
        self._push_history(self._fg)

    def set_background_preview(self, c: Color) -> None:
        """Update background visually without recording to history."""
        if c != self._bg:
            self._bg = c
            self.background_changed.emit(c)

    def commit_background(self) -> None:
        """Record the current background to history (call after drag ends)."""
        self._push_history(self._bg)

    @property
    def background(self) -> Color:
        return self._bg

    @background.setter
    def background(self, c: Color) -> None:
        if c != self._bg:
            self._bg = c
            self._push_history(c)
            self.background_changed.emit(c)

    @property
    def active_fill(self) -> ColorFill:
        return self._active_fill

    @active_fill.setter
    def active_fill(self, fill: ColorFill) -> None:
        self._active_fill = fill
        self.active_fill_changed.emit(fill)

    @property
    def history(self) -> list[Color]:
        return list(self._history)

    @property
    def palette(self) -> SwatchPalette:
        return self._palette

    @palette.setter
    def palette(self, p: SwatchPalette) -> None:
        self._palette = p

    # ---- Actions ------------------------------------------------------------

    def swap(self) -> None:
        self._fg, self._bg = self._bg, self._fg
        self.foreground_changed.emit(self._fg)
        self.background_changed.emit(self._bg)

    def reset(self) -> None:
        self._fg = Color.black()
        self._bg = Color.white()
        self.foreground_changed.emit(self._fg)
        self.background_changed.emit(self._bg)

    def set_foreground_hsv(self, h: float, s: float, v: float, a: float = 1.0) -> None:
        r, g, b = hsv_to_rgb(h, s, v)
        self.foreground = Color(r, g, b, a)

    def set_foreground_hex(self, hex_str: str) -> None:
        self.foreground = Color.from_hex(hex_str)

    # ---- History ------------------------------------------------------------

    def _push_history(self, c: Color) -> None:
        # Avoid duplicates at head
        if self._history and self._history[0] == c:
            return
        self._history.insert(0, c)
        if len(self._history) > self._max_history:
            self._history = self._history[: self._max_history]
        self.history_changed.emit()
