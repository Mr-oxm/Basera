"""Text tool — renders text onto a new layer using PIL/Pillow."""

import numpy as np

from .tool_base import Tool
from ..core.document import Document


class TextTool(Tool):
    """Places rendered text onto the canvas at the click location."""

    def __init__(self) -> None:
        super().__init__("Text")
        self.text: str = "Text"
        self.font_family: str = "arial"
        self.font_size: int = 36
        self.color: np.ndarray = np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32)
        self.alignment: str = "left"  # "left" | "center" | "right"
        self.spacing: int = 4  # extra line spacing in pixels

    # ------------------------------------------------------------------
    # Text rendering via Pillow
    # ------------------------------------------------------------------

    @staticmethod
    def _load_font(family: str, size: int):
        """Try to load a TrueType font, fall back to default bitmap font."""
        from PIL import ImageFont
        try:
            return ImageFont.truetype(family, size)
        except (OSError, IOError):
            # Try common suffixes
            for suffix in (".ttf", ".otf"):
                try:
                    return ImageFont.truetype(family + suffix, size)
                except (OSError, IOError):
                    continue
            return ImageFont.load_default()

    def _render_text_image(self) -> np.ndarray:
        """Return an RGBA float32 array with the rendered text."""
        from PIL import Image, ImageDraw

        font = self._load_font(self.font_family, self.font_size)

        # Measure text bounding box
        dummy = Image.new("RGBA", (1, 1))
        draw = ImageDraw.Draw(dummy)
        bbox = draw.multiline_textbbox(
            (0, 0), self.text, font=font, spacing=self.spacing, align=self.alignment,
        )
        tw = max(1, bbox[2] - bbox[0] + 4)
        th = max(1, bbox[3] - bbox[1] + 4)

        # Render
        img = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        # Convert float [0,1] colour to 0-255 RGBA tuple
        r, g, b, a = (np.clip(self.color * 255, 0, 255)).astype(np.uint8)
        draw.multiline_text(
            (-bbox[0] + 2, -bbox[1] + 2),
            self.text,
            font=font,
            fill=(int(r), int(g), int(b), int(a)),
            spacing=self.spacing,
            align=self.alignment,
        )
        # Convert to float32 [0,1]
        arr = np.array(img, dtype=np.float32) / 255.0
        return arr

    # ------------------------------------------------------------------
    # Compositing helper
    # ------------------------------------------------------------------

    @staticmethod
    def _paste(target: np.ndarray, patch: np.ndarray, ox: int, oy: int) -> None:
        """Alpha-composite *patch* onto *target* at offset (ox, oy)."""
        th, tw = target.shape[:2]
        ph, pw = patch.shape[:2]
        # Clip to target bounds
        sx = max(0, -ox)
        sy = max(0, -oy)
        dx = max(0, ox)
        dy = max(0, oy)
        cw = min(pw - sx, tw - dx)
        ch = min(ph - sy, th - dy)
        if cw <= 0 or ch <= 0:
            return
        src = patch[sy:sy + ch, sx:sx + cw]
        alpha = src[..., 3:4]
        target[dy:dy + ch, dx:dx + cw] = (
            target[dy:dy + ch, dx:dx + cw] * (1 - alpha) + src * alpha
        )

    # ------------------------------------------------------------------
    # Tool interface
    # ------------------------------------------------------------------

    def on_press(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        if not self.text:
            return

        # Create a new layer for the text
        text_layer = doc.add_layer(name=f"Text: {self.text[:20]}")
        text_img = self._render_text_image()

        self._paste(text_layer.pixels, text_img, x, y)
        np.clip(text_layer.pixels, 0, 1, out=text_layer.pixels)

    def on_move(self, doc: Document, x: int, y: int, pressure: float = 1.0) -> None:
        pass  # Text placement is single-click

    def on_release(self, doc: Document, x: int, y: int) -> None:
        pass
