"""Canvas viewport state (zoom, pan, guides, grid)."""

from dataclasses import dataclass, field


@dataclass
class CanvasState:
    """Mutable viewport state for the canvas widget."""

    zoom: float = 1.0
    pan_x: float = 0.0
    pan_y: float = 0.0
    rotation: float = 0.0
    show_grid: bool = False
    grid_size: int = 32
    snap_to_grid: bool = False
    show_rulers: bool = True
    show_guides: bool = True
    guides_h: list[float] = field(default_factory=list)
    guides_v: list[float] = field(default_factory=list)

    # ---- Zoom ---------------------------------------------------------------

    def zoom_in(self, factor: float = 1.25) -> None:
        self.zoom = min(self.zoom * factor, 32.0)

    def zoom_out(self, factor: float = 1.25) -> None:
        self.zoom = max(self.zoom / factor, 0.01)

    def zoom_to_fit(self, canvas_w: int, canvas_h: int, view_w: int, view_h: int) -> None:
        sx = view_w / max(canvas_w, 1)
        sy = view_h / max(canvas_h, 1)
        self.zoom = min(sx, sy) * 0.9
        self.pan_x = self.pan_y = 0.0

    def zoom_to_100(self) -> None:
        self.zoom = 1.0

    def reset(self) -> None:
        self.zoom = 1.0
        self.pan_x = self.pan_y = 0.0
        self.rotation = 0.0

    # ---- Guides -------------------------------------------------------------

    def add_guide_h(self, position: float) -> None:
        self.guides_h.append(position)

    def add_guide_v(self, position: float) -> None:
        self.guides_v.append(position)

    def clear_guides(self) -> None:
        self.guides_h.clear()
        self.guides_v.clear()

    # ---- Snap ---------------------------------------------------------------

    def snap_point(self, x: float, y: float) -> tuple[float, float]:
        if not self.snap_to_grid:
            return x, y
        gs = self.grid_size
        return round(x / gs) * gs, round(y / gs) * gs
