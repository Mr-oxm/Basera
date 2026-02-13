
import sys
import unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication

# Mock config path to avoid messing with user's real config
import photo_editor.ui.shortcut_manager as sm

# Use a temporary file for config
import tempfile
import os

class TestShortcutManager(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp_dir.name) / "shortcuts.json"
        
        # Monkeypatch config path
        self.original_config_path = sm._config_path
        sm._config_path = lambda: self.tmp_path

        # Reset singleton if possible (it's not easily reset in the code provided, 
        # but we can just re-instantiate since __init__ resets state if we don't check _instance)
        # Actually calling ShortcutManager() calls __init__ which resets state.
        self.mgr = sm.ShortcutManager()

    def tearDown(self):
        sm._config_path = self.original_config_path
        self.tmp_dir.cleanup()

    def test_default_preset(self):
        self.assertEqual(self.mgr.preset_name, "Photoshop")
        self.assertEqual(self.mgr.binding("tool_brush"), "B")

    def test_switch_preset(self):
        self.mgr.set_preset("Affinity Photo")
        self.assertEqual(self.mgr.preset_name, "Affinity Photo")
        # In Affinity, Redo might be different or same. 
        # Photoshop: Ctrl+Shift+Z. Affinity: Ctrl+Y.
        self.assertEqual(self.mgr.binding("redo"), "Ctrl+Y")

    def test_custom_binding(self):
        self.mgr.set_binding("tool_brush", "Shift+X")
        self.assertEqual(self.mgr.binding("tool_brush"), "Shift+X")
        self.assertTrue(self.mgr.is_custom("tool_brush"))
        
        # Check persistence
        # Re-load
        mgr2 = sm.ShortcutManager()
        self.assertEqual(mgr2.binding("tool_brush"), "Shift+X")

    def test_reset(self):
        self.mgr.set_binding("tool_brush", "Shift+X")
        self.mgr.reset_to_preset()
        self.assertFalse(self.mgr.is_custom("tool_brush"))
        self.assertEqual(self.mgr.binding("tool_brush"), "B")

if __name__ == "__main__":
    # QApp needed for QObject signals
    app = QApplication.instance() or QApplication(sys.argv)
    unittest.main()
