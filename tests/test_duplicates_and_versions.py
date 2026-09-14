"""Tests: exact/visual duplicate detection and filename-based version clustering."""
from discovery import discover_assets
from metadata import inspect_file, metadata_to_dict
from duplicates import run_all_duplicate_detection
from version_analysis import normalize_stem, build_version_clusters, annotate_clusters
import hashlib


def _build_assets(project_dir):
    assets = []
    for f in discover_assets(project_dir):
        if not f.is_supported:
            continue
        meta = metadata_to_dict(inspect_file(f.absolute_path, f.relpath, f.extension, f.in_source_folder))
        meta["id"] = "a-" + hashlib.sha1(f.relpath.encode()).hexdigest()[:12]
        assets.append(meta)
    return assets


def test_exact_duplicates_detected_across_different_filenames(test_cases_dir):
    assets = _build_assets(test_cases_dir / "exact_duplicates")
    run_all_duplicate_detection(assets)
    by_name = {a["filename"]: a for a in assets}
    assert by_name["asset_a_copy.png"]["exact_duplicate_of"] == [by_name["asset_a.png"]["id"]]


def test_visual_duplicates_do_not_include_exact_duplicates_twice(messy_project):
    assets = _build_assets(messy_project)
    run_all_duplicate_detection(assets)
    by_name = {a["filename"]: a for a in assets}
    logo_new = by_name["logo_new.svg"]  # not raster -> no phash -> no visual dup entries possible
    assert logo_new["visual_duplicate_of"] == []


def test_normalize_stem_groups_version_family():
    assert normalize_stem("final.png") == normalize_stem("final_v2.png")
    assert normalize_stem("final_FINAL.png") == normalize_stem("final.png")


def test_version_clusters_do_not_cross_unrelated_stems(messy_project):
    assets = _build_assets(messy_project)
    run_all_duplicate_detection(assets)
    clusters = build_version_clusters(assets)
    annotate_clusters(assets, clusters)
    by_name = {a["filename"]: a for a in assets}
    assert by_name["final.png"]["version_cluster_id"] == by_name["final_v2.png"]["version_cluster_id"]
    assert by_name["final.png"]["version_cluster_id"] != by_name["lookbook_cover_final.jpg"]["version_cluster_id"]
