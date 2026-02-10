"""Professional dark theme for the photo editor."""

DARK_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #2b2b2b;
    color: #cccccc;
    font-family: "Segoe UI", "Helvetica Neue", sans-serif;
    font-size: 12px;
}
QMenuBar {
    background-color: #333333;
    color: #cccccc;
    border-bottom: 1px solid #444444;
}
QMenuBar::item:selected { background-color: #505050; }
QMenu {
    background-color: #383838;
    color: #cccccc;
    border: 1px solid #555555;
}
QMenu::item:selected { background-color: #4a6fa5; }
QMenu::separator { height: 1px; background: #555555; margin: 4px 8px; }
QToolBar {
    background-color: #333333;
    border: none;
    spacing: 2px;
    padding: 2px;
}
QToolButton { background: transparent; border: 1px solid transparent; border-radius: 3px; padding: 4px; }
QToolButton:hover { background-color: #444444; border-color: #555555; }
QToolButton:checked { background-color: #4a6fa5; border-color: #5a7fb5; }
QDockWidget {
    titlebar-close-icon: none;
    color: #cccccc;
}
QDockWidget::title {
    background-color: #383838;
    padding: 6px;
    border-bottom: 1px solid #444444;
}
QListWidget, QTreeWidget {
    background-color: #2f2f2f;
    border: 1px solid #444444;
    alternate-background-color: #333333;
}
QListWidget::item:selected, QTreeWidget::item:selected {
    background-color: #4a6fa5;
}
QScrollBar:vertical {
    background-color: #2b2b2b; width: 10px; border: none;
}
QScrollBar::handle:vertical {
    background-color: #555555; min-height: 30px; border-radius: 5px;
}
QScrollBar::handle:vertical:hover { background-color: #666666; }
QScrollBar:horizontal {
    background-color: #2b2b2b; height: 10px; border: none;
}
QScrollBar::handle:horizontal {
    background-color: #555555; min-width: 30px; border-radius: 5px;
}
QPushButton {
    background-color: #444444; border: 1px solid #555555;
    border-radius: 3px; padding: 5px 12px; color: #cccccc;
}
QPushButton:hover { background-color: #505050; }
QPushButton:pressed { background-color: #4a6fa5; }
QSlider::groove:horizontal {
    background: #444444; height: 4px; border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #aaaaaa; width: 12px; height: 12px;
    margin: -4px 0; border-radius: 6px;
}
QSlider::handle:horizontal:hover { background: #cccccc; }
QComboBox {
    background-color: #444444; border: 1px solid #555555;
    border-radius: 3px; padding: 3px 8px; color: #cccccc;
}
QComboBox::drop-down { border: none; }
QComboBox QAbstractItemView {
    background-color: #383838; color: #cccccc;
    selection-background-color: #4a6fa5;
}
QSpinBox, QDoubleSpinBox {
    background-color: #3a3a3a; border: 1px solid #555555;
    border-radius: 3px; padding: 2px; color: #cccccc;
}
QLabel { color: #cccccc; }
QStatusBar {
    background-color: #2e2e2e; color: #999999;
    border-top: 1px solid #3a3a3a;
    padding: 0px;
}
QStatusBar::item { border: none; }
QTabWidget::pane { border: 1px solid #444444; }
QTabBar::tab {
    background-color: #383838; color: #aaaaaa;
    padding: 6px 14px; border: 1px solid #444444;
}
QTabBar::tab:selected { background-color: #2b2b2b; color: #cccccc; border-bottom: none; }
QGroupBox {
    border: 1px solid #444444; border-radius: 4px;
    margin-top: 8px; padding-top: 12px; color: #cccccc;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
"""
