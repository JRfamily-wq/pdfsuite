#!/usr/bin/env python3
"""Regenerate requirements.lock with exact versions and SHA-256 hashes.

Run this only when you deliberately want to move to a newer dependency
version. Review what changed before committing the result — the whole point
of the lock file is that dependency updates are a conscious, reviewable act
rather than something that happens silently on the next build.

    python tools/lock_requirements.py                 # re-pin current versions
    python tools/lock_requirements.py --latest        # move to newest releases

The full dependency tree is three packages. PyMuPDF bundles MuPDF and pulls
in nothing else; PySide6-Essentials needs only shiboken6. If that ever stops
being true this script will say so rather than quietly under-pinning.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

# name on PyPI -> name as written in the requirements file
PACKAGES = {
    "pymupdf": "PyMuPDF",
    "pyside6-essentials": "PySide6-Essentials",
    "shiboken6": "shiboken6",
}

PINNED = {"pymupdf": "1.28.2", "pyside6-essentials": "6.11.1", "shiboken6": "6.11.1"}

HEADER = """\
# Cryptographically pinned dependencies — DO NOT EDIT BY HAND.
#
# Regenerate with:  python tools/lock_requirements.py
#
# Every dependency is pinned to an exact version and to the SHA-256 of each
# distribution file that version publishes. Installed with --require-hashes,
# pip refuses to continue if a file differs by a single byte from what is
# recorded here, so a hijacked maintainer account, a poisoned mirror or a
# tampered CDN fails the build loudly instead of being baked silently into
# the executable.
#
# Always install with BOTH flags:
#     pip install --require-hashes --only-binary :all: -r requirements.lock
#
# --only-binary matters: without it, a rejected wheel makes pip fall back to
# the source distribution, which downloads and compiles MuPDF at build time
# and widens the attack surface considerably.
#
# This is the complete tree — three packages, no further dependencies.
"""


def fetch(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.load(response)


def latest_version(pkg: str) -> str:
    return fetch(f"https://pypi.org/pypi/{pkg}/json")["info"]["version"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--latest", action="store_true",
                        help="pin to the newest release instead of the tested versions")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent.parent
                                             / "requirements.lock"))
    args = parser.parse_args()

    chunks = [HEADER]
    for pkg, display in PACKAGES.items():
        version = latest_version(pkg) if args.latest else PINNED[pkg]
        data = fetch(f"https://pypi.org/pypi/{pkg}/{version}/json")

        requires = data["info"].get("requires_dist") or []
        unexpected = [r for r in requires
                      if r.split()[0].split("[")[0].lower().replace("_", "-")
                      not in PACKAGES and "extra ==" not in r]
        if unexpected:
            print(f"WARNING: {display} {version} declares dependencies this lock "
                  f"does not cover: {unexpected}", file=sys.stderr)

        digests = sorted({f["digests"]["sha256"] for f in data["urls"]})
        if not digests:
            print(f"ERROR: no distribution files for {display} {version}", file=sys.stderr)
            return 1
        chunks.append(f"\n{display}=={version} \\\n" +
                      " \\\n".join(f"    --hash=sha256:{d}" for d in digests))
        print(f"{display}=={version}: {len(digests)} hashes")

    Path(args.out).write_text("\n".join(chunks) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
