"""Document model — represents a single open image project."""

from __future__ import annotations

import numpy as np

from .enums import BlendMode, LayerType
from .history import HistoryManager, HistoryState
from .layer import Layer
from .layer_stack import LayerStack
from .selection import Selection


class Document:
    """Top-level container for an editing session."""

    def __init__(self, width: int, height: int, name: str = "Untitled") -> None:
        self.name = name
        self.width = width
        self.height = height
        self.file_path: str | None = None
        self.dpi: int = 72
        self.layers = LayerStack()
        self.history = HistoryManager()
        self.selection = Selection(width, height)
        self._dirty = False

        bg = Layer(name="Background", width=width, height=height)
        bg.pixels[:] = np.array([1.0, 1.0, 1.0, 1.0], dtype=np.float32)
        self.layers.add(bg)

    # ---- Dirty flag ---------------------------------------------------------

    @property
    def dirty(self) -> bool:
        return self._dirty

    def mark_dirty(self) -> None:
        self._dirty = True

    def mark_clean(self) -> None:
        self._dirty = False

    # ---- Layer operations ---------------------------------------------------

    def add_layer(
        self, name: str = "Layer", layer_type: LayerType = LayerType.RASTER,
    ) -> Layer:
        layer = Layer(name=name, width=self.width, height=self.height, layer_type=layer_type)
        self.layers.add(layer)
        self._snapshot(f"Add {name}")
        self._dirty = True
        return layer

    def add_group(self, name: str = "Group") -> Layer:
        group = Layer(name=name, width=self.width, height=self.height, layer_type=LayerType.GROUP)
        self.layers.add(group)
        self._snapshot(f"Add Group {name}")
        self._dirty = True
        return group

    def group_selected_layers(self, layer_ids: list[str], name: str = "Group") -> Layer | None:
        """Create a new group containing the given layers."""
        group = self.layers.create_group_from(layer_ids, name)
        if group:
            self._snapshot("Group Layers")
            self._dirty = True
        return group

    def place_image(self, pixels: np.ndarray, name: str = "Placed Image") -> Layer:
        """Import an RGBA image as a new layer."""
        h, w = pixels.shape[:2]
        layer = Layer(name=name, width=w, height=h)
        layer.pixels = pixels
        self.layers.add(layer)
        self._snapshot(f"Place {name}")
        self._dirty = True
        return layer

    def remove_layer(self, layer_id: str) -> None:
        removed = self.layers.remove(layer_id)
        if removed:
            self._snapshot(f"Delete {removed.name}")
            self._dirty = True

    def duplicate_layer(self, layer_id: str) -> Layer | None:
        dup = self.layers.duplicate(layer_id)
        if dup:
            self._snapshot(f"Duplicate {dup.name}")
            self._dirty = True
        return dup

    def flatten(self) -> None:
        """Merge all visible layers into the background."""
        from ..engine.render_pipeline import RenderPipeline
        pipeline = RenderPipeline()
        merged = pipeline.execute(self)
        # Remove all layers, create single flattened one
        self.layers = LayerStack()
        bg = Layer(name="Background", width=self.width, height=self.height)
        bg.pixels = merged
        bg.locked = True
        self.layers.add(bg)
        self._snapshot("Flatten Image")
        self._dirty = True

    # ---- History ------------------------------------------------------------

    def undo(self) -> None:
        state = self.history.undo()
        if state:
            self._restore(state)

    def redo(self) -> None:
        state = self.history.redo()
        if state:
            self._restore(state)

    def navigate_history(self, target_index: int) -> None:
        """Jump to a specific history state by index."""
        while self.history.current_index > target_index and self.history.can_undo:
            self.history.undo()
        while self.history.current_index < target_index and self.history.can_redo:
            self.history.redo()
        current = self.history.current()
        if current:
            self._restore(current)

    def save_snapshot(self, action: str) -> None:
        self._snapshot(action)

    def _snapshot(self, action: str) -> None:
        state = HistoryState(name=action)
        # Save pixel data and mask data for every layer
        for layer in self.layers:
            state.layer_data[layer.id] = layer.pixels.copy()
            if layer._source_pixels is not None:
                state.layer_data[f"_src_{layer.id}"] = layer._source_pixels.copy()
            if layer._source_mask is not None:
                state.layer_data[f"_srcmask_{layer.id}"] = layer._source_mask.copy()
            if layer._mask is not None:
                state.layer_data[f"_mask_{layer.id}"] = layer._mask.copy()
        # Save the full layer structure so add/remove can be undone
        layer_metas = []
        for layer in self.layers:
            meta = {
                "id": layer.id,
                "name": layer.name,
                "width": layer.width,
                "height": layer.height,
                "layer_type": layer.layer_type,
                "opacity": layer.opacity,
                "blend_mode": layer.blend_mode,
                "visible": layer.visible,
                "locked": layer.locked,
                "position": layer.position,
                "mask_enabled": layer.mask_enabled,
                "clipping_mask": layer.clipping_mask,
                "parent_id": layer.parent_id,
                "children": list(layer.children),
                "transform_angle": layer.transform_angle,
                "transform_scale_x": layer.transform_scale_x,
                "transform_scale_y": layer.transform_scale_y,
                "transform_base_w": layer.transform_base_w,
                "transform_base_h": layer.transform_base_h,
            }
            # Save text layer data if present
            td = getattr(layer, "_text_data", None)
            if td is not None:
                meta["_text_data"] = td.to_dict()
            # Save adjustment / filter layer data if present
            if layer.adjustment is not None:
                meta["_adjustment_name"] = layer.adjustment.name
                meta["_adjustment_params"] = dict(layer.adjustment_params)
            layer_metas.append(meta)
        state.metadata["_layer_order"] = [l.id for l in self.layers]
        state.metadata["_layer_meta"] = {m["id"]: m for m in layer_metas}
        state.metadata["_active_index"] = self.layers.active_index
        state.metadata["_doc_width"] = self.width
        state.metadata["_doc_height"] = self.height
        self.history.push(state)

    def _restore(self, state: HistoryState) -> None:
        order: list[str] | None = state.metadata.get("_layer_order")
        meta_map: dict | None = state.metadata.get("_layer_meta")

        if order is not None and meta_map is not None:
            # Rebuild the layer stack from the snapshot
            from .layer_stack import LayerStack
            new_stack = LayerStack()
            for lid in order:
                meta = meta_map[lid]
                layer = Layer(
                    name=meta["name"],
                    width=meta["width"],
                    height=meta["height"],
                    layer_type=meta["layer_type"],
                    id=lid,
                    opacity=meta["opacity"],
                    blend_mode=meta["blend_mode"],
                    visible=meta["visible"],
                    locked=meta["locked"],
                    position=meta["position"],
                    mask_enabled=meta["mask_enabled"],
                    clipping_mask=meta["clipping_mask"],
                    parent_id=meta["parent_id"],
                    transform_angle=meta.get("transform_angle", 0.0),
                    transform_scale_x=meta.get("transform_scale_x", 1.0),
                    transform_scale_y=meta.get("transform_scale_y", 1.0),
                    transform_base_w=meta.get("transform_base_w", 0),
                    transform_base_h=meta.get("transform_base_h", 0),
                )
                # Restore children list
                layer.children = list(meta.get("children", []))
                # Restore pixel data
                if lid in state.layer_data:
                    layer.pixels = state.layer_data[lid].copy()
                src_key = f"_src_{lid}"
                if src_key in state.layer_data:
                    layer._source_pixels = state.layer_data[src_key].copy()
                srcmask_key = f"_srcmask_{lid}"
                if srcmask_key in state.layer_data:
                    layer._source_mask = state.layer_data[srcmask_key].copy()
                # Restore mask data
                mask_key = f"_mask_{lid}"
                if mask_key in state.layer_data:
                    layer._mask = state.layer_data[mask_key].copy()
                # Restore text layer data
                td_dict = meta.get("_text_data")
                if td_dict is not None:
                    from .text_layer import TextLayerData
                    layer._text_data = TextLayerData.from_dict(td_dict)
                # Restore adjustment / filter layer data
                adj_name = meta.get("_adjustment_name")
                if adj_name is not None:
                    from ..ui.filter_runner import _adj_map, _filter_name_map
                    layer_lt = meta.get("layer_type")
                    if layer_lt == LayerType.FILTER:
                        cls = _filter_name_map().get(adj_name)
                    else:
                        cls = _adj_map().get(adj_name)
                    if cls is not None:
                        layer._adjustment = cls()
                        layer._adjustment_params = dict(meta.get("_adjustment_params", {}))
                new_stack.add(layer)
            new_stack.active_index = state.metadata.get("_active_index", 0)
            self.layers = new_stack
        else:
            # Legacy fallback: only pixel data & positions stored
            for layer in self.layers:
                if layer.id in state.layer_data:
                    layer.pixels = state.layer_data[layer.id].copy()
                pos_key = f"pos_{layer.id}"
                if pos_key in state.metadata:
                    layer.position = state.metadata[pos_key]
        # Restore document dimensions (canvas crop undo)
        saved_w = state.metadata.get("_doc_width")
        saved_h = state.metadata.get("_doc_height")
        if saved_w is not None and saved_h is not None:
            self.width = saved_w
            self.height = saved_h
            self.selection.resize(saved_w, saved_h)
        self._dirty = True

    # ---- Canvas ops ---------------------------------------------------------

    def resize(self, width: int, height: int) -> None:
        self.width, self.height = width, height
        self.selection.resize(width, height)
