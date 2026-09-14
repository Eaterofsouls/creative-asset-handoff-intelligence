"""Stage 7: apply human review decisions on top of automatic classification.

The n8n Form Trigger node collects decisions from a human for every asset
in the review queue; this function is the deterministic merge step shared
by both the live n8n `Execute Command` call and the local demo/test path.
No AI here at all — a human decision is authoritative once given.
"""
from __future__ import annotations

from typing import Any, Optional

VALID_ACTIONS = {"approve", "reject", "mark_final", "mark_duplicate", "exclude", "rename_category"}


def build_review_queue(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The exact set of assets the Human Review form must show."""
    queue = []
    for a in assets:
        if a.get("classification", {}).get("requires_review"):
            queue.append({
                "asset_id": a["id"],
                "filename": a["filename"],
                "relpath": a["relpath"],
                "status": a["classification"]["status"],
                "score": a["classification"]["score"],
                "reasons": a["classification"]["reasons"],
                "duplicate_of": a.get("exact_duplicate_of") or [m["asset_id"] for m in a.get("visual_duplicate_of", [])],
                "version_cluster_id": a.get("version_cluster_id"),
                "ai_summary": (a.get("ai") or {}).get("visual_summary"),
                "ai_mode": (a.get("ai") or {}).get("ai_mode"),
            })
    return queue


def apply_review(assets: list[dict[str, Any]], decisions: Optional[dict[str, dict[str, Any]]]) -> None:
    decisions = decisions or {}
    for a in assets:
        cls = a.get("classification", {})
        decision = decisions.get(a["id"])

        if decision:
            action = decision.get("action")
            if action not in VALID_ACTIONS:
                action = "exclude"  # fail safe: unrecognized action never auto-delivers
            a["review_decision"] = {"action": action, "note": decision.get("note"), "by": "human"}
            if action in ("approve", "mark_final"):
                a["final_status"] = "approved_reviewed"
                if action == "mark_final":
                    a["classification"]["status"] = "LIKELY_FINAL"
            elif action == "rename_category":
                a["final_status"] = "approved_reviewed"
                a["delivery_category_override"] = decision.get("category")
            else:  # reject, mark_duplicate, exclude
                a["final_status"] = "excluded"
                if action == "mark_duplicate":
                    a["classification"]["status"] = "DUPLICATE"
            continue

        a["review_decision"] = None
        if not cls.get("requires_review") and cls.get("status") == "LIKELY_FINAL":
            a["final_status"] = "approved_auto"
        elif cls.get("requires_review"):
            a["final_status"] = "pending_review"
        else:
            a["final_status"] = "excluded_auto"
