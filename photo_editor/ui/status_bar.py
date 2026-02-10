"""Status bar showing document info, zoom level, cursor position.

Modern pill-based layout with subtle depth cues and clean typography.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QStatusBar, QWidget

# ── tiny helpers ────────────────────────────────────────────────────────

_H_PAD = 14  # horizontal padding applied via contentsMargins

_PILL_CSS = """
    QLabel {{
        background: {bg};
        color: {fg};
        border-radius: 9px;
        padding: 0px;
        font-size: 11px;
        font-weight: {weight};
        letter-spacing: 0.3px;
    }}
"""

_ACCENT_PILL = _PILL_CSS.format(bg="#3d5a80", fg="#d0dcea", weight=600)
_MUTED_PILL = _PILL_CSS.format(bg="rgba(255,255,255,0.06)", fg="#9a9a9a", weight=400)
_DIM_PILL = _PILL_CSS.format(bg="transparent", fg="#777777", weight=400)


def _pill(text: str = "", style: str = _MUTED_PILL) -> QLabel:
    """Create a pill-shaped label."""
    lbl = QLabel(text)
    lbl.setStyleSheet(style)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setFixedHeight(20)
    lbl.setContentsMargins(_H_PAD, 0, _H_PAD, 0)
    return lbl


def _dot_sep() -> QLabel:
    """Tiny dot separator between pills."""
    dot = QLabel("\u00b7")
    dot.setStyleSheet("color: #555555; font-size: 14px; font-weight: 700;")
    dot.setFixedWidth(8)
    dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
    dot.setContentsMargins(0, 0, 0, 0)
    return dot


# ── status bar ──────────────────────────────────────────────────────────


class EditorStatusBar(QStatusBar):
    """Bottom status bar with contextual information pills."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setSizeGripEnabled(False)
        self.setFixedHeight(30)

        # Remove default QStatusBar item frames
        self.setStyleSheet(
            "QStatusBar { border-top: 1px solid #3a3a3a; background: #2e2e2e; }"
            "QStatusBar::item { border: none; }"
        )

        # ── left cluster ────────────────────────────────────────────────
        left = QWidget()
        left.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(left)
        hl.setContentsMargins(6, 0, 0, 0)
        hl.setSpacing(5)

        self._doc_pill = _pill("No document", _ACCENT_PILL)
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
        right.setStyleSheet("background: transparent;")
        hr = QHBoxLayout(right)
        hr.setContentsMargins(0, 0, 6, 0)
        hr.setSpacing(5)

        self._pos_pill = _pill("x: 0  y: 0", _DIM_PILL)
        self._zoom_pill = _pill("100 %")

        hr.addStretch()
        hr.addWidget(self._pos_pill)
        hr.addWidget(_dot_sep())
        hr.addWidget(self._zoom_pill)

        # Attach clusters to the status bar
        self.addWidget(left, 1)
        self.addPermanentWidget(right)

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
