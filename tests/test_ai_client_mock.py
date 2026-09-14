"""Tests: mock AI path (used when ANTHROPIC_API_KEY is unset) always returns
schema-valid, clearly-labeled output -- and the pipeline degrades gracefully
when live analysis is unavailable or fails."""
import os
from ai_client import analyze_cluster, _mock_analysis
from schemas import validate_ai_response


MEMBERS = [
    {"id": "a-1", "filename": "final.png", "relpath": "final.png", "asset_type": "image",
     "width": 1080, "height": 1080, "size_bytes": 1000, "modified_at": "2026-01-01T00:00:00Z",
     "exact_duplicate_of": [], "visually_similar_to": [], "visual_duplicate_of": [], "extension": "png",
     "inspection_ok": True},
    {"id": "a-2", "filename": "final_v2.png", "relpath": "final_v2.png", "asset_type": "image",
     "width": 1080, "height": 1080, "size_bytes": 1010, "modified_at": "2026-01-02T00:00:00Z",
     "exact_duplicate_of": [], "visually_similar_to": [], "visual_duplicate_of": [], "extension": "png",
     "inspection_ok": True},
]


def test_mock_analysis_is_schema_valid():
    result = _mock_analysis("cluster_test", MEMBERS)
    ok, err = validate_ai_response(result)
    assert ok is True, err


def test_analyze_cluster_falls_back_to_mock_without_api_key(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = analyze_cluster("cluster_test", MEMBERS, tmp_path, mode="auto")
    assert result["ai_mode"] == "mock"
    assert result["ai_error"] is None


def test_analyze_cluster_never_raises_on_bad_network(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-test")

    def boom(*args, **kwargs):
        raise ConnectionError("simulated network failure")

    import ai_client
    monkeypatch.setattr(ai_client, "_call_anthropic", boom)
    result = analyze_cluster("cluster_test", MEMBERS, tmp_path, mode="live")
    assert result["ai_mode"] == "failed"
    assert result["ai_error"] is not None
    assert result["recommended_review"] is True  # failure routes to human review, never silently drops


def test_analyze_cluster_retries_then_fails_on_persistent_malformed_output(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key-for-test")

    import ai_client

    def malformed(*args, **kwargs):
        return {"not": "the right shape"}

    monkeypatch.setattr(ai_client, "_call_anthropic", malformed)
    result = analyze_cluster("cluster_test", MEMBERS, tmp_path, mode="live")
    assert result["ai_mode"] == "failed"
