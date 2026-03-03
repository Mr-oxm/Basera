"""Brush engine — ABR file parsing, brush presets, and global brush manager.

Supports ABR v1/v2 (old format) and v6+ (new 8BIM-tagged format).
Brush tip images are extracted as grayscale numpy arrays.
"""

from __future__ import annotations

import os
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
from PySide6.QtCore import QObject, Signal


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class BrushPreset:
    """A single brush preset loaded from an ABR file."""
    name: str
    size: int  # default diameter in pixels
    tip_image: np.ndarray | None  # grayscale H×W uint8 (None for computed)
    hardness: float = 0.8
    spacing: float = 0.25
    opacity: float = 1.0
    flow: float = 1.0
    rotation: float = 0.0
    # Source info
    abr_file: str = ""
    index: int = 0

    def preview_thumbnail(self, target_h: int = 48, target_w: int = 200) -> np.ndarray:
        """Return an RGBA thumbnail suitable for display in the brushes panel."""
        if self.tip_image is None:
            return self._generate_round_preview(target_h, target_w)
        return self._render_stroke_preview(target_h, target_w)

    def _generate_round_preview(self, th: int, tw: int) -> np.ndarray:
        """Generate a simple round brush stroke preview."""
        out = np.zeros((th, tw, 4), dtype=np.uint8)
        cy, cx = th // 2, tw // 2
        r = min(th, 28) // 2
        # Draw a series of overlapping dabs to simulate a stroke
        num_dabs = max(1, tw // max(1, int(r * 2 * self.spacing)))
        x_start = int(tw * 0.1)
        x_end = int(tw * 0.9)
        for i in range(num_dabs):
            t = i / max(num_dabs - 1, 1)
            dx = int(x_start + (x_end - x_start) * t)
            yy = np.arange(max(0, cy - r), min(th, cy + r + 1), dtype=np.float32)[:, None]
            xx = np.arange(max(0, dx - r), min(tw, dx + r + 1), dtype=np.float32)[None, :]
            dist = np.sqrt((xx - dx) ** 2 + (yy - cy) ** 2)
            mask = np.clip(1.0 - dist / max(r, 1), 0, 1)
            mask = mask ** (1.0 / max(self.hardness, 0.01))
            y0 = max(0, cy - r)
            x0 = max(0, dx - r)
            h = mask.shape[0]
            w = mask.shape[1]
            alpha_add = (mask * 80).astype(np.uint8)
            roi = out[y0:y0 + h, x0:x0 + w]
            roi[..., :3] = np.maximum(roi[..., :3], 255)
            roi[..., 3] = np.clip(roi[..., 3].astype(np.int16) + alpha_add, 0, 255).astype(np.uint8)
        return out

    def _render_stroke_preview(self, th: int, tw: int) -> np.ndarray:
        """Render a stroke preview using the actual tip image."""
        out = np.zeros((th, tw, 4), dtype=np.uint8)
        tip = self.tip_image
        if tip is None:
            return out
        # Scale tip to fit within height
        tip_h, tip_w = tip.shape[:2]
        scale = min(1.0, (th - 4) / max(tip_h, 1), 28.0 / max(tip_h, 1))
        new_h = max(1, int(tip_h * scale))
        new_w = max(1, int(tip_w * scale))
        # Fast resize using stride tricks or simple indexing
        if new_h != tip_h or new_w != tip_w:
            from PIL import Image
            pil_tip = Image.fromarray(tip)
            pil_tip = pil_tip.resize((new_w, new_h), Image.BILINEAR)
            tip = np.array(pil_tip)
        cy = th // 2
        x_start = int(tw * 0.08)
        x_end = int(tw * 0.92)
        step = max(1, int(new_w * self.spacing * 2))
        num_dabs = max(1, (x_end - x_start) // step)
        for i in range(num_dabs):
            t = i / max(num_dabs - 1, 1)
            dx = int(x_start + (x_end - x_start) * t)
            y0 = cy - new_h // 2
            x0 = dx - new_w // 2
            # Clip to bounds
            src_y0 = max(0, -y0)
            src_x0 = max(0, -x0)
            dst_y0 = max(0, y0)
            dst_x0 = max(0, x0)
            src_y1 = min(new_h, th - y0)
            src_x1 = min(new_w, tw - x0)
            dst_y1 = dst_y0 + (src_y1 - src_y0)
            dst_x1 = dst_x0 + (src_x1 - src_x0)
            if dst_y1 <= dst_y0 or dst_x1 <= dst_x0:
                continue
            alpha = tip[src_y0:src_y1, src_x0:src_x1].astype(np.float32) / 255.0
            roi = out[dst_y0:dst_y1, dst_x0:dst_x1]
            roi[..., :3] = np.maximum(roi[..., :3], 255)
            new_alpha = np.clip(
                roi[..., 3].astype(np.float32) / 255.0 + alpha * 0.4,
                0, 1
            )
            roi[..., 3] = (new_alpha * 255).astype(np.uint8)
        return out


# ---------------------------------------------------------------------------
# ABR Parser
# ---------------------------------------------------------------------------

def _read_u16(data: bytes, offset: int) -> tuple[int, int]:
    return struct.unpack_from(">H", data, offset)[0], offset + 2


def _read_u32(data: bytes, offset: int) -> tuple[int, int]:
    return struct.unpack_from(">I", data, offset)[0], offset + 4


def _read_i32(data: bytes, offset: int) -> tuple[int, int]:
    return struct.unpack_from(">i", data, offset)[0], offset + 4


def _read_pascal_string(data: bytes, offset: int) -> tuple[str, int]:
    """Read a Pascal-style string (1-byte length prefix)."""
    if offset >= len(data):
        return "", offset
    length = data[offset]
    offset += 1
    if offset + length > len(data):
        return "", offset
    s = data[offset:offset + length]
    offset += length
    # Pad to even
    if (length + 1) % 2 != 0:
        offset += 1
    try:
        return s.decode("ascii", errors="replace"), offset
    except Exception:
        return "", offset


def _read_unicode_string(data: bytes, offset: int) -> tuple[str, int]:
    """Read a Unicode string (4-byte length prefix, UTF-16BE chars)."""
    if offset + 4 > len(data):
        return "", offset
    length, offset = _read_u32(data, offset)
    if length == 0:
        return "", offset
    byte_len = length * 2
    if offset + byte_len > len(data):
        return "", offset + byte_len
    s = data[offset:offset + byte_len]
    offset += byte_len
    try:
        return s.decode("utf-16-be").rstrip("\x00"), offset
    except Exception:
        return "", offset


def _parse_abr_v1v2(data: bytes, abr_name: str) -> list[BrushPreset]:
    """Parse ABR v1/v2 (old format with counted brushes)."""
    presets = []
    offset = 2  # skip version
    if len(data) < 4:
        return presets
    count, offset = _read_u16(data, offset)

    for idx in range(count):
        if offset + 2 > len(data):
            break
        brush_type, offset = _read_u16(data, offset)
        # Skip brush size field
        if offset + 4 > len(data):
            break
        brush_size, offset = _read_u32(data, offset)
        end_offset = offset + brush_size - 4  # size includes itself
        if end_offset > len(data):
            end_offset = len(data)

        if brush_type == 1:
            # Computed brush
            if offset + 24 <= end_offset:
                # misc (4), spacing (2), diameter (2), roundness (2), angle (2), hardness (2)
                _misc, offset = _read_u32(data, offset)
                spacing, offset = _read_u16(data, offset)
                diameter, offset = _read_u16(data, offset)
                _roundness, offset = _read_u16(data, offset)
                _angle, offset = _read_u16(data, offset)
                hardness, offset = _read_u16(data, offset)
                presets.append(BrushPreset(
                    name=f"Round {diameter}",
                    size=diameter,
                    tip_image=None,
                    hardness=hardness / 100.0,
                    spacing=max(spacing, 1) / 100.0,
                    abr_file=abr_name,
                    index=idx,
                ))
            offset = end_offset
        elif brush_type == 2:
            # Sampled brush
            if offset + 18 <= end_offset:
                _misc, offset = _read_u32(data, offset)
                spacing, offset = _read_u16(data, offset)
                # antialias byte
                offset += 1
                # bounds: top, left, bottom, right
                top, offset = _read_u16(data, offset)
                left, offset = _read_u16(data, offset)
                bottom, offset = _read_u16(data, offset)
                right, offset = _read_u16(data, offset)
                depth, offset = _read_u16(data, offset)
                h = bottom - top
                w = right - left
                compression, offset = offset, offset + 1
                comp_byte = data[compression] if compression < len(data) else 0
                pixel_count = h * w
                if comp_byte == 0 and offset + pixel_count <= end_offset:
                    pixels = np.frombuffer(data[offset:offset + pixel_count], dtype=np.uint8).reshape((h, w))
                    offset += pixel_count
                else:
                    pixels = None
                    offset = end_offset
                presets.append(BrushPreset(
                    name=f"Sampled {idx + 1}",
                    size=max(h, w),
                    tip_image=pixels.copy() if pixels is not None else None,
                    spacing=max(spacing, 1) / 100.0,
                    abr_file=abr_name,
                    index=idx,
                ))
            else:
                offset = end_offset
        else:
            offset = end_offset

    return presets


def _decompress_rle(data: bytes, expected_size: int) -> bytes:
    """Decompress Photoshop-style RLE (PackBits)."""
    result = bytearray()
    i = 0
    while i < len(data) and len(result) < expected_size:
        n = data[i]
        i += 1
        if n < 128:
            count = n + 1
            result.extend(data[i:i + count])
            i += count
        elif n > 128:
            count = 257 - n
            if i < len(data):
                result.extend([data[i]] * count)
                i += 1
        # n == 128: no-op
    return bytes(result[:expected_size])


def _parse_samp_section(data: bytes, offset: int, section_end: int, abr_name: str) -> list[BrushPreset]:
    """Parse the 'samp' (sampled brushes) section of v6+ ABR files.

    Supports v6.2 format which uses a Virtual Memory Array List (VMAL)
    with multiple channel slots. Brush images are grayscale and typically
    stored in the last written channel.
    """
    presets = []
    idx = 0
    while offset < section_end - 4:
        if offset + 4 > section_end:
            break
        item_len, offset = _read_u32(data, offset)
        item_end = offset + item_len
        if item_end > section_end:
            item_end = section_end
        if item_len < 10:
            offset = (item_end + 3) & ~3
            idx += 1
            continue

        try:
            pos = offset
            # Pascal string (brush ID — typically a UUID, not a display name)
            _brush_id, pos = _read_pascal_string(data, pos)
            name = f"Brush {idx + 1}"

            # After pascal string: 3 unknown bytes (misc + 2 padding)
            pos += 3

            # VMAL header: version(4) + length(4) + rect(16) + num_channels(4)
            if pos + 28 > item_end:
                offset = (item_end + 3) & ~3
                idx += 1
                continue

            vmal_ver, _ = _read_u32(data, pos)
            _vmal_len, _ = _read_u32(data, pos + 4)
            top, _ = _read_u32(data, pos + 8)
            left, _ = _read_u32(data, pos + 12)
            bottom, _ = _read_u32(data, pos + 16)
            right, _ = _read_u32(data, pos + 20)
            num_channels, _ = _read_u32(data, pos + 24)
            pos += 28

            h = bottom - top
            w = right - left

            if vmal_ver != 3 or w <= 0 or h <= 0 or w > 10000 or h > 10000 or num_channels > 500:
                offset = (item_end + 3) & ~3
                idx += 1
                continue

            # Iterate through channel slots looking for written channels
            tip = None
            for _ch_idx in range(num_channels):
                if pos + 4 > item_end:
                    break
                written, pos = _read_u32(data, pos)
                if written == 0:
                    continue
                # Written channel: read data length
                if pos + 4 > item_end:
                    break
                ch_data_len, pos = _read_u32(data, pos)
                ch_data_start = pos

                # Channel image header:
                #   pixel_depth(4), rect(16), depth(2), compression(1)
                if pos + 23 <= item_end and pos + 23 <= ch_data_start + ch_data_len:
                    pd, _ = _read_u32(data, pos)
                    ct, _ = _read_u32(data, pos + 4)
                    cl, _ = _read_u32(data, pos + 8)
                    cb, _ = _read_u32(data, pos + 12)
                    cr, _ = _read_u32(data, pos + 16)
                    cdepth, _ = _read_u16(data, pos + 20)
                    comp = data[pos + 22]

                    cw = cr - cl
                    ch2 = cb - ct

                    if cw > 0 and ch2 > 0 and cw < 10000 and ch2 < 10000 and cdepth in (8, 16):
                        bpp = cdepth // 8
                        pixel_count = cw * ch2 * bpp
                        pixel_off = pos + 23

                        if comp == 0:
                            # Raw uncompressed
                            if pixel_off + pixel_count <= ch_data_start + ch_data_len:
                                raw = data[pixel_off:pixel_off + pixel_count]
                                if cdepth == 8:
                                    tip = np.frombuffer(raw, dtype=np.uint8).reshape((ch2, cw)).copy()
                                elif cdepth == 16:
                                    tip16 = np.frombuffer(raw, dtype=">u2").reshape((ch2, cw))
                                    tip = (tip16 >> 8).astype(np.uint8).copy()
                        elif comp == 1:
                            # RLE: row byte counts then packed data
                            rle_off = pixel_off
                            if rle_off + ch2 * 2 <= ch_data_start + ch_data_len:
                                row_bytes = []
                                for _ in range(ch2):
                                    rb, rle_off = _read_u16(data, rle_off)
                                    row_bytes.append(rb)
                                total_rle = sum(row_bytes)
                                rle_data = data[rle_off:rle_off + total_rle]
                                decompressed = _decompress_rle(rle_data, cw * ch2 * bpp)
                                if len(decompressed) >= pixel_count:
                                    if cdepth == 8:
                                        tip = np.frombuffer(
                                            decompressed[:pixel_count], dtype=np.uint8
                                        ).reshape((ch2, cw)).copy()
                                    elif cdepth == 16:
                                        tip16 = np.frombuffer(
                                            decompressed[:pixel_count], dtype=">u2"
                                        ).reshape((ch2, cw))
                                        tip = (tip16 >> 8).astype(np.uint8).copy()

                # Advance past this channel's data
                pos = ch_data_start + ch_data_len

            presets.append(BrushPreset(
                name=name,
                size=max(h, w),
                tip_image=tip,
                abr_file=abr_name,
                index=idx,
            ))
        except Exception:
            pass

        # Advance to next item (pad to 4-byte boundary)
        offset = (item_end + 3) & ~3
        idx += 1

    return presets


def _parse_abr_v6plus(data: bytes, abr_name: str) -> list[BrushPreset]:
    """Parse ABR v6+ (new format with 8BIM sections)."""
    presets = []
    offset = 4  # skip version(2) + subversion(2)

    while offset + 12 <= len(data):
        # Look for 8BIM signature
        sig = data[offset:offset + 4]
        if sig != b"8BIM":
            offset += 1
            continue
        offset += 4

        # 4-char key
        key = data[offset:offset + 4]
        offset += 4

        # Section length
        section_len, offset = _read_u32(data, offset)
        section_end = offset + section_len

        if key == b"samp":
            samp_presets = _parse_samp_section(data, offset, section_end, abr_name)
            presets.extend(samp_presets)

        offset = section_end

    return presets


def load_abr_file(filepath: str) -> list[BrushPreset]:
    """Load brushes from an ABR file. Returns list of BrushPreset."""
    try:
        with open(filepath, "rb") as f:
            data = f.read()
    except (IOError, OSError):
        return []

    if len(data) < 4:
        return []

    version = struct.unpack_from(">H", data, 0)[0]
    abr_name = Path(filepath).stem

    if version in (1, 2):
        presets = _parse_abr_v1v2(data, abr_name)
    elif version in (6, 7, 9, 10):
        presets = _parse_abr_v6plus(data, abr_name)
    else:
        # Try v6+ parsing as fallback
        presets = _parse_abr_v6plus(data, abr_name)

    # Filter out presets with no useful data at all
    return [p for p in presets if p.tip_image is not None or p.size > 0]


# ---------------------------------------------------------------------------
# Global Brush Manager (singleton)
# ---------------------------------------------------------------------------

class BrushManager(QObject):
    """Global brush state manager — singleton.

    Loads ABR files, maintains brush collections, and signals
    when the active brush changes so both the panel and toolbar
    stay in sync.
    """
    brush_changed = Signal(object)  # emits BrushPreset or None

    _instance: Optional["BrushManager"] = None

    @classmethod
    def instance(cls) -> "BrushManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        super().__init__()
        # Structure: {abr_name: [BrushPreset, ...]}
        self._collections: dict[str, list[BrushPreset]] = {}
        self._all_presets: list[BrushPreset] = []
        self._active_preset: BrushPreset | None = None
        self._loaded = False

    # ---- Loading -----------------------------------------------------------

    def load_brushes_dir(self, directory: str) -> None:
        """Scan a directory for .abr files and load them all."""
        if self._loaded:
            return
        self._loaded = True
        
        # Always load basic default round brushes first
        basic_brushes = [
            BrushPreset("Hard Round", size=20, tip_image=None, hardness=0.95, abr_file="Basic Brushes", index=0),
            BrushPreset("Soft Round", size=40, tip_image=None, hardness=0.2, abr_file="Basic Brushes", index=1),
            BrushPreset("Soft Airbrush", size=60, tip_image=None, hardness=0.1, flow=0.3, abr_file="Basic Brushes", index=2),
            BrushPreset("Pixel Hard", size=5, tip_image=None, hardness=1.0, abr_file="Basic Brushes", index=3)
        ]
        self._collections["Basic Brushes"] = basic_brushes
        self._all_presets.extend(basic_brushes)
        
        dirpath = Path(directory)
        if not dirpath.is_dir():
            return
        for abr_file in sorted(dirpath.glob("*.abr")):
            self._load_one(str(abr_file))

    def _load_one(self, filepath: str) -> None:
        presets = load_abr_file(filepath)
        if not presets:
            return
        name = Path(filepath).stem
        # Pretty name: replace underscores, title case
        display_name = name.replace("_", " ").title()
        for p in presets:
            p.abr_file = display_name
        self._collections[display_name] = presets
        self._all_presets.extend(presets)

    # ---- Access ------------------------------------------------------------

    @property
    def collections(self) -> dict[str, list[BrushPreset]]:
        return self._collections

    @property
    def collection_names(self) -> list[str]:
        return list(self._collections.keys())

    @property
    def all_presets(self) -> list[BrushPreset]:
        return self._all_presets

    def get_collection(self, name: str) -> list[BrushPreset]:
        return self._collections.get(name, [])

    @property
    def active_preset(self) -> BrushPreset | None:
        return self._active_preset

    def set_active(self, preset: BrushPreset | None) -> None:
        if preset is self._active_preset:
            return
        self._active_preset = preset
        self.brush_changed.emit(preset)

    def search(self, query: str, collection: str | None = None) -> list[BrushPreset]:
        """Search brushes by name. If collection is set, search only that collection."""
        q = query.lower().strip()
        source = self._collections.get(collection, []) if collection else self._all_presets
        if not q:
            return source
        return [p for p in source if q in p.name.lower()]
