from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap

from ..core.document import Document
from ..core.enums import BlendMode, LayerType
from ..core.layer import Layer
from ..core.layer_stack import LayerStack
from ..styles.style_engine import StyleEngine
from .compositor import Compositor


@dataclass
class _LayerPixmapEntry:
    pixmap: QPixmap
    size: tuple[int, int]
    blend_position: tuple[int, int]
    alpha_pixmap: QPixmap | None = None
    rgba_u8: np.ndarray | None = None


@dataclass
class _RenderStep:
    graph_index: int = -1


@dataclass
class _PrefixRenderStep(_RenderStep):
    pass


@dataclass
class _SegmentRenderStep(_RenderStep):
    segment_layers: tuple[Layer, ...] = ()
    cache_key: str = ""


@dataclass
class _MaskRenderStep(_RenderStep):
    layer: Layer | None = None


@dataclass
class _ChainRenderStep(_RenderStep):
    layer: Layer | None = None
    chain: tuple[Layer, ...] = ()


@dataclass
class _BarrierSegment:
    barrier_layer: Layer
    start_index: int
    end_index: int

    @property
    def segment_cache_key(self) -> str:
        return f"segment:{self.barrier_layer.id}"


@dataclass
class _TopLevelRunSegment:
    start_index: int
    end_index: int
    cache_key: str


@dataclass
class _TopLevelGraphNode:
    start_index: int
    end_index: int
    graph_dependencies: tuple[int, ...] = ()

    def contains(self, top_index: int) -> bool:
        return self.start_index <= top_index < self.end_index


@dataclass
class _TopLevelCacheNode(_TopLevelGraphNode):
    cache_key: str = ""


@dataclass
class _TopLevelVisibleNode(_TopLevelGraphNode):
    pass


@dataclass
class _RunCacheNode(_TopLevelCacheNode):
    layers: tuple[Layer, ...] = ()


@dataclass
class _PrefixCacheNode(_TopLevelCacheNode):
    cache_key: str = ""
    layer: Layer | None = None
    cache_dependencies: tuple[str, ...] = ()


@dataclass
class _PrefixNode(_TopLevelVisibleNode):
    cache_key: str = ""
    layer: Layer | None = None
    cache_dependencies: tuple[str, ...] = ()


@dataclass
class _SegmentNode(_TopLevelVisibleNode):
    cache_key: str = ""
    layers: tuple[Layer, ...] = ()


@dataclass
class _MaskNode(_TopLevelVisibleNode):
    layer: Layer | None = None

    @property
    def layers(self) -> tuple[Layer, ...]:
        return () if self.layer is None else (self.layer,)


@dataclass
class _ChainNode(_TopLevelVisibleNode):
    cache_key: str = ""
    layers: tuple[Layer, ...] = ()

    @property
    def layer(self) -> Layer | None:
        return self.layers[0] if self.layers else None


@dataclass
class _TopLevelGraphBuilder:
    graph: list[_TopLevelGraphNode]
    cache_key_to_index: dict[str, int]
    previous_prefix_key: str | None = None
    previous_visible_index: int | None = None

    def _cache_dependency_indices(self, cache_dependencies: tuple[str, ...]) -> tuple[int, ...]:
        return tuple(self.cache_key_to_index[cache_key] for cache_key in cache_dependencies)

    def _visible_dependencies(self) -> tuple[int, ...]:
        return () if self.previous_visible_index is None else (self.previous_visible_index,)

    def add_run_cache(
        self,
        start_index: int,
        end_index: int,
        cache_key: str,
        layers: tuple[Layer, ...],
    ) -> None:
        self.graph.append(
            _RunCacheNode(
                start_index=start_index,
                end_index=end_index,
                cache_key=cache_key,
                layers=layers,
            )
        )
        self.cache_key_to_index[cache_key] = len(self.graph) - 1

    def add_prefix(
        self,
        *,
        is_visible: bool,
        end_index: int,
        cache_key: str,
        layer: Layer,
        cache_dependencies: tuple[str, ...],
    ) -> None:
        node_cls = _PrefixNode if is_visible else _PrefixCacheNode
        self.graph.append(
            node_cls(
                start_index=0,
                end_index=end_index,
                cache_key=cache_key,
                layer=layer,
                cache_dependencies=cache_dependencies,
                graph_dependencies=self._cache_dependency_indices(cache_dependencies),
            )
        )
        self.cache_key_to_index[cache_key] = len(self.graph) - 1
        if is_visible:
            self.previous_visible_index = len(self.graph) - 1
        self.previous_prefix_key = cache_key

    def add_segment(
        self,
        start_index: int,
        end_index: int,
        cache_key: str,
        layers: tuple[Layer, ...],
    ) -> None:
        self.graph.append(
            _SegmentNode(
                start_index=start_index,
                end_index=end_index,
                cache_key=cache_key,
                layers=layers,
                graph_dependencies=self._visible_dependencies(),
            )
        )
        self.cache_key_to_index[cache_key] = len(self.graph) - 1
        self.previous_visible_index = len(self.graph) - 1

    def add_mask(self, index: int, layer: Layer) -> None:
        self.graph.append(
            _MaskNode(
                start_index=index,
                end_index=index + 1,
                layer=layer,
                graph_dependencies=self._visible_dependencies(),
            )
        )
        self.previous_visible_index = len(self.graph) - 1

    def add_chain(
        self,
        start_index: int,
        end_index: int,
        chain: tuple[Layer, ...],
    ) -> None:
        self.graph.append(
            _ChainNode(
                start_index=start_index,
                end_index=end_index,
                cache_key=chain[0].id,
                layers=chain,
                graph_dependencies=self._visible_dependencies(),
            )
        )
        self.cache_key_to_index[chain[0].id] = len(self.graph) - 1
        self.previous_visible_index = len(self.graph) - 1


class QtGpuCompositorBackend:
    """Optional GPU-accelerated interactive compositor using Qt painting.

    This backend targets the common case of large flat raster stacks. It is
    intentionally conservative: any document feature that risks visual drift
    falls back to the existing CPU compositor.
    """

    _SUPPORTED_BLENDS: dict[BlendMode, QPainter.CompositionMode] = {
        BlendMode.NORMAL: QPainter.CompositionMode.CompositionMode_SourceOver,
        BlendMode.MULTIPLY: QPainter.CompositionMode.CompositionMode_Multiply,
        BlendMode.SCREEN: QPainter.CompositionMode.CompositionMode_Screen,
        BlendMode.OVERLAY: QPainter.CompositionMode.CompositionMode_Overlay,
        BlendMode.DARKEN: QPainter.CompositionMode.CompositionMode_Darken,
        BlendMode.LIGHTEN: QPainter.CompositionMode.CompositionMode_Lighten,
        BlendMode.COLOR_DODGE: QPainter.CompositionMode.CompositionMode_ColorDodge,
        BlendMode.COLOR_BURN: QPainter.CompositionMode.CompositionMode_ColorBurn,
        BlendMode.HARD_LIGHT: QPainter.CompositionMode.CompositionMode_HardLight,
        BlendMode.SOFT_LIGHT: QPainter.CompositionMode.CompositionMode_SoftLight,
        BlendMode.DIFFERENCE: QPainter.CompositionMode.CompositionMode_Difference,
        BlendMode.EXCLUSION: QPainter.CompositionMode.CompositionMode_Exclusion,
    }

    _SUPPORTED_LAYER_TYPES = {
        LayerType.RASTER,
        LayerType.TEXT,
        LayerType.SHAPE,
        LayerType.GROUP,
        LayerType.MASK,
        LayerType.ADJUSTMENT,
        LayerType.FILTER,
    }

    def __init__(self) -> None:
        self._layer_pixmaps: dict[str, _LayerPixmapEntry] = {}
        self._compositor = Compositor(quality_mode="final")

    def invalidate_all(self) -> None:
        self._layer_pixmaps.clear()

    def invalidate_layer(self, layer_id: str | None) -> None:
        if layer_id is None:
            self.invalidate_all()
            return
        self._layer_pixmaps.pop(layer_id, None)

    def invalidate_document_layer(self, document: Document | None, layer_id: str | None) -> None:
        if document is None or layer_id is None:
            self.invalidate_all()
            return
        invalidation_keys = self._invalidation_keys_for_document(document, layer_id)
        if invalidation_keys is None:
            self.invalidate_all()
            return
        for invalidation_key in invalidation_keys:
            self.invalidate_layer(invalidation_key)

    def can_render_document(self, document: Document | None) -> bool:
        if document is None:
            return False
        return self._build_graph_and_render_plan(document) is not None

    def render_document(self, painter: QPainter, document: Document, target_rect: QRectF) -> bool:
        graph_and_plan = self._build_graph_and_render_plan(document)
        if graph_and_plan is None:
            return False
        graph, plan = graph_and_plan
        if document.width <= 0 or document.height <= 0 or target_rect.width() <= 0 or target_rect.height() <= 0:
            return False

        for step in plan:
            if not self._execute_render_step(painter, document, target_rect, step, graph):
                return False
        return True

    def _top_level_visible_layers(self, document: Document) -> list[Layer]:
        return [
            layer for layer in document.layers
            if layer.visible and layer.parent_id is None
        ]

    @staticmethod
    def _is_root_effect(layer: Layer) -> bool:
        return layer.layer_type in (LayerType.ADJUSTMENT, LayerType.FILTER)

    def _needs_prefix_barrier(self, layer: Layer) -> bool:
        return self._is_root_effect(layer) or (
            layer.layer_type == LayerType.MASK and layer.ex_parent_id is not None
        )

    def _barrier_segments(self, top_level: list[Layer]) -> list[_BarrierSegment]:
        segments: list[_BarrierSegment] = []
        start_index = 0
        for index, layer in enumerate(top_level):
            if self._needs_prefix_barrier(layer):
                segments.append(
                    _BarrierSegment(
                        barrier_layer=layer,
                        start_index=start_index,
                        end_index=index + 1,
                    )
                )
                start_index = index + 1
        return segments

    def _suffix_segments(
        self,
        top_level: list[Layer],
        barrier_segments: list[_BarrierSegment],
    ) -> list[_TopLevelRunSegment]:
        if not barrier_segments:
            return []
        anchor = barrier_segments[-1].barrier_layer.id
        segments: list[_TopLevelRunSegment] = []
        start_index = barrier_segments[-1].end_index
        for index in range(start_index, len(top_level)):
            if top_level[index].layer_type == LayerType.MASK:
                if start_index < index:
                    segments.append(
                        _TopLevelRunSegment(
                            start_index=start_index,
                            end_index=index,
                            cache_key=f"suffix:{anchor}:{start_index}",
                        )
                    )
                start_index = index + 1
        if start_index < len(top_level):
            segments.append(
                _TopLevelRunSegment(
                    start_index=start_index,
                    end_index=len(top_level),
                    cache_key=f"suffix:{anchor}:{start_index}",
                )
            )
        return segments

    def _build_top_level_graph(self, top_level: list[Layer]) -> list[_TopLevelGraphNode]:
        barrier_segments = self._barrier_segments(top_level)
        suffix_segments = self._suffix_segments(top_level, barrier_segments)
        builder = _TopLevelGraphBuilder(graph=[], cache_key_to_index={})

        for barrier_index, barrier_segment in enumerate(barrier_segments):
            run_cache_key: str | None = None
            if barrier_segment.start_index < barrier_segment.end_index - 1:
                run_cache_key = barrier_segment.segment_cache_key
                builder.add_run_cache(
                    barrier_segment.start_index,
                    barrier_segment.end_index - 1,
                    run_cache_key,
                    tuple(top_level[barrier_segment.start_index:barrier_segment.end_index - 1]),
                )
            cache_dependencies = tuple(
                cache_key
                for cache_key in (builder.previous_prefix_key, run_cache_key)
                if cache_key is not None
            )
            builder.add_prefix(
                is_visible=barrier_index == len(barrier_segments) - 1,
                end_index=barrier_segment.end_index,
                cache_key=barrier_segment.barrier_layer.id,
                layer=barrier_segment.barrier_layer,
                cache_dependencies=cache_dependencies,
            )

        index = barrier_segments[-1].end_index if barrier_segments else 0
        suffix_segment_map = {segment.start_index: segment for segment in suffix_segments}
        while index < len(top_level):
            suffix_segment = suffix_segment_map.get(index)
            if suffix_segment is not None:
                builder.add_segment(
                    suffix_segment.start_index,
                    suffix_segment.end_index,
                    suffix_segment.cache_key,
                    tuple(top_level[suffix_segment.start_index:suffix_segment.end_index]),
                )
                index = suffix_segment.end_index
                continue
            layer = top_level[index]
            if layer.layer_type == LayerType.MASK:
                builder.add_mask(index, layer)
                index += 1
                continue
            chain_start = index
            chain = [layer]
            index += 1
            while index < len(top_level) and top_level[index].clipping_mask:
                chain.append(top_level[index])
                index += 1
            builder.add_chain(chain_start, index, tuple(chain))

        return builder.graph

    def _cache_segment_by_key(
        self,
        graph: list[_TopLevelGraphNode],
        cache_key: str,
    ) -> _TopLevelCacheNode | _TopLevelVisibleNode | None:
        def matches_cache_key(segment: _TopLevelGraphNode) -> bool:
            segment_cache_key = self._cache_key_for_graph_node(segment)
            return segment_cache_key == cache_key

        return next(
            (segment for segment in graph if matches_cache_key(segment)),
            None,
        )

    @staticmethod
    def _cache_key_for_graph_node(segment: _TopLevelGraphNode) -> str | None:
        if isinstance(segment, (_TopLevelCacheNode, _PrefixNode, _SegmentNode, _ChainNode)):
            return segment.cache_key
        return None

    @staticmethod
    def _cache_dependencies_for_graph_node(segment: _TopLevelGraphNode) -> tuple[str, ...]:
        if isinstance(segment, (_PrefixNode, _PrefixCacheNode)):
            return segment.cache_dependencies
        return ()

    def _cache_descendants(
        self,
        graph: list[_TopLevelGraphNode],
        cache_key: str,
    ) -> list[str]:
        reverse_edges: dict[str, set[str]] = {}
        for segment in graph:
            segment_cache_key = self._cache_key_for_graph_node(segment)
            if segment_cache_key is None:
                continue
            for dependency_key in self._cache_dependencies_for_graph_node(segment):
                reverse_edges.setdefault(dependency_key, set()).add(segment_cache_key)

        visited = {cache_key}
        queue = [cache_key]
        while queue:
            current_key = queue.pop(0)
            for dependent_key in reverse_edges.get(current_key, ()):
                if dependent_key in visited:
                    continue
                visited.add(dependent_key)
                queue.append(dependent_key)
        return [
            segment_cache_key
            for segment in graph
            if (segment_cache_key := self._cache_key_for_graph_node(segment)) is not None and segment_cache_key in visited
        ]

    def _primary_cache_key_for_index(
        self,
        graph: list[_TopLevelGraphNode],
        top_index: int,
    ) -> str | None:
        for segment in graph:
            segment_cache_key = self._cache_key_for_graph_node(segment)
            if not segment.contains(top_index) or segment_cache_key is None:
                continue
            if isinstance(segment, (_RunCacheNode, _SegmentNode, _ChainNode)):
                return segment_cache_key
            if isinstance(segment, (_PrefixNode, _PrefixCacheNode)) and top_index == segment.end_index - 1:
                return segment_cache_key
        return None

    @staticmethod
    def _is_visible_graph_segment(segment: _TopLevelGraphNode) -> bool:
        return isinstance(segment, (_PrefixNode, _SegmentNode, _MaskNode, _ChainNode))

    def _render_schedule_indices(self, graph: list[_TopLevelGraphNode]) -> list[int] | None:
        state = [0] * len(graph)
        ordered: list[int] = []

        def visit(index: int) -> bool:
            if index < 0 or index >= len(graph):
                return False
            if state[index] == 2:
                return True
            if state[index] == 1:
                return False
            state[index] = 1
            segment = graph[index]
            for dependency_index in segment.graph_dependencies:
                if dependency_index >= index:
                    return False
                if not visit(dependency_index):
                    return False
            state[index] = 2
            if self._is_visible_graph_segment(segment):
                ordered.append(index)
            return True

        for index in range(len(graph)):
            if not self._is_visible_graph_segment(graph[index]):
                continue
            if not visit(index):
                return None
        return ordered

    def _render_plan_from_graph(
        self,
        document: Document,
        graph: list[_TopLevelGraphNode],
    ) -> list[_RenderStep] | None:
        plan: list[_RenderStep] = []
        schedule = self._render_schedule_indices(graph)
        if schedule is None:
            return None
        for graph_index in schedule:
            segment = graph[graph_index]
            if not isinstance(segment, _TopLevelVisibleNode):
                return None
            render_step = self._render_step_for_visible_segment(document, graph_index, segment)
            if isinstance(segment, _PrefixCacheNode):
                continue
            if render_step is None:
                return None
            plan.append(render_step)
        return plan

    def _render_step_for_visible_segment(
        self,
        document: Document,
        graph_index: int,
        segment: _TopLevelVisibleNode,
    ) -> _RenderStep | None:
        if isinstance(segment, _PrefixNode):
            return self._render_step_for_prefix_node(graph_index, segment)
        if isinstance(segment, _SegmentNode):
            return self._render_step_for_segment_node(document, graph_index, segment)
        if isinstance(segment, _MaskNode):
            return self._render_step_for_mask_node(document, graph_index, segment)
        if isinstance(segment, _ChainNode):
            return self._render_step_for_chain_node(document, graph_index, segment)
        return None

    @staticmethod
    def _render_step_for_prefix_node(
        graph_index: int,
        segment: _PrefixNode,
    ) -> _PrefixRenderStep | None:
        if not segment.cache_key:
            return None
        return _PrefixRenderStep(graph_index=graph_index)

    def _render_step_for_segment_node(
        self,
        document: Document,
        graph_index: int,
        segment: _SegmentNode,
    ) -> _SegmentRenderStep | None:
        if not segment.cache_key:
            return None
        for layer in segment.layers:
            if layer.clipping_mask:
                return None
            if not self._supports_layer(document, layer, allow_clipping_mask=False):
                return None
        return _SegmentRenderStep(
            segment_layers=segment.layers,
            cache_key=segment.cache_key,
            graph_index=graph_index,
        )

    def _render_step_for_mask_node(
        self,
        document: Document,
        graph_index: int,
        segment: _MaskNode,
    ) -> _MaskRenderStep | None:
        if segment.layer is None:
            return None
        if not self._supports_layer(document, segment.layer, allow_clipping_mask=False):
            return None
        return _MaskRenderStep(layer=segment.layer, graph_index=graph_index)

    def _render_step_for_chain_node(
        self,
        document: Document,
        graph_index: int,
        segment: _ChainNode,
    ) -> _ChainRenderStep | None:
        if segment.layer is None or not segment.layers:
            return None
        base_layer = segment.layers[0]
        if base_layer.clipping_mask:
            return None
        if not self._supports_layer(document, base_layer, allow_clipping_mask=False):
            return None
        for clipped_layer in segment.layers[1:]:
            if not clipped_layer.clipping_mask:
                return None
            if not self._supports_layer(document, clipped_layer, allow_clipping_mask=True):
                return None
        return _ChainRenderStep(layer=segment.layer, chain=segment.layers, graph_index=graph_index)

    def _invalidation_keys_for_document(self, document: Document, layer_id: str) -> list[str] | None:
        layer = document.layers.get(layer_id)
        if layer is None:
            return None
        root = layer
        while root.parent_id is not None:
            parent = document.layers.get(root.parent_id)
            if parent is None:
                return None
            root = parent

        top_level = self._top_level_visible_layers(document)
        graph = self._build_top_level_graph(top_level)
        top_index = next((index for index, candidate in enumerate(top_level) if candidate.id == root.id), None)
        if top_index is None:
            return [root.id]
        primary_cache_key = self._primary_cache_key_for_index(graph, top_index)
        if primary_cache_key is not None:
            return self._cache_descendants(graph, primary_cache_key)
        return [root.id]

    def _build_graph_and_render_plan(
        self,
        document: Document,
    ) -> tuple[list[_TopLevelGraphNode], list[_RenderStep]] | None:
        top_level = self._top_level_visible_layers(document)
        graph = self._build_top_level_graph(top_level)
        plan = self._render_plan_from_graph(document, graph)
        if plan is None:
            return None
        return graph, plan

    def _build_render_plan(self, document: Document) -> list[_RenderStep] | None:
        graph_and_plan = self._build_graph_and_render_plan(document)
        if graph_and_plan is None:
            return None
        return graph_and_plan[1]

    def _execute_render_step(
        self,
        painter: QPainter,
        document: Document,
        target_rect: QRectF,
        step: _RenderStep,
        graph: list[_TopLevelGraphNode],
    ) -> bool:
        if isinstance(step, _PrefixRenderStep):
            return self._execute_prefix_render_step(painter, document, target_rect, step, graph)
        if isinstance(step, _MaskRenderStep):
            return self._execute_mask_render_step(painter, document, target_rect, step)
        if isinstance(step, _ChainRenderStep):
            return self._execute_chain_render_step(painter, document, target_rect, step)
        if isinstance(step, _SegmentRenderStep):
            return self._execute_segment_render_step(painter, document, target_rect, step)
        return False

    def _execute_prefix_render_step(
        self,
        painter: QPainter,
        document: Document,
        target_rect: QRectF,
        step: _PrefixRenderStep,
        graph: list[_TopLevelGraphNode],
    ) -> bool:
        if step.graph_index < 0:
            return False
        entry = self._pixmap_for_prefix(document, graph, graph[step.graph_index])
        if entry is None:
            return False
        self._draw_pixmap(
            painter,
            document,
            target_rect,
            entry,
            opacity=1.0,
            composition_mode=QPainter.CompositionMode.CompositionMode_SourceOver,
        )
        return True

    def _execute_mask_render_step(
        self,
        painter: QPainter,
        document: Document,
        target_rect: QRectF,
        step: _MaskRenderStep,
    ) -> bool:
        if step.layer is None:
            return False
        return self._apply_mask_step(painter, document, target_rect, step.layer)

    def _execute_chain_render_step(
        self,
        painter: QPainter,
        document: Document,
        target_rect: QRectF,
        step: _ChainRenderStep,
    ) -> bool:
        if step.layer is None or not step.chain:
            return False
        entry = self._pixmap_for_chain(document, list(step.chain)) if len(step.chain) > 1 else self._pixmap_for_layer(document, step.layer)
        if entry is None:
            return False
        self._draw_pixmap(
            painter,
            document,
            target_rect,
            entry,
            opacity=float(step.layer.opacity),
            composition_mode=self._SUPPORTED_BLENDS[step.layer.blend_mode],
        )
        return True

    def _execute_segment_render_step(
        self,
        painter: QPainter,
        document: Document,
        target_rect: QRectF,
        step: _SegmentRenderStep,
    ) -> bool:
        if not step.segment_layers:
            return False
        entry = self._pixmap_for_segment(document, list(step.segment_layers), step.cache_key)
        if entry is None:
            return False
        self._draw_pixmap(
            painter,
            document,
            target_rect,
            entry,
            opacity=1.0,
            composition_mode=QPainter.CompositionMode.CompositionMode_SourceOver,
        )
        return True

    def _draw_pixmap(
        self,
        painter: QPainter,
        document: Document,
        target_rect: QRectF,
        entry: _LayerPixmapEntry,
        *,
        opacity: float,
        composition_mode: QPainter.CompositionMode,
    ) -> None:
        painter.save()
        painter.setOpacity(opacity)
        painter.setCompositionMode(composition_mode)
        dest = QRectF(
            target_rect.left() + (float(entry.blend_position[0]) / float(document.width)) * target_rect.width(),
            target_rect.top() + (float(entry.blend_position[1]) / float(document.height)) * target_rect.height(),
            (float(entry.size[0]) / float(document.width)) * target_rect.width(),
            (float(entry.size[1]) / float(document.height)) * target_rect.height(),
        )
        painter.drawPixmap(dest, entry.pixmap, QRectF(0, 0, entry.size[0], entry.size[1]))
        painter.restore()

    def _apply_mask_step(
        self,
        painter: QPainter,
        document: Document,
        target_rect: QRectF,
        layer: Layer,
    ) -> bool:
        entry = self._mask_pixmap_for_layer(layer)
        if entry is None or entry.alpha_pixmap is None:
            return False
        dest = QRectF(
            target_rect.left() + (float(entry.blend_position[0]) / float(document.width)) * target_rect.width(),
            target_rect.top() + (float(entry.blend_position[1]) / float(document.height)) * target_rect.height(),
            (float(entry.size[0]) / float(document.width)) * target_rect.width(),
            (float(entry.size[1]) / float(document.height)) * target_rect.height(),
        )
        painter.save()
        if layer.ex_parent_id is None:
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Multiply)
            painter.drawPixmap(dest, entry.pixmap, QRectF(0, 0, entry.size[0], entry.size[1]))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        painter.drawPixmap(dest, entry.alpha_pixmap, QRectF(0, 0, entry.size[0], entry.size[1]))
        painter.restore()
        return True

    def _supports_layer(self, document: Document, layer: Layer, *, allow_clipping_mask: bool) -> bool:
        if layer.layer_type not in self._SUPPORTED_LAYER_TYPES:
            return False
        if getattr(layer, "_pixels_dirty", False):
            return False
        if layer.parent_id is not None:
            return False
        if self._is_root_effect(layer):
            return layer.adjustment is not None
        if layer.layer_type == LayerType.MASK:
            return layer.ex_parent_id is None
        if layer.clips_parent:
            return False
        if layer.clipping_mask and not allow_clipping_mask:
            return False
        if layer.blend_mode not in self._SUPPORTED_BLENDS:
            return False
        if layer.layer_type == LayerType.GROUP:
            return True
        child_processors = self._child_processors(document, layer)
        child_masks = self._child_masks(document, layer)
        processor_ids = {processor.id for processor in child_processors}
        mask_ids = {mask.id for mask in child_masks}
        for child in self._direct_visible_children(document, layer):
            if child.id in processor_ids or child.id in mask_ids:
                continue
            return False
        return True

    def _direct_visible_children(self, document: Document, layer: Layer) -> list[Layer]:
        return [candidate for candidate in document.layers if candidate.visible and candidate.parent_id == layer.id]

    def _child_processors(self, document: Document, layer: Layer) -> list[Layer]:
        return [
            child for child in self._direct_visible_children(document, layer)
            if child.layer_type in (LayerType.ADJUSTMENT, LayerType.FILTER)
        ]

    def _child_masks(self, document: Document, layer: Layer) -> list[Layer]:
        return [
            child for child in self._direct_visible_children(document, layer)
            if child.layer_type == LayerType.MASK
        ]

    @staticmethod
    def _apply_effective_mask(
        pixels: np.ndarray,
        mask: np.ndarray | None,
        blend_position: tuple[int, int],
        mask_position: tuple[int, int],
    ) -> np.ndarray:
        if mask is None:
            return pixels

        mh, mw = mask.shape[:2]
        px, py = blend_position
        mx, my = mask_position
        ix0 = max(px, mx)
        iy0 = max(py, my)
        ix1 = min(px + pixels.shape[1], mx + mw)
        iy1 = min(py + pixels.shape[0], my + mh)

        masked = pixels.copy()
        masked[..., 3] = 0.0
        if ix1 <= ix0 or iy1 <= iy0:
            return masked

        dx0 = ix0 - px
        dy0 = iy0 - py
        dx1 = dx0 + (ix1 - ix0)
        dy1 = dy0 + (iy1 - iy0)
        mx0 = ix0 - mx
        my0 = iy0 - my
        mx1 = mx0 + (ix1 - ix0)
        my1 = my0 + (iy1 - iy0)

        masked[dy0:dy1, dx0:dx1, :3] = pixels[dy0:dy1, dx0:dx1, :3]
        masked[dy0:dy1, dx0:dx1, 3] = (
            pixels[dy0:dy1, dx0:dx1, 3] * mask[my0:my1, mx0:mx1]
        )
        return masked

    def _flatten_layer_pixels(self, document: Document, layer: Layer) -> tuple[np.ndarray, tuple[int, int]] | None:
        if layer.layer_type == LayerType.GROUP:
            return self._flatten_group_pixels(document, layer)
        child_processors = self._child_processors(document, layer)
        mask = self._compositor._get_effective_mask(layer, document.layers)
        channels_default = layer.channel_r and layer.channel_g and layer.channel_b and layer.channel_a
        if not layer.styles and not child_processors and mask is None and channels_default:
            return layer.copy_display_u8(), layer.position

        pixels = layer.pixels
        if layer.styles:
            pixels = StyleEngine.apply_styles(pixels, layer.styles)
        pixels = self._compositor._apply_channels(pixels, layer)
        blend_pos = layer.position
        if child_processors:
            pixels, pad = self._compositor._apply_filters_padded(pixels, child_processors)
            if pad > 0:
                blend_pos = (layer.position[0] - pad, layer.position[1] - pad)
        pixels = self._apply_effective_mask(pixels, mask, blend_pos, layer.position)
        rgba_u8 = np.rint(np.clip(pixels, 0.0, 1.0) * 255.0).astype(np.uint8)
        return rgba_u8, blend_pos

    def _flatten_group_pixels(self, document: Document, group: Layer) -> tuple[np.ndarray, tuple[int, int]] | None:
        bounds = self._compositor._layer_bounds(group, document.layers)
        if bounds is None:
            rgba = np.zeros((1, 1, 4), dtype=np.uint8)
            return rgba, group.position

        group_img = self._compositor.composite_group_tight(group, document.layers)
        if group_img is None:
            rgba = np.zeros((1, 1, 4), dtype=np.uint8)
            return rgba, group.position

        blend_pos = (int(bounds[0]), int(bounds[1]))
        child_processors = self._child_processors(document, group)
        if child_processors:
            group_img, pad = self._compositor._apply_filters_padded(group_img, child_processors)
            if pad > 0:
                blend_pos = (blend_pos[0] - pad, blend_pos[1] - pad)
        if group.styles:
            group_img = StyleEngine.apply_styles(group_img, group.styles)
        group_img = self._compositor._apply_channels(group_img, group)

        group_mask = self._compositor._get_effective_mask(group, document.layers)
        group_img = self._apply_effective_mask(group_img, group_mask, blend_pos, group.position)

        rgba_u8 = np.rint(np.clip(group_img, 0.0, 1.0) * 255.0).astype(np.uint8)
        return rgba_u8, blend_pos

    def _composite_chain_tight(
        self,
        document: Document,
        chain: list[Layer],
    ) -> tuple[np.ndarray, tuple[int, int]] | None:
        flattened: list[tuple[Layer, np.ndarray, tuple[int, int]]] = []
        min_x = float("inf")
        min_y = float("inf")
        max_x = float("-inf")
        max_y = float("-inf")

        for layer in chain:
            layer_result = self._flatten_layer_pixels(document, layer)
            if layer_result is None:
                return None
            rgba_u8, blend_position = layer_result
            flattened.append((layer, rgba_u8, blend_position))
            min_x = min(min_x, float(blend_position[0]))
            min_y = min(min_y, float(blend_position[1]))
            max_x = max(max_x, float(blend_position[0] + rgba_u8.shape[1]))
            max_y = max(max_y, float(blend_position[1] + rgba_u8.shape[0]))

        if not flattened:
            return None

        origin_x = int(min_x)
        origin_y = int(min_y)
        width = max(1, int(max_x - min_x))
        height = max(1, int(max_y - min_y))
        canvas = np.zeros((height, width, 4), dtype=np.float32)
        previous = None

        for layer, rgba_u8, blend_position in flattened:
            pixels = rgba_u8.astype(np.float32) / 255.0
            local_pos = (blend_position[0] - origin_x, blend_position[1] - origin_y)
            if layer.clipping_mask:
                if previous is None:
                    return None
                placed = self._compositor._place_pixels(pixels, local_pos, width, height)
                placed[..., 3:4] *= previous[..., 3:4]
                self._compositor._blending.blend_region_inplace(
                    canvas,
                    placed,
                    (0, 0),
                    layer.blend_mode,
                    layer.opacity,
                )
                previous = placed
                continue

            self._compositor._blending.blend_region_inplace(
                canvas,
                pixels,
                local_pos,
                layer.blend_mode,
                layer.opacity,
            )
            previous = self._compositor._place_pixels(pixels, local_pos, width, height)

        rgba_u8 = np.rint(np.clip(canvas, 0.0, 1.0) * 255.0).astype(np.uint8)
        return rgba_u8, (origin_x, origin_y)

    def _pixmap_for_chain(self, document: Document, chain: list[Layer]) -> _LayerPixmapEntry | None:
        base = chain[0]
        existing = self._layer_pixmaps.get(base.id)
        flattened = self._composite_chain_tight(document, chain)
        if flattened is None:
            return None
        rgba, blend_position = flattened
        current_size = (int(rgba.shape[1]), int(rgba.shape[0]))
        if existing is not None and existing.size == current_size and existing.blend_position == blend_position:
            return existing

        if rgba.size == 0:
            return None
        h, w = rgba.shape[:2]
        qimg = QImage(rgba.data, w, h, w * 4, QImage.Format.Format_RGBA8888)
        pixmap = QPixmap.fromImage(qimg.copy())
        entry = _LayerPixmapEntry(pixmap=pixmap, size=(w, h), blend_position=blend_position)
        self._layer_pixmaps[base.id] = entry
        return entry

    def _pixmap_for_layer(self, document: Document, layer: Layer) -> _LayerPixmapEntry | None:
        existing = self._layer_pixmaps.get(layer.id)
        flattened = self._flatten_layer_pixels(document, layer)
        if flattened is None:
            return None
        rgba, blend_position = flattened
        current_size = (int(rgba.shape[1]), int(rgba.shape[0]))
        if existing is not None and existing.size == current_size and existing.blend_position == blend_position:
            return existing

        if rgba.size == 0:
            return None
        h, w = rgba.shape[:2]
        qimg = QImage(rgba.data, w, h, w * 4, QImage.Format.Format_RGBA8888)
        pixmap = QPixmap.fromImage(qimg.copy())
        entry = _LayerPixmapEntry(pixmap=pixmap, size=(w, h), blend_position=blend_position)
        self._layer_pixmaps[layer.id] = entry
        return entry

    @staticmethod
    def _entry_to_canvas_float(
        entry: _LayerPixmapEntry,
        canvas_width: int,
        canvas_height: int,
    ) -> np.ndarray:
        canvas = np.zeros((canvas_height, canvas_width, 4), dtype=np.float32)
        if entry.rgba_u8 is None:
            return canvas
        x, y = entry.blend_position
        h, w = entry.rgba_u8.shape[:2]
        sx = max(0, -x)
        sy = max(0, -y)
        dx = max(0, x)
        dy = max(0, y)
        width = min(w - sx, canvas_width - dx)
        height = min(h - sy, canvas_height - dy)
        if width > 0 and height > 0:
            canvas[dy:dy + height, dx:dx + width] = (
                entry.rgba_u8[sy:sy + height, sx:sx + width].astype(np.float32) / 255.0
            )
        return canvas

    def _pixmap_for_prefix(
        self,
        document: Document,
        graph: list[_TopLevelGraphNode],
        prefix_segment: _PrefixNode | _PrefixCacheNode,
    ) -> _LayerPixmapEntry | None:
        cache_key = prefix_segment.cache_key
        if cache_key is None or prefix_segment.layer is None:
            return None
        existing = self._layer_pixmaps.get(cache_key)
        stack = LayerStack()
        for dependency_key in prefix_segment.cache_dependencies:
            dependency_segment = self._cache_segment_by_key(graph, dependency_key)
            if dependency_segment is None:
                return None
            if isinstance(dependency_segment, (_PrefixNode, _PrefixCacheNode)):
                dependency_entry = self._pixmap_for_prefix(document, graph, dependency_segment)
            elif isinstance(dependency_segment, (_RunCacheNode, _SegmentNode)):
                dependency_entry = self._pixmap_for_segment(document, list(dependency_segment.layers), dependency_key)
            else:
                return None
            if dependency_entry is None or dependency_entry.rgba_u8 is None:
                continue
            synthetic_dependency = Layer(
                name="GPU Prefix Dependency",
                width=document.width,
                height=document.height,
            )
            synthetic_dependency.pixels[:] = self._entry_to_canvas_float(
                dependency_entry,
                document.width,
                document.height,
            )
            stack.add(synthetic_dependency)
        stack.add(prefix_segment.layer)
        prefix = self._compositor.composite(stack, document.width, document.height)
        alpha = prefix[..., 3] > 0.0
        if not np.any(alpha):
            rgba = np.zeros((1, 1, 4), dtype=np.uint8)
            blend_position = (0, 0)
        else:
            ys, xs = np.nonzero(alpha)
            min_y = int(ys.min())
            max_y = int(ys.max()) + 1
            min_x = int(xs.min())
            max_x = int(xs.max()) + 1
            cropped = prefix[min_y:max_y, min_x:max_x]
            rgba = np.rint(np.clip(cropped, 0.0, 1.0) * 255.0).astype(np.uint8)
            blend_position = (min_x, min_y)
        current_size = (int(rgba.shape[1]), int(rgba.shape[0]))
        if existing is not None and existing.size == current_size and existing.blend_position == blend_position:
            return existing
        h, w = rgba.shape[:2]
        qimg = QImage(rgba.data, w, h, w * 4, QImage.Format.Format_RGBA8888)
        pixmap = QPixmap.fromImage(qimg.copy())
        entry = _LayerPixmapEntry(pixmap=pixmap, size=(w, h), blend_position=blend_position, rgba_u8=rgba.copy())
        self._layer_pixmaps[cache_key] = entry
        return entry

    def _pixmap_for_segment(
        self,
        document: Document,
        segment_layers: list[Layer],
        cache_key: str,
    ) -> _LayerPixmapEntry | None:
        existing = self._layer_pixmaps.get(cache_key)
        if not segment_layers:
            rgba = np.zeros((1, 1, 4), dtype=np.uint8)
            blend_position = (0, 0)
        else:
            stack = LayerStack()
            for layer in segment_layers:
                stack.add(layer)
            segment = self._compositor.composite(stack, document.width, document.height)
            alpha = segment[..., 3] > 0.0
            if not np.any(alpha):
                rgba = np.zeros((1, 1, 4), dtype=np.uint8)
                blend_position = (0, 0)
            else:
                ys, xs = np.nonzero(alpha)
                min_y = int(ys.min())
                max_y = int(ys.max()) + 1
                min_x = int(xs.min())
                max_x = int(xs.max()) + 1
                cropped = segment[min_y:max_y, min_x:max_x]
                rgba = np.rint(np.clip(cropped, 0.0, 1.0) * 255.0).astype(np.uint8)
                blend_position = (min_x, min_y)
        current_size = (int(rgba.shape[1]), int(rgba.shape[0]))
        if existing is not None and existing.size == current_size and existing.blend_position == blend_position:
            return existing
        h, w = rgba.shape[:2]
        qimg = QImage(rgba.data, w, h, w * 4, QImage.Format.Format_RGBA8888)
        pixmap = QPixmap.fromImage(qimg.copy())
        entry = _LayerPixmapEntry(pixmap=pixmap, size=(w, h), blend_position=blend_position, rgba_u8=rgba.copy())
        self._layer_pixmaps[cache_key] = entry
        return entry

    def _mask_pixmap_for_layer(self, layer: Layer) -> _LayerPixmapEntry | None:
        existing = self._layer_pixmaps.get(layer.id)
        gray = np.clip(layer.get_mask_grayscale(), 0.0, 1.0)
        alpha_u8 = np.rint(gray * 255.0).astype(np.uint8)
        h, w = alpha_u8.shape[:2]
        current_size = (int(w), int(h))
        if (
            existing is not None
            and existing.size == current_size
            and existing.blend_position == layer.position
            and existing.alpha_pixmap is not None
        ):
            return existing

        multiply_rgba = np.full((h, w, 4), 255, dtype=np.uint8)
        multiply_rgba[..., 0] = alpha_u8
        multiply_rgba[..., 1] = alpha_u8
        multiply_rgba[..., 2] = alpha_u8
        multiply_qimg = QImage(multiply_rgba.data, w, h, w * 4, QImage.Format.Format_RGBA8888)
        multiply_pixmap = QPixmap.fromImage(multiply_qimg.copy())

        alpha_rgba = np.zeros((h, w, 4), dtype=np.uint8)
        alpha_rgba[..., 3] = alpha_u8
        alpha_qimg = QImage(alpha_rgba.data, w, h, w * 4, QImage.Format.Format_RGBA8888)
        alpha_pixmap = QPixmap.fromImage(alpha_qimg.copy())

        entry = _LayerPixmapEntry(
            pixmap=multiply_pixmap,
            size=current_size,
            blend_position=layer.position,
            alpha_pixmap=alpha_pixmap,
        )
        self._layer_pixmaps[layer.id] = entry
        return entry
