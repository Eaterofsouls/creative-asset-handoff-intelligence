"""Tests: metadata extraction across image/video/svg/corrupted/zero-byte files."""
from pathlib import Path
from metadata import inspect_file


def test_png_dimensions_extracted(messy_project):
    p = messy_project / "final.png"
    meta = inspect_file(p, "final.png", ".png", False)
    assert meta.width == 1080 and meta.height == 1080
    assert meta.inspection_ok is True
    assert meta.sha256 is not None
    assert meta.perceptual_hash is not None


def test_svg_dimensions_extracted_without_raster_decode(messy_project):
    p = messy_project / "logo.svg"
    meta = inspect_file(p, "logo.svg", ".svg", False)
    assert meta.width == 512 and meta.height == 512
    assert meta.perceptual_hash is None  # SVG is not raster-hashed


def test_video_metadata_via_ffprobe(messy_project):
    p = messy_project / "reel_final.mp4"
    meta = inspect_file(p, "reel_final.mp4", ".mp4", False)
    assert meta.inspection_ok is True
    assert meta.width == 1080 and meta.height == 1920
    assert meta.duration_seconds is not None and meta.duration_seconds > 0
    assert meta.codec is not None


def test_corrupted_image_flagged_not_crashed(test_cases_dir):
    p = test_cases_dir / "corrupted_and_unsupported" / "corrupted.jpg"
    meta = inspect_file(p, "corrupted.jpg", ".jpg", False)
    assert meta.inspection_ok is False
    assert meta.inspection_error is not None


def test_zero_byte_file_flagged_not_crashed(test_cases_dir):
    p = test_cases_dir / "corrupted_and_unsupported" / "empty.png"
    meta = inspect_file(p, "empty.png", ".png", False)
    assert meta.inspection_ok is False


def test_proprietary_format_gets_limited_metadata_not_crash(messy_project):
    p = messy_project / "source" / "campaign_master.psd"
    meta = inspect_file(p, "source/campaign_master.psd", ".psd", True)
    assert meta.asset_type == "source_unsupported"
    assert meta.sha256 is not None  # file-level facts still captured
    assert meta.inspection_error == "proprietary_format_metadata_limited"
