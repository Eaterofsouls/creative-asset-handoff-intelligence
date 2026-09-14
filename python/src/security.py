"""Path-safety helpers.

Everything here exists because the pipeline accepts a directory path from a
caller (ultimately from an n8n Set node / form field) and must never let
that path escape the intended project root, follow a symlink out of it, or
be used to execute arbitrary files. See docs/security.md.
"""
from __future__ import annotations

import os
from pathlib import Path


class UnsafePathError(ValueError):
    pass


def resolve_within(root: str | Path, candidate: str | Path) -> Path:
    """Resolve `candidate` and guarantee it is inside `root`.

    Raises UnsafePathError on any attempt to traverse outside root
    (e.g. via `..`, absolute paths pointing elsewhere, or symlinks).
    """
    root_resolved = Path(root).expanduser().resolve()
    candidate_resolved = (root_resolved / candidate).resolve() if not Path(candidate).is_absolute() \
        else Path(candidate).expanduser().resolve()

    try:
        candidate_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise UnsafePathError(
            f"Path '{candidate}' resolves outside of allowed root '{root_resolved}'"
        ) from exc
    return candidate_resolved


def validate_project_root(path: str | Path) -> Path:
    """Validate that a project root exists, is a directory, and is not a
    sensitive system path. Used at the entry point of every CLI command
    that accepts a --project argument."""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise UnsafePathError(f"Project path does not exist: {p}")
    if not p.is_dir():
        raise UnsafePathError(f"Project path is not a directory: {p}")

    disallowed_roots = {Path("/"), Path("/etc"), Path("/root"), Path("/var"), Path("/usr"), Path("/bin"), Path("/sbin")}
    if p in disallowed_roots:
        raise UnsafePathError(f"Refusing to operate directly on system path: {p}")
    return p


def safe_relpath(path: str | Path, root: str | Path) -> str:
    """POSIX-style relative path for JSON output (never leak absolute host paths)."""
    return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
