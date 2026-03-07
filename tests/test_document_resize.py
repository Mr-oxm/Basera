import numpy as np

from photo_editor.core.services.document_resize import resize_canvas, resize_image


class MockLayer:
    def __init__(self, pixels, position=(0, 0)) -> None:
        self._pixels = pixels
        self.width = pixels.shape[1]
        self.height = pixels.shape[0]
        self.position = position

    @property
    def pixels(self):
        return self._pixels


class MockDocument:
    def __init__(self, width: int, height: int, layers: list[MockLayer]) -> None:
        self.width = width
        self.height = height
        self.layers = type("Layers", (), {"layers": layers})()
        self.snapshots = []

    def _snapshot(self, name: str) -> None:
        self.snapshots.append(name)

    def resize(self, width: int, height: int) -> None:
        self.width = width
        self.height = height


def test_resize_canvas_updates_document_size_and_snapshot() -> None:
    document = MockDocument(100, 50, [])

    resize_canvas(document, 200, 120)

    assert document.snapshots == ["Resize Canvas"]
    assert (document.width, document.height) == (200, 120)


def test_resize_image_resizes_layers_and_offsets() -> None:
    pixels = np.zeros((10, 20, 4), dtype=np.float32)
    layer = MockLayer(pixels, position=(5, 7))
    document = MockDocument(40, 20, [layer])

    calls = []

    def fake_resize(image, size):
        calls.append((image.shape, size))
        return np.zeros((size[1], size[0], 4), dtype=np.float32)

    resize_image(document, 80, 40, fake_resize)

    assert document.snapshots == ["Resize Image"]
    assert calls == [((10, 20, 4), (40, 20))]
    assert (layer.width, layer.height) == (40, 20)
    assert layer.position == (10, 14)
    assert (document.width, document.height) == (80, 40)