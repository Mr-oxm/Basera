//! Native performance core for the Photo Editor.
//!
//! Exposes SIMD-accelerated blend kernels, an LRU tile store, and a
//! task scheduler to Python via PyO3.  The Python tile compositor calls
//! into these functions for the hot inner loops, replacing NumPy.

mod blend;
mod gpu;
mod tile_store;

use numpy::{PyReadonlyArray2, PyReadonlyArray3, PyReadwriteArray3, IntoPyArray, PyArray3};
use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;
use std::sync::Mutex;

/// Blend `src` onto `dst` in-place using the specified blend mode.
///
/// Both arrays are (H, W, 4) float32 RGBA.  `opacity` scales the source
/// alpha before blending.  Optional `mask` is (H, W) float32 [0..1].
#[pyfunction]
#[pyo3(signature = (dst, src, mode, opacity, mask=None))]
fn blend_into(
    _py: Python<'_>,
    mut dst: PyReadwriteArray3<'_, f32>,
    src: PyReadonlyArray3<'_, f32>,
    mode: u8,
    opacity: f32,
    mask: Option<PyReadonlyArray2<'_, f32>>,
) -> PyResult<()> {
    let mut dst_arr = dst.as_array_mut();
    let src_arr = src.as_array();
    let (dh, dw, dc) = (dst_arr.shape()[0], dst_arr.shape()[1], dst_arr.shape()[2]);
    let (sh, sw, sc) = (src_arr.shape()[0], src_arr.shape()[1], src_arr.shape()[2]);

    if dc != 4 || sc != 4 {
        return Err(PyValueError::new_err("Both arrays must have 4 channels"));
    }
    if dh != sh || dw != sw {
        return Err(PyValueError::new_err("src and dst must have the same H x W"));
    }

    let mask_slice: Option<&[f32]> = mask.as_ref().map(|m| {
        let arr = m.as_array();
        unsafe { std::slice::from_raw_parts(arr.as_ptr(), arr.len()) }
    });

    let dst_slice = unsafe {
        std::slice::from_raw_parts_mut(dst_arr.as_mut_ptr(), dh * dw * 4)
    };
    let src_slice = unsafe {
        std::slice::from_raw_parts(src_arr.as_ptr(), sh * sw * 4)
    };

    let mode_enum = blend::BlendMode::from_u8(mode);
    blend::blend_region(dst_slice, src_slice, dw, dh, mode_enum, opacity, mask_slice);

    Ok(())
}

/// Blend `src` at `position` into the larger `canvas` in-place.
///
/// canvas: (CH, CW, 4) float32, src: (SH, SW, 4) float32.
/// position: (x, y) of src's top-left in canvas space.
/// mask: optional (SH, SW) float32 mask at source size.
#[pyfunction]
#[pyo3(signature = (canvas, src, pos_x, pos_y, mode, opacity, mask=None))]
fn blend_region_inplace(
    _py: Python<'_>,
    mut canvas: PyReadwriteArray3<'_, f32>,
    src: PyReadonlyArray3<'_, f32>,
    pos_x: i32,
    pos_y: i32,
    mode: u8,
    opacity: f32,
    mask: Option<PyReadonlyArray2<'_, f32>>,
) -> PyResult<()> {
    let mut c_arr = canvas.as_array_mut();
    let s_arr = src.as_array();
    let (ch, cw) = (c_arr.shape()[0], c_arr.shape()[1]);
    let (sh, sw) = (s_arr.shape()[0], s_arr.shape()[1]);

    // Compute overlap between canvas and source
    let sx = 0i32.max(-pos_x) as usize;
    let sy = 0i32.max(-pos_y) as usize;
    let dx = 0i32.max(pos_x) as usize;
    let dy = 0i32.max(pos_y) as usize;
    let mut w = (sw - sx).min(cw - dx);
    let mut h = (sh - sy).min(ch - dy);
    if w == 0 || h == 0 {
        return Ok(());
    }

    // Clamp to mask dimensions if present
    let mask_arr = mask.as_ref().map(|m| m.as_array());
    if let Some(ref ma) = mask_arr {
        let (mh, mw) = (ma.shape()[0], ma.shape()[1]);
        if sx < mw { w = w.min(mw - sx); } else { return Ok(()); }
        if sy < mh { h = h.min(mh - sy); } else { return Ok(()); }
    }

    let mode_enum = blend::BlendMode::from_u8(mode);
    let c_ptr = c_arr.as_mut_ptr();
    let s_ptr = s_arr.as_ptr();
    let mask_ptr: Option<(*const f32, usize)> = mask_arr.as_ref().map(|ma| {
        (ma.as_ptr(), ma.shape()[1])
    });

    for row in 0..h {
        let c_row_off = ((dy + row) * cw + dx) * 4;
        let s_row_off = ((sy + row) * sw + sx) * 4;
        let c_row = unsafe { std::slice::from_raw_parts_mut(c_ptr.add(c_row_off), w * 4) };
        let s_row = unsafe { std::slice::from_raw_parts(s_ptr.add(s_row_off), w * 4) };

        let mask_row: Option<&[f32]> = mask_ptr.map(|(mptr, mw)| {
            let moff = (sy + row) * mw + sx;
            unsafe { std::slice::from_raw_parts(mptr.add(moff), w) }
        });

        blend::blend_row(c_row, s_row, w, mode_enum, opacity, mask_row);
    }

    Ok(())
}

// ---------------------------------------------------------------
// TileStore Python wrapper
// ---------------------------------------------------------------

/// Python-facing LRU tile cache with byte-budget eviction.
#[pyclass]
struct PyTileStore {
    inner: Mutex<tile_store::TileStore>,
}

#[pymethods]
impl PyTileStore {
    /// Create a new tile store with the given byte budget and max tile count.
    #[new]
    #[pyo3(signature = (byte_budget=512*1024*1024, max_tiles=4096))]
    fn new(byte_budget: usize, max_tiles: usize) -> Self {
        Self { inner: Mutex::new(tile_store::TileStore::new(byte_budget, max_tiles)) }
    }

    /// Store a tile's pixel data.  `pixels` is (H, W, 4) float32.
    fn put(
        &self,
        layer_id: u64,
        tx: u32,
        ty: u32,
        mip: u8,
        pixels: PyReadonlyArray3<'_, f32>,
    ) {
        let arr = pixels.as_array();
        let h = arr.shape()[0] as u32;
        let w = arr.shape()[1] as u32;
        let data = arr.iter().copied().collect::<Vec<f32>>();
        let key = tile_store::TileKey { layer_id, tx, ty, mip };
        let td = tile_store::TileData { pixels: data, width: w, height: h };
        self.inner.lock().unwrap().put(key, td);
    }

    /// Retrieve a cached tile.  Returns (H, W, 4) float32 array or None.
    fn get<'py>(
        &self,
        py: Python<'py>,
        layer_id: u64,
        tx: u32,
        ty: u32,
        mip: u8,
    ) -> Option<Bound<'py, PyArray3<f32>>> {
        let key = tile_store::TileKey { layer_id, tx, ty, mip };
        let mut store = self.inner.lock().unwrap();
        store.get(&key).map(|td| {
            let h = td.height as usize;
            let w = td.width as usize;
            let arr = numpy::ndarray::Array3::from_shape_vec((h, w, 4), td.pixels.clone())
                .expect("tile data shape mismatch");
            arr.into_pyarray(py)
        })
    }

    /// Invalidate all tiles for a given layer.
    fn invalidate_layer(&self, layer_id: u64) {
        self.inner.lock().unwrap().invalidate_layer(layer_id);
    }

    /// Clear the entire cache.
    fn clear(&self) {
        self.inner.lock().unwrap().clear();
    }

    /// Number of cached tiles.
    #[getter]
    fn len(&self) -> usize {
        self.inner.lock().unwrap().len()
    }

    /// Current memory usage in bytes.
    #[getter]
    fn current_bytes(&self) -> usize {
        self.inner.lock().unwrap().current_bytes()
    }

    /// Configured byte budget.
    #[getter]
    fn byte_budget(&self) -> usize {
        self.inner.lock().unwrap().byte_budget()
    }
}

// ---------------------------------------------------------------
// GPU compute blend wrapper
// ---------------------------------------------------------------

#[pyclass]
struct GpuBlendEngine {
    ctx: gpu::GpuContext,
}

#[pymethods]
impl GpuBlendEngine {
    /// Try to initialise the GPU.  Returns None if no adapter found.
    #[staticmethod]
    fn create() -> Option<Self> {
        gpu::GpuContext::new().map(|ctx| Self { ctx })
    }

    /// Name of the GPU backend (Vulkan, DX12, Metal, GL).
    #[getter]
    fn backend(&self) -> &str {
        self.ctx.backend_name()
    }

    /// Blend src onto dst on the GPU (both (H,W,4) float32).
    #[pyo3(signature = (dst, src, mode, opacity, mask=None))]
    fn blend(
        &self,
        _py: Python<'_>,
        mut dst: PyReadwriteArray3<'_, f32>,
        src: PyReadonlyArray3<'_, f32>,
        mode: u32,
        opacity: f32,
        mask: Option<PyReadonlyArray2<'_, f32>>,
    ) -> PyResult<()> {
        let mut dst_arr = dst.as_array_mut();
        let src_arr = src.as_array();
        let h = dst_arr.shape()[0] as u32;
        let w = dst_arr.shape()[1] as u32;

        let dst_slice = unsafe {
            std::slice::from_raw_parts_mut(dst_arr.as_mut_ptr(), (h * w * 4) as usize)
        };
        let src_slice = unsafe {
            std::slice::from_raw_parts(src_arr.as_ptr(), (h * w * 4) as usize)
        };
        let mask_slice: Option<&[f32]> = mask.as_ref().map(|m| {
            let arr = m.as_array();
            unsafe { std::slice::from_raw_parts(arr.as_ptr(), arr.len()) }
        });

        self.ctx.blend_gpu(dst_slice, src_slice, w, h, mode, opacity, mask_slice);
        Ok(())
    }
}

/// Python module definition.
#[pymodule]
fn photo_engine(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(blend_into, m)?)?;
    m.add_function(wrap_pyfunction!(blend_region_inplace, m)?)?;
    m.add_class::<PyTileStore>()?;
    m.add_class::<GpuBlendEngine>()?;
    Ok(())
}
