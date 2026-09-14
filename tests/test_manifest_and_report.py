"""Tests: manifest/report JSON+HTML generation produce well-formed, consistent output."""
import json
from manifest import build_manifest_json, build_manifest_html
from report import build_report_context, build_report_html


ASSET = {
    "id": "a-1", "filename": "final.png", "final_status": "approved_auto", "delivered_path": "delivery/Images/final.png",
    "delivery_category": "Images", "asset_type": "image", "width": 1080, "height": 1080, "duration_seconds": None,
    "size_bytes": 5000, "classification": {"status": "LIKELY_FINAL"}, "sha256": "a" * 64,
    "validation": {"matched_deliverable": "instagram_post"}, "review_decision": None,
}


def test_manifest_json_has_expected_shape():
    m = build_manifest_json("Test Project", [ASSET], {"categories_created": ["Images"]}, {"missing_deliverables": []})
    assert m["project"] == "Test Project"
    assert m["asset_count"] == 1
    assert m["assets"][0]["filename"] == "final.png"
    json.dumps(m)  # must be JSON-serializable


def test_manifest_status_ready_with_warnings_when_missing_deliverables():
    m = build_manifest_json("P", [ASSET], {"categories_created": ["Images"]},
                             {"missing_deliverables": [{"type": "x", "format": "png", "dimensions": "1x1"}]})
    assert m["delivery_status"] == "READY WITH WARNINGS"


def test_manifest_not_ready_when_nothing_delivered():
    m = build_manifest_json("P", [], {"categories_created": []}, {"missing_deliverables": []})
    assert m["delivery_status"] == "NOT READY"


def test_manifest_html_renders_without_error():
    m = build_manifest_json("Test Project", [ASSET], {"categories_created": ["Images"]}, {"missing_deliverables": []})
    html = build_manifest_html(m)
    assert "<html" in html and "Test Project" in html


def test_report_context_counts_match_input():
    assets = [ASSET, dict(ASSET, id="a-2", filename="dup.png", exact_duplicate_of=["a-1"])]
    ctx = build_report_context(assets, [], {"manifest_supplied": True, "missing_deliverables": []},
                                {"copied": [{"asset_id": "a-1"}]}, "Test Project")
    assert ctx["total"] == 2
    assert ctx["final_delivered"] == 1


def test_report_html_renders_without_error():
    ctx = build_report_context([ASSET], [], {"manifest_supplied": False, "missing_deliverables": []}, {"copied": []}, "P")
    html = build_report_html(ctx, [ASSET])
    assert "<html" in html and "Processing Report" in html
