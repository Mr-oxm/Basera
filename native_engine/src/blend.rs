//! SIMD-accelerated blend kernels for all major Photoshop-compatible modes.
//!
//! Each function operates on raw `&mut [f32]` pixel slices (RGBA interleaved)
//! to avoid per-pixel overhead.  The compiler auto-vectorises these loops to
//! AVX2 on x86-64 and NEON on ARM when built with `opt-level = 3`.

/// Blend mode IDs match `BlendMode(Enum)` values from Python (1-based auto()).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum BlendMode {
    Normal = 1,
    Dissolve = 2,
    Darken = 3,
    Multiply = 4,
    ColorBurn = 5,
    LinearBurn = 6,
    DarkerColor = 7,
    Lighten = 8,
    Screen = 9,
    ColorDodge = 10,
    LinearDodge = 11,
    LighterColor = 12,
    Overlay = 13,
    SoftLight = 14,
    HardLight = 15,
    VividLight = 16,
    LinearLight = 17,
    PinLight = 18,
    HardMix = 19,
    Difference = 20,
    Exclusion = 21,
    Subtract = 22,
    Divide = 23,
    Hue = 24,
    Saturation = 25,
    Color = 26,
    Luminosity = 27,
}

impl BlendMode {
    pub fn from_u8(v: u8) -> Self {
        match v {
            1 => Self::Normal,
            2 => Self::Dissolve,
            3 => Self::Darken,
            4 => Self::Multiply,
            5 => Self::ColorBurn,
            6 => Self::LinearBurn,
            7 => Self::DarkerColor,
            8 => Self::Lighten,
            9 => Self::Screen,
            10 => Self::ColorDodge,
            11 => Self::LinearDodge,
            12 => Self::LighterColor,
            13 => Self::Overlay,
            14 => Self::SoftLight,
            15 => Self::HardLight,
            16 => Self::VividLight,
            17 => Self::LinearLight,
            18 => Self::PinLight,
            19 => Self::HardMix,
            20 => Self::Difference,
            21 => Self::Exclusion,
            22 => Self::Subtract,
            23 => Self::Divide,
            24 => Self::Hue,
            25 => Self::Saturation,
            26 => Self::Color,
            27 => Self::Luminosity,
            _ => Self::Normal,
        }
    }
}

// ---------------------------------------------------------------
// Per-channel blend functions (inlined for auto-vectorisation)
// ---------------------------------------------------------------

#[inline(always)]
fn blend_multiply(b: f32, s: f32) -> f32 { b * s }

#[inline(always)]
fn blend_screen(b: f32, s: f32) -> f32 { 1.0 - (1.0 - b) * (1.0 - s) }

#[inline(always)]
fn blend_overlay(b: f32, s: f32) -> f32 {
    if b < 0.5 { 2.0 * b * s } else { 1.0 - 2.0 * (1.0 - b) * (1.0 - s) }
}

#[inline(always)]
fn blend_darken(b: f32, s: f32) -> f32 { b.min(s) }

#[inline(always)]
fn blend_lighten(b: f32, s: f32) -> f32 { b.max(s) }

#[inline(always)]
fn blend_color_dodge(b: f32, s: f32) -> f32 {
    if s >= 1.0 { 1.0 } else { (b / (1.0 - s)).min(1.0) }
}

#[inline(always)]
fn blend_color_burn(b: f32, s: f32) -> f32 {
    if s <= 0.0 { 0.0 } else { (1.0 - (1.0 - b) / s).max(0.0) }
}

#[inline(always)]
fn blend_hard_light(b: f32, s: f32) -> f32 {
    if s < 0.5 { 2.0 * b * s } else { 1.0 - 2.0 * (1.0 - b) * (1.0 - s) }
}

#[inline(always)]
fn blend_soft_light(b: f32, s: f32) -> f32 {
    if s <= 0.5 {
        b - (1.0 - 2.0 * s) * b * (1.0 - b)
    } else {
        b + (2.0 * s - 1.0) * (b.max(0.0).sqrt() - b)
    }
}

#[inline(always)]
fn blend_difference(b: f32, s: f32) -> f32 { (b - s).abs() }

#[inline(always)]
fn blend_exclusion(b: f32, s: f32) -> f32 { b + s - 2.0 * b * s }

#[inline(always)]
fn blend_linear_burn(b: f32, s: f32) -> f32 { (b + s - 1.0).max(0.0) }

#[inline(always)]
fn blend_linear_dodge(b: f32, s: f32) -> f32 { (b + s).min(1.0) }

#[inline(always)]
fn blend_vivid_light(b: f32, s: f32) -> f32 {
    if s < 0.5 { blend_color_burn(b, 2.0 * s) } else { blend_color_dodge(b, 2.0 * s - 1.0) }
}

#[inline(always)]
fn blend_linear_light(b: f32, s: f32) -> f32 {
    (b + 2.0 * s - 1.0).clamp(0.0, 1.0)
}

#[inline(always)]
fn blend_pin_light(b: f32, s: f32) -> f32 {
    if s < 0.5 { b.min(2.0 * s) } else { b.max(2.0 * s - 1.0) }
}

#[inline(always)]
fn blend_hard_mix(b: f32, s: f32) -> f32 {
    if b + s >= 1.0 { 1.0 } else { 0.0 }
}

#[inline(always)]
fn blend_divide(b: f32, s: f32) -> f32 {
    if s <= 0.0001 { 1.0 } else { (b / s).min(1.0) }
}

#[inline(always)]
fn blend_subtract(b: f32, s: f32) -> f32 { (b - s).max(0.0) }

/// Apply per-channel blend formula.  HSL-based modes (Hue, Saturation,
/// Color, Luminosity) fall back to Normal since they require multi-channel
/// logic that can't be expressed per-component.
#[inline(always)]
fn apply_blend(mode: BlendMode, b: f32, s: f32) -> f32 {
    match mode {
        BlendMode::Normal | BlendMode::Dissolve
        | BlendMode::DarkerColor | BlendMode::LighterColor
        | BlendMode::Hue | BlendMode::Saturation
        | BlendMode::Color | BlendMode::Luminosity => s,
        BlendMode::Multiply => blend_multiply(b, s),
        BlendMode::Screen => blend_screen(b, s),
        BlendMode::Overlay => blend_overlay(b, s),
        BlendMode::Darken => blend_darken(b, s),
        BlendMode::Lighten => blend_lighten(b, s),
        BlendMode::ColorDodge => blend_color_dodge(b, s),
        BlendMode::ColorBurn => blend_color_burn(b, s),
        BlendMode::HardLight => blend_hard_light(b, s),
        BlendMode::SoftLight => blend_soft_light(b, s),
        BlendMode::Difference => blend_difference(b, s),
        BlendMode::Exclusion => blend_exclusion(b, s),
        BlendMode::LinearBurn => blend_linear_burn(b, s),
        BlendMode::LinearDodge => blend_linear_dodge(b, s),
        BlendMode::VividLight => blend_vivid_light(b, s),
        BlendMode::LinearLight => blend_linear_light(b, s),
        BlendMode::PinLight => blend_pin_light(b, s),
        BlendMode::HardMix => blend_hard_mix(b, s),
        BlendMode::Divide => blend_divide(b, s),
        BlendMode::Subtract => blend_subtract(b, s),
    }
}

// ---------------------------------------------------------------
// Porter-Duff "over" compositing
// ---------------------------------------------------------------

/// Blend a single row of pixels: `dst[0..w*4]` and `src[0..w*4]`.
///
/// This is the hot inner loop.  Keeping it as a standalone function on
/// contiguous slices lets the compiler auto-vectorise with AVX2/NEON.
pub fn blend_row(
    dst: &mut [f32],
    src: &[f32],
    w: usize,
    mode: BlendMode,
    opacity: f32,
    mask: Option<&[f32]>,
) {
    debug_assert!(dst.len() >= w * 4);
    debug_assert!(src.len() >= w * 4);

    for i in 0..w {
        let off = i * 4;
        let mut sa = src[off + 3] * opacity;

        if let Some(m) = mask {
            if i < m.len() {
                sa *= m[i];
            } else {
                sa = 0.0;
            }
        }

        if sa <= 0.0 {
            continue;
        }

        let da = dst[off + 3];
        let inv_sa = 1.0 - sa;
        let out_a = sa + da * inv_sa;

        if out_a <= 1e-10 {
            continue;
        }

        let inv_out = 1.0 / out_a;

        if mode == BlendMode::Normal {
            for c in 0..3 {
                dst[off + c] = (src[off + c] * sa + dst[off + c] * da * inv_sa) * inv_out;
            }
        } else {
            for c in 0..3 {
                let blended = apply_blend(mode, dst[off + c], src[off + c]);
                dst[off + c] = (blended * sa + dst[off + c] * da * inv_sa) * inv_out;
            }
        }
        dst[off + 3] = out_a;
    }
}

/// Blend entire same-sized `src` onto `dst` (both w*h*4 flat slices).
pub fn blend_region(
    dst: &mut [f32],
    src: &[f32],
    w: usize,
    h: usize,
    mode: BlendMode,
    opacity: f32,
    mask: Option<&[f32]>,
) {
    for row in 0..h {
        let off = row * w * 4;
        let mask_row = mask.map(|m| {
            let moff = row * w;
            let end = (moff + w).min(m.len());
            &m[moff..end]
        });
        blend_row(
            &mut dst[off..off + w * 4],
            &src[off..off + w * 4],
            w,
            mode,
            opacity,
            mask_row,
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_normal_blend_opaque() {
        let mut dst = [0.0f32, 0.0, 0.0, 1.0];
        let src = [1.0f32, 0.0, 0.0, 1.0];
        blend_row(&mut dst, &src, 1, BlendMode::Normal, 1.0, None);
        assert!((dst[0] - 1.0).abs() < 1e-5);
        assert!((dst[3] - 1.0).abs() < 1e-5);
    }

    #[test]
    fn test_normal_blend_half_opacity() {
        let mut dst = [0.0, 0.0, 0.0, 1.0];
        let src = [1.0, 1.0, 1.0, 1.0];
        blend_row(&mut dst, &src, 1, BlendMode::Normal, 0.5, None);
        assert!((dst[0] - 0.5).abs() < 1e-4);
    }

    #[test]
    fn test_multiply() {
        let mut dst = [0.5, 0.5, 0.5, 1.0];
        let src = [0.5, 0.5, 0.5, 1.0];
        blend_row(&mut dst, &src, 1, BlendMode::Multiply, 1.0, None);
        assert!((dst[0] - 0.25).abs() < 1e-4);
    }

    #[test]
    fn test_screen() {
        let mut dst = [0.5, 0.5, 0.5, 1.0];
        let src = [0.5, 0.5, 0.5, 1.0];
        blend_row(&mut dst, &src, 1, BlendMode::Screen, 1.0, None);
        assert!((dst[0] - 0.75).abs() < 1e-4);
    }

    #[test]
    fn test_mask() {
        let mut dst = [0.0, 0.0, 0.0, 1.0];
        let src = [1.0, 1.0, 1.0, 1.0];
        let mask = [0.0f32];
        blend_row(&mut dst, &src, 1, BlendMode::Normal, 1.0, Some(&mask));
        assert!((dst[0] - 0.0).abs() < 1e-5);
    }
}
