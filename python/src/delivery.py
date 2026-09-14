"""Stage 8: build the clean delivery folder.

Copy-only. Never deletes or overwrites the source project. Only creates the
category subfolders that actually end up containing at least one file.
See docs/architecture-decision.md §11.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any


def _category_for(asset: dict[str, Any]) -> str:
    override = asset.get("delivery_category_override")
    if override:
        return override

    name = asset["filename"].lower()
    relpath_lower = asset["relpath"].lower()
    deliverable = (asset.get("validation") or {}).get("matched_deliverable") or ""

    if asset.get("in_source_folder") or asset.get("asset_type") == "source_unsupported":
        return "Source"
    if "logo" in name or "brand" in name or "brand" in deliverable.lower():
        return "Brand_Assets"
    if any(k in deliverable.lower() for k in ("instagram", "social", "reel", "post", "story")) or "social" in relpath_lower:
        return "Social"
    if "web" in deliverable.lower() or "web" in relpath_lower:
        return "Web"
    if asset.get("asset_type") == "video":
        return "Videos"
    if asset.get("asset_type") == "image":
        return "Images"
    return "Images"


def build_delivery(assets: list[dict[str, Any]], project_root: Path, delivery_root: Path) -> dict[str, Any]:
    delivery_root.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []

    for asset in assets:
        status = asset.get("final_status")
        src = project_root / asset["relpath"]
        if not src.exists():
            skipped.append({"asset_id": asset["id"], "reason": "source_file_missing_at_delivery_time"})
            continue

        if status in ("approved_auto", "approved_reviewed"):
            category = _category_for(asset)
        elif status == "pending_review":
            category = "REVIEW_REQUIRED"
        else:
            skipped.append({"asset_id": asset["id"], "reason": f"final_status={status}"})
            continue

        dest_dir = delivery_root / category
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = dest_dir / asset["filename"]
        # avoid silent overwrite if two delivered assets share a filename in the same category
        if dest_path.exists():
            dest_path = dest_dir / f"{Path(asset['filename']).stem}__{asset['id'][:8]}{Path(asset['filename']).suffix}"
        shutil.copy2(src, dest_path)
        asset["delivered_path"] = str(dest_path.relative_to(delivery_root.parent))
        asset["delivery_category"] = category
        copied.append({"asset_id": asset["id"], "category": category, "dest": str(dest_path.name)})

    categories_created = sorted({c["category"] for c in copied})
    return {"copied": copied, "skipped": skipped, "categories_created": categories_created}
