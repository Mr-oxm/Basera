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
    assert payload["current_state"]["metadata"]["_doc_width"] == 64
    assert payload["current_state"]["metadata"]["_doc_height"] == 48
    assert "__selection_mask__" in payload["current_state"]["layer_data"]


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
    bad = tmp_path / "broken.basera"
    # Write only a fragment of a gzip stream.
    bad.write_bytes(b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\x03")

    with pytest.raises(ValueError, match="incomplete or corrupted"):
        load_basera_payload(bad)
