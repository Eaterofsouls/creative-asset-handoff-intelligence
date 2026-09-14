"""Stage 1: recursive, safe asset discovery.

Deterministic. No AI, no heuristics beyond "is this extension one we know
how to inspect". Unsupported files are flagged, never silently dropped and
never crash the run.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from config import ALL_KNOWN_EXTENSIONS, SOURCE_FOLDER_NAMES
from security import validate_project_root

# Directories we never walk into (hidden/system/version-control noise)
IGNORED_DIR_NAMES = {".git", ".DS_Store", "__pycache__", ".venv", "node_modules", "$RECYCLE.BIN"}


@dataclass
class DiscoveredFile:
    absolute_path: Path
    relpath: str
    extension: str
    is_supported: bool
    in_source_folder: bool


def _in_source_folder(relpath: str) -> bool:
    parts = {p.lower() for p in Path(relpath).parts[:-1]}
    return bool(parts & SOURCE_FOLDER_NAMES)


def discover_assets(project_root: str | Path) -> list[DiscoveredFile]:
    """Recursively walk project_root and return every regular file found.

    Symlinks are not followed (prevents escaping the project root via a
    crafted symlink). Directories in IGNORED_DIR_NAMES are skipped.
    """
    root = validate_project_root(project_root)
    results: list[DiscoveredFile] = []

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIR_NAMES and not d.startswith(".")]
        for fname in filenames:
            if fname.startswith("."):
                continue
            abs_path = Path(dirpath) / fname
            if abs_path.is_symlink():
                continue
            relpath = abs_path.resolve().relative_to(root).as_posix()
            ext = abs_path.suffix.lower()
            results.append(
                DiscoveredFile(
                    absolute_path=abs_path,
                    relpath=relpath,
                    extension=ext,
                    is_supported=ext in ALL_KNOWN_EXTENSIONS,
                    in_source_folder=_in_source_folder(relpath),
                )
            )
    return sorted(results, key=lambda f: f.relpath)
