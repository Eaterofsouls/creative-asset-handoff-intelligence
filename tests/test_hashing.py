"""Tests: exact hashing determinism + perceptual hash distance behavior."""
from hashing import sha256_of_file, perceptual_hash_of_image, hamming_distance


def test_sha256_identical_for_byte_identical_files(test_cases_dir):
    d = test_cases_dir / "exact_duplicates"
    h1 = sha256_of_file(d / "asset_a.png")
    h2 = sha256_of_file(d / "asset_a_copy.png")
    assert h1 == h2
    assert len(h1) == 64


def test_sha256_differs_for_different_content(messy_project):
    h1 = sha256_of_file(messy_project / "final.png")
    h2 = sha256_of_file(messy_project / "final_v2.png")
    assert h1 != h2


def test_perceptual_hash_near_duplicates_close_distance(test_cases_dir):
    d = test_cases_dir / "near_duplicates"
    h1 = perceptual_hash_of_image(d / "creative_v1.png")
    h2 = perceptual_hash_of_image(d / "creative_v2.png")
    h3 = perceptual_hash_of_image(d / "unrelated_creative.png")
    assert h1 is not None and h2 is not None and h3 is not None
    dist_close = hamming_distance(h1, h2)
    dist_far = hamming_distance(h1, h3)
    assert dist_close < dist_far
    assert dist_close <= 28  # VISUALLY_SIMILAR_MAX_DISTANCE


def test_perceptual_hash_none_for_non_raster(messy_project):
    assert perceptual_hash_of_image(messy_project / "logo.svg") is None


def test_hamming_distance_handles_bad_input():
    assert hamming_distance("", "abc") is None
    assert hamming_distance("ab", "abcd") is None
