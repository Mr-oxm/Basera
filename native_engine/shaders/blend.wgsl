// GPU blend compute shader — dispatches one thread per pixel.
//
// Push constants carry the blend mode, opacity, dimensions, and flags.
// Source and destination tiles are bound as storage buffers (RGBA f32).

struct Params {
    width: u32,
    height: u32,
    mode: u32,
    has_mask: u32,
    opacity: f32,
    _pad0: f32,
    _pad1: f32,
    _pad2: f32,
};

@group(0) @binding(0) var<storage, read_write> dst: array<vec4f>;
@group(0) @binding(1) var<storage, read>       src: array<vec4f>;
@group(0) @binding(2) var<storage, read>       mask_buf: array<f32>;
@group(0) @binding(3) var<uniform>             params: Params;

// ---------------------------------------------------------------
// Per-channel blend formulas
// ---------------------------------------------------------------

fn blend_normal(b: f32, s: f32) -> f32 { return s; }
fn blend_multiply(b: f32, s: f32) -> f32 { return b * s; }
fn blend_screen(b: f32, s: f32) -> f32 { return 1.0 - (1.0 - b) * (1.0 - s); }

fn blend_overlay(b: f32, s: f32) -> f32 {
    if (b < 0.5) { return 2.0 * b * s; }
    return 1.0 - 2.0 * (1.0 - b) * (1.0 - s);
}

fn blend_darken(b: f32, s: f32) -> f32 { return min(b, s); }
fn blend_lighten(b: f32, s: f32) -> f32 { return max(b, s); }

fn blend_color_dodge(b: f32, s: f32) -> f32 {
    if (s >= 1.0) { return 1.0; }
    return min(b / (1.0 - s), 1.0);
}

fn blend_color_burn(b: f32, s: f32) -> f32 {
    if (s <= 0.0) { return 0.0; }
    return max(1.0 - (1.0 - b) / s, 0.0);
}

fn blend_hard_light(b: f32, s: f32) -> f32 {
    if (s < 0.5) { return 2.0 * b * s; }
    return 1.0 - 2.0 * (1.0 - b) * (1.0 - s);
}

fn blend_soft_light(b: f32, s: f32) -> f32 {
    if (s <= 0.5) {
        return b - (1.0 - 2.0 * s) * b * (1.0 - b);
    }
    return b + (2.0 * s - 1.0) * (sqrt(max(b, 0.0)) - b);
}

fn blend_difference(b: f32, s: f32) -> f32 { return abs(b - s); }
fn blend_exclusion(b: f32, s: f32) -> f32 { return b + s - 2.0 * b * s; }
fn blend_linear_burn(b: f32, s: f32) -> f32 { return max(b + s - 1.0, 0.0); }
fn blend_linear_dodge(b: f32, s: f32) -> f32 { return min(b + s, 1.0); }

fn blend_vivid_light(b: f32, s: f32) -> f32 {
    if (s < 0.5) { return blend_color_burn(b, 2.0 * s); }
    return blend_color_dodge(b, 2.0 * s - 1.0);
}

fn blend_linear_light(b: f32, s: f32) -> f32 {
    return clamp(b + 2.0 * s - 1.0, 0.0, 1.0);
}

fn blend_pin_light(b: f32, s: f32) -> f32 {
    if (s < 0.5) { return min(b, 2.0 * s); }
    return max(b, 2.0 * s - 1.0);
}

fn blend_hard_mix(b: f32, s: f32) -> f32 {
    if (b + s >= 1.0) { return 1.0; }
    return 0.0;
}

fn blend_divide(b: f32, s: f32) -> f32 {
    if (s <= 0.0001) { return 1.0; }
    return min(b / s, 1.0);
}

fn blend_subtract(b: f32, s: f32) -> f32 { return max(b - s, 0.0); }

fn apply_blend(mode: u32, b: f32, s: f32) -> f32 {
    switch (mode) {
        case 1u:  { return blend_normal(b, s); }     // NORMAL
        case 3u:  { return blend_darken(b, s); }      // DARKEN
        case 4u:  { return blend_multiply(b, s); }    // MULTIPLY
        case 5u:  { return blend_color_burn(b, s); }   // COLOR_BURN
        case 6u:  { return blend_linear_burn(b, s); }  // LINEAR_BURN
        case 8u:  { return blend_lighten(b, s); }      // LIGHTEN
        case 9u:  { return blend_screen(b, s); }       // SCREEN
        case 10u: { return blend_color_dodge(b, s); }  // COLOR_DODGE
        case 11u: { return blend_linear_dodge(b, s); } // LINEAR_DODGE
        case 13u: { return blend_overlay(b, s); }      // OVERLAY
        case 14u: { return blend_soft_light(b, s); }   // SOFT_LIGHT
        case 15u: { return blend_hard_light(b, s); }   // HARD_LIGHT
        case 16u: { return blend_vivid_light(b, s); }  // VIVID_LIGHT
        case 17u: { return blend_linear_light(b, s); } // LINEAR_LIGHT
        case 18u: { return blend_pin_light(b, s); }    // PIN_LIGHT
        case 19u: { return blend_hard_mix(b, s); }     // HARD_MIX
        case 20u: { return blend_difference(b, s); }   // DIFFERENCE
        case 21u: { return blend_exclusion(b, s); }    // EXCLUSION
        case 22u: { return blend_subtract(b, s); }     // SUBTRACT
        case 23u: { return blend_divide(b, s); }       // DIVIDE
        default:  { return blend_normal(b, s); }
    }
}

// ---------------------------------------------------------------
// Main compute kernel — one thread per pixel
// ---------------------------------------------------------------

@compute @workgroup_size(16, 16, 1)
fn main(@builtin(global_invocation_id) gid: vec3<u32>) {
    let x = gid.x;
    let y = gid.y;
    if (x >= params.width || y >= params.height) { return; }

    let idx = y * params.width + x;
    var s = src[idx];
    let d = dst[idx];

    var sa = s.a * params.opacity;
    if (params.has_mask != 0u) {
        sa *= mask_buf[idx];
    }

    if (sa <= 0.0) { return; }

    let da = d.a;
    let inv_sa = 1.0 - sa;
    let out_a = sa + da * inv_sa;
    if (out_a <= 1e-10) { return; }

    let inv_out = 1.0 / out_a;

    var out_r: f32;
    var out_g: f32;
    var out_b: f32;

    if (params.mode == 1u) {
        // Normal fast path
        out_r = (s.r * sa + d.r * da * inv_sa) * inv_out;
        out_g = (s.g * sa + d.g * da * inv_sa) * inv_out;
        out_b = (s.b * sa + d.b * da * inv_sa) * inv_out;
    } else {
        let br = apply_blend(params.mode, d.r, s.r);
        let bg = apply_blend(params.mode, d.g, s.g);
        let bb = apply_blend(params.mode, d.b, s.b);
        out_r = (br * sa + d.r * da * inv_sa) * inv_out;
        out_g = (bg * sa + d.g * da * inv_sa) * inv_out;
        out_b = (bb * sa + d.b * da * inv_sa) * inv_out;
    }

    dst[idx] = vec4f(out_r, out_g, out_b, out_a);
}
