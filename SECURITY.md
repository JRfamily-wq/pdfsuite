# Security notes

Written for a security or IT review before deploying PDF Studio internally.

## What the application talks to

**Nothing.** PDF Studio has no networking code of any kind. There are no
imports of `socket`, `urllib`, `http`, `requests` or any HTTP client anywhere
in the source, no telemetry, no update check, no licence check, and no
account. Qt's networking module is explicitly excluded from the build
(`pdfstudio.spec` → `excludes`), so the network stack is not even present in
the shipped binary.

This is verifiable rather than a promise:

```bash
# no networking code in the source
grep -rE "import (socket|urllib|http|requests|ftplib|smtplib)" pdfstudio/

# run it with its network stack physically removed — it works normally
unshare -n ./dist/PDFStudio some.pdf
```

Files are read and written only where the user points a file dialog.

## What is inside the executable

The build produces a single self-contained file. Everything it needs is sealed
inside it — there is no installer, no runtime download, and no dependency on
Python or any library being present on the target machine. An air-gapped
workstation runs it fine.

The bundle contains the Qt GUI libraries, the MuPDF rendering engine, and the
application code. You can list the exact contents of a build:

```python
from PyInstaller.archive.readers import CArchiveReader
for entry in CArchiveReader("dist/PDFStudio").toc:
    print(entry)
```

## Dependency surface

The complete third-party tree is **three packages**:

| Package | Purpose | Licence |
|---|---|---|
| PyMuPDF | Parses and rasterises PDF files (bundles MuPDF) | AGPL-3.0 |
| PySide6-Essentials | Qt GUI toolkit bindings | LGPL-3.0 |
| shiboken6 | Binding runtime required by PySide6 | LGPL-3.0 |

There are no other transitive dependencies. For comparison, this is a very
small surface for a desktop application of this scope.

Everything else — the text layout and editing engine, caret and selection
model, font resolution and re-embedding, the page canvas, theme and icons —
is first-party code in this repository (~4,800 lines).

## Supply chain controls

**Dependencies are pinned by cryptographic hash.** `requirements.lock` records
an exact version and the SHA-256 of every distribution file. CI installs with:

```
pip install --require-hashes --only-binary :all: -r requirements.lock
```

If a package's contents differ by a single byte from what is recorded — a
hijacked maintainer account, a compromised mirror, a tampered CDN — pip aborts
with *"THESE PACKAGES DO NOT MATCH THE HASHES FROM THE REQUIREMENTS FILE"* and
the build fails. A malicious release cannot be silently pulled into an
executable.

`--only-binary :all:` is not optional. Without it, a rejected wheel makes pip
fall back to the source distribution, which downloads and compiles MuPDF from
the internet at build time — a far larger attack surface.

Upgrading a dependency is therefore a deliberate, reviewable act:
`python tools/lock_requirements.py --latest`, then review and commit the diff.

**Known vulnerabilities are checked on every push.** A separate CI job runs
`pip-audit` against the pinned versions using the Python Advisory Database, in
an isolated job so the auditing tool's own dependencies never touch the
environment the shipped binary is built from.

**Builds are checksummed.** Each CI run publishes `SHA256SUMS.txt` alongside
the executable so a downloaded binary can be verified against what CI produced.

## Threat model notes

The main risk in any PDF application is a **malicious PDF file**, not the
supply chain — crafted PDFs are a long-standing malware delivery vector.
Parsing is handled by MuPDF, which has two decades of fuzzing and CVE
hardening behind it. This is a deliberate choice: a hand-written PDF parser
would be significantly more vulnerable, not less, however appealing "no
dependencies" sounds. Keep the pinned MuPDF version current — that is what the
`pip-audit` job is for.

Residual items a reviewer should weigh:

- **The executable is unsigned.** Windows SmartScreen warns on first run. For
  fleet deployment, sign it with your organisation's code-signing certificate,
  or distribute it through your software portal.
- **PyMuPDF is AGPL-3.0.** Internal use inside a company is fine. If you
  distribute the application outside the organisation, the AGPL's source
  availability obligations apply. If that is a problem, the PDF engine would
  need replacing with a permissively licensed one (PDFium is the usual
  candidate) or a commercial MuPDF licence obtained from Artifex.
- **Redaction is real but final.** The redact and whiteout tools remove the
  underlying content from the file rather than drawing a black box over it, so
  redacted text cannot be recovered by copy-paste or text extraction. Verify
  the saved output before circulating a redacted document, as you would with
  any tool.

## Reporting a problem

Open an issue in this repository, or contact the repository owner directly for
anything sensitive.
