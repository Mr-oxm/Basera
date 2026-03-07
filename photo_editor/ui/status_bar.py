"""Status bar showing document info, zoom level, cursor position.

Modern pill-based layout with subtle depth cues and clean typography.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QStatusBar, QWidget

from .styles import render_qss

# ── tiny helpers ────────────────────────────────────────────────────────

_H_PAD = 14  # horizontal padding applied via contentsMargins

def _pill(text: str = "") -> QLabel:
    """Create a pill-shaped label."""
    lbl = QLabel(text)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setFixedHeight(20)
    lbl.setContentsMargins(_H_PAD, 0, _H_PAD, 0)
    return lbl


def _dot_sep() -> QLabel:
    """Tiny dot separator between pills."""
    dot = QLabel("\u00b7")
    dot.setStyleSheet(render_qss("status_bar_dot.qss", fg="#555555"))
    dot.setFixedWidth(8)
    dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
    dot.setContentsMargins(0, 0, 0, 0)
    return dot


# ── status bar ──────────────────────────────────────────────────────────


class EditorStatusBar(QStatusBar):
    """Bottom status bar with contextual information pills."""

    # Emitted when the user toggles auto-rasterize on/off
    auto_rasterize_changed = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setSizeGripEnabled(False)
        self.setFixedHeight(30)

        # ── left cluster ────────────────────────────────────────────────
        left = QWidget()
        hl = QHBoxLayout(left)
        hl.setContentsMargins(6, 0, 0, 0)
        hl.setSpacing(5)

        self._doc_pill = _pill("No document")
        self._size_pill = _pill("")
        self._tool_pill = _pill("")

        hl.addWidget(self._doc_pill)
        hl.addWidget(_dot_sep())
        hl.addWidget(self._size_pill)
        hl.addWidget(_dot_sep())
        hl.addWidget(self._tool_pill)
        hl.addStretch()

        # ── right cluster ───────────────────────────────────────────────
        right = QWidget()
        hr = QHBoxLayout(right)
        hr.setContentsMargins(0, 0, 6, 0)
        hr.setSpacing(5)

        # Auto-rasterize toggle for vector layers
        self._auto_rasterize_cb = QCheckBox("Auto-Rasterize")
        self._auto_rasterize_cb.setChecked(True)
        self._auto_rasterize_cb.setToolTip(
            "When checked, vector layers are continuously rasterized.\n"
            "Uncheck to view curves only (better performance)."
        )
        self._auto_rasterize_cb.toggled.connect(self.auto_rasterize_changed.emit)

        self._pos_pill = _pill("x: 0  y: 0")
        self._zoom_pill = _pill("100 %")

        hr.addStretch()
        hr.addWidget(self._auto_rasterize_cb)
        hr.addWidget(_dot_sep())
        hr.addWidget(self._pos_pill)
        hr.addWidget(_dot_sep())
        hr.addWidget(self._zoom_pill)

        # Attach clusters to the status bar
        self.addWidget(left, 1)
        self.addPermanentWidget(right)

        from .theme import ThemeManager
        ThemeManager.instance().theme_changed.connect(self._apply_theme)
        self._apply_theme(ThemeManager.instance().active_palette)

    # ── public API (unchanged signatures) ───────────────────────────────

    def set_document_info(self, name: str, width: int, height: int) -> None:
        self._doc_pill.setText(name)
        self._size_pill.setText(f"{width}\u2009\u00d7\u2009{height}\u2009px")

    def set_zoom(self, zoom: float) -> None:
        self._zoom_pill.setText(f"{zoom * 100:.0f}\u2009%")

    def set_cursor_pos(self, x: int, y: int) -> None:
        self._pos_pill.setText(f"x:\u2009{x}\u2003y:\u2009{y}")

    def set_tool(self, name: str) -> None:
        self._tool_pill.setText(name)

    @property
    def auto_rasterize(self) -> bool:
        """Whether vector layers should be continuously rasterized."""
        return self._auto_rasterize_cb.isChecked()

    @auto_rasterize.setter
    def auto_rasterize(self, value: bool) -> None:
        self._auto_rasterize_cb.setChecked(value)

    def _apply_theme(self, palette: dict) -> None:
        self.setStyleSheet(render_qss("status_bar.qss", palette))
        
        accent_pill = render_qss(
            "status_bar_pill.qss",
            bg=palette['accent'],
            fg=palette['fg_accent'],
            weight=600,
        )
        dim_pill = render_qss(
            "status_bar_pill.qss",
            bg="transparent",
            fg=palette['fg_dim'],
            weight=400,
        )
        
        self._doc_pill.setStyleSheet(accent_pill)
        self._size_pill.setStyleSheet(dim_pill)
        self._tool_pill.setStyleSheet(dim_pill)
        self._pos_pill.setStyleSheet(dim_pill)
        self._zoom_pill.setStyleSheet(dim_pill)
        
        self._auto_rasterize_cb.setStyleSheet(render_qss("status_bar_checkbox.qss", palette))
