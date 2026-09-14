"""Stage 4: deterministic version-family clustering.

Groups files whose filenames strip down to the same "creative stem" (e.g.
final.png / final_v2.png / final_FINAL.png -> stem "final"). This runs
before any AI call and is what decides *which* clusters are even worth
sending to the AI sub-workflow (see docs/architecture-decision.md §6).
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from config import VERSION_SUFFIX_PATTERN

_SUFFIX_RE = re.compile(VERSION_SUFFIX_PATTERN, re.IGNORECASE)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def normalize_stem(filename: str) -> str:
    stem = Path(filename).stem.lower()
    prev = None
    # Strip repeated version-like suffixes: "final_final_v2" -> "final_final" -> "final" -> ""
    while prev != stem:
        prev = stem
        stem = _SUFFIX_RE.sub("", stem)
    stem = _NON_ALNUM_RE.sub("_", stem).strip("_")
    return stem or Path(filename).stem.lower()


def build_version_clusters(assets: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Returns {cluster_id: [asset_id, ...]} for every stem shared by 2+ assets
    of the same asset_type in the same parent folder (cross-folder name
    collisions are NOT clustered — a `final.png` in Social/ and one in
    Brand_Assets/ are unrelated creatives that happen to share a common
    generic name).
    """
    groups: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for a in assets:
        if a.get("asset_type") not in ("image", "video"):
            continue
        parent = str(Path(a["relpath"]).parent)
        stem = normalize_stem(a["filename"])
        groups[(parent, a["asset_type"], stem)].append(a["id"])

    clusters: dict[str, list[str]] = {}
    for idx, ((parent, atype, stem), ids) in enumerate(sorted(groups.items())):
        if len(ids) >= 2:
            cluster_id = f"cluster_{idx:03d}_{stem}"
            clusters[cluster_id] = ids
    return clusters


def annotate_clusters(assets: list[dict[str, Any]], clusters: dict[str, list[str]]) -> None:
    by_id = {a["id"]: a for a in assets}
    for a in assets:
        a["version_cluster_id"] = None
    for cluster_id, ids in clusters.items():
        for aid in ids:
            if aid in by_id:
                by_id[aid]["version_cluster_id"] = cluster_id
