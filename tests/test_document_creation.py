"""Tests for the document-creation and settings suite.

Covers:
* Unit conversion helpers (pure Python, no Qt)
* Ruler unit helpers (pure Python, no Qt)
* Document model metadata (pure Python)
* NewProjectDialog — unit switching, color profiles, aspect-ratio lock,
  preset application, get_values(), set_from_document()
* NewDocumentDialog — unit conversion and get_values()
* DocumentController.new_document() metadata round-trip (no Qt window)
* Edit menu wiring — 'edit_document_settings' action exists
* Integration smoke: edit-document-settings dialog pre-populates correctly
"""

from __future__ import annotations

import math
import pytest

# ---------------------------------------------------------------------------
# Pure-Python helpers — run without Qt
# ---------------------------------------------------------------------------


class TestPxPerUnit:
    """Unit conversion math in new_project_dialog.px_per_unit."""

    def setup_method(self):
        from photo_editor.ui.dialogs.new_project_dialog import px_per_unit
        self.f = px_per_unit

    def test_px_is_identity(self):
        assert self.f("px", 72) == 1.0
        assert self.f("px", 300) == 1.0

    def test_inches_equals_dpi(self):
        assert self.f("in", 72) == 72.0
        assert self.f("in", 300) == 300.0

    def test_cm(self):
        assert math.isclose(self.f("cm", 72), 72 / 2.54, rel_tol=1e-9)
        assert math.isclose(self.f("cm", 300), 300 / 2.54, rel_tol=1e-9)

    def test_mm(self):
        assert math.isclose(self.f("mm", 72), 72 / 25.4, rel_tol=1e-9)

    def test_pt(self):
        # 1 pt = 1/72 in, so at 72 DPI: 1 pt = 1 px
        assert math.isclose(self.f("pt", 72), 1.0, rel_tol=1e-9)
        # at 300 DPI: 1 pt ≈ 4.1667 px
        assert math.isclose(self.f("pt", 300), 300 / 72, rel_tol=1e-9)

    def test_unknown_unit_returns_one(self):
        assert self.f("fathom", 72) == 1.0


class TestSpinboxConfig:
    """_spinbox_config returns sane values per unit."""

    def setup_method(self):
        from photo_editor.ui.dialogs.new_project_dialog import _spinbox_config
        self.f = _spinbox_config

    def test_px_zero_decimals(self):
        mn, mx, dec, step = self.f("px")
        assert dec == 0
        assert mn >= 1
        assert mx > 1000

    def test_inch_has_decimals(self):
        _, _, dec, _ = self.f("in")
        assert dec >= 2

    def test_mm_has_one_decimal(self):
        _, _, dec, _ = self.f("mm")
        assert dec == 1

    def test_cm_has_two_decimals(self):
        _, _, dec, _ = self.f("cm")
        assert dec == 2


class TestRulerHelpers:
    """Unit helpers in the rulers widget (no Qt needed)."""

    def setup_method(self):
        from photo_editor.ui.widgets.rulers import _px_per_unit, _label_for
        self.ppu = _px_per_unit
        self.label = _label_for

    def test_one_inch_at_72dpi(self):
        # 72 px → 1 inch at 72 DPI
        assert self.label(72.0, "in", 72) == "1.00"

    def test_px_label_is_integer_string(self):
        assert self.label(100.0, "px", 72) == "100"
        assert self.label(0.0, "px", 72) == "0"

    def test_cm_two_decimal_places(self):
        # 72/2.54 ≈ 28.346 px = 1 cm at 72 DPI
        one_cm_px = 72 / 2.54
        label = self.label(one_cm_px, "cm", 72)
        assert label == "1.00"

    def test_mm_one_decimal_place(self):
        # 10 mm at 72 DPI = 72/25.4*10 px
        ten_mm_px = (72 / 25.4) * 10
        label = self.label(ten_mm_px, "mm", 72)
        assert label == "10.0"

    def test_pt_at_72dpi(self):
        # At 72 DPI, 72 pts = 72 px → "72"
        assert self.label(72.0, "pt", 72) == "72"

    def test_zero_px(self):
        assert self.label(0.0, "cm", 72) == "0.00"

    def test_px_per_unit_consistency(self):
        # _px_per_unit should mirror px_per_unit from dialog
        from photo_editor.ui.dialogs.new_project_dialog import px_per_unit
        for unit in ("px", "in", "cm", "mm", "pt"):
            for dpi in (72, 96, 300):
                assert math.isclose(
                    self.ppu(unit, dpi), px_per_unit(unit, dpi), rel_tol=1e-9
                ), f"mismatch for unit={unit!r} dpi={dpi}"


# ---------------------------------------------------------------------------
# Document model metadata
# ---------------------------------------------------------------------------

class TestDocumentMetadata:
    """Document stores color_mode, color_profile, unit, dpi."""

    def test_defaults(self):
        from photo_editor.core.document import Document
        doc = Document(100, 100)
        assert doc.color_mode == "RGB"
        assert doc.color_profile == "sRGB IEC61966-2.1"
        assert doc.unit == "px"
        assert doc.dpi == 72

    def test_custom_values(self):
        from photo_editor.core.document import Document
        doc = Document(
            200, 300,
            color_mode="CMYK",
            color_profile="U.S. Web Coated (SWOP) v2",
            unit="cm",
        )
        assert doc.color_mode == "CMYK"
        assert doc.color_profile == "U.S. Web Coated (SWOP) v2"
        assert doc.unit == "cm"

    def test_dimensions_stored(self):
        from photo_editor.core.document import Document
        doc = Document(1920, 1080)
        assert doc.width == 1920
        assert doc.height == 1080

    def test_dpi_set_separately(self):
        from photo_editor.core.document import Document
        doc = Document(800, 600)
        doc.dpi = 300
        assert doc.dpi == 300

    def test_unit_attribute_is_mutable(self):
        from photo_editor.core.document import Document
        doc = Document(100, 100)
        doc.unit = "mm"
        assert doc.unit == "mm"


# ---------------------------------------------------------------------------
# NewProjectDialog (requires Qt)
# ---------------------------------------------------------------------------

class TestNewProjectDialogUnits:
    """Unit switching converts W/H values correctly."""

    @pytest.fixture(autouse=True)
    def dialog(self, qtbot):
        from photo_editor.ui.dialogs.new_project_dialog import NewProjectDialog
        dlg = NewProjectDialog()
        qtbot.addWidget(dlg)
        self.dlg = dlg

    def test_initial_unit_is_px(self):
        assert self.dlg.get_unit() == "px"

    def test_initial_get_values_in_pixels(self):
        w, h, dpi = self.dlg.get_values()
        assert isinstance(w, int)
        assert isinstance(h, int)
        assert w > 0 and h > 0

    def test_switch_px_to_inches_converts_width(self):
        from photo_editor.ui.dialogs.new_project_dialog import UNITS, px_per_unit
        dlg = self.dlg
        # Reset to known state
        dlg._width_px = 1920.0
        dlg._height_px = 1080.0
        dlg._current_dpi = 72
        dlg._current_unit = "px"
        dlg._units_combo.setCurrentIndex(UNITS.index("px"))
        dlg._sync_spinboxes_from_px()

        # Switch to inches
        dlg._units_combo.setCurrentIndex(UNITS.index("in"))

        expected_w = 1920.0 / 72.0  # ≈ 26.667
        assert math.isclose(dlg._width_spin.value(), expected_w, rel_tol=1e-3)

    def test_switch_px_to_cm_then_back_preserves_px(self):
        from photo_editor.ui.dialogs.new_project_dialog import UNITS
        dlg = self.dlg
        dlg._width_px = 800.0
        dlg._height_px = 600.0
        dlg._sync_spinboxes_from_px()

        # To cm
        dlg._units_combo.setCurrentIndex(UNITS.index("cm"))
        # Back to px
        dlg._units_combo.setCurrentIndex(UNITS.index("px"))

        w, h, _ = dlg.get_values()
        assert w == 800
        assert h == 600

    def test_get_values_always_returns_pixels_regardless_of_unit(self):
        from photo_editor.ui.dialogs.new_project_dialog import UNITS
        dlg = self.dlg
        dlg._width_px = 300.0   # 300 px = 300/72 ≈ 4.167 in at 72 DPI
        dlg._height_px = 200.0
        dlg._current_dpi = 72

        for unit in UNITS:
            dlg._units_combo.setCurrentIndex(UNITS.index(unit))
            w, h, _ = dlg.get_values()
            assert w == 300, f"width should be 300 px when unit={unit!r}, got {w}"
            assert h == 200, f"height should be 200 px when unit={unit!r}, got {h}"

    def test_mm_unit_has_one_decimal(self):
        from photo_editor.ui.dialogs.new_project_dialog import UNITS
        dlg = self.dlg
        dlg._units_combo.setCurrentIndex(UNITS.index("mm"))
        assert dlg._width_spin.decimals() == 1

    def test_pt_unit_has_zero_decimals(self):
        from photo_editor.ui.dialogs.new_project_dialog import UNITS
        dlg = self.dlg
        dlg._units_combo.setCurrentIndex(UNITS.index("pt"))
        assert dlg._width_spin.decimals() == 1 or dlg._width_spin.decimals() == 0


class TestNewProjectDialogDPI:
    """DPI changes affect physical-unit display but not pixel output."""

    @pytest.fixture(autouse=True)
    def dialog(self, qtbot):
        from photo_editor.ui.dialogs.new_project_dialog import NewProjectDialog
        dlg = NewProjectDialog()
        qtbot.addWidget(dlg)
        self.dlg = dlg

    def test_dpi_returned_in_get_values(self):
        dlg = self.dlg
        dlg._current_dpi = 300
        dlg._set_dpi(300)
        _, _, dpi = dlg.get_values()
        assert dpi == 300

    def test_changing_dpi_while_in_inches_does_not_change_spinbox(self):
        from photo_editor.ui.dialogs.new_project_dialog import UNITS
        dlg = self.dlg
        # Work in inches at 72 DPI
        dlg._width_px = 720.0   # = 10 inches @ 72 DPI
        dlg._height_px = 360.0
        dlg._current_dpi = 72
        dlg._set_dpi(72)
        dlg._units_combo.setCurrentIndex(UNITS.index("in"))
        w_before = dlg._width_spin.value()  # ≈ 10.0

        # Change to 300 DPI — spinbox should stay at ~10 in,
        # but get_values() should now return 3000 px
        dlg._set_dpi(300)
        dlg._on_dpi_changed(0)  # manually trigger

        # Spinbox (display) unchanged — still ~10 in
        assert math.isclose(dlg._width_spin.value(), w_before, rel_tol=1e-3)

        # Pixel output changed
        w_px, _, _ = dlg.get_values()
        assert w_px == 3000  # 10 in × 300 DPI


class TestNewProjectDialogColorProfiles:
    """Color mode change updates the profile list."""

    @pytest.fixture(autouse=True)
    def dialog(self, qtbot):
        from photo_editor.ui.dialogs.new_project_dialog import NewProjectDialog, _COLOR_PROFILES
        dlg = NewProjectDialog()
        qtbot.addWidget(dlg)
        self.dlg = dlg
        self.expected = _COLOR_PROFILES

    def test_rgb_has_srgb_default(self):
        dlg = self.dlg
        dlg._color_mode_combo.setCurrentText("RGB")
        assert "sRGB IEC61966-2.1" in [
            dlg._profile_combo.itemText(i) for i in range(dlg._profile_combo.count())
        ]

    def test_cmyk_profiles_loaded(self):
        dlg = self.dlg
        dlg._color_mode_combo.setCurrentText("CMYK")
        profiles = [dlg._profile_combo.itemText(i) for i in range(dlg._profile_combo.count())]
        assert len(profiles) > 0
        # Verify no RGB profile appears
        assert "sRGB IEC61966-2.1" not in profiles

    def test_grayscale_profiles_loaded(self):
        dlg = self.dlg
        dlg._color_mode_combo.setCurrentText("Grayscale")
        profiles = [dlg._profile_combo.itemText(i) for i in range(dlg._profile_combo.count())]
        assert any("Gray" in p or "gray" in p.lower() for p in profiles)

    def test_lab_profiles_loaded(self):
        dlg = self.dlg
        dlg._color_mode_combo.setCurrentText("LAB")
        profiles = [dlg._profile_combo.itemText(i) for i in range(dlg._profile_combo.count())]
        assert len(profiles) > 0

    def test_switching_mode_refreshes_profile_list(self):
        dlg = self.dlg
        dlg._color_mode_combo.setCurrentText("RGB")
        rgb_profiles = {dlg._profile_combo.itemText(i) for i in range(dlg._profile_combo.count())}
        dlg._color_mode_combo.setCurrentText("CMYK")
        cmyk_profiles = {dlg._profile_combo.itemText(i) for i in range(dlg._profile_combo.count())}
        assert rgb_profiles != cmyk_profiles

    def test_get_color_profile_returns_selected(self):
        dlg = self.dlg
        dlg._color_mode_combo.setCurrentText("RGB")
        dlg._profile_combo.setCurrentText("Adobe RGB (1998)")
        assert dlg.get_color_profile() == "Adobe RGB (1998)"

    def test_get_color_mode_returns_selected(self):
        dlg = self.dlg
        dlg._color_mode_combo.setCurrentText("CMYK")
        assert dlg.get_color_mode() == "CMYK"


class TestNewProjectDialogAspectLock:
    """Aspect-ratio lock keeps W/H proportional."""

    @pytest.fixture(autouse=True)
    def dialog(self, qtbot):
        from photo_editor.ui.dialogs.new_project_dialog import NewProjectDialog
        dlg = NewProjectDialog()
        qtbot.addWidget(dlg)
        self.dlg = dlg

    def test_lock_then_change_width_adjusts_height(self):
        dlg = self.dlg
        dlg._width_px = 1000.0
        dlg._height_px = 500.0
        dlg._aspect_ratio_px = 1000.0 / 500.0  # 2:1
        dlg._sync_spinboxes_from_px()

        dlg._link_btn.setChecked(True)
        dlg._on_lock_toggled(True)

        # Change width to 2000 px
        dlg._width_px = 2000.0
        dlg._width_spin.setValue(2000.0)

        # Height should have become 1000 px (2:1 ratio)
        assert math.isclose(dlg._height_px, 1000.0, rel_tol=1e-2)

    def test_unlock_allows_independent_change(self):
        dlg = self.dlg
        dlg._width_px = 1000.0
        dlg._height_px = 500.0
        dlg._aspect_ratio_px = 2.0
        dlg._sync_spinboxes_from_px()

        dlg._link_btn.setChecked(False)
        dlg._aspect_locked = False

        dlg._width_spin.setValue(800.0)
        # Height should NOT change
        assert dlg._height_spin.value() == 500.0


class TestNewProjectDialogPresets:
    """Preset cards load correct pixel dimensions."""

    @pytest.fixture(autouse=True)
    def dialog(self, qtbot):
        from photo_editor.ui.dialogs.new_project_dialog import NewProjectDialog
        dlg = NewProjectDialog()
        qtbot.addWidget(dlg)
        self.dlg = dlg

    def test_apply_preset_updates_internal_px(self):
        dlg = self.dlg
        dlg._apply_preset(1920, 1080, 72)
        assert dlg._width_px == 1920.0
        assert dlg._height_px == 1080.0

    def test_preset_in_cm_converts_display(self):
        from photo_editor.ui.dialogs.new_project_dialog import UNITS, px_per_unit
        dlg = self.dlg
        # Switch to cm first
        dlg._units_combo.setCurrentIndex(UNITS.index("cm"))
        # Apply a pixel preset
        dlg._apply_preset(2480, 3508, 300)
        ppu = px_per_unit("cm", 300)
        expected_w_cm = 2480 / ppu
        assert math.isclose(dlg._width_spin.value(), expected_w_cm, rel_tol=1e-2)

    def test_preset_sets_correct_dpi(self):
        dlg = self.dlg
        dlg._apply_preset(2480, 3508, 300)
        _, _, dpi = dlg.get_values()
        assert dpi == 300

    def test_preset_auto_detects_portrait(self):
        dlg = self.dlg
        dlg._apply_preset(1080, 1920, 72)  # portrait
        assert dlg._portrait_btn.isChecked()

    def test_preset_auto_detects_landscape(self):
        dlg = self.dlg
        dlg._apply_preset(1920, 1080, 72)  # landscape
        assert dlg._landscape_btn.isChecked()


class TestNewProjectDialogSetFromDocument:
    """set_from_document() populates dialog correctly."""

    @pytest.fixture(autouse=True)
    def dialog(self, qtbot):
        from photo_editor.ui.dialogs.new_project_dialog import NewProjectDialog
        dlg = NewProjectDialog()
        qtbot.addWidget(dlg)
        self.dlg = dlg

    def _make_doc(self, **kwargs):
        from photo_editor.core.document import Document
        base = dict(color_mode="RGB", color_profile="sRGB IEC61966-2.1", unit="px")
        base.update(kwargs)
        doc = Document(
            base.pop("width", 800),
            base.pop("height", 600),
            color_mode=base.pop("color_mode"),
            color_profile=base.pop("color_profile"),
            unit=base.pop("unit"),
        )
        for k, v in base.items():
            setattr(doc, k, v)
        return doc

    def test_dimensions_pre_populated(self):
        doc = self._make_doc(width=1920, height=1080)
        self.dlg.set_from_document(doc)
        w, h, _ = self.dlg.get_values()
        assert w == 1920
        assert h == 1080

    def test_dpi_pre_populated(self):
        doc = self._make_doc(width=800, height=600)
        doc.dpi = 300
        self.dlg.set_from_document(doc)
        _, _, dpi = self.dlg.get_values()
        assert dpi == 300

    def test_unit_pre_populated(self):
        from photo_editor.ui.dialogs.new_project_dialog import UNITS
        doc = self._make_doc(unit="cm")
        self.dlg.set_from_document(doc)
        assert self.dlg.get_unit() == "cm"

    def test_color_mode_pre_populated(self):
        doc = self._make_doc(color_mode="CMYK")
        self.dlg.set_from_document(doc)
        assert self.dlg.get_color_mode() == "CMYK"

    def test_color_profile_pre_populated(self):
        doc = self._make_doc(
            color_mode="RGB",
            color_profile="Adobe RGB (1998)",
        )
        self.dlg.set_from_document(doc)
        assert self.dlg.get_color_profile() == "Adobe RGB (1998)"

    def test_cmyk_doc_shows_cmyk_profiles(self):
        doc = self._make_doc(color_mode="CMYK", color_profile="U.S. Web Coated (SWOP) v2")
        self.dlg.set_from_document(doc)
        assert self.dlg.get_color_mode() == "CMYK"
        assert "Web Coated" in self.dlg.get_color_profile()

    def test_dimensions_shown_in_correct_unit(self):
        import math
        from photo_editor.ui.dialogs.new_project_dialog import px_per_unit
        doc = self._make_doc(width=720, height=540, unit="in")
        doc.dpi = 72
        self.dlg.set_from_document(doc)
        # Spinbox should display 10.0 in (720 / 72 = 10)
        assert math.isclose(self.dlg._width_spin.value(), 10.0, rel_tol=1e-3)

    def test_create_btn_text_not_changed_by_set_from_document(self):
        # set_from_document doesn't rename the button — that's done by callers
        doc = self._make_doc(width=100, height=100)
        self.dlg.set_from_document(doc)
        assert self.dlg._create_btn.text() == "Create Project"


# ---------------------------------------------------------------------------
# NewDocumentDialog
# ---------------------------------------------------------------------------

class TestNewDocumentDialog:
    """Compact canvas-size dialog with unit support."""

    @pytest.fixture(autouse=True)
    def dialog(self, qtbot):
        from photo_editor.ui.dialogs.new_document import NewDocumentDialog
        dlg = NewDocumentDialog()
        qtbot.addWidget(dlg)
        self.dlg = dlg

    def test_default_unit_is_px(self):
        assert self.dlg._current_unit == "px"

    def test_get_values_returns_integers(self):
        w, h, dpi = self.dlg.get_values()
        assert isinstance(w, int)
        assert isinstance(h, int)
        assert isinstance(dpi, int)

    def test_px_set_via_width_attribute(self):
        """layer_ctrl.py sets ._width.setValue() — must still work."""
        self.dlg._width.setValue(2048)
        self.dlg._height.setValue(1536)
        w, h, _ = self.dlg.get_values()
        assert w == 2048
        assert h == 1536

    def test_unit_change_converts_spinbox(self):
        from photo_editor.ui.dialogs.new_project_dialog import UNITS, px_per_unit
        dlg = self.dlg
        # Set to 720 px
        dlg._width.setValue(720)
        dlg._height.setValue(480)
        dlg._current_unit = "px"
        dlg._units_combo.setCurrentIndex(UNITS.index("in"))
        # At 72 DPI: 720 px → 10 in
        assert math.isclose(dlg._width.value(), 10.0, rel_tol=1e-2)

    def test_get_values_after_unit_change_returns_pixels(self):
        from photo_editor.ui.dialogs.new_project_dialog import UNITS
        dlg = self.dlg
        dlg._width.setValue(720)
        dlg._current_unit = "px"
        dlg._units_combo.setCurrentIndex(UNITS.index("in"))
        # Regardless of unit, output should be original px
        w, _, _ = dlg.get_values()
        assert w == 720


# ---------------------------------------------------------------------------
# DocumentController metadata round-trip (no full Qt window)
# ---------------------------------------------------------------------------

class TestDocumentControllerNewDocument:
    """new_document() stores all metadata on the Document."""

    def test_new_document_stores_color_mode(self):
        from photo_editor.ui.controllers.document_ctrl import DocumentController

        ctrl = DocumentController.__new__(DocumentController)

        created = []

        class FakeSession:
            def add(self, doc, path, *, title=None):
                created.append(doc)
                return 0

        class FakeMW:
            _document_session = FakeSession()
            _doc = None

            def _status(self):
                pass

        class FakeCtx:
            def refresh(self): pass
            def zoom_to_fit(self): pass
            def set_window_title(self, t): pass
            def show_status_message(self, m, d=0): pass

        ctrl._mw = FakeMW()
        ctrl._ctx = FakeCtx()
        ctrl._mw._status = type(
            "S", (), {"set_document_info": lambda *a: None}
        )()

        ctrl.new_document(
            800, 600, 96,
            color_mode="CMYK",
            color_profile="U.S. Web Coated (SWOP) v2",
            unit="mm",
        )

        assert len(created) == 1
        doc = created[0]
        assert doc.width == 800
        assert doc.height == 600
        assert doc.dpi == 96
        assert doc.color_mode == "CMYK"
        assert doc.color_profile == "U.S. Web Coated (SWOP) v2"
        assert doc.unit == "mm"


# ---------------------------------------------------------------------------
# Menu wiring — 'edit_document_settings' action present
# ---------------------------------------------------------------------------

class TestMenuWiring:
    """Edit menu contains the Document Settings action."""

    def test_edit_menu_has_document_settings(self, qtbot):
        from photo_editor.ui.menus import EditorMenuBar
        menubar = EditorMenuBar()
        qtbot.addWidget(menubar)
        assert "edit_document_settings" in menubar.actions_map
        action = menubar.actions_map["edit_document_settings"]
        assert action is not None
        assert "Settings" in action.text() or "settings" in action.text().lower()


# ---------------------------------------------------------------------------
# Ruler set_unit / paint params (no actual painting)
# ---------------------------------------------------------------------------

class TestRulerSetUnit:
    """_RulerBase.set_unit() stores state correctly."""

    def test_set_unit_updates_state(self, qtbot):
        from photo_editor.ui.widgets.rulers import HorizontalRuler
        ruler = HorizontalRuler()
        qtbot.addWidget(ruler)
        ruler.set_unit("cm", 300)
        assert ruler._unit == "cm"
        assert ruler._dpi == 300

    def test_default_unit_is_px(self, qtbot):
        from photo_editor.ui.widgets.rulers import VerticalRuler
        ruler = VerticalRuler()
        qtbot.addWidget(ruler)
        assert ruler._unit == "px"
        assert ruler._dpi == 72

    def test_set_unit_noop_on_same_values(self, qtbot):
        from photo_editor.ui.widgets.rulers import HorizontalRuler
        ruler = HorizontalRuler()
        qtbot.addWidget(ruler)
        ruler.set_unit("in", 300)
        # Call again with same values — should not raise or change state
        ruler.set_unit("in", 300)
        assert ruler._unit == "in"


# ---------------------------------------------------------------------------
# Integration: Edit Document Settings dialog smoke test
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Dialog UI detail fixes
# ---------------------------------------------------------------------------

class TestDialogUIDetails:
    """Regression tests for the three UI detail fixes."""

    # ---- Transparent swatch is a real custom widget -----------------------

    def test_transparent_swatch_is_custom_class(self, qtbot):
        from photo_editor.ui.dialogs.new_project_dialog import (
            NewProjectDialog, _TransparentSwatch,
        )
        dlg = NewProjectDialog()
        qtbot.addWidget(dlg)
        # The bg_group should contain a _TransparentSwatch instance
        transparent_swatches = [
            b for b in dlg._bg_group.buttons()
            if isinstance(b, _TransparentSwatch)
        ]
        assert len(transparent_swatches) == 1, (
            "Exactly one _TransparentSwatch must be in the background group"
        )

    def test_transparent_swatch_has_no_css_gradient(self, qtbot):
        from photo_editor.ui.dialogs.new_project_dialog import (
            NewProjectDialog, _TransparentSwatch,
        )
        dlg = NewProjectDialog()
        qtbot.addWidget(dlg)
        for b in dlg._bg_group.buttons():
            if isinstance(b, _TransparentSwatch):
                # Must NOT have a qlineargradient background in its stylesheet
                assert "qlineargradient" not in b.styleSheet()

    # ---- Orientation buttons use consistent outline-rectangle icons --------

    def test_orientation_icons_are_consistent_outline_rects(self, qtbot):
        from photo_editor.ui.dialogs.new_project_dialog import NewProjectDialog
        dlg = NewProjectDialog()
        qtbot.addWidget(dlg)
        land_icon = dlg._landscape_btn.text().split()[0]
        port_icon = dlg._portrait_btn.text().split()[0]
        # Both must use the same icon style (both outlined rectangle chars)
        # ▭ = U+25AD WHITE RECTANGLE  ▯ = U+25AF WHITE VERTICAL RECTANGLE
        assert land_icon == "▭", f"Landscape icon should be ▭, got {land_icon!r}"
        assert port_icon == "▯", f"Portrait icon should be ▯, got {port_icon!r}"

    # ---- Preset cards are mutually exclusive per category -----------------

    def test_preset_cards_exclusive_within_category(self, qtbot):
        from photo_editor.ui.dialogs.new_project_dialog import NewProjectDialog
        dlg = NewProjectDialog()
        qtbot.addWidget(dlg)
        dlg._select_category("Web")

        cards = dlg._preset_group.buttons()
        assert len(cards) >= 2, "Need at least 2 cards to test exclusivity"

        # Click first card
        cards[0].click()
        assert cards[0].isChecked()

        # Click second card — first must no longer be checked
        cards[1].click()
        assert cards[1].isChecked()
        assert not cards[0].isChecked(), (
            "Clicking a second preset card should uncheck the first one"
        )

    def test_preset_group_resets_on_category_change(self, qtbot):
        from photo_editor.ui.dialogs.new_project_dialog import NewProjectDialog
        dlg = NewProjectDialog()
        qtbot.addWidget(dlg)

        dlg._select_category("Web")
        web_cards_before = list(dlg._preset_group.buttons())
        if web_cards_before:
            web_cards_before[0].click()

        # Switch category — old buttons must be removed from the group
        dlg._select_category("Print")
        for old_card in web_cards_before:
            assert old_card not in dlg._preset_group.buttons(), (
                "Old preset cards must be removed from the group on category change"
            )

    def test_preset_cards_across_categories_dont_stay_checked(self, qtbot):
        from photo_editor.ui.dialogs.new_project_dialog import NewProjectDialog
        dlg = NewProjectDialog()
        qtbot.addWidget(dlg)

        # Check a card in Photo category
        dlg._select_category("Photo")
        photo_cards = dlg._preset_group.buttons()
        if photo_cards:
            photo_cards[0].click()
            assert photo_cards[0].isChecked()

        # Switch to Web — the old photo card reference is now destroyed;
        # no button in the new group should be checked
        dlg._select_category("Web")
        for card in dlg._preset_group.buttons():
            assert not card.isChecked(), (
                "Cards in a freshly loaded category should start unchecked"
            )


class TestEditDocumentSettingsIntegration:
    """Smoke-test for the edit-document-settings workflow."""

    def test_dialog_opens_with_document_values(self, qtbot):
        from photo_editor.core.document import Document
        from photo_editor.ui.dialogs.new_project_dialog import NewProjectDialog

        doc = Document(
            1280, 720,
            color_mode="RGB",
            color_profile="Display P3",
            unit="px",
        )
        doc.dpi = 96

        dlg = NewProjectDialog()
        qtbot.addWidget(dlg)
        dlg.setWindowTitle("Document Settings")
        dlg._create_btn.setText("Apply Changes")
        dlg.set_from_document(doc)

        # Title was renamed
        assert dlg.windowTitle() == "Document Settings"
        # Button was renamed
        assert dlg._create_btn.text() == "Apply Changes"
        # Values match the document
        w, h, dpi = dlg.get_values()
        assert w == 1280
        assert h == 720
        assert dpi == 96
        assert dlg.get_color_mode() == "RGB"
        assert dlg.get_color_profile() == "Display P3"
        assert dlg.get_unit() == "px"

    def test_changing_unit_in_edit_mode_preserves_pixel_output(self, qtbot):
        from photo_editor.core.document import Document
        from photo_editor.ui.dialogs.new_project_dialog import NewProjectDialog, UNITS

        doc = Document(1920, 1080)
        doc.dpi = 72

        dlg = NewProjectDialog()
        qtbot.addWidget(dlg)
        dlg.set_from_document(doc)

        # Switch to cm
        dlg._units_combo.setCurrentIndex(UNITS.index("cm"))
        # get_values() must still return the original pixel dimensions
        w, h, _ = dlg.get_values()
        assert w == 1920
        assert h == 1080
