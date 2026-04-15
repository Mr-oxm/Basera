//! GPU compute backend using wgpu for blend modes and compositing.
//!
//! The blend pipeline runs all 20 supported blend modes as a single
//! WGSL compute shader dispatched over `(W/16, H/16)` workgroups.
//! Source, destination, and mask tiles are storage buffers in GPU memory.

use std::sync::Arc;
use wgpu::util::DeviceExt;

/// Shader push constants matching the WGSL `Params` struct.
#[repr(C)]
#[derive(Copy, Clone, Debug, bytemuck::Pod, bytemuck::Zeroable)]
struct BlendParams {
    width: u32,
    height: u32,
    mode: u32,
    has_mask: u32,
    opacity: f32,
    _pad0: f32,
    _pad1: f32,
    _pad2: f32,
}

/// Owns the wgpu device and blend pipeline.  Created once at startup.
pub struct GpuContext {
    pub device: Arc<wgpu::Device>,
    pub queue: Arc<wgpu::Queue>,
    blend_pipeline: wgpu::ComputePipeline,
    bind_group_layout: wgpu::BindGroupLayout,
    backend_name: String,
}

impl GpuContext {
    /// Initialise the GPU.  Returns `None` if no adapter is found.
    pub fn new() -> Option<Self> {
        let instance = wgpu::Instance::new(&wgpu::InstanceDescriptor {
            backends: wgpu::Backends::VULKAN
                | wgpu::Backends::DX12
                | wgpu::Backends::METAL
                | wgpu::Backends::GL,
            ..Default::default()
        });

        let adapter = pollster::block_on(instance.request_adapter(&wgpu::RequestAdapterOptions {
            power_preference: wgpu::PowerPreference::HighPerformance,
            force_fallback_adapter: false,
            compatible_surface: None,
        })).ok()?;

        let backend_name = format!("{:?}", adapter.get_info().backend);

        let (device, queue) = pollster::block_on(adapter.request_device(
            &wgpu::DeviceDescriptor {
                label: Some("photo_engine"),
                required_features: wgpu::Features::empty(),
                required_limits: wgpu::Limits::default(),
                ..Default::default()
            },
        ))
        .ok()?;

        let shader_src = include_str!("../../shaders/blend.wgsl");
        let shader_module = device.create_shader_module(wgpu::ShaderModuleDescriptor {
            label: Some("blend_shader"),
            source: wgpu::ShaderSource::Wgsl(shader_src.into()),
        });

        let bind_group_layout =
            device.create_bind_group_layout(&wgpu::BindGroupLayoutDescriptor {
                label: Some("blend_bgl"),
                entries: &[
                    // dst (read_write storage)
                    wgpu::BindGroupLayoutEntry {
                        binding: 0,
                        visibility: wgpu::ShaderStages::COMPUTE,
                        ty: wgpu::BindingType::Buffer {
                            ty: wgpu::BufferBindingType::Storage { read_only: false },
                            has_dynamic_offset: false,
                            min_binding_size: None,
                        },
                        count: None,
                    },
                    // src (read-only storage)
                    wgpu::BindGroupLayoutEntry {
                        binding: 1,
                        visibility: wgpu::ShaderStages::COMPUTE,
                        ty: wgpu::BindingType::Buffer {
                            ty: wgpu::BufferBindingType::Storage { read_only: true },
                            has_dynamic_offset: false,
                            min_binding_size: None,
                        },
                        count: None,
                    },
                    // mask (read-only storage)
                    wgpu::BindGroupLayoutEntry {
                        binding: 2,
                        visibility: wgpu::ShaderStages::COMPUTE,
                        ty: wgpu::BindingType::Buffer {
                            ty: wgpu::BufferBindingType::Storage { read_only: true },
                            has_dynamic_offset: false,
                            min_binding_size: None,
                        },
                        count: None,
                    },
                    // params (uniform)
                    wgpu::BindGroupLayoutEntry {
                        binding: 3,
                        visibility: wgpu::ShaderStages::COMPUTE,
                        ty: wgpu::BindingType::Buffer {
                            ty: wgpu::BufferBindingType::Uniform,
                            has_dynamic_offset: false,
                            min_binding_size: None,
                        },
                        count: None,
                    },
                ],
            });

        let pipeline_layout = device.create_pipeline_layout(&wgpu::PipelineLayoutDescriptor {
            label: Some("blend_pl"),
            bind_group_layouts: &[&bind_group_layout],
            push_constant_ranges: &[],
        });

        let blend_pipeline = device.create_compute_pipeline(&wgpu::ComputePipelineDescriptor {
            label: Some("blend_pipeline"),
            layout: Some(&pipeline_layout),
            module: &shader_module,
            entry_point: Some("main"),
            compilation_options: Default::default(),
            cache: None,
        });

        Some(Self {
            device: Arc::new(device),
            queue: Arc::new(queue),
            blend_pipeline,
            bind_group_layout,
            backend_name,
        })
    }

    pub fn backend_name(&self) -> &str {
        &self.backend_name
    }

    /// Blend `src` onto `dst` (both w×h×4 f32 flat slices) on the GPU.
    ///
    /// This performs a round-trip: upload → compute → readback.  For
    /// interactive compositing the tiles will already reside in VRAM
    /// (Phase C full integration), eliminating the upload/readback cost.
    pub fn blend_gpu(
        &self,
        dst: &mut [f32],
        src: &[f32],
        w: u32,
        h: u32,
        mode: u32,
        opacity: f32,
        mask: Option<&[f32]>,
    ) {
        let pixel_count = (w * h) as usize;
        let buf_size = (pixel_count * 4 * 4) as u64; // 4 channels × 4 bytes
        let mask_size = (pixel_count * 4) as u64;

        // Create GPU buffers
        let dst_buf = self.device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
            label: Some("dst"),
            contents: bytemuck::cast_slice(dst),
            usage: wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_SRC,
        });

        let src_buf = self.device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
            label: Some("src"),
            contents: bytemuck::cast_slice(src),
            usage: wgpu::BufferUsages::STORAGE,
        });

        let dummy_mask = vec![1.0f32; pixel_count];
        let mask_data: &[f32] = mask.unwrap_or(&dummy_mask);
        let mask_buf = self.device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
            label: Some("mask"),
            contents: bytemuck::cast_slice(mask_data),
            usage: wgpu::BufferUsages::STORAGE,
        });

        let params = BlendParams {
            width: w,
            height: h,
            mode,
            has_mask: if mask.is_some() { 1 } else { 0 },
            opacity,
            _pad0: 0.0,
            _pad1: 0.0,
            _pad2: 0.0,
        };
        let params_buf = self.device.create_buffer_init(&wgpu::util::BufferInitDescriptor {
            label: Some("params"),
            contents: bytemuck::cast_slice(&[params]),
            usage: wgpu::BufferUsages::UNIFORM,
        });

        let bind_group = self.device.create_bind_group(&wgpu::BindGroupDescriptor {
            label: Some("blend_bg"),
            layout: &self.bind_group_layout,
            entries: &[
                wgpu::BindGroupEntry { binding: 0, resource: dst_buf.as_entire_binding() },
                wgpu::BindGroupEntry { binding: 1, resource: src_buf.as_entire_binding() },
                wgpu::BindGroupEntry { binding: 2, resource: mask_buf.as_entire_binding() },
                wgpu::BindGroupEntry { binding: 3, resource: params_buf.as_entire_binding() },
            ],
        });

        // Readback buffer
        let readback_buf = self.device.create_buffer(&wgpu::BufferDescriptor {
            label: Some("readback"),
            size: buf_size,
            usage: wgpu::BufferUsages::COPY_DST | wgpu::BufferUsages::MAP_READ,
            mapped_at_creation: false,
        });

        // Dispatch compute
        let mut encoder = self.device.create_command_encoder(&Default::default());
        {
            let mut pass = encoder.begin_compute_pass(&Default::default());
            pass.set_pipeline(&self.blend_pipeline);
            pass.set_bind_group(0, &bind_group, &[]);
            pass.dispatch_workgroups((w + 15) / 16, (h + 15) / 16, 1);
        }
        encoder.copy_buffer_to_buffer(&dst_buf, 0, &readback_buf, 0, buf_size);
        self.queue.submit(std::iter::once(encoder.finish()));

        // Read back result
        let buf_slice = readback_buf.slice(..);
        let (sender, receiver) = std::sync::mpsc::channel();
        buf_slice.map_async(wgpu::MapMode::Read, move |result| {
            let _ = sender.send(result);
        });
        self.device.poll(wgpu::PollType::Wait).ok();
        receiver.recv().unwrap().unwrap();

        let data = buf_slice.get_mapped_range();
        let result: &[f32] = bytemuck::cast_slice(&data);
        dst.copy_from_slice(result);
    }
}
