"""Tests: AI response schema validation -- the "never trust raw model text" contract."""
from schemas import validate_ai_response, AI_CLUSTER_ANALYSIS_SCHEMA


VALID = {
    "cluster_id": "cluster_001_final",
    "relationship": "likely_version_family",
    "confidence": 0.8,
    "creative_type": "instagram_post",
    "visual_summary": "Three exports of the same square post layout with minor text differences.",
    "reason": "Filenames and layout match; text content differs slightly between exports.",
    "recommended_review": True,
    "members": [
        {"asset_id": "a-1", "likely_role": "final", "role_confidence": 0.7, "differs_visually": False},
    ],
}


def test_valid_response_passes():
    ok, err = validate_ai_response(VALID)
    assert ok is True
    assert err is None


def test_missing_required_field_fails():
    bad = dict(VALID)
    del bad["confidence"]
    ok, err = validate_ai_response(bad)
    assert ok is False
    assert "confidence" in err or err is not None


def test_confidence_out_of_range_fails():
    bad = dict(VALID)
    bad["confidence"] = 1.5
    ok, err = validate_ai_response(bad)
    assert ok is False


def test_invalid_enum_value_fails():
    bad = dict(VALID)
    bad["relationship"] = "definitely_the_same_file"  # model inventing certainty -- must be rejected
    ok, err = validate_ai_response(bad)
    assert ok is False


def test_additional_properties_rejected():
    bad = dict(VALID)
    bad["extra_field_model_hallucinated"] = "oops"
    ok, err = validate_ai_response(bad)
    assert ok is False


def test_malformed_non_dict_response_fails_gracefully():
    ok, err = validate_ai_response("this is just a string, not json")
    assert ok is False
    assert err is not None


def test_empty_members_list_fails():
    bad = dict(VALID)
    bad["members"] = []
    ok, err = validate_ai_response(bad)
    assert ok is False
