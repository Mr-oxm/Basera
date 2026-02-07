"""Application entry point — initialises Qt and launches the main window."""

import sys

from PySide6.QtWidgets import QApplication

from photo_editor.ui.main_window import MainWindow


def run() -> int:
    """Create the QApplication, show the main window, and enter the event loop."""
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Photo Editor")
    app.setOrganizationName("PhotoEditorProject")

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(run())
