from photo_editor.ui.services.guide_ui_state import apply_guides, apply_preview_guide


class FakeCanvas:
    def __init__(self) -> None:
        self.guides = []
        self.preview_guides = []

    def set_guides(self, guides) -> None:
        self.guides.append(guides)

    def set_preview_guide(self, guide) -> None:
        self.preview_guides.append(guide)


class FakeRuler:
    def __init__(self) -> None:
        self.guides = []

    def set_guides(self, guides) -> None:
        self.guides.append(guides)


def test_apply_guides_updates_canvas_and_rulers() -> None:
    canvas = FakeCanvas()
    h_ruler = FakeRuler()
    v_ruler = FakeRuler()
    guides = ["g1"]

    apply_guides(canvas, h_ruler, v_ruler, guides)

    assert canvas.guides == [guides]
    assert h_ruler.guides == [guides]
    assert v_ruler.guides == [guides]


def test_apply_preview_guide_updates_preview_and_guides() -> None:
    canvas = FakeCanvas()
    h_ruler = FakeRuler()
    v_ruler = FakeRuler()
    guides = ["g1"]

    apply_preview_guide(canvas, h_ruler, v_ruler, guides, "preview")

    assert canvas.preview_guides == ["preview"]
    assert canvas.guides == [guides]
    assert h_ruler.guides == [guides]
    assert v_ruler.guides == [guides]