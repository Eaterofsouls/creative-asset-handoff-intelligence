"""Stage: deterministic technical validation + optional manifest comparison.

No AI. Pure rules against measured facts (see docs/architecture-decision.md §8).
Must run before classification.py, since classification rewards assets that
matched a manifest deliverable.
"""
from __future__ import annotations

from typing import Any, Optional

from config import (
    IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, MAX_IMAGE_SIZE_BYTES, MAX_VIDEO_SIZE_BYTES,
    ASPECT_RATIO_TOLERANCE,
)


def _parse_dimensions(spec: str) -> Optional[tuple[int, int]]:
    if not spec or "x" not in spec.lower():
        return None
    try:
        w, h = spec.lower().split("x")
        return int(w), int(h)
    except ValueError:
        return None


def _dimensions_match(asset: dict[str, Any], expected: tuple[int, int]) -> bool:
    w, h = asset.get("width"), asset.get("height")
    if w is None or h is None:
        return False
    if (w, h) == expected:
        return True
    exp_ratio = expected[0] / expected[1]
    actual_ratio = w / h if h else 0
    return abs(actual_ratio - exp_ratio) <= ASPECT_RATIO_TOLERANCE


def validate_technical(asset: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []

    if not asset.get("inspection_ok", True):
        issues.append(f"inspection failed: {asset.get('inspection_error', 'unknown error')}")

    ext = asset.get("extension", "")
    size = asset.get("size_bytes", 0)
    if f".{ext}" in IMAGE_EXTENSIONS and size > MAX_IMAGE_SIZE_BYTES:
        issues.append(f"image file unusually large ({size / 1_048_576:.1f} MB > {MAX_IMAGE_SIZE_BYTES / 1_048_576:.0f} MB)")
    if f".{ext}" in VIDEO_EXTENSIONS and size > MAX_VIDEO_SIZE_BYTES:
        issues.append(f"video file unusually large ({size / 1_048_576:.1f} MB > {MAX_VIDEO_SIZE_BYTES / 1_048_576:.0f} MB)")
    if size == 0:
        issues.append("file is zero bytes")

    if asset.get("asset_type") == "image" and ext != "svg" and asset.get("inspection_ok"):
        w, h = asset.get("width"), asset.get("height")
        if not w or not h:
            issues.append("could not determine image dimensions")

    return {"valid": len(issues) == 0, "issues": issues, "matched_deliverable": None}


def compare_to_manifest(assets: list[dict[str, Any]], manifest: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Matches assets to expected deliverables by (format, dimensions).
    Mutates each asset's `validation.matched_deliverable` / issues in place.
    Returns a summary including any MISSING_DELIVERABLE entries."""
    summary = {"manifest_supplied": manifest is not None, "missing_deliverables": [], "matched_count": 0}
    if not manifest:
        return summary

    expected_list = manifest.get("expected_deliverables", [])
    matched_expected_indices: set[int] = set()

    for asset in assets:
        for idx, expected in enumerate(expected_list):
            exp_format = (expected.get("format") or "").lower().lstrip(".")
            exp_dims = _parse_dimensions(expected.get("dimensions", ""))
            if asset.get("extension") != exp_format:
                continue
            if exp_dims and not _dimensions_match(asset, exp_dims):
                continue
            asset["validation"]["matched_deliverable"] = expected.get("type", f"deliverable_{idx}")
            matched_expected_indices.add(idx)
            summary["matched_count"] += 1
            break

    for idx, expected in enumerate(expected_list):
        if idx not in matched_expected_indices:
            summary["missing_deliverables"].append(expected)

    # Flag assets whose extension matches an expected type but dimensions don't -> INVALID DIMENSIONS
    for asset in assets:
        if asset.get("validation", {}).get("matched_deliverable"):
            continue
        exp_format_matches = [e for e in expected_list if (e.get("format") or "").lower().lstrip(".") == asset.get("extension")]
        for expected in exp_format_matches:
            exp_dims = _parse_dimensions(expected.get("dimensions", ""))
            if exp_dims and asset.get("width") and asset.get("height"):
                asset["validation"]["issues"].append(
                    f"format matches expected deliverable '{expected.get('type')}' but dimensions "
                    f"{asset.get('width')}x{asset.get('height')} != expected {expected.get('dimensions')}"
                )
                asset["validation"]["valid"] = False
                break

    return summary


def run_validation(assets: list[dict[str, Any]], manifest: Optional[dict[str, Any]]) -> dict[str, Any]:
    for asset in assets:
        asset["validation"] = validate_technical(asset)
    return compare_to_manifest(assets, manifest)
