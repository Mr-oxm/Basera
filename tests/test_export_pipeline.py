"""Tests for document export and .basera project snapshot export."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from photo_editor.commands.document.save_document import SaveDocumentCommand
from photo_editor.core.document import Document
from photo_editor.core.enums import LayerType
from photo_editor.engine.render_pipeline import RenderPipeline
from photo_editor.utils.image_io import supported_write_extensions
from photo_editor.utils.project_io import load_basera_payload, load_basera_project
import pytest


def _make_doc() -> Document:
    doc = Document(64, 48, name="ExportTest")
    layer = doc.add_layer(name="Fill")
    layer.pixels[:] = np.array([0.2, 0.6, 0.9, 1.0], dtype=np.float32)
    doc.selection.select_rect(8, 8, 16, 12)
    return doc


def test_basera_export_writes_full_snapshot(tmp_path: Path) -> None:
    doc = _make_doc()
    out = tmp_path / "snapshot.basera"

    SaveDocumentCommand(out, RenderPipeline()).execute(doc)

    assert out.exists()
    assert out.stat().st_size > 0

    payload = load_basera_payload(out)
    assert payload["magic"] == "BASERA_PROJECT"
    assert payload["document"]["name"] == "ExportTest"
    assert payload["document"]["width"] == 64
    assert payload["document"]["height"] == 48
    # v3 format: selection presence is flagged in the manifest
    assert "has_selection" in payload


def test_save_document_command_exports_all_supported_formats(tmp_path: Path) -> None:
    doc = _make_doc()
    cmd_pipeline = RenderPipeline()

    for ext in sorted(supported_write_extensions()):
        out = tmp_path / f"export{ext}"
        SaveDocumentCommand(out, cmd_pipeline).execute(doc)
        assert out.exists(), f"Missing exported file for {ext}"
        assert out.stat().st_size > 0, f"Empty exported file for {ext}"


def test_basera_round_trip_restores_layers_and_adjustment(tmp_path: Path) -> None:
    doc = Document(80, 60, name="RoundTrip")
    base = doc.add_layer(name="Base")
    base.pixels[:] = np.array([0.9, 0.2, 0.2, 1.0], dtype=np.float32)

    # Add one adjustment layer attached to base.
    from photo_editor.adjustments.brightness_contrast import BrightnessContrast

    adj = doc.add_layer(name="Brightness", layer_type=LayerType.ADJUSTMENT)
    adj.adjustment = BrightnessContrast()
    adj.adjustment_params = {"brightness": 0.25, "contrast": -0.1}
    adj.parent_id = base.id
    base.children.append(adj.id)

    # Add one mask layer attached to base.
    doc.layers.active_index = doc.layers.layers.index(base)
    mask = doc.add_mask_layer(fill_white=True)
    assert mask is not None

    out = tmp_path / "round_trip.basera"
    SaveDocumentCommand(out, RenderPipeline()).execute(doc)

    loaded = load_basera_project(out)
    assert loaded.name == "RoundTrip"
    assert loaded.width == 80
    assert loaded.height == 60

    loaded_base = next((l for l in loaded.layers if l.name == "Base"), None)
    assert loaded_base is not None
    loaded_adj = next((l for l in loaded.layers if l.name == "Brightness"), None)
    assert loaded_adj is not None
    assert loaded_adj.layer_type == LayerType.ADJUSTMENT
    assert loaded_adj.parent_id == loaded_base.id
    assert loaded_adj.adjustment is not None
    assert loaded_adj.adjustment_params.get("brightness") == 0.25
    assert loaded_adj.adjustment_params.get("contrast") == -0.1
    assert len(loaded_base.mask_layers) == 1


def test_basera_truncated_file_reports_friendly_error(tmp_path: Path) -> None:
    # A file that is not a valid ZIP and not a valid gzip should raise ValueError.
    bad = tmp_path / "broken.basera"
    bad.write_bytes(b"this is not a valid basera file at all")

    with pytest.raises(ValueError, match="incomplete or corrupted"):
        load_basera_payload(bad)


def test_basera_truncated_zip_reports_friendly_error(tmp_path: Path) -> None:
    """A valid ZIP with missing / corrupt manifest raises ValueError."""
    import zipfile as zf_mod

    bad = tmp_path / "no_manifest.basera"
    with zf_mod.ZipFile(bad, "w") as zf:
        zf.writestr("unrelated.txt", "hello")

    with pytest.raises(ValueError, match="incomplete or corrupted"):
        load_basera_payload(bad)


# ---------------------------------------------------------------------------
# Resize-on-export tests
# ---------------------------------------------------------------------------

def test_export_with_target_size_produces_correct_dimensions(tmp_path: Path) -> None:
    """Exported JPEG at custom target_size must have the requested pixel dimensions."""
    from PIL import Image as PILImage
    from photo_editor.utils.image_io import save_image

    arr = np.ones((64, 128, 4), dtype=np.float32)  # 128×64 RGBA
    out = tmp_path / "resized.jpg"
    save_image(arr, out, quality=80, target_size=(256, 128))

    img = PILImage.open(out)
    assert img.size == (256, 128), f"Expected (256, 128), got {img.size}"


def test_export_target_size_works_for_png(tmp_path: Path) -> None:
    from PIL import Image as PILImage
    from photo_editor.utils.image_io import save_image

    arr = np.ones((100, 100, 4), dtype=np.float32)
    out = tmp_path / "scaled.png"
    save_image(arr, out, target_size=(50, 50))

    img = PILImage.open(out)
    assert img.size == (50, 50)


def test_save_document_command_target_size(tmp_path: Path) -> None:
    """SaveDocumentCommand with target_size resizes the composited output."""
    from PIL import Image as PILImage

    doc = _make_doc()  # 64×48
    out = tmp_path / "resized.png"
    SaveDocumentCommand(out, RenderPipeline(), target_size=(32, 24)).execute(doc)

    assert out.exists()
    img = PILImage.open(out)
    assert img.size == (32, 24)


# ---------------------------------------------------------------------------
# JPEG background colour tests
# ---------------------------------------------------------------------------

def test_jpeg_export_transparent_pixel_uses_bg_color(tmp_path: Path) -> None:
    """Fully-transparent pixels in a JPEG export must be replaced by jpeg_bg."""
    from PIL import Image as PILImage
    from photo_editor.utils.image_io import save_image

    # Create a fully transparent 10×10 image.
    arr = np.zeros((10, 10, 4), dtype=np.float32)
    out = tmp_path / "transparent.jpg"
    save_image(arr, out, quality=95, jpeg_bg=(255, 0, 0))  # red background

    img = PILImage.open(out).convert("RGB")
    r, g, b = img.getpixel((5, 5))
    assert r > 200, f"Expected ~255 red, got ({r},{g},{b})"
    assert g < 30,  f"Expected ~0 green, got ({r},{g},{b})"
    assert b < 30,  f"Expected ~0 blue, got ({r},{g},{b})"


def test_jpeg_export_opaque_pixels_unaffected_by_bg(tmp_path: Path) -> None:
    """Fully-opaque pixels should not be influenced by jpeg_bg."""
    from PIL import Image as PILImage
    from photo_editor.utils.image_io import save_image

    # Solid blue image.
    arr = np.zeros((10, 10, 4), dtype=np.float32)
    arr[:, :, 2] = 1.0  # blue
    arr[:, :, 3] = 1.0  # fully opaque
    out = tmp_path / "opaque.jpg"
    save_image(arr, out, quality=95, jpeg_bg=(255, 0, 0))  # red bg should not bleed

    img = PILImage.open(out).convert("RGB")
    r, g, b = img.getpixel((5, 5))
    assert b > 150, f"Expected blue channel dominant, got ({r},{g},{b})"
    assert r < 100, f"Red BG bleed detected ({r},{g},{b})"


def test_jpeg_default_bg_is_white(tmp_path: Path) -> None:
    """Default jpeg_bg=(255,255,255) means transparent areas become white."""
    from PIL import Image as PILImage
    from photo_editor.utils.image_io import save_image

    arr = np.zeros((10, 10, 4), dtype=np.float32)  # fully transparent
    out = tmp_path / "default_bg.jpg"
    save_image(arr, out, quality=95)

    img = PILImage.open(out).convert("RGB")
    r, g, b = img.getpixel((5, 5))
    assert r > 200 and g > 200 and b > 200, f"Expected white, got ({r},{g},{b})"


# ---------------------------------------------------------------------------
# All-formats regression test (preserves original coverage)
# ---------------------------------------------------------------------------

def test_save_document_command_exports_all_supported_formats_with_new_params(
    tmp_path: Path,
) -> None:
    """All supported formats export successfully when target_size and jpeg_bg are supplied."""
    doc = _make_doc()
    pipeline = RenderPipeline()

    for ext in sorted(supported_write_extensions()):
        out = tmp_path / f"export_new{ext}"
        SaveDocumentCommand(
            out, pipeline, quality=80,
            target_size=(32, 24),
            jpeg_bg=(200, 200, 200),
        ).execute(doc)
        assert out.exists(), f"Missing file for {ext}"
        assert out.stat().st_size > 0, f"Empty file for {ext}"
