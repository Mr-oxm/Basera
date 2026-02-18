"""Document lifecycle, file I/O, tabs, and history."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox

from ...core.document import Document
from ...core.enums import LayerType
from ..dialogs.new_document import NewDocumentDialog
from ...utils.image_io import load_image, save_image

_IMG_FLT = "Images (*.png *.jpg *.jpeg *.webp *.tiff *.tif *.bmp)"


class DocumentController:
    """Handles new/open/save/close, tabs, and undo/redo."""

    def __init__(self) -> None:
        self._mw = None

    def wire(self, main_window) -> None:
        """Connect to main window and wire menu/tab signals."""
        self._mw = main_window
        mw = main_window

        # File menu
        a = mw._menu.actions_map
        a["new"].triggered.connect(self.on_new)
        a["open"].triggered.connect(self.on_open)
        a["place_image"].triggered.connect(self.on_place_image)
        a["save"].triggered.connect(self.on_save)
        a["save_as"].triggered.connect(self.on_save_as)
        a["export"].triggered.connect(self.on_save_as)
        a["import_svg"].triggered.connect(self.on_import_svg)
        a["export_svg"].triggered.connect(self.on_export_svg)
        a["export_pdf"].triggered.connect(self.on_export_pdf)
        a["quit"].triggered.connect(mw.close)

        # History
        a["undo"].triggered.connect(self.on_undo)
        a["redo"].triggered.connect(self.on_redo)

        # Tabs
        mw._file_tabs.tab_selected.connect(self.on_tab_selected)
        mw._file_tabs.tab_close_requested.connect(self.on_tab_close)

        # History panel
        mw._history_panel.state_selected.connect(self.on_history_jump)

    def on_new(self) -> None:
        dlg = NewDocumentDialog(self._mw)
        if dlg.exec():
            self.new_document(*dlg.get_values())

    def new_document(self, w: int, h: int, dpi: int = 72) -> None:
        """Create a new blank document and switch to it."""
        mw = self._mw
        mw._doc = Document(w, h)
        mw._doc.dpi = dpi
        mw._open_docs.append((mw._doc, None))
        mw._file_tabs.add_tab(mw._doc.name)
        mw._refresh()
        mw._canvas.zoom_to_fit()
        mw._status.set_document_info(mw._doc.name, w, h)

    def on_open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self._mw, "Open Image", "", _IMG_FLT)
        if not path:
            return
        img = load_image(path)
        h, w = img.shape[:2]
        mw = self._mw
        mw._doc = Document(w, h, name=Path(path).stem)
        mw._doc.file_path = path
        mw._doc.layers[0].pixels = img
        mw._doc.save_snapshot("Open Image")
        mw._open_docs.append((mw._doc, path))
        mw._file_tabs.add_tab(Path(path).name, tooltip=path)
        mw._refresh()
        mw._canvas.zoom_to_fit()
        mw._status.set_document_info(mw._doc.name, w, h)

    def on_place_image(self) -> None:
        if not self._mw._doc:
            return
        path, _ = QFileDialog.getOpenFileName(
            self._mw, "Place Image as Layer", "", _IMG_FLT
        )
        if path:
            img = load_image(path)
            self._mw._doc.place_image(img, name=Path(path).stem)
            self._mw._refresh()

    def on_save(self) -> None:
        if self._mw._doc and self._mw._doc.file_path:
            self._save_to(self._mw._doc.file_path)
        else:
            self.on_save_as()

    def on_save_as(self) -> None:
        if not self._mw._doc:
            return
        path, _ = QFileDialog.getSaveFileName(self._mw, "Save As", "", _IMG_FLT)
        if path:
            self._mw._doc.file_path = path
            self._save_to(path)

    def _save_to(self, path: str) -> None:
        mw = self._mw
        if mw._doc:
            save_image(mw._pipeline.execute(mw._doc), path)
            mw._doc.mark_clean()
            mw.setWindowTitle(f"Photo Editor — {Path(path).name}")
            idx = mw._file_tabs.current_index()
            if 0 <= idx < len(mw._open_docs):
                mw._open_docs[idx] = (mw._doc, path)
                mw._file_tabs.set_tab_text(idx, Path(path).name)

    def on_import_svg(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self._mw, "Import SVG", "", "SVG Files (*.svg)"
        )
        if not path:
            return
        try:
            from ...vector.svg import import_svg, SVGGroup, SVGLeaf
            from ...vector.geometry import BBox, AffineTransform, Vec2
            from ...vector.rasterizer import rasterize_vector_layer_tight

            root_node = import_svg(path)
            if isinstance(root_node, SVGGroup) and not root_node.children:
                QMessageBox.information(
                    self._mw, "Import SVG", "No vector objects found in SVG."
                )
                return

            def _compute_bbox(node):
                bb = BBox.empty()
                if isinstance(node, SVGLeaf):
                    bb = node.object.bbox()
                elif isinstance(node, SVGGroup):
                    for child in node.children:
                        bb = bb.union(_compute_bbox(child))
                return bb

            all_bb = _compute_bbox(root_node)
            mw = self._mw

            if mw._doc is None:
                w = max(int(all_bb.max_pt.x + 20), 200)
                h = max(int(all_bb.max_pt.y + 20), 200)
                mw._doc = Document(w, h, name=Path(path).stem)
                mw._open_docs.append((mw._doc, path))
                mw._file_tabs.add_tab(Path(path).name, tooltip=path)

            doc_w, doc_h = mw._doc.width, mw._doc.height
            content_w, content_h = all_bb.width, all_bb.height

            scale = 1.0
            if content_w > doc_w or content_h > doc_h:
                scale_w = doc_w / content_w if content_w > 0 else 1.0
                scale_h = doc_h / content_h if content_h > 0 else 1.0
                scale = min(scale_w, scale_h) * 0.9

            c_center = all_bb.center
            doc_center = Vec2(doc_w / 2, doc_h / 2)

            xf = AffineTransform.translation(-c_center.x, -c_center.y).concat(
                AffineTransform.scaling(scale)
            ).concat(
                AffineTransform.translation(doc_center.x, doc_center.y)
            )

            def _apply_transform(node, transform):
                if isinstance(node, SVGLeaf):
                    node.object.transform = transform.concat(node.object.transform)
                elif isinstance(node, SVGGroup):
                    for child in node.children:
                        _apply_transform(child, transform)

            _apply_transform(root_node, xf)

            def _create_layers(node, parent_id=None):
                if isinstance(node, SVGGroup):
                    name = node.name if node.name and node.name != "svg" else "Group"
                    layer = mw._doc.add_group(name=name)
                    if parent_id:
                        mw._doc.layers.reparent([layer.id], parent_id)
                    for child in node.children:
                        _create_layers(child, layer.id)
                elif isinstance(node, SVGLeaf):
                    obj = node.object
                    layer = mw._doc.add_vector_layer(name=node.name)
                    layer._vector_data.add(obj)
                    if parent_id:
                        mw._doc.layers.reparent([layer.id], parent_id)
                    layer.opacity = getattr(obj, "opacity", 1.0)
                    rasterize_vector_layer_tight(mw._doc, layer=layer, force=True)
                    svg_filt = getattr(obj, "svg_filter", None)
                    if svg_filt and svg_filt.get("type") == "gaussian_blur":
                        from ..filter_runner import _filter_name_map
                        filt_cls = _filter_name_map().get("Gaussian Blur")
                        if filt_cls is not None:
                            filt = filt_cls()
                            std_dev = svg_filt.get("std_deviation", 0.0)
                            radius = max(0.1, std_dev * 2.0)
                            filt_layer = mw._doc.add_layer(
                                name="Gaussian Blur", layer_type=LayerType.FILTER
                            )
                            filt_layer.adjustment = filt
                            filt_layer.adjustment_params = {
                                "radius": radius,
                                "preserve_alpha": svg_filt.get("preserve_alpha", False),
                            }
                            filt_layer.parent_id = layer.id
                            layer.children.append(filt_layer.id)
                            mw._doc.layers.reposition_before(filt_layer.id, layer.id)

            _create_layers(root_node, parent_id=None)

            mw._refresh()
            mw._canvas.zoom_to_fit()
            mw._status.showMessage("Imported SVG successfully", 3000)

        except Exception as exc:
            import traceback
            traceback.print_exc()
            QMessageBox.warning(self._mw, "Import SVG Error", str(exc))

    def on_export_svg(self) -> None:
        if not self._mw._doc:
            return
        path, _ = QFileDialog.getSaveFileName(
            self._mw, "Export SVG", "", "SVG Files (*.svg)"
        )
        if not path:
            return
        try:
            objects = []
            for layer in self._mw._doc.layers:
                vl = getattr(layer, "_vector_data", None)
                if vl is not None:
                    objects.extend(vl.objects)
            if not objects:
                QMessageBox.information(
                    self._mw, "Export SVG", "No vector objects to export."
                )
                return
            from ...vector.svg import export_svg
            svg_str = export_svg(
                objects, self._mw._doc.width, self._mw._doc.height
            )
            with open(path, "w", encoding="utf-8") as f:
                f.write(svg_str)
            self._mw._status.showMessage(
                f"Exported {len(objects)} objects to SVG", 3000
            )
        except Exception as exc:
            QMessageBox.warning(self._mw, "Export SVG Error", str(exc))

    def on_export_pdf(self) -> None:
        if not self._mw._doc:
            return
        path, _ = QFileDialog.getSaveFileName(
            self._mw, "Export PDF", "", "PDF Files (*.pdf)"
        )
        if not path:
            return
        try:
            objects = []
            for layer in self._mw._doc.layers:
                vl = getattr(layer, "_vector_data", None)
                if vl is not None:
                    objects.extend(vl.objects)
            if not objects:
                QMessageBox.information(
                    self._mw, "Export PDF", "No vector objects to export."
                )
                return
            from ...vector.pdf import export_pdf_bytes
            pdf_data = export_pdf_bytes(
                objects, self._mw._doc.width, self._mw._doc.height
            )
            with open(path, "wb") as f:
                f.write(pdf_data)
            self._mw._status.showMessage(
                f"Exported {len(objects)} objects to PDF", 3000
            )
        except Exception as exc:
            QMessageBox.warning(self._mw, "Export PDF Error", str(exc))

    def on_tab_selected(self, index: int) -> None:
        if index < 0 or index >= len(self._mw._open_docs):
            return
        doc, path = self._mw._open_docs[index]
        self._mw._doc = doc
        self._mw._refresh()
        self._mw._canvas.zoom_to_fit()
        name = Path(path).name if path else doc.name
        self._mw._status.set_document_info(name, doc.width, doc.height)
        self._mw.setWindowTitle(f"Photo Editor — {name}")

    def on_tab_close(self, index: int) -> None:
        if index < 0 or index >= len(self._mw._open_docs):
            return
        if self._mw._file_tabs.count() <= 1:
            return
        self._mw._open_docs.pop(index)
        self._mw._file_tabs.remove_tab(index)
        new_idx = self._mw._file_tabs.current_index()
        if 0 <= new_idx < len(self._mw._open_docs):
            self.on_tab_selected(new_idx)

    def on_undo(self) -> None:
        if self._mw._doc:
            self._mw._doc.undo()
            self._mw._pipeline.invalidate()
            self._mw._refresh()

    def on_redo(self) -> None:
        if self._mw._doc:
            self._mw._doc.redo()
            self._mw._pipeline.invalidate()
            self._mw._refresh()

    def on_history_jump(self, index: int) -> None:
        if self._mw._doc:
            self._mw._doc.navigate_history(index)
            self._mw._pipeline.invalidate()
            self._mw._refresh()
