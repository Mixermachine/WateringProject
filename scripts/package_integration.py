"""Build an installable zip of the integration.

The archive contains a single top-level ``watering_project/`` folder, so it can be
unzipped straight into ``/config/custom_components/`` on Home Assistant OS.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "custom_components" / "watering_project"
DIST = ROOT / "dist"

SKIP_DIRS = {"__pycache__"}
SKIP_SUFFIXES = {".pyc", ".pyo"}


def version() -> str:
    return json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))["version"]


def iter_files() -> list[Path]:
    files: list[Path] = []
    for path in sorted(SOURCE.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix in SKIP_SUFFIXES:
            continue
        files.append(path)
    return files


def main() -> None:
    DIST.mkdir(exist_ok=True)
    target = DIST / "watering_project.zip"

    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in iter_files():
            archive.write(path, Path("watering_project") / path.relative_to(SOURCE))

    size = target.stat().st_size
    print(f"{target} ({size / 1024:.1f} KiB, version {version()})")


if __name__ == "__main__":
    main()
