# PDF Studio

A free, open-source desktop PDF editor — an "Acrobat Pro lite" you can build
into a single executable. View, annotate, edit, organize, merge, redact,
watermark, encrypt and print PDFs. No subscriptions, no accounts, no uploads —
everything runs locally.

Built with [PySide6](https://doc.qt.io/qtforpython-6/) (Qt) and
[PyMuPDF](https://pymupdf.readthedocs.io/).

![Screenshot](docs/screenshot.png)

## Features

**Viewing & navigation**
- Open any PDF, including password-protected files
- Page thumbnails sidebar, zoom (Ctrl+scroll), fit width / fit page
- Full-text search (Ctrl+F) with match highlighting across pages
- Print, export a page as PNG, copy page text

**Editing & annotation**
- **Add text** boxes anywhere (choose font size and color)
- **Edit existing text** — click a paragraph, retype it in place
- Highlight, rectangles, ellipses, lines, arrows, freehand drawing
- Sticky notes and image stamps (place a signature image, logo, photo…)
- **Whiteout** — erase content and cover the area in white
- **Redact** — permanently remove content, filled black
- Select any annotation and delete it (Del)
- Undo / redo for every operation

**Page management**
- Rotate, delete, reorder pages (drag thumbnails or use the menu)
- Insert blank pages, merge/insert another PDF, extract pages to a new PDF
- Add page numbers and diagonal watermarks

**Documents**
- Create new blank PDFs (A4 / Letter / Legal)
- Save with AES-256 password protection
- Save an optimized (compressed) copy
- Edit document properties (title, author, subject, keywords)

## Getting the executable

### Option A — build it on your machine (Windows)

1. Install Python 3.10–3.12 from [python.org](https://www.python.org/downloads/)
   (tick **"Add python.exe to PATH"** in the installer).
2. Double-click **`build.bat`** in this folder.
3. When it finishes, your standalone app is **`dist\PDFStudio.exe`** —
   copy it anywhere, no installation needed.

On Linux/macOS run `./build.sh` instead; the executable lands in `dist/PDFStudio`.

### Option B — download from GitHub Actions

Every push builds Windows, macOS and Linux executables automatically.
On GitHub: **Actions → "Build PDF Studio executables" → latest run →
Artifacts** → download `PDFStudio-Windows` (or `-macOS` / `-Linux`).

### Option C — run from source

```bash
cd pdf-studio
pip install -r requirements.txt
python main.py [optional-file.pdf]
```

## Keyboard shortcuts

| Keys | Action |
|---|---|
| Ctrl+O / Ctrl+S | Open / Save |
| Ctrl+Shift+S | Save As |
| Ctrl+Z / Ctrl+Shift+Z | Undo / Redo |
| Ctrl+F | Find text |
| PgUp / PgDown | Previous / next page |
| Ctrl++ / Ctrl+- / Ctrl+0 | Zoom in / out / 100% |
| Ctrl+1 / Ctrl+2 | Fit width / fit page |
| Ctrl+scroll | Zoom |
| Del | Delete selected annotation |
| Ctrl+M | Insert / merge PDF |
| Ctrl+N / Ctrl+P | New PDF / Print |

## Tests

```bash
python tests/test_document.py                          # engine tests
QT_QPA_PLATFORM=offscreen python tests/test_gui.py     # GUI smoke test
```

## Notes & limitations

- **Edit Text** re-sets the paragraph in Helvetica at the detected size. It's
  great for fixing typos and replacing lines; heavily designed layouts with
  exotic fonts may shift slightly (true font-preserving reflow is something
  even Acrobat only approximates).
- Whiteout/redact are **permanent** once saved — that's the point — but you can
  undo before saving.
- Form-field editing and digital signatures are not in this version. You can
  place a signature *image* with the Insert Image tool.
- The Windows executable is unsigned, so SmartScreen may warn on first run —
  choose "More info → Run anyway".

## License

The application code in this folder is provided under the **AGPL-3.0** — this
is required because it uses PyMuPDF, which is AGPL-licensed. In short: the app
is free to use and share, and its source must stay available (it lives right
here in this repository).
