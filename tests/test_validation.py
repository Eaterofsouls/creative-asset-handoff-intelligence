"""Tests: deterministic technical validation + project manifest comparison."""
from validation import run_validation, validate_technical, _dimensions_match, _parse_dimensions


def test_parse_dimensions():
    assert _parse_dimensions("1080x1920") == (1080, 1920)
    assert _parse_dimensions("") is None
    assert _parse_dimensions("garbage") is None


def test_dimensions_match_exact():
    asset = {"width": 1080, "height": 1080}
    assert _dimensions_match(asset, (1080, 1080)) is True


def test_dimensions_match_within_aspect_tolerance():
    asset = {"width": 1081, "height": 1080}  # same-ish aspect ratio
    assert _dimensions_match(asset, (1080, 1080)) is True


def test_zero_byte_file_is_invalid():
    asset = {"extension": "png", "size_bytes": 0, "inspection_ok": True, "asset_type": "image", "width": 10, "height": 10}
    result = validate_technical(asset)
    assert result["valid"] is False
    assert any("zero bytes" in i for i in result["issues"])


def test_manifest_comparison_flags_missing_deliverable():
    assets = [{"id": "a1", "extension": "png", "width": 100, "height": 100, "size_bytes": 10,
               "inspection_ok": True, "asset_type": "image", "validation": {"valid": True, "issues": [], "matched_deliverable": None}}]
    manifest = {"expected_deliverables": [{"type": "instagram_reel", "format": "mp4", "dimensions": "1080x1920"}]}
    summary = run_validation(assets, manifest)
    assert summary["missing_deliverables"] == manifest["expected_deliverables"]


def test_manifest_comparison_matches_correct_deliverable():
    assets = [{"id": "a1", "extension": "png", "width": 1080, "height": 1080, "size_bytes": 10,
               "inspection_ok": True, "asset_type": "image"}]
    manifest = {"expected_deliverables": [{"type": "instagram_post", "format": "png", "dimensions": "1080x1080"}]}
    run_validation(assets, manifest)
    assert assets[0]["validation"]["matched_deliverable"] == "instagram_post"


def test_runs_without_manifest():
    assets = [{"id": "a1", "extension": "png", "width": 1080, "height": 1080, "size_bytes": 10,
               "inspection_ok": True, "asset_type": "image"}]
    summary = run_validation(assets, None)
    assert summary["manifest_supplied"] is False
    assert assets[0]["validation"]["valid"] is True
