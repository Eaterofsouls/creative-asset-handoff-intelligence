"""Tests: human review merge logic + copy-only delivery packaging."""
from pathlib import Path
from review import apply_review, build_review_queue, VALID_ACTIONS
from delivery import build_delivery


def _asset(**overrides):
    a = {
        "id": "a-1", "filename": "final.png", "relpath": "final.png", "asset_type": "image",
        "in_source_folder": False, "exact_duplicate_of": [], "visual_duplicate_of": [],
        "classification": {"status": "NEEDS_REVIEW", "score": 0.5, "requires_review": True, "reasons": []},
        "validation": {"matched_deliverable": None},
    }
    a.update(overrides)
    return a


def test_review_queue_only_includes_flagged_assets():
    flagged = _asset(id="a-1")
    clear = _asset(id="a-2", classification={"status": "LIKELY_FINAL", "score": 0.9, "requires_review": False, "reasons": []})
    queue = build_review_queue([flagged, clear])
    assert len(queue) == 1 and queue[0]["asset_id"] == "a-1"


def test_apply_review_approve_sets_approved_reviewed():
    asset = _asset()
    apply_review([asset], {"a-1": {"action": "approve"}})
    assert asset["final_status"] == "approved_reviewed"


def test_apply_review_unknown_action_fails_safe_to_exclude():
    asset = _asset()
    apply_review([asset], {"a-1": {"action": "delete_everything"}})  # not a valid action
    assert asset["final_status"] == "excluded"
    assert asset["review_decision"]["action"] == "exclude"


def test_apply_review_no_decision_confident_final_auto_approves():
    asset = _asset(classification={"status": "LIKELY_FINAL", "score": 0.9, "requires_review": False, "reasons": []})
    apply_review([asset], {})
    assert asset["final_status"] == "approved_auto"


def test_apply_review_no_decision_pending_review_stays_pending():
    asset = _asset()
    apply_review([asset], {})
    assert asset["final_status"] == "pending_review"


def test_delivery_never_deletes_or_moves_source(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    src_file = project / "final.png"
    src_file.write_bytes(b"fake png bytes")

    asset = _asset(final_status="approved_auto")
    delivery_root = tmp_path / "delivery"
    build_delivery([asset], project, delivery_root)

    assert src_file.exists()  # source untouched
    assert (delivery_root / "Images" / "final.png").exists()  # copy created


def test_delivery_skips_missing_source_without_crashing(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    asset = _asset(final_status="approved_auto", relpath="does_not_exist.png")
    summary = build_delivery([asset], project, tmp_path / "delivery")
    assert len(summary["skipped"]) == 1


def test_delivery_pending_review_goes_to_review_required_folder(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "final.png").write_bytes(b"data")
    asset = _asset(final_status="pending_review")
    summary = build_delivery([asset], project, tmp_path / "delivery")
    assert "REVIEW_REQUIRED" in summary["categories_created"]
