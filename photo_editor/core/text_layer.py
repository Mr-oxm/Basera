"""Rich text layer data model — character-level formatting, paragraph layout, and rendering.

A ``TextLayerData`` object is attached to any ``Layer`` whose
``layer_type == LayerType.TEXT``.  It stores the full rich-text
document as a sequence of ``TextRun`` objects (contiguous spans of
identically formatted characters) plus paragraph-level layout
settings.

The renderer uses PIL/Pillow for glyph rasterisation and caches the
result.  The cache is invalidated whenever runs, formatting, or the
bounding box change.

Coordinate convention
---------------------
*box_width* / *box_height* define the editable text area in document
pixels.  Text wraps to *box_width*; if content exceeds *box_height*
it overflows visually but the bounding box stays fixed (unless the
user resizes it in text-tool mode).
"""

from __future__ import annotations

import hashlib
import math
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

from .color import (
    Color, ColorFill, SolidFill, LinearGradient, RadialGradient,
    GradientStop, FillType,
)

# ---------------------------------------------------------------------------
# Arabic text support
# ---------------------------------------------------------------------------

def _process_arabic_text(text: str) -> str:
    """Process Arabic text for proper rendering with RTL and character shaping.
    
    This function handles:
    - Character reshaping (connecting forms)
    - Bidirectional text (RTL/LTR mixing)
    
    Parameters
    ----------
    text : str
        Input text that may contain Arabic characters
        
    Returns
    -------
    str
        Processed text ready for rendering
    """
    if not text:
        return text
    
    # Check if text contains Arabic characters (U+0600 to U+06FF)
    has_arabic = any('\u0600' <= c <= '\u06FF' for c in text)
    
    if not has_arabic:
        return text
    
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        
        # Reshape Arabic characters (connect letters properly)
        reshaped = arabic_reshaper.reshape(text)
        
        # Apply bidirectional algorithm for RTL display
        bidi_text = get_display(reshaped)
        
        return bidi_text
    except ImportError:
        # If libraries not available, return original text
        return text


# ---------------------------------------------------------------------------
# Character-level formatting
# ---------------------------------------------------------------------------

@dataclass
class CharFormat:
    """Formatting applied to a contiguous run of characters."""
    font_family: str = "arial"
    font_size: float = 36.0
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strikethrough: bool = False
    color: ColorFill = field(default_factory=lambda: SolidFill(color=Color.black()))
    letter_spacing: float = 0.0  # extra pixels between characters

    def copy(self) -> CharFormat:
        return CharFormat(
            font_family=self.font_family,
            font_size=self.font_size,
            bold=self.bold,
            italic=self.italic,
            underline=self.underline,
            strikethrough=self.strikethrough,
            color=self.color,  # immutable
            letter_spacing=self.letter_spacing,
        )

    def to_dict(self) -> dict:
        return {
            "font_family": self.font_family,
            "font_size": self.font_size,
            "bold": self.bold,
            "italic": self.italic,
            "underline": self.underline,
            "strikethrough": self.strikethrough,
            "color": self.color.to_dict(),
            "letter_spacing": self.letter_spacing,
        }

    @classmethod
    def from_dict(cls, d: dict) -> CharFormat:
        cf = cls()
        cf.font_family = d.get("font_family", "arial")
        cf.font_size = d.get("font_size", 36.0)
        cf.bold = d.get("bold", False)
        cf.italic = d.get("italic", False)
        cf.underline = d.get("underline", False)
        cf.strikethrough = d.get("strikethrough", False)
        cf.color = ColorFill.from_dict(d.get("color", {}))
        cf.letter_spacing = d.get("letter_spacing", 0.0)
        return cf

    def _font_variant(self) -> str:
        """Return a key fragment identifying the typeface variant."""
        parts = [self.font_family]
        if self.bold:
            parts.append("Bold")
        if self.italic:
            parts.append("Italic")
        return "-".join(parts)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CharFormat):
            return NotImplemented
        return (self.font_family == other.font_family
                and self.font_size == other.font_size
                and self.bold == other.bold
                and self.italic == other.italic
                and self.underline == other.underline
                and self.strikethrough == other.strikethrough
                and self.color == other.color
                and self.letter_spacing == other.letter_spacing)


# ---------------------------------------------------------------------------
# Paragraph-level formatting
# ---------------------------------------------------------------------------

@dataclass
class ParagraphFormat:
    """Layout settings for a paragraph (text separated by newlines)."""
    alignment: str = "left"  # "left" | "center" | "right" | "justify" - default alignment
    line_height: float = 1.2  # multiplier on font size
    paragraph_spacing: float = 0.0  # extra px after paragraph
    # Per-paragraph alignment tracking (maps paragraph index to alignment)
    paragraph_alignments: dict[int, str] = field(default_factory=dict)

    def copy(self) -> ParagraphFormat:
        return ParagraphFormat(
            alignment=self.alignment,
            line_height=self.line_height,
            paragraph_spacing=self.paragraph_spacing,
            paragraph_alignments=self.paragraph_alignments.copy(),
        )

    def to_dict(self) -> dict:
        return {
            "alignment": self.alignment,
            "line_height": self.line_height,
            "paragraph_spacing": self.paragraph_spacing,
            "paragraph_alignments": self.paragraph_alignments,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ParagraphFormat:
        return cls(
            alignment=d.get("alignment", "left"),
            line_height=d.get("line_height", 1.2),
            paragraph_spacing=d.get("paragraph_spacing", 0.0),
            paragraph_alignments=d.get("paragraph_alignments", {}),
        )


# ---------------------------------------------------------------------------
# Text Run
# ---------------------------------------------------------------------------

@dataclass
class TextRun:
    """Contiguous span of identically formatted characters."""
    text: str
    fmt: CharFormat = field(default_factory=CharFormat)

    def copy(self) -> TextRun:
        return TextRun(text=self.text, fmt=self.fmt.copy())

    def to_dict(self) -> dict:
        return {"text": self.text, "fmt": self.fmt.to_dict()}

    @classmethod
    def from_dict(cls, d: dict) -> TextRun:
        return cls(text=d["text"], fmt=CharFormat.from_dict(d.get("fmt", {})))


# ---------------------------------------------------------------------------
# TextLayerData  — the rich-text document stored on a text layer
# ---------------------------------------------------------------------------

class TextLayerData:
    """Full rich-text content for a text layer.

    Parameters
    ----------
    box_width, box_height : int
        Bounding box size in document pixels.  Text wraps to *box_width*.
    """

    def __init__(self, box_width: int = 200, box_height: int = 100) -> None:
        self.box_width: int = box_width
        self.box_height: int = box_height
        self.runs: list[TextRun] = [TextRun(text="", fmt=CharFormat())]
        self.paragraph_fmt: ParagraphFormat = ParagraphFormat()
        # Cursor / selection state (character indices)
        self.cursor_pos: int = 0
        self.selection_start: int | None = None  # None means no selection
        # Render cache
        self._cache: np.ndarray | None = None
        self._cache_hash: str = ""
        # Layout cache: list of laid-out lines for cursor mapping
        self._layout_lines: list[_LayoutLine] = []
        self._layout_hash: str = ""

    # ------------------------------------------------------------------
    # Plain text helpers
    # ------------------------------------------------------------------

    @property
    def plain_text(self) -> str:
        return "".join(r.text for r in self.runs)

    @plain_text.setter
    def plain_text(self, value: str) -> None:
        """Replace all runs with a single run using the first run's format."""
        fmt = self.runs[0].fmt.copy() if self.runs else CharFormat()
        self.runs = [TextRun(text=value, fmt=fmt)]
        self.invalidate()

    @property
    def char_count(self) -> int:
        return sum(len(r.text) for r in self.runs)

    def get_paragraph_index_at_cursor(self) -> int:
        """Get the paragraph index at the current cursor position."""
        text = self.plain_text
        para_idx = 0
        for i in range(min(self.cursor_pos, len(text))):
            if text[i] == '\n':
                para_idx += 1
        return para_idx

    def get_current_paragraph_alignment(self) -> str:
        """Get the alignment for the paragraph at the cursor position."""
        para_idx = self.get_paragraph_index_at_cursor()
        return self.paragraph_fmt.paragraph_alignments.get(para_idx, self.paragraph_fmt.alignment)

    def set_current_paragraph_alignment(self, alignment: str) -> None:
        """Set the alignment for the paragraph at the cursor position."""
        para_idx = self.get_paragraph_index_at_cursor()
        self.paragraph_fmt.paragraph_alignments[para_idx] = alignment
        self.invalidate()

    # ------------------------------------------------------------------
    # Run-level editing
    # ------------------------------------------------------------------

    def _run_at(self, char_index: int) -> tuple[int, int]:
        """Return (run_index, offset_within_run) for global *char_index*."""
        pos = 0
        for i, run in enumerate(self.runs):
            if char_index <= pos + len(run.text):
                return i, char_index - pos
            pos += len(run.text)
        # Past end — append to last run
        return len(self.runs) - 1, len(self.runs[-1].text) if self.runs else 0

    def insert_text(self, char_index: int, text: str) -> None:
        """Insert *text* at *char_index*, inheriting the format at that position."""
        if not self.runs:
            self.runs = [TextRun(text=text, fmt=CharFormat())]
            self.invalidate()
            return
        ri, off = self._run_at(char_index)
        run = self.runs[ri]
        run.text = run.text[:off] + text + run.text[off:]
        self.invalidate()

    def delete_range(self, start: int, end: int) -> None:
        """Delete characters in [start, end)."""
        if start >= end:
            return
        new_runs: list[TextRun] = []
        pos = 0
        for run in self.runs:
            rlen = len(run.text)
            rend = pos + rlen
            # Entirely before or after the deleted range
            if rend <= start or pos >= end:
                new_runs.append(run)
            else:
                # Partial overlap
                kept = ""
                if pos < start:
                    kept += run.text[:start - pos]
                if rend > end:
                    kept += run.text[end - pos:]
                if kept:
                    new_runs.append(TextRun(text=kept, fmt=run.fmt))
            pos += rlen
        if not new_runs:
            new_runs = [TextRun(text="", fmt=self.runs[0].fmt.copy() if self.runs else CharFormat())]
        self.runs = new_runs
        self.invalidate()

    def apply_format(self, start: int, end: int, **attrs) -> None:
        """Apply formatting attributes to the character range [start, end).

        Any keyword argument matching a ``CharFormat`` field is set on
        the affected runs (splitting runs at boundaries as needed).
        """
        if start >= end or not self.runs:
            return
        # Flatten to per-char format list, apply, re-run-length-encode
        chars = []
        fmts = []
        for run in self.runs:
            for ch in run.text:
                chars.append(ch)
                fmts.append(run.fmt.copy())
        for i in range(start, min(end, len(fmts))):
            for k, v in attrs.items():
                if hasattr(fmts[i], k):
                    setattr(fmts[i], k, v)
        # Re-encode runs
        new_runs: list[TextRun] = []
        if chars:
            cur_text = chars[0]
            cur_fmt = fmts[0]
            for ch, fmt in zip(chars[1:], fmts[1:]):
                if fmt == cur_fmt:
                    cur_text += ch
                else:
                    new_runs.append(TextRun(text=cur_text, fmt=cur_fmt))
                    cur_text = ch
                    cur_fmt = fmt
            new_runs.append(TextRun(text=cur_text, fmt=cur_fmt))
        else:
            new_runs = [TextRun(text="", fmt=CharFormat())]
        self.runs = new_runs
        self.invalidate()

    def format_at(self, char_index: int) -> CharFormat:
        """Return the CharFormat at *char_index*."""
        ri, off = self._run_at(char_index)
        return self.runs[ri].fmt

    # ------------------------------------------------------------------
    # Selection helpers
    # ------------------------------------------------------------------

    @property
    def has_selection(self) -> bool:
        return (self.selection_start is not None
                and self.selection_start != self.cursor_pos)

    @property
    def selection_range(self) -> tuple[int, int] | None:
        """Return (lo, hi) or None."""
        if not self.has_selection:
            return None
        a, b = self.selection_start, self.cursor_pos
        return (min(a, b), max(a, b))

    def select_all(self) -> None:
        self.selection_start = 0
        self.cursor_pos = self.char_count

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def invalidate(self) -> None:
        self._cache = None
        self._layout_lines = []

    def _content_hash(self) -> str:
        """Quick hash of text content + formatting for cache comparison."""
        parts: list[str] = []
        for run in self.runs:
            parts.append(f"{run.text}|{run.fmt.font_family}|{run.fmt.font_size}|"
                         f"{run.fmt.bold}|{run.fmt.italic}|{run.fmt.underline}|"
                         f"{run.fmt.strikethrough}|{run.fmt.letter_spacing}|"
                         f"{run.fmt.color.to_dict()}")
        parts.append(f"box:{self.box_width}x{self.box_height}")
        parts.append(f"para:{self.paragraph_fmt.alignment}|{self.paragraph_fmt.line_height}|"
                     f"{self.paragraph_fmt.paragraph_spacing}")
        raw = "\n".join(parts).encode()
        return hashlib.md5(raw).hexdigest()

    # ------------------------------------------------------------------
    # Layout engine
    # ------------------------------------------------------------------

    def compute_layout(self) -> list[_LayoutLine]:
        """Compute laid-out lines, caching the result.

        Returns a list of ``_LayoutLine`` objects used by both the
        renderer and cursor-position mapper.
        """
        h = self._content_hash()
        if self._layout_lines and self._layout_hash == h:
            return self._layout_lines
        self._layout_lines = _layout_text(self)
        self._layout_hash = h
        return self._layout_lines

    # ------------------------------------------------------------------
    # Render to RGBA float32
    # ------------------------------------------------------------------

    def render(self) -> np.ndarray:
        """Return an RGBA float32 array of the rendered text.

        The image size matches the *actual content extent* (may differ
        from box_width × box_height when text overflows).  Callers
        composite this onto the layer's pixel buffer.
        """
        h = self._content_hash()
        if self._cache is not None and self._cache_hash == h:
            return self._cache

        lines = self.compute_layout()
        img = _render_layout(lines, self.box_width, self.box_height,
                             self.paragraph_fmt)
        self._cache = img
        self._cache_hash = h
        return img

    # ------------------------------------------------------------------
    # Cursor ↔ layout mapping
    # ------------------------------------------------------------------

    def cursor_to_xy(self, char_index: int) -> tuple[int, int]:
        """Map a character index to (x, y) pixel position in the text image."""
        lines = self.compute_layout()
        pos = 0
        for line in lines:
            line_len = sum(len(g.char) for g in line.glyphs)
            # Count newline as part of the line for cursor positioning
            if line.has_newline:
                line_len += 1
            # When a line ends with a newline, the cursor right after
            # the newline (pos + line_len) belongs to the *next* line,
            # so use strict '<'.  For other lines use '<='.
            on_this_line = (char_index < pos + line_len
                           or (char_index == pos + line_len
                               and not line.has_newline))
            if on_this_line:
                # Find x within line
                x = line.x_offset
                for g in line.glyphs:
                    if pos == char_index:
                        return (int(x), int(line.y))
                    x += g.advance
                    pos += len(g.char)
                # Cursor is at end of line or on the newline
                return (int(x), int(line.y))
            pos += line_len
        # Past end
        if lines:
            last = lines[-1]
            x = last.x_offset + sum(g.advance for g in last.glyphs)
            return (int(x), int(last.y))
        return (0, 0)

    def xy_to_cursor(self, x: int, y: int) -> int:
        """Map pixel coords to the nearest character index."""
        lines = self.compute_layout()
        if not lines:
            return 0
        # Find the closest line by y
        best_line_idx = 0
        best_dist = abs(y - lines[0].y)
        for i, line in enumerate(lines):
            dist = abs(y - line.y)
            if dist < best_dist:
                best_dist = dist
                best_line_idx = i
        # Find position within line
        line = lines[best_line_idx]
        # Compute char offset of this line (include newline chars)
        char_offset = 0
        for li in range(best_line_idx):
            char_offset += sum(len(g.char) for g in lines[li].glyphs)
            if lines[li].has_newline:
                char_offset += 1
        gx = line.x_offset
        for g in line.glyphs:
            mid = gx + g.advance / 2
            if x < mid:
                return char_offset
            gx += g.advance
            char_offset += len(g.char)
        return char_offset

    def cursor_line_height(self, char_index: int) -> int:
        """Return the line height at the cursor position (for drawing the caret)."""
        lines = self.compute_layout()
        pos = 0
        for line in lines:
            line_len = sum(len(g.char) for g in line.glyphs)
            if line.has_newline:
                line_len += 1
            on_this_line = (char_index < pos + line_len
                           or (char_index == pos + line_len
                               and not line.has_newline))
            if on_this_line:
                return int(line.height)
            pos += line_len
        if lines:
            return int(lines[-1].height)
        return int(self.runs[0].fmt.font_size * 1.2) if self.runs else 20

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "box_width": self.box_width,
            "box_height": self.box_height,
            "runs": [r.to_dict() for r in self.runs],
            "paragraph_fmt": self.paragraph_fmt.to_dict(),
            "cursor_pos": self.cursor_pos,
        }

    @classmethod
    def from_dict(cls, d: dict) -> TextLayerData:
        td = cls(box_width=d.get("box_width", 200),
                 box_height=d.get("box_height", 100))
        td.runs = [TextRun.from_dict(r) for r in d.get("runs", [])]
        if not td.runs:
            td.runs = [TextRun(text="", fmt=CharFormat())]
        td.paragraph_fmt = ParagraphFormat.from_dict(d.get("paragraph_fmt", {}))
        td.cursor_pos = d.get("cursor_pos", 0)
        return td

    def deep_copy(self) -> TextLayerData:
        """Return a fully independent copy."""
        td = TextLayerData(self.box_width, self.box_height)
        td.runs = [r.copy() for r in self.runs]
        td.paragraph_fmt = self.paragraph_fmt.copy()
        td.cursor_pos = self.cursor_pos
        td.selection_start = self.selection_start
        return td


# ============================================================================
# Internal layout types
# ============================================================================

@dataclass
class _GlyphInfo:
    """A single character with its computed metrics."""
    char: str
    advance: float  # horizontal advance including letter_spacing
    ascent: float
    descent: float
    fmt: CharFormat
    # Position set during line layout
    x: float = 0.0


@dataclass
class _LayoutLine:
    """One visual line of text after word-wrapping."""
    glyphs: list[_GlyphInfo]
    y: float = 0.0  # baseline y
    height: float = 0.0
    x_offset: float = 0.0  # left offset for alignment
    paragraph_index: int = 0
    has_newline: bool = False  # True if this line ends with a newline character


# ============================================================================
# Font loading (cached) — robust system font discovery
# ============================================================================

_font_cache: dict[str, Any] = {}
_system_font_map: dict[str, str] | None = None  # lowercase name → full path


def _build_system_font_map() -> dict[str, str]:
    """Scan the system fonts directory and build a name→path mapping."""
    import os
    import sys
    font_dirs: list[str] = []
    if sys.platform == "win32":
        windir = os.environ.get("WINDIR", r"C:\Windows")
        font_dirs.append(os.path.join(windir, "Fonts"))
        localappdata = os.environ.get("LOCALAPPDATA", "")
        if localappdata:
            font_dirs.append(os.path.join(localappdata,
                                          "Microsoft", "Windows", "Fonts"))
    elif sys.platform == "darwin":
        font_dirs.extend(["/Library/Fonts", "/System/Library/Fonts",
                          os.path.expanduser("~/Library/Fonts")])
    else:
        font_dirs.extend(["/usr/share/fonts", "/usr/local/share/fonts",
                          os.path.expanduser("~/.fonts"),
                          os.path.expanduser("~/.local/share/fonts")])

    mapping: dict[str, str] = {}
    for d in font_dirs:
        if not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for f in files:
                low = f.lower()
                if low.endswith((".ttf", ".otf", ".ttc")):
                    full = os.path.join(root, f)
                    # Map by filename without extension
                    stem = low.rsplit(".", 1)[0]
                    mapping[stem] = full
                    # Also map with extension
                    mapping[low] = full
    return mapping


def _find_system_font(family: str, bold: bool, italic: bool) -> str | None:
    """Try to find a system font file matching the family and style."""
    global _system_font_map
    if _system_font_map is None:
        _system_font_map = _build_system_font_map()
    if not _system_font_map:
        return None

    base = family.lower().replace(" ", "")

    # Build suffix variants to try
    suffixes: list[str] = []
    if bold and italic:
        suffixes.extend(["bolditalic", "bi", "bold_italic", "boldoblique",
                         "z"])  # z = bolditalic in some naming
    elif bold:
        suffixes.extend(["bold", "bd", "b"])
    elif italic:
        suffixes.extend(["italic", "it", "i", "oblique"])
    suffixes.append("")  # fallback to regular

    # Also try "regular" variant names
    regular_suffixes = ["regular", ""]

    for suffix in suffixes:
        # e.g. "arial" + "bold" = "arialbold", "arialbd", etc.
        candidates = []
        if suffix:
            candidates.append(f"{base}{suffix}")
            candidates.append(f"{base}-{suffix}")
            candidates.append(f"{base}_{suffix}")
        else:
            candidates.append(base)
            for rs in regular_suffixes:
                if rs:
                    candidates.append(f"{base}{rs}")
                    candidates.append(f"{base}-{rs}")

        for c in candidates:
            if c in _system_font_map:
                return _system_font_map[c]

    # Last resort: just find any font starting with the base name
    for name, path in _system_font_map.items():
        if name.startswith(base):
            return path

    return None


def _get_font(family: str, size: float, bold: bool = False,
              italic: bool = False):
    """Load (and cache) a PIL ImageFont with robust system font lookup."""
    from PIL import ImageFont
    key = f"{family}|{size}|{bold}|{italic}"
    if key in _font_cache:
        return _font_cache[key]

    int_size = max(1, int(size))

    # Strategy 1: Try PIL's built-in name resolution (works on some systems)
    try_names = [family]
    base = family.lower().replace(" ", "")
    if base != family:
        try_names.append(base)
    for name in try_names:
        try:
            font = ImageFont.truetype(name, int_size)
            _font_cache[key] = font
            return font
        except (OSError, IOError):
            pass

    # Strategy 2: Search system font directories
    path = _find_system_font(family, bold, italic)
    if path:
        try:
            font = ImageFont.truetype(path, int_size)
            _font_cache[key] = font
            return font
        except (OSError, IOError):
            pass

    # Strategy 3: Try without bold/italic (get at least the right family)
    if bold or italic:
        path = _find_system_font(family, False, False)
        if path:
            try:
                font = ImageFont.truetype(path, int_size)
                _font_cache[key] = font
                return font
            except (OSError, IOError):
                pass

    # Strategy 4: Fall back to a known-good font
    for fallback in ["arial", "segoeui", "calibri", "DejaVuSans"]:
        path = _find_system_font(fallback, bold, italic)
        if path:
            try:
                font = ImageFont.truetype(path, int_size)
                _font_cache[key] = font
                return font
            except (OSError, IOError):
                pass

    font = ImageFont.load_default(int_size)
    _font_cache[key] = font
    return font


# ============================================================================
# Layout algorithm
# ============================================================================

def _layout_text(td: TextLayerData) -> list[_LayoutLine]:
    """Word-wrap and lay out all text runs into lines."""
    from PIL import Image, ImageDraw

    # Flatten runs into per-character glyph infos
    all_glyphs: list[_GlyphInfo] = []
    dummy = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(dummy)

    for run in td.runs:
        font = _get_font(run.fmt.font_family, run.fmt.font_size,
                         run.fmt.bold, run.fmt.italic)
        
        # Process text for proper Arabic rendering (RTL + character shaping)
        processed_text = _process_arabic_text(run.text)
        
        for ch in processed_text:
            if ch == "\n":
                all_glyphs.append(_GlyphInfo(
                    char="\n", advance=0, ascent=run.fmt.font_size,
                    descent=run.fmt.font_size * 0.3, fmt=run.fmt,
                ))
                continue
            bbox = draw.textbbox((0, 0), ch, font=font)
            w = bbox[2] - bbox[0]
            advance = w + run.fmt.letter_spacing
            ascent = run.fmt.font_size
            descent = run.fmt.font_size * 0.3
            all_glyphs.append(_GlyphInfo(
                char=ch, advance=max(advance, 1),
                ascent=ascent, descent=descent, fmt=run.fmt,
            ))

    if not all_glyphs:
        # Empty text — single empty line
        default_h = td.runs[0].fmt.font_size if td.runs else 36
        return [_LayoutLine(glyphs=[], y=0, height=default_h * td.paragraph_fmt.line_height)]

    # Word-wrap into lines
    lines: list[_LayoutLine] = []
    box_w = td.box_width
    current_glyphs: list[_GlyphInfo] = []
    current_w = 0.0
    para_idx = 0

    def _finish_line(has_newline: bool = False) -> None:
        nonlocal current_glyphs, current_w
        lines.append(_LayoutLine(glyphs=current_glyphs, paragraph_index=para_idx, has_newline=has_newline))
        current_glyphs = []
        current_w = 0.0

    i = 0
    while i < len(all_glyphs):
        g = all_glyphs[i]
        if g.char == "\n":
            _finish_line(has_newline=True)
            para_idx += 1
            i += 1
            continue
        # Check if adding this glyph overflows
        if current_w + g.advance > box_w and current_glyphs:
            # Try to break at last space
            space_idx = None
            for j in range(len(current_glyphs) - 1, -1, -1):
                if current_glyphs[j].char in (" ", "\t"):
                    space_idx = j
                    break
            if space_idx is not None:
                # Break after the space
                line_glyphs = current_glyphs[:space_idx + 1]
                remaining = current_glyphs[space_idx + 1:]
                lines.append(_LayoutLine(glyphs=line_glyphs, paragraph_index=para_idx))
                current_glyphs = remaining
                current_w = sum(gg.advance for gg in remaining)
            else:
                # Force break (no space found)
                _finish_line()
        current_glyphs.append(g)
        current_w += g.advance
        i += 1

    if current_glyphs:
        _finish_line()

    # If the last line ends with a newline, add an empty line so the
    # cursor has a place to go on the new line.
    if lines and lines[-1].has_newline:
        lines.append(_LayoutLine(glyphs=[], paragraph_index=para_idx,
                                 has_newline=False))

    # Compute line metrics (height, y position, x_offset for alignment)
    y = 0.0
    line_height_mult = td.paragraph_fmt.line_height
    prev_para = 0
    for line in lines:
        max_ascent = 0.0
        max_descent = 0.0
        for g in line.glyphs:
            max_ascent = max(max_ascent, g.ascent)
            max_descent = max(max_descent, g.descent)
        if not line.glyphs:
            default_fs = td.runs[0].fmt.font_size if td.runs else 36
            max_ascent = default_fs
            max_descent = default_fs * 0.3
        lh = (max_ascent + max_descent) * line_height_mult
        line.height = lh
        # Paragraph spacing
        if line.paragraph_index != prev_para:
            y += td.paragraph_fmt.paragraph_spacing
            prev_para = line.paragraph_index
        line.y = y
        y += lh
        # Alignment - use per-paragraph alignment if available, otherwise default
        line_w = sum(g.advance for g in line.glyphs)
        # Get alignment for this specific paragraph
        align = td.paragraph_fmt.paragraph_alignments.get(line.paragraph_index, td.paragraph_fmt.alignment)
        if align == "center":
            line.x_offset = (box_w - line_w) / 2
        elif align == "right":
            line.x_offset = box_w - line_w
        else:
            line.x_offset = 0.0
        # Set glyph x positions
        gx = line.x_offset
        for g in line.glyphs:
            g.x = gx
            gx += g.advance

    return lines


# ============================================================================
# Renderer
# ============================================================================

def _render_layout(lines: list[_LayoutLine], box_w: int, box_h: int,
                   para_fmt: ParagraphFormat) -> np.ndarray:
    """Rasterise laid-out lines to an RGBA float32 image."""
    from PIL import Image, ImageDraw

    if not lines:
        return np.zeros((max(box_h, 1), max(box_w, 1), 4), dtype=np.float32)

    # Compute total height
    total_h = 0.0
    for line in lines:
        total_h = max(total_h, line.y + line.height)
    img_h = max(int(math.ceil(total_h)) + 4, box_h, 1)
    img_w = max(box_w, 1)

    img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    for line in lines:
        for g in line.glyphs:
            if g.char in ("\n", ""):
                continue
            font = _get_font(g.fmt.font_family, g.fmt.font_size,
                             g.fmt.bold, g.fmt.italic)
            # Sample colour from the fill
            fill = g.fmt.color
            if isinstance(fill, SolidFill):
                c = fill.color
            else:
                # For gradients, sample at normalised glyph position
                u = g.x / max(img_w, 1)
                v = line.y / max(img_h, 1)
                c = fill.sample(u, v)
            r8, g8, b8, a8 = c.to_rgb8()

            draw.text((g.x, line.y), g.char, font=font,
                      fill=(r8, g8, b8, a8))

            # Underline
            if g.fmt.underline:
                uy = line.y + g.ascent + 2
                draw.line([(g.x, uy), (g.x + g.advance, uy)],
                          fill=(r8, g8, b8, a8), width=max(1, int(g.fmt.font_size / 18)))

            # Strikethrough
            if g.fmt.strikethrough:
                sy = line.y + g.ascent * 0.55
                draw.line([(g.x, sy), (g.x + g.advance, sy)],
                          fill=(r8, g8, b8, a8), width=max(1, int(g.fmt.font_size / 18)))

    arr = np.array(img, dtype=np.float32) / 255.0
    return arr
