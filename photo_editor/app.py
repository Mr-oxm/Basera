"""Application entry point — initialises Qt and launches the main window."""

import sys
import os

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from photo_editor.ui.main_window import MainWindow


def run() -> int:
    """Create the QApplication, show the main window, and enter the event loop."""
    # On Windows, set the AppUserModelID so the taskbar displays the custom icon
    # instead of the default Python executable icon.
    if sys.platform == "win32":
        import ctypes
        myappid = "baseraproject.basera.app.1.0"
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except AttributeError:
            pass  # Fallback for very old Windows versions

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Basera")
    app.setOrganizationName("BaseraProject")
    
    icon_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "assets", "app", "logo.png"
    )
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    splash_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "assets", "app", "splash.jpg"
    )

    from PySide6.QtWidgets import QSplashScreen
    from PySide6.QtGui import QPixmap
    from PySide6.QtCore import Qt

    splash = None
    if os.path.exists(splash_path):
        pixmap = QPixmap(splash_path)
        pixmap = pixmap.scaledToWidth(600, Qt.TransformationMode.SmoothTransformation)
        splash = QSplashScreen(pixmap, Qt.WindowType.WindowStaysOnTopHint)
        splash.show()
        app.processEvents()

    window = MainWindow()
    window.show()

    if splash:
        splash.finish(window)

    return app.exec()


if __name__ == "__main__":
    sys.exit(run())
