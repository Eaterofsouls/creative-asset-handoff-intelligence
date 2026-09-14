"""Stage 6: final-asset classification.

Deterministic, weighted scoring — the AI's confidence is ONE input among
several, never the decision by itself (see docs/architecture-decision.md §7).
"""
from __future__ import annotations

import re
from typing import Any

from config import (
    FINAL_PATTERNS, INTERMEDIATE_PATTERNS,
    SCORE_FINAL_FILENAME, SCORE_MOST_RECENT_IN_FAMILY, SCORE_MATCHES_MANIFEST,
    SCORE_NOT_DUPLICATE, SCORE_AI_CONFIDENCE_WEIGHT,
    PENALTY_EXACT_DUPLICATE, PENALTY_INTERMEDIATE_FILENAME,
    THRESHOLD_LIKELY_FINAL, THRESHOLD_NEEDS_REVIEW_LOW, REVIEW_BAND_MARGIN,
)

_FINAL_RE = re.compile("|".join(FINAL_PATTERNS), re.IGNORECASE)
_INTERMEDIATE_RE = re.compile("|".join(INTERMEDIATE_PATTERNS), re.IGNORECASE)


def _normalize_for_word_match(filename: str) -> str:
    """Python's \\b treats underscores as word characters, so "final" inside
    "final_v2" or "reel_final" would NOT be seen as a whole word by \\bfinal\\b
    (no boundary exists between "l" and "_"). Replacing separators with
    spaces before matching restores the intended "whole token" behavior for
    the realistic, underscore-heavy filenames this pipeline targets."""
    return re.sub(r"[_\-.]+", " ", filename)


def _most_recent_in_family(asset: dict[str, Any], all_assets: list[dict[str, Any]]) -> bool:
    cluster_id = asset.get("version_cluster_id")
    if not cluster_id:
        return False
    family = [a for a in all_assets if a.get("version_cluster_id") == cluster_id]
    if len(family) < 2:
        return False
    newest = max(family, key=lambda a: a.get("modified_at") or "")
    return newest["id"] == asset["id"]


def score_asset(asset: dict[str, Any], all_assets: list[dict[str, Any]]) -> dict[str, Any]:
    reasons: list[str] = []
    score = 0.0
    name = asset["filename"]
    name_normalized = _normalize_for_word_match(name)

    if _FINAL_RE.search(name_normalized):
        score += SCORE_FINAL_FILENAME
        reasons.append(f"filename matches a final-like pattern (+{SCORE_FINAL_FILENAME})")

    if _most_recent_in_family(asset, all_assets):
        score += SCORE_MOST_RECENT_IN_FAMILY
        reasons.append(f"most recently modified file in its version family (+{SCORE_MOST_RECENT_IN_FAMILY})")

    if asset.get("validation", {}).get("matched_deliverable"):
        score += SCORE_MATCHES_MANIFEST
        reasons.append(f"matches an expected deliverable in the project manifest (+{SCORE_MATCHES_MANIFEST})")

    is_exact_dup = bool(asset.get("exact_duplicate_of"))
    if not is_exact_dup:
        score += SCORE_NOT_DUPLICATE
        reasons.append(f"not an exact duplicate of another asset (+{SCORE_NOT_DUPLICATE})")
    else:
        score += PENALTY_EXACT_DUPLICATE
        reasons.append(f"is an exact duplicate of another asset ({PENALTY_EXACT_DUPLICATE})")

    if _INTERMEDIATE_RE.search(name_normalized):
        score += PENALTY_INTERMEDIATE_FILENAME
        reasons.append(f"filename matches an intermediate/draft-like pattern ({PENALTY_INTERMEDIATE_FILENAME})")

    ai = asset.get("ai")
    ai_confidence_used = False
    if ai and ai.get("ai_mode") in ("live", "mock"):
        member = next((m for m in ai.get("members", []) if m.get("asset_id") == asset["id"]), None)
        if member and member.get("likely_role") == "final":
            contribution = SCORE_AI_CONFIDENCE_WEIGHT * member.get("role_confidence", 0)
            score += contribution
            reasons.append(f"AI ({ai['ai_mode']}) rates this member as likely-final, "
                            f"confidence {member.get('role_confidence')} (+{contribution:.3f})")
            ai_confidence_used = True

    score = max(0.0, min(1.0, score))

    if asset.get("in_source_folder") or asset.get("asset_type") == "source_unsupported":
        status = "LIKELY_SOURCE"
    elif not asset.get("inspection_ok", True):
        status = "INVALID"
    elif score >= THRESHOLD_LIKELY_FINAL:
        status = "LIKELY_FINAL"
    elif score >= THRESHOLD_NEEDS_REVIEW_LOW:
        status = "NEEDS_REVIEW"
    elif is_exact_dup:
        status = "DUPLICATE"
    else:
        status = "LIKELY_INTERMEDIATE"

    near_boundary = (
        abs(score - THRESHOLD_LIKELY_FINAL) <= REVIEW_BAND_MARGIN
        or abs(score - THRESHOLD_NEEDS_REVIEW_LOW) <= REVIEW_BAND_MARGIN
    )
    unresolved_cluster = bool(asset.get("version_cluster_id")) and (not ai or ai.get("ai_mode") == "failed")
    requires_review = (
        status == "NEEDS_REVIEW"
        or near_boundary
        or unresolved_cluster
        or (ai is not None and ai.get("ai_mode") == "failed")
        or bool(asset.get("visually_similar_to")) and not ai_confidence_used
    )

    return {
        "status": status,
        "score": round(score, 3),
        "requires_review": bool(requires_review),
        "reasons": reasons,
    }


def classify_all(assets: list[dict[str, Any]]) -> None:
    for a in assets:
        a["classification"] = score_asset(a, assets)
