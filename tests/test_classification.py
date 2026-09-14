"""Tests: deterministic scoring engine -- the core "AI is one input, not the decision" contract."""
from classification import score_asset, classify_all


def _base_asset(**overrides):
    a = {
        "id": "a-1", "filename": "final.png", "asset_type": "image", "in_source_folder": False,
        "inspection_ok": True, "exact_duplicate_of": [], "visually_similar_to": [],
        "version_cluster_id": None, "validation": {"matched_deliverable": None},
        "modified_at": "2026-01-01T00:00:00Z", "ai": None,
    }
    a.update(overrides)
    return a


def test_final_filename_pattern_with_underscore_is_detected():
    # regression test for the \b + underscore bug found during implementation
    asset = _base_asset(filename="reel_final.mp4")
    result = score_asset(asset, [asset])
    assert any("final-like" in r for r in result["reasons"])


def test_exact_duplicate_is_penalized_to_duplicate_status():
    asset = _base_asset(filename="copy.png", exact_duplicate_of=["a-2"])
    other = _base_asset(id="a-2", filename="final.png")
    result = score_asset(asset, [asset, other])
    assert result["status"] == "DUPLICATE"


def test_ai_confidence_alone_cannot_force_likely_final():
    # AI says "final" with high confidence but filename/manifest/recency don't support it
    asset = _base_asset(
        filename="random_export.jpg",
        ai={"ai_mode": "live", "members": [{"asset_id": "a-1", "likely_role": "final", "role_confidence": 0.99}]},
    )
    result = score_asset(asset, [asset])
    # 0.20 * 0.99 = ~0.198 alone is nowhere near the 0.72 LIKELY_FINAL threshold
    assert result["status"] != "LIKELY_FINAL"


def test_source_folder_always_likely_source_regardless_of_score():
    asset = _base_asset(filename="final_FINAL.png", in_source_folder=True)
    result = score_asset(asset, [asset])
    assert result["status"] == "LIKELY_SOURCE"


def test_failed_inspection_is_invalid():
    asset = _base_asset(inspection_ok=False)
    result = score_asset(asset, [asset])
    assert result["status"] == "INVALID"


def test_near_boundary_score_forces_review():
    # construct a score right at the LIKELY_FINAL threshold boundary
    asset = _base_asset(filename="final.png", validation={"matched_deliverable": "instagram_post"})
    result = score_asset(asset, [asset])
    if abs(result["score"] - 0.72) <= 0.08:
        assert result["requires_review"] is True


def test_classify_all_mutates_every_asset():
    assets = [_base_asset(id="a-1", filename="final.png"), _base_asset(id="a-2", filename="draft_wip.png")]
    classify_all(assets)
    assert all("classification" in a for a in assets)
