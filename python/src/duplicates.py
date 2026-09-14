"""Stage 3: duplicate detection — exact (hash) + near-duplicate (perceptual).

Two independent, deterministic layers (see docs/architecture-decision.md §5).
Never deletes or picks a winner; only annotates relationships for the
classification stage and the human review queue to use.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from config import VISUAL_DUPLICATE_MAX_DISTANCE, VISUALLY_SIMILAR_MAX_DISTANCE
from hashing import hamming_distance


def find_exact_duplicates(assets: list[dict[str, Any]]) -> None:
    """Mutates assets in place, adding `exact_duplicate_of: [asset_id, ...]`."""
    by_hash: dict[str, list[str]] = defaultdict(list)
    for a in assets:
        if a.get("sha256"):
            by_hash[a["sha256"]].append(a["id"])

    for a in assets:
        a["exact_duplicate_of"] = []
        h = a.get("sha256")
        if h and len(by_hash.get(h, [])) > 1:
            a["exact_duplicate_of"] = [aid for aid in by_hash[h] if aid != a["id"]]


def find_visual_duplicates(assets: list[dict[str, Any]]) -> None:
    """Mutates assets in place, adding `visual_duplicate_of` and
    `visually_similar_to`, each a list of {asset_id, distance}.

    Only compares image assets that carry a perceptual_hash and are not
    already exact duplicates of each other (that relationship is already
    captured, no need to double-report it as "visual").
    """
    images = [a for a in assets if a.get("asset_type") == "image" and a.get("perceptual_hash")]

    for a in assets:
        a["visual_duplicate_of"] = []
        a["visually_similar_to"] = []

    for i, a in enumerate(images):
        for b in images[i + 1:]:
            if b["id"] in a.get("exact_duplicate_of", []):
                continue
            dist = hamming_distance(a["perceptual_hash"], b["perceptual_hash"])
            if dist is None:
                continue
            if dist <= VISUAL_DUPLICATE_MAX_DISTANCE:
                a["visual_duplicate_of"].append({"asset_id": b["id"], "distance": dist})
                b["visual_duplicate_of"].append({"asset_id": a["id"], "distance": dist})
            elif dist <= VISUALLY_SIMILAR_MAX_DISTANCE:
                a["visually_similar_to"].append({"asset_id": b["id"], "distance": dist})
                b["visually_similar_to"].append({"asset_id": a["id"], "distance": dist})


def find_video_possible_duplicates(assets: list[dict[str, Any]]) -> None:
    """Coarser, lower-confidence signal for videos: same duration (±0.5s),
    same resolution, same codec, different hash => POSSIBLE_DUPLICATE.
    Documented explicitly as weaker evidence than image perceptual hashing.
    """
    videos = [a for a in assets if a.get("asset_type") == "video" and a.get("inspection_ok")]
    for a in assets:
        a["possible_duplicate_of"] = []
    for i, a in enumerate(videos):
        for b in videos[i + 1:]:
            if b["id"] in a.get("exact_duplicate_of", []):
                continue
            same_res = a.get("width") == b.get("width") and a.get("height") == b.get("height")
            dur_a, dur_b = a.get("duration_seconds"), b.get("duration_seconds")
            same_dur = dur_a is not None and dur_b is not None and abs(dur_a - dur_b) <= 0.5
            same_codec = a.get("codec") == b.get("codec")
            if same_res and same_dur and same_codec:
                a["possible_duplicate_of"].append(b["id"])
                b["possible_duplicate_of"].append(a["id"])


def run_all_duplicate_detection(assets: list[dict[str, Any]]) -> None:
    find_exact_duplicates(assets)
    find_visual_duplicates(assets)
    find_video_possible_duplicates(assets)
