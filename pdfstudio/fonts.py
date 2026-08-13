"""In-house font resolution, measurement and re-embedding.

Everything the editor knows about type lives here. Given a text span taken from
a page, we work out:
  * which physical font drew it (embedded buffer if there is one, else base-14),
  * how to measure it exactly (glyph advances, not estimates),
  * how to draw it live on screen in Qt, and
  * how to write it back into the PDF in the *same* typeface.

That last point is what keeps inline editing honest: text you retype comes back
in the font it started in, not a generic substitute.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import fitz

# PyMuPDF span flag bits.
FLAG_SUPERSCRIPT = 1
FLAG_ITALIC = 2
FLAG_SERIF = 4
FLAG_MONO = 8
FLAG_BOLD = 16

SUBSET_PREFIX = re.compile(r"^[A-Z]{6}\+")

# base-14 codes: (regular, bold, italic, bold-italic)
BASE14 = {
    "helv": ("helv", "hebo", "heit", "hebi"),
    "tiro": ("tiro", "tibo", "tiit", "tibi"),
    "cour": ("cour", "cobo", "coit", "cobi"),
    "symb": ("symb", "symb", "symb", "symb"),
    "zadb": ("zadb", "zadb", "zadb", "zadb"),
}

# Map common PostScript/base font names onto a base-14 family.
FAMILY_HINTS = [
    ("courier", "cour"), ("mono", "cour"), ("consol", "cour"),
    ("times", "tiro"), ("georgia", "tiro"), ("book", "tiro"),
    ("garamond", "tiro"), ("minion", "tiro"), ("roman", "tiro"),
    ("serif", "tiro"), ("cambria", "tiro"),
    ("symbol", "symb"), ("dingbat", "zadb"), ("zapf", "zadb"),
]

# Qt families to try when we have no embedded buffer, best match first.
QT_FALLBACK = {
    "helv": ["Helvetica", "Arial", "Liberation Sans", "DejaVu Sans", "Nimbus Sans"],
    "tiro": ["Times New Roman", "Liberation Serif", "DejaVu Serif", "Nimbus Roman"],
    "cour": ["Courier New", "Liberation Mono", "DejaVu Sans Mono", "Nimbus Mono PS"],
    "symb": ["Standard Symbols PS", "DejaVu Sans"],
    "zadb": ["D050000L", "DejaVu Sans"],
}


def clean_name(name: str) -> str:
    """'ABCDEF+Helvetica-Bold' -> 'Helvetica-Bold'."""
    return SUBSET_PREFIX.sub("", name or "")


def base14_family(basefont: str, flags: int = 0) -> str:
    low = clean_name(basefont).lower()
    for needle, family in FAMILY_HINTS:
        if needle in low:
            return family
    if flags & FLAG_MONO:
        return "cour"
    if flags & FLAG_SERIF:
        return "tiro"
    return "helv"


def base14_code(basefont: str, flags: int = 0) -> str:
    """Pick the concrete base-14 code, honouring bold/italic."""
    family = base14_family(basefont, flags)
    low = clean_name(basefont).lower()
    bold = bool(flags & FLAG_BOLD) or "bold" in low or "black" in low or "heavy" in low
    italic = bool(flags & FLAG_ITALIC) or "italic" in low or "oblique" in low
    regular, b, i, bi = BASE14[family]
    if bold and italic:
        return bi
    if bold:
        return b
    if italic:
        return i
    return regular


@dataclass
class ResolvedFont:
    """A font we can measure, draw in Qt, and write back into the PDF."""

    key: str
    display_name: str
    base14: str | None = None          # set when not embedded
    buffer: bytes | None = None        # set when embedded
    flags: int = 0
    _font: fitz.Font | None = field(default=None, repr=False)
    _qt_family: str | None = field(default=None, repr=False)

    @property
    def embedded(self) -> bool:
        return self.buffer is not None

    @property
    def bold(self) -> bool:
        return bool(self.flags & FLAG_BOLD)

    @property
    def italic(self) -> bool:
        return bool(self.flags & FLAG_ITALIC)

    def font(self) -> fitz.Font:
        if self._font is None:
            try:
                self._font = (fitz.Font(fontbuffer=self.buffer) if self.embedded
                              else fitz.Font(self.base14 or "helv"))
            except Exception:
                self._font = fitz.Font("helv")
                self.buffer = None
                self.base14 = self.base14 or "helv"
        return self._font

    # ------------------------------------------------------------- measuring

    def width(self, text: str, size: float) -> float:
        if not text:
            return 0.0
        try:
            return self.font().text_length(text, size)
        except Exception:
            return fitz.get_text_length(text, fontname=self.base14 or "helv", fontsize=size)

    def advance(self, ch: str, size: float) -> float:
        return self.width(ch, size)

    def ascender(self, size: float) -> float:
        try:
            return self.font().ascender * size
        except Exception:
            return 0.8 * size

    def descender(self, size: float) -> float:
        try:
            return self.font().descender * size
        except Exception:
            return -0.2 * size

    def has_glyph(self, ch: str) -> bool:
        try:
            return self.font().has_glyph(ord(ch))
        except Exception:
            return True

    # ------------------------------------------------------ drawing in Qt

    def qt_family(self) -> str:
        """Family name usable in a QFont — the real embedded face when possible."""
        if self._qt_family is not None:
            return self._qt_family
        family = None
        if self.embedded:
            try:
                from PySide6.QtCore import QByteArray
                from PySide6.QtGui import QFontDatabase
                fid = QFontDatabase.addApplicationFontFromData(QByteArray(self.buffer))
                if fid != -1:
                    families = QFontDatabase.applicationFontFamilies(fid)
                    if families:
                        family = families[0]
            except Exception:
                family = None
        if not family:
            try:
                from PySide6.QtGui import QFontDatabase
                available = set(QFontDatabase.families())
            except Exception:
                available = set()
            for candidate in QT_FALLBACK.get(self.base14_family_code(), []):
                if candidate in available:
                    family = candidate
                    break
            if not family:
                family = QT_FALLBACK.get(self.base14_family_code(), ["Sans"])[0]
        self._qt_family = family
        return family

    def base14_family_code(self) -> str:
        code = self.base14 or base14_code(self.display_name, self.flags)
        for family, variants in BASE14.items():
            if code in variants:
                return family
        return "helv"

    # ------------------------------------------------- writing into the PDF

    def install(self, page: fitz.Page, resolver: "FontResolver") -> str:
        """Make this font usable on `page`; returns the fontname to pass to insert_text."""
        if not self.embedded:
            return self.base14 or "helv"
        tag = resolver.page_tag(page, self)
        return tag


class FontResolver:
    """Caches font lookups per document.

    Spans only tell us a *name*; the buffer lives on the page's font list. We
    match them up once and reuse the result everywhere.
    """

    def __init__(self, doc: fitz.Document):
        self.doc = doc
        self._by_key: dict[str, ResolvedFont] = {}
        self._page_fonts: dict[int, dict[str, str]] = {}   # page -> {name: xref-list}
        self._installed: dict[tuple[int, str], str] = {}
        self._counter = 0

    def reset(self, doc: fitz.Document | None = None):
        if doc is not None:
            self.doc = doc
        self._by_key.clear()
        self._page_fonts.clear()
        self._installed.clear()

    # ------------------------------------------------------------- lookups

    def _page_font_table(self, pno: int) -> dict[str, int]:
        table = self._page_fonts.get(pno)
        if table is None:
            table = {}
            try:
                for entry in self.doc[pno].get_fonts(full=True):
                    xref, basefont = entry[0], entry[3]
                    table[clean_name(basefont).lower()] = xref
            except Exception:
                pass
            self._page_fonts[pno] = table
        return table

    def resolve_span(self, pno: int, span: dict) -> ResolvedFont:
        name = clean_name(span.get("font", "") or "Helvetica")
        flags = int(span.get("flags", 0) or 0)
        key = f"{name}|{flags}"
        cached = self._by_key.get(key)
        if cached is not None:
            return cached

        buffer = None
        xref = self._page_font_table(pno).get(name.lower())
        if xref:
            try:
                info = self.doc.extract_font(xref)
                # (basefont, ext, type, buffer)
                if info and len(info) >= 4 and info[3] and info[1] not in ("n/a", ""):
                    buffer = bytes(info[3])
            except Exception:
                buffer = None

        resolved = ResolvedFont(
            key=key, display_name=name, flags=flags,
            buffer=buffer,
            base14=None if buffer else base14_code(name, flags))
        # Validate the buffer actually loads; fall back cleanly if not.
        if buffer is not None:
            try:
                fitz.Font(fontbuffer=buffer)
            except Exception:
                resolved.buffer = None
                resolved.base14 = base14_code(name, flags)
        self._by_key[key] = resolved
        return resolved

    def synthetic(self, family_code: str = "helv", bold=False, italic=False,
                  display: str | None = None) -> ResolvedFont:
        """A font for text we are creating from scratch (the Text tool)."""
        flags = (FLAG_BOLD if bold else 0) | (FLAG_ITALIC if italic else 0)
        if family_code == "cour":
            flags |= FLAG_MONO
        if family_code == "tiro":
            flags |= FLAG_SERIF
        regular, b, i, bi = BASE14.get(family_code, BASE14["helv"])
        code = bi if (bold and italic) else b if bold else i if italic else regular
        key = f"@synthetic|{code}"
        cached = self._by_key.get(key)
        if cached is None:
            cached = ResolvedFont(key=key, display_name=display or code,
                                  base14=code, flags=flags)
            self._by_key[key] = cached
        return cached

    # -------------------------------------------------------- installation

    def page_tag(self, page: fitz.Page, font: ResolvedFont) -> str:
        """Embed `font` into `page` (once) and return its resource name."""
        cache_key = (page.number, font.key)
        tag = self._installed.get(cache_key)
        if tag:
            return tag
        self._counter += 1
        tag = f"PS{self._counter}"
        try:
            page.insert_font(fontname=tag, fontbuffer=font.buffer)
        except Exception:
            tag = font.base14 or base14_code(font.display_name, font.flags)
        self._installed[cache_key] = tag
        return tag

    def invalidate_pages(self):
        """Call after structural edits — page numbers and resources may shift."""
        self._page_fonts.clear()
        self._installed.clear()
