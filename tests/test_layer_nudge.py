"""Tests for keyboard arrow key layer movement (nudge)."""

import unittest
from unittest.mock import MagicMock, patch
import numpy as np

from PySide6.QtWidgets import QApplication, QLineEdit, QMainWindow, QSpinBox
from PySide6.QtGui import QKeySequence

from photo_editor.core.document import Document
from photo_editor.core.enums import LayerType, ToolType
from photo_editor.vector.shapes import RectangleShape
from photo_editor.vector.scene import VectorObject
from photo_editor.vector.rasterizer import rasterize_vector_layer_tight
from photo_editor.ui.shortcut_manager import ShortcutManager, PRESETS, ACTION_REGISTRY
from photo_editor.ui.controllers.layer_ctrl import LayerController
from photo_editor.ui.controllers.shortcut_ctrl import ShortcutController


app = QApplication.instance() or QApplication([])


class TestShortcutManagerNudge(unittest.TestCase):
    def test_nudge_presets_exist(self):
        sm = ShortcutManager.instance()
        expected = {
            "nudge_up": "Up",
            "nudge_down": "Down",
            "nudge_left": "Left",
            "nudge_right": "Right",
            "nudge_up_10": "Shift+Up",
            "nudge_down_10": "Shift+Down",
            "nudge_left_10": "Shift+Left",
            "nudge_right_10": "Shift+Right",
        }
        for aid, key_seq in expected.items():
            self.assertEqual(sm.binding(aid), key_seq)
            self.assertEqual(PRESETS["Photoshop"].get(aid), key_seq)
            self.assertEqual(PRESETS["Affinity Photo"].get(aid), key_seq)

    def test_nudge_in_action_registry(self):
        layer_actions = [aid for cat, aid, name in ACTION_REGISTRY if cat == "Layer"]
        self.assertIn("nudge_up", layer_actions)
        self.assertIn("nudge_down", layer_actions)
        self.assertIn("nudge_left", layer_actions)
        self.assertIn("nudge_right", layer_actions)
        self.assertIn("nudge_up_10", layer_actions)
        self.assertIn("nudge_down_10", layer_actions)
        self.assertIn("nudge_left_10", layer_actions)
        self.assertIn("nudge_right_10", layer_actions)


class TestLayerControllerNudge(unittest.TestCase):
    def setUp(self):
        self.doc = Document(200, 200)
        self.ctrl = LayerController()
        # Mock MainWindow and Context
        self.mw = MagicMock()
        self.mw._doc = self.doc
        self.mw._tools.active_type = ToolType.MOVE
        self.mw._tools.active_tool = MagicMock()
        self.mw._tools.active_tool._floating = False
        self.ctrl.wire(self.mw)

    def test_nudge_raster_layer_directions(self):
        layer = self.doc.add_layer("Layer 1")
        layer.position = (50, 50)
        self.doc.layers.active_index = self.doc.layers.layers.index(layer)

        # Up 1px
        self.assertTrue(self.ctrl.nudge_layer(0, -1))
        self.assertEqual(layer.position, (50, 49))

        # Down 1px
        self.assertTrue(self.ctrl.nudge_layer(0, 1))
        self.assertEqual(layer.position, (50, 50))

        # Left 1px
        self.assertTrue(self.ctrl.nudge_layer(-1, 0))
        self.assertEqual(layer.position, (49, 50))

        # Right 1px
        self.assertTrue(self.ctrl.nudge_layer(1, 0))
        self.assertEqual(layer.position, (50, 50))

        # Large nudge (10px)
        self.assertTrue(self.ctrl.nudge_layer(10, -10))
        self.assertEqual(layer.position, (60, 40))

    def test_nudge_locked_layer_rejected(self):
        layer = self.doc.add_layer("Locked Layer")
        layer.position = (50, 50)
        layer.locked = True
        self.doc.layers.active_index = self.doc.layers.layers.index(layer)

        self.assertFalse(self.ctrl.nudge_layer(1, 0))
        self.assertEqual(layer.position, (50, 50))

    def test_nudge_undo_redo(self):
        layer = self.doc.add_layer("Undo Test")
        layer.position = (10, 10)
        self.doc.layers.active_index = self.doc.layers.layers.index(layer)

        self.ctrl.nudge_layer(5, 5)
        self.assertEqual(self.doc.layers.active_layer.position, (15, 15))

        self.doc.undo()
        self.assertEqual(self.doc.layers.active_layer.position, (10, 10))

        self.doc.redo()
        self.assertEqual(self.doc.layers.active_layer.position, (15, 15))

    def test_nudge_vector_layer(self):
        vlayer = self.doc.add_vector_layer("Vector Layer")
        rect = RectangleShape(30, 30).to_path()
        obj = VectorObject(path=rect)
        vlayer._vector_data.add(obj)
        rasterize_vector_layer_tight(self.doc, layer=vlayer, force=True)
        orig_pos = vlayer.position
        self.doc.layers.active_index = self.doc.layers.layers.index(vlayer)

        self.ctrl.nudge_layer(3, 4)
        expected = (orig_pos[0] + 3, orig_pos[1] + 4)
        self.assertEqual(vlayer.position, expected)

    def test_nudge_group_layer(self):
        group = self.doc.add_group("My Group")
        child = self.doc.add_layer("Child")
        child.position = (20, 20)
        child.pixels = np.zeros((30, 30, 4), dtype=np.float32)
        child.parent_id = group.id
        self.doc.layers.update_group_bbox(group)
        orig_group_pos = group.position
        orig_child_pos = child.position

        # Select the group
        self.doc.layers.active_index = self.doc.layers.layers.index(group)
        self.ctrl.nudge_layer(5, 5)

        self.assertEqual(child.position, (orig_child_pos[0] + 5, orig_child_pos[1] + 5))
        self.assertEqual(group.position, (orig_group_pos[0] + 5, orig_group_pos[1] + 5))

    def test_nudge_layer_with_mask(self):
        parent = self.doc.add_layer("Parent")
        parent.position = (10, 10)
        mask = self.doc.add_layer("Mask", layer_type=LayerType.MASK)
        mask.position = (10, 10)
        parent.mask_layers.append(mask.id)
        self.doc.layers.active_index = self.doc.layers.layers.index(parent)

        self.ctrl.nudge_layer(2, 3)
        self.assertEqual(parent.position, (12, 13))
        self.assertEqual(mask.position, (12, 13))

    def test_nudge_multi_selected_layers(self):
        l1 = self.doc.add_layer("L1")
        l1.position = (10, 10)
        l2 = self.doc.add_layer("L2")
        l2.position = (50, 50)

        idx1 = self.doc.layers.layers.index(l1)
        idx2 = self.doc.layers.layers.index(l2)
        self.doc.layers.select_clear()
        self.doc.layers.select_add(idx1)
        self.doc.layers.select_add(idx2)
        self.doc.layers._active_index = idx1

        self.ctrl.nudge_layer(-2, 4)
        self.assertEqual(l1.position, (8, 14))
        self.assertEqual(l2.position, (48, 54))


class TestShortcutControllerGuards(unittest.TestCase):
    def setUp(self):
        self.sctrl = ShortcutController()
        self.mw = QMainWindow()
        self.mw._shortcut_mgr = ShortcutManager.instance()
        self.mw._tools = MagicMock()
        self.mw._canvas = MagicMock()
        self.mw._canvas._text_editing = False
        self.mw._layer_ctrl = MagicMock()
        self.sctrl.wire(self.mw)

    def test_skip_when_canvas_text_editing(self):
        self.mw._tools.active_type = ToolType.TEXT
        self.mw._canvas._text_editing = True
        self.sctrl._on_nudge(1, 0)
        self.mw._layer_ctrl.nudge_layer.assert_not_called()

    def test_skip_when_line_edit_focused(self):
        le = QLineEdit()
        with patch.object(QApplication, "focusWidget", return_value=le):
            self.sctrl._on_nudge(1, 0)
            self.mw._layer_ctrl.nudge_layer.assert_not_called()

    def test_step_spinbox_when_focused(self):
        sb = QSpinBox()
        sb.setValue(10)
        with patch.object(QApplication, "focusWidget", return_value=sb):
            self.sctrl._on_nudge(0, -1)  # Nudge Up -> step up
            self.assertEqual(sb.value(), 11)
            self.mw._layer_ctrl.nudge_layer.assert_not_called()

            self.sctrl._on_nudge(0, 1)  # Nudge Down -> step down
            self.assertEqual(sb.value(), 10)
            self.mw._layer_ctrl.nudge_layer.assert_not_called()

    def test_nudge_called_when_no_input_focused(self):
        with patch.object(QApplication, "focusWidget", return_value=None):
            self.sctrl._on_nudge(1, 0)
            self.mw._layer_ctrl.nudge_layer.assert_called_once_with(1, 0)


if __name__ == "__main__":
    unittest.main()
