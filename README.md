# PDF Studio

A free, open-source desktop PDF editor that builds into a single executable —
an Acrobat-Pro-class tool with no subscription, no account, and no uploads.
Everything runs locally on your machine.

**Text is genuinely editable.** Click into a paragraph, get a real caret, and
type. Text reflows as you go, and when you're done the words are written back
in the document's own font — including fonts embedded in the file, not a
generic substitute.

![Screenshot](docs/screenshot.png)

## Features

**Editing text in place**
- Click any text to put a caret in it and start typing
- Full keyboard editing: arrows, word-jump (Ctrl+←/→), Home/End, shift-select,
  double-click a word, Ctrl+A, cut/copy/paste, undo
- Live reflow with real glyph metrics — the line breaks the way it will save
- **Drag a text block** anywhere on the page by its handle bar
- **Resize the wrap width** with the round grip; the paragraph re-wraps live
- Restyle while editing: font family, size, **bold** (Ctrl+B), *italic*
  (Ctrl+I), colour — applied to a selection or to what you type next
- Add brand-new text boxes anywhere with the Text tool
- Original typeface is preserved on save, embedded fonts included

**Annotation and markup**
- Highlight, underline, strike out (drag across text — it snaps to words)
- Rectangles, ellipses, lines, arrows, freehand ink, with colour and thickness
- Sticky notes and image stamps (drop in a signature, logo or photo)
- Click any object to select it, drag to move, drag a corner handle to resize,
  Delete to remove
- **Whiteout** erases an area to white; **Redact** permanently removes the
  content and fills it black
- Undo/redo across every operation

**Pages and documents**
- Continuous scrolling view of the whole document, with a thumbnail sidebar
- Rotate, delete, reorder (drag thumbnails), insert blank pages
- Merge another PDF in, or extract pages out to a new file
- Bookmarks panel, whole-document search with match-case / whole-word options
- Watermarks, page numbers, document properties
- Create new PDFs (A4 / Letter / Legal)
- Save with AES-256 password protection, or save an optimised (smaller) copy
- Print, export a page as an image, export all text
- Opens password-protected files; drag and drop a PDF onto the window

## Getting the app

### Option A — download a prebuilt executable

Every push builds all three platforms. On GitHub go to
**Actions → "Build PDF Studio executables" → the latest run → Artifacts**, and
download `PDFStudio-Windows` (or `-macOS` / `-Linux`). Unzip it and run
`PDFStudio.exe` — no installation, no dependencies.

Windows shows a SmartScreen warning for unsigned apps the first time:
choose **More info → Run anyway**.

### Option B — build it yourself

1. Install Python 3.10–3.12 from [python.org](https://www.python.org/downloads/)
   (tick **"Add python.exe to PATH"**).
2. Double-click **`build.bat`** (Windows) or run **`./build.sh`** (Linux/macOS).
3. The executable appears in **`dist/`**.

### Option C — run from source

```bash
pip install -r requirements.txt
python main.py [file.pdf]
```

## Keyboard shortcuts

| Keys | Action |
|---|---|
| Ctrl+O / Ctrl+S / Ctrl+Shift+S | Open / Save / Save As |
| Ctrl+Z / Ctrl+Shift+Z | Undo / Redo |
| Ctrl+F / F3 / Shift+F3 | Find / next / previous |
| Ctrl+B / Ctrl+I | Bold / italic while editing text |
| Esc | Finish editing a text block |
| Ctrl+← / Ctrl+→ | Move the caret a word at a time |
| Ctrl+A | Select all (in the text block, or the page's text) |
| PgUp / PgDown, Ctrl+Home / Ctrl+End | Page navigation |
| Ctrl++ / Ctrl+- / Ctrl+0 | Zoom in / out / 100% |
| Ctrl+1 / Ctrl+2 | Fit width / fit page |
| Ctrl+scroll | Zoom around the pointer |
| Space+drag, or middle-drag | Pan |
| Del | Delete the selected object |
| Ctrl+M / Ctrl+P | Insert-merge a PDF / Print |
| F9 / F10 | Toggle sidebar / properties panel |

## How it works

The parts that make a PDF editor an *editor* are written from scratch here:

| Module | Responsibility |
|---|---|
| `textengine.py` | Character model, word-wrap layout, caret, selection, editing operations |
| `fonts.py` | Font resolution, exact glyph measurement, embedded-font extraction and re-embedding |
| `canvas.py` | Continuous page canvas, all direct manipulation and live text rendering |
| `document.py` | Document model, undo/redo, and the commit path back into the PDF |
| `panels.py` / `theme.py` / `icons.py` | Sidebar, inspector, dark theme, runtime-drawn icons |

Editing text works by rebuilding the structure a PDF throws away. Characters
are extracted with their individual bounding boxes and styles, laid out again
with the real glyph advances of the original font, edited like an ordinary text
field, then written back: the original glyphs are erased with a text-only
redaction and the new layout is drawn in the same typeface at the same size and
colour.

The only third-party runtime pieces are Qt (the windowing toolkit) and MuPDF
(the PDF parser/rasteriser) — the equivalent of the operating system for this
kind of app. No PDF-editing library is doing the work.

## Tests

```bash
python tests/test_document.py                        # document engine
python tests/test_textengine.py                      # layout / caret / commit fidelity
QT_QPA_PLATFORM=offscreen python tests/test_gui.py   # GUI with synthesized input
```

The GUI test drives the real window with synthesized mouse and keyboard events:
clicking into text, typing, dragging a text block, drawing and resizing shapes,
highlighting, searching and navigating. All three suites run in CI on every
platform before the executable is built.

## Limitations worth knowing

- Re-typed text is laid out by this application, not by whatever produced the
  original PDF. Heavily designed pages (multi-column, tight kerning, justified
  text) can shift slightly. Corrections, rewrites and retitling are reliable;
  reflowing a magazine layout is not.
- If a paragraph grows, following lines move down and may overlap content
  beneath. That is inherent to editing text in a fixed-layout format.
- Whiteout and redaction are permanent once saved — that is the point — but
  undo works right up until you save.
- Form filling and digital signatures are not implemented. You can place a
  signature *image* with the Image tool.

## Licence

AGPL-3.0, required because it links MuPDF (PyMuPDF). The app is free to use
and share, and its source stays available — it is in this repository.
