"""In-house text layout and editing engine.

PDFs have no notion of an editable paragraph — they hold positioned glyphs. To
edit text in place we rebuild that structure ourselves:

  extract  ->  characters + per-character styles + original line geometry
  layout   ->  word-wrapped lines with exact glyph advances
  edit     ->  caret / selection / insert / delete, like any text field
  commit   ->  erase the original glyphs, redraw ours in the same typeface

Nothing here depends on Qt, so the whole editor is testable headless.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import fitz

from .fonts import FontResolver, ResolvedFont

ALIGN_LEFT, ALIGN_CENTER, ALIGN_RIGHT = 0, 1, 2


@dataclass
class Style:
    """Formatting for a single character."""

    font: ResolvedFont
    size: float
    color: tuple = (0.0, 0.0, 0.0)

    def key(self):
        return (self.font.key, round(self.size, 2), self.color)

    def replace(self, **kw) -> "Style":
        return Style(kw.get("font", self.font), kw.get("size", self.size),
                     kw.get("color", self.color))


@dataclass
class LayoutLine:
    start: int
    end: int                      # exclusive, not counting the newline
    x: float                      # left edge in page coords
    baseline: float
    ascent: float
    descent: float
    offsets: list[float] = field(default_factory=list)  # x offset per char, len = end-start+1

    @property
    def top(self) -> float:
        return self.baseline - self.ascent

    @property
    def bottom(self) -> float:
        return self.baseline - self.descent      # descent is negative

    @property
    def height(self) -> float:
        return self.bottom - self.top

    @property
    def width(self) -> float:
        return self.offsets[-1] if self.offsets else 0.0


@dataclass
class DrawRun:
    """A run of same-styled text ready to be painted or written back."""

    x: float
    baseline: float
    text: str
    style: Style


def rgb_from_int(value: int) -> tuple:
    try:
        return fitz.sRGB_to_pdf(int(value))
    except Exception:
        return (0.0, 0.0, 0.0)


def int_from_rgb(color: tuple) -> int:
    r, g, b = (max(0, min(255, int(round(c * 255)))) for c in color)
    return (r << 16) | (g << 8) | b


class EditableText:
    """A block of text you can put a caret in."""

    def __init__(self, text: str, styles: list[Style], origin: tuple[float, float],
                 width: float, leading: float, align: int = ALIGN_LEFT,
                 first_baseline: float | None = None):
        self.text = text
        self.styles = styles
        self.x, self.y = origin                 # y is the top of the first line
        self.width = max(12.0, width)
        self.leading = leading
        self.align = align
        self.first_baseline = first_baseline

        self.caret = 0
        self.anchor: int | None = None
        self._layout: list[LayoutLine] | None = None
        self.dirty = False                      # text/styles changed since load

    # ------------------------------------------------------------ factories

    @classmethod
    def from_block(cls, block: dict, resolver: FontResolver, pno: int,
                   page_rect: fitz.Rect | None = None) -> "EditableText":
        """Build from a PyMuPDF 'rawdict' text block."""
        chars: list[str] = []
        styles: list[Style] = []
        baselines: list[float] = []
        line_lefts: list[float] = []
        line_rights: list[float] = []

        lines = [ln for ln in block.get("lines", []) if ln.get("spans")]
        for li, line in enumerate(lines):
            if li:
                chars.append("\n")
                styles.append(styles[-1] if styles else Style(
                    resolver.synthetic(), 11.0))
            left, right = None, None
            for span in line["spans"]:
                font = resolver.resolve_span(pno, span)
                style = Style(font, float(span.get("size", 11.0)),
                              rgb_from_int(span.get("color", 0)))
                for ch in span.get("chars", []):
                    glyph = ch.get("c", "")
                    if not glyph:
                        continue
                    chars.append(glyph)
                    styles.append(style)
                    bbox = ch.get("bbox")
                    if bbox:
                        left = bbox[0] if left is None else min(left, bbox[0])
                        right = bbox[2] if right is None else max(right, bbox[2])
                if not span.get("chars") and span.get("text"):
                    for glyph in span["text"]:
                        chars.append(glyph)
                        styles.append(style)
            origin = line["spans"][0].get("origin")
            if origin:
                baselines.append(origin[1])
            if left is not None:
                line_lefts.append(left)
                line_rights.append(right)

        bbox = fitz.Rect(block["bbox"])
        # Leading: measured from the document itself when there is more than one
        # line, otherwise derived from the type size.
        if len(baselines) >= 2:
            gaps = [b - a for a, b in zip(baselines, baselines[1:]) if b > a]
            leading = sum(gaps) / len(gaps) if gaps else styles[0].size * 1.2
        else:
            leading = (styles[0].size if styles else 11.0) * 1.2

        align = ALIGN_LEFT
        if len(line_lefts) >= 2:
            left_spread = max(line_lefts) - min(line_lefts)
            right_spread = max(line_rights) - min(line_rights)
            if left_spread > 2.0 and right_spread <= 2.0:
                align = ALIGN_RIGHT
            elif left_spread > 2.0 and right_spread > 2.0:
                centers = [(l + r) / 2 for l, r in zip(line_lefts, line_rights)]
                if max(centers) - min(centers) < 2.0:
                    align = ALIGN_CENTER

        origin_x = min(line_lefts) if line_lefts else bbox.x0

        # Wrap width. A paragraph keeps its original column so re-layout
        # reproduces the wrap it already had; a single line is free to grow to
        # the right margin, because typing into a heading should extend it
        # rather than silently fold a word onto a second line.
        if len(lines) <= 1:
            right_limit = (page_rect.x1 - 18.0) if page_rect is not None else bbox.x1
            width = max(bbox.width, right_limit - origin_x)
        else:
            width = max(bbox.width, max(line_rights) - origin_x if line_rights else 0) + 1.0
        if align == ALIGN_RIGHT:
            origin_x = bbox.x0
        obj = cls("".join(chars), styles, (origin_x, bbox.y0), width, leading,
                  align, first_baseline=baselines[0] if baselines else None)
        obj.source_rect = bbox
        obj.source_baselines = baselines
        return obj

    @classmethod
    def blank(cls, resolver: FontResolver, origin: tuple[float, float],
              width: float, size: float = 14.0, color=(0, 0, 0),
              bold=False, italic=False, family="helv") -> "EditableText":
        style = Style(resolver.synthetic(family, bold, italic), size, color)
        obj = cls("", [style], origin, width, size * 1.25, ALIGN_LEFT)
        obj._pending_style = style
        obj.dirty = True
        return obj

    # --------------------------------------------------------------- layout

    def invalidate(self):
        self._layout = None

    def style_at(self, index: int) -> Style:
        if not self.styles:
            return Style(None, 11.0)
        return self.styles[max(0, min(index, len(self.styles) - 1))]

    @property
    def pending_style(self) -> Style:
        """Style applied to the next typed character."""
        explicit = getattr(self, "_pending_style", None)
        if explicit is not None:
            return explicit
        if not self.text:
            return self.style_at(0)
        return self.style_at(self.caret - 1 if self.caret > 0 else 0)

    def set_pending_style(self, style: Style | None):
        self._pending_style = style

    def layout(self) -> list[LayoutLine]:
        if self._layout is not None:
            return self._layout

        lines: list[LayoutLine] = []
        text, styles = self.text, self.styles
        n = len(text)

        # Paragraph = run between explicit newlines.
        para_start = 0
        segments: list[tuple[int, int]] = []
        for i, ch in enumerate(text):
            if ch == "\n":
                segments.append((para_start, i))
                para_start = i + 1
        segments.append((para_start, n))

        rows: list[tuple[int, int]] = []
        for start, end in segments:
            if start >= end:
                rows.append((start, end))
                continue
            cursor = start
            while cursor < end:
                used = 0.0
                last_break = -1
                idx = cursor
                while idx < end:
                    style = styles[idx] if idx < len(styles) else self.style_at(idx)
                    advance = style.font.advance(text[idx], style.size) if style.font else 0.0
                    if used + advance > self.width and idx > cursor:
                        break
                    used += advance
                    if text[idx] == " ":
                        last_break = idx
                    idx += 1
                if idx >= end:
                    rows.append((cursor, end))
                    cursor = end
                else:
                    brk = last_break + 1 if last_break >= cursor else idx
                    rows.append((cursor, brk))
                    cursor = brk

        # Vertical placement.
        use_source = (not self.dirty and getattr(self, "source_baselines", None)
                      and len(self.source_baselines) == len(rows))
        baseline = None
        for row_index, (start, end) in enumerate(rows):
            row_styles = [styles[i] for i in range(start, min(end, len(styles)))]
            if not row_styles:
                row_styles = [self.pending_style]
            size = max((s.size for s in row_styles), default=11.0)
            font = next((s.font for s in row_styles if s.font), None)
            ascent = font.ascender(size) if font else size * 0.8
            descent = font.descender(size) if font else -size * 0.2

            if use_source:
                baseline = self.source_baselines[row_index]
            elif baseline is None:
                baseline = (self.first_baseline if (self.first_baseline is not None
                                                    and not self.dirty)
                            else self.y + ascent)
            else:
                baseline += self.leading

            offsets = [0.0]
            for i in range(start, end):
                style = styles[i] if i < len(styles) else self.pending_style
                advance = style.font.advance(text[i], style.size) if style.font else 0.0
                offsets.append(offsets[-1] + advance)

            line_width = offsets[-1]
            if self.align == ALIGN_CENTER:
                x = self.x + (self.width - line_width) / 2
            elif self.align == ALIGN_RIGHT:
                x = self.x + self.width - line_width
            else:
                x = self.x
            lines.append(LayoutLine(start, end, x, baseline, ascent, descent, offsets))

        self._layout = lines
        return lines

    def bounds(self) -> fitz.Rect:
        lines = self.layout()
        if not lines:
            size = self.pending_style.size
            return fitz.Rect(self.x, self.y, self.x + self.width, self.y + size * 1.3)
        x0 = min(l.x for l in lines)
        x1 = max(l.x + l.width for l in lines)
        return fitz.Rect(min(x0, self.x), lines[0].top,
                         max(x1, self.x + 4), lines[-1].bottom)

    def draw_runs(self) -> list[DrawRun]:
        """Split every line into same-style runs for painting / writing back."""
        runs: list[DrawRun] = []
        for line in self.layout():
            i = line.start
            while i < line.end:
                style = self.style_at(i)
                j = i
                while j < line.end and self.style_at(j).key() == style.key():
                    j += 1
                text = self.text[i:j]
                if text.strip():
                    runs.append(DrawRun(line.x + line.offsets[i - line.start],
                                        line.baseline, text, style))
                i = j
        return runs

    # ----------------------------------------------------------- caret model

    def line_of(self, index: int) -> int:
        lines = self.layout()
        for i, line in enumerate(lines):
            if index <= line.end:
                return i
        return max(0, len(lines) - 1)

    def caret_x(self, index: int) -> float:
        lines = self.layout()
        if not lines:
            return self.x
        li = self.line_of(index)
        line = lines[li]
        offset_index = max(0, min(index - line.start, len(line.offsets) - 1))
        return line.x + line.offsets[offset_index]

    def caret_rect(self, index: int | None = None) -> fitz.Rect:
        index = self.caret if index is None else index
        lines = self.layout()
        if not lines:
            size = self.pending_style.size
            return fitz.Rect(self.x, self.y, self.x + 1.0, self.y + size * 1.2)
        line = lines[self.line_of(index)]
        x = self.caret_x(index)
        return fitz.Rect(x, line.top, x + 1.0, line.bottom)

    def hit_test(self, point: fitz.Point) -> int:
        """Nearest caret position to a page-space point."""
        lines = self.layout()
        if not lines:
            return 0
        line = lines[-1]
        for candidate in lines:
            if point.y <= candidate.bottom:
                line = candidate
                break
        best, best_dist = line.start, None
        for k, offset in enumerate(line.offsets):
            dist = abs(line.x + offset - point.x)
            if best_dist is None or dist < best_dist:
                best, best_dist = line.start + k, dist
        return max(0, min(best, len(self.text)))

    def selection_range(self) -> tuple[int, int] | None:
        if self.anchor is None or self.anchor == self.caret:
            return None
        return (min(self.anchor, self.caret), max(self.anchor, self.caret))

    def selection_rects(self) -> list[fitz.Rect]:
        span = self.selection_range()
        if not span:
            return []
        start, end = span
        rects = []
        for line in self.layout():
            a, b = max(start, line.start), min(end, line.end)
            if a >= b:
                continue
            x0 = line.x + line.offsets[a - line.start]
            x1 = line.x + line.offsets[b - line.start]
            rects.append(fitz.Rect(x0, line.top, x1, line.bottom))
        return rects

    def selected_text(self) -> str:
        span = self.selection_range()
        return self.text[span[0]:span[1]] if span else ""

    # -------------------------------------------------------------- editing

    def _mark_dirty(self):
        self.dirty = True
        self.invalidate()

    def set_caret(self, index: int, extend: bool = False):
        index = max(0, min(index, len(self.text)))
        if extend:
            if self.anchor is None:
                self.anchor = self.caret
        else:
            self.anchor = None
        self.caret = index
        self.set_pending_style(None)

    def select_all(self):
        self.anchor, self.caret = 0, len(self.text)

    def select_word_at(self, index: int):
        text = self.text
        if not text:
            return
        index = max(0, min(index, len(text) - 1))
        if text[index].isspace():
            start = end = index
        else:
            start = index
            while start > 0 and not text[start - 1].isspace():
                start -= 1
            end = index
            while end < len(text) and not text[end].isspace():
                end += 1
        self.anchor, self.caret = start, end

    def select_line_at(self, index: int):
        line = self.layout()[self.line_of(index)]
        self.anchor, self.caret = line.start, line.end

    def delete_selection(self) -> bool:
        span = self.selection_range()
        if not span:
            return False
        start, end = span
        style = self.style_at(start)
        self.text = self.text[:start] + self.text[end:]
        del self.styles[start:end]
        self.caret, self.anchor = start, None
        self.set_pending_style(style)
        self._mark_dirty()
        return True

    def insert(self, chunk: str):
        if not chunk:
            return
        style = self.pending_style
        self.delete_selection()
        at = self.caret
        self.text = self.text[:at] + chunk + self.text[at:]
        self.styles[at:at] = [style] * len(chunk)
        self.caret = at + len(chunk)
        self.anchor = None
        self.set_pending_style(style)
        self._mark_dirty()

    def backspace(self):
        if self.delete_selection():
            return
        if self.caret <= 0:
            return
        at = self.caret - 1
        self.text = self.text[:at] + self.text[at + 1:]
        del self.styles[at]
        self.caret = at
        self._mark_dirty()

    def delete_forward(self):
        if self.delete_selection():
            return
        if self.caret >= len(self.text):
            return
        at = self.caret
        self.text = self.text[:at] + self.text[at + 1:]
        del self.styles[at]
        self._mark_dirty()

    # ------------------------------------------------------ caret movement

    def move_horizontal(self, delta: int, extend: bool = False, word: bool = False):
        if word:
            index = self.caret
            step = 1 if delta > 0 else -1
            if step < 0:
                index -= 1
                while index > 0 and self.text[index].isspace():
                    index -= 1
                while index > 0 and not self.text[index - 1].isspace():
                    index -= 1
            else:
                while index < len(self.text) and not self.text[index].isspace():
                    index += 1
                while index < len(self.text) and self.text[index].isspace():
                    index += 1
            self.set_caret(index, extend)
            return
        span = self.selection_range()
        if span and not extend:
            self.set_caret(span[1] if delta > 0 else span[0])
            return
        self.set_caret(self.caret + delta, extend)

    def move_vertical(self, delta: int, extend: bool = False):
        lines = self.layout()
        if not lines:
            return
        li = self.line_of(self.caret)
        target = li + delta
        if target < 0 or target >= len(lines):
            self.set_caret(0 if target < 0 else len(self.text), extend)
            return
        x = self.caret_x(self.caret)
        line = lines[target]
        best, best_dist = line.start, None
        for k, offset in enumerate(line.offsets):
            dist = abs(line.x + offset - x)
            if best_dist is None or dist < best_dist:
                best, best_dist = line.start + k, dist
        self.set_caret(best, extend)

    def move_line_edge(self, to_end: bool, extend: bool = False):
        line = self.layout()[self.line_of(self.caret)]
        self.set_caret(line.end if to_end else line.start, extend)

    def move_document_edge(self, to_end: bool, extend: bool = False):
        self.set_caret(len(self.text) if to_end else 0, extend)

    # ----------------------------------------------------------- formatting

    def apply_style(self, **changes):
        """Restyle the selection (or set the style for what you type next)."""
        span = self.selection_range()
        if span:
            start, end = span
            for i in range(start, end):
                self.styles[i] = self._changed(self.styles[i], changes)
            self._mark_dirty()
        else:
            self.set_pending_style(self._changed(self.pending_style, changes))

    def _changed(self, style: Style, changes: dict) -> Style:
        font = style.font
        if "bold" in changes or "italic" in changes or "family" in changes:
            resolver = changes["resolver"]
            bold = changes.get("bold", font.bold if font else False)
            italic = changes.get("italic", font.italic if font else False)
            family = changes.get("family", font.base14_family_code() if font else "helv")
            if font and font.embedded and "family" not in changes:
                # Keep the embedded face; synthesise the weight only if needed.
                new_font = font if (bold == font.bold and italic == font.italic) \
                    else resolver.synthetic(font.base14_family_code(), bold, italic,
                                            display=font.display_name)
            else:
                new_font = resolver.synthetic(family, bold, italic)
            font = new_font
        return Style(font, changes.get("size", style.size),
                     changes.get("color", style.color))

    def move_by(self, dx: float, dy: float):
        self.x += dx
        self.y += dy
        if self.first_baseline is not None:
            self.first_baseline += dy
        if getattr(self, "source_baselines", None):
            self.source_baselines = [b + dy for b in self.source_baselines]
        self.invalidate()

    def set_wrap_width(self, width: float):
        self.width = max(16.0, width)
        self.dirty = True
        self.invalidate()

    def is_empty(self) -> bool:
        return not self.text.strip()
