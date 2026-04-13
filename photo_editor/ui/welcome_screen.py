"""Welcome screen — Basera branding, New/Open/Recent actions."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap, QFont, QPainter, QColor, QPen, QLinearGradient
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QFrame, QSizePolicy,
    QGraphicsDropShadowEffect,
)

from .styles import render_qss


_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "app"


class WelcomeScreen(QWidget):
    """Full-window welcome screen with Basera branding and recent projects."""

    new_project_requested = Signal()
    open_image_requested = Signal()
    open_basera_requested = Signal()
    recent_project_selected = Signal(str)  # path

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("WelcomeScreen")
        self._build_ui()

        from .theme import ThemeManager
        ThemeManager.instance().theme_changed.connect(self._apply_theme)
        self._apply_theme(ThemeManager.instance().active_palette)

    def _apply_theme(self, palette: dict) -> None:
        self.setStyleSheet(render_qss("welcome_screen.qss", palette))

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Center everything
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(60, 40, 60, 40)
        center_layout.setSpacing(0)
        center_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # ---- Logo + Branding ----
        brand_layout = QVBoxLayout()
        brand_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        brand_layout.setSpacing(12)

        # Logo
        logo_label = QLabel()
        logo_label.setObjectName("WelcomeLogo")
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_path = _ASSETS_DIR / "logo.svg"
        if logo_path.exists():
            pixmap = QPixmap(str(logo_path))
            scaled = pixmap.scaled(
                QSize(140, 140),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            logo_label.setPixmap(scaled)
        logo_label.setFixedSize(160, 160)
        brand_layout.addWidget(logo_label, 0, Qt.AlignmentFlag.AlignHCenter)

        # Title
        title = QLabel("Basera")
        title.setObjectName("WelcomeTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_layout.addWidget(title)

        # Subtitle
        subtitle = QLabel("Professional Photo Editor")
        subtitle.setObjectName("WelcomeSubtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_layout.addWidget(subtitle)

        center_layout.addStretch(2)
        center_layout.addLayout(brand_layout)
        center_layout.addSpacing(40)

        # ---- Action buttons ----
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(16)
        actions_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # New Project
        btn_new = QPushButton("  ✦  New Project")
        btn_new.setObjectName("WelcomePrimaryButton")
        btn_new.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_new.clicked.connect(self.new_project_requested.emit)
        self._add_shadow(btn_new)
        actions_layout.addWidget(btn_new)

        # Open Image
        btn_open = QPushButton("  📂  Open Image")
        btn_open.setObjectName("WelcomeActionButton")
        btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_open.clicked.connect(self.open_image_requested.emit)
        self._add_shadow(btn_open)
        actions_layout.addWidget(btn_open)

        # Open .basera
        btn_basera = QPushButton("  📦  Open .basera")
        btn_basera.setObjectName("WelcomeActionButton")
        btn_basera.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_basera.clicked.connect(self.open_basera_requested.emit)
        self._add_shadow(btn_basera)
        actions_layout.addWidget(btn_basera)

        center_layout.addLayout(actions_layout)
        center_layout.addSpacing(36)

        # ---- Recent projects ----
        recent_section = QVBoxLayout()
        recent_section.setSpacing(10)

        recent_title = QLabel("RECENT PROJECTS")
        recent_title.setObjectName("WelcomeSectionTitle")
        recent_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        recent_section.addWidget(recent_title)

        self._recent_container = QVBoxLayout()
        self._recent_container.setSpacing(6)
        self._recent_container.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        # Placeholder — no recent projects yet
        no_recent = QLabel("No recent projects")
        no_recent.setObjectName("WelcomeRecentInfo")
        no_recent.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._recent_container.addWidget(no_recent)

        recent_section.addLayout(self._recent_container)
        center_layout.addLayout(recent_section)

        center_layout.addStretch(3)

        # Version
        version = QLabel("v0.4-alpha")
        version.setObjectName("WelcomeVersion")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_layout.addWidget(version)

        root.addWidget(center_widget)

    def _add_shadow(self, widget: QWidget, blur: int = 20, alpha: int = 40) -> None:
        shadow = QGraphicsDropShadowEffect(widget)
        shadow.setBlurRadius(blur)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, alpha))
        widget.setGraphicsEffect(shadow)

    def set_recent_projects(self, projects: list[dict]) -> None:
        """Update the recent projects list. Each dict: {name, path, size, thumbnail?}."""
        # Clear existing
        while self._recent_container.count():
            item = self._recent_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not projects:
            no_recent = QLabel("No recent projects")
            no_recent.setObjectName("WelcomeRecentInfo")
            no_recent.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._recent_container.addWidget(no_recent)
            return

        for proj in projects[:8]:
            item = self._create_recent_item(proj)
            self._recent_container.addWidget(item)

    def _create_recent_item(self, project: dict) -> QWidget:
        item = QWidget()
        item.setObjectName("WelcomeRecentItem")
        item.setFixedHeight(52)
        item.setFixedWidth(500)
        item.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(item)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(12)

        # Thumbnail
        thumb = QLabel()
        thumb.setObjectName("WelcomeRecentThumb")
        thumb.setFixedSize(36, 36)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb.setText("📄")
        layout.addWidget(thumb)

        # Info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        name = QLabel(project.get("name", "Untitled"))
        name.setObjectName("WelcomeRecentName")
        info_layout.addWidget(name)

        path_str = project.get("path", "")
        size_str = project.get("size", "")
        detail = QLabel(f"{path_str}  ·  {size_str}" if size_str else path_str)
        detail.setObjectName("WelcomeRecentInfo")
        info_layout.addWidget(detail)

        layout.addLayout(info_layout, 1)

        # Make clickable
        path = project.get("path", "")
        item.mousePressEvent = lambda e, p=path: self.recent_project_selected.emit(p)

        return item
