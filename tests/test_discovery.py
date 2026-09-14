"""Tests: recursive discovery, unsupported-file flagging, source-folder detection."""
from discovery import discover_assets
from security import UnsafePathError
import pytest


def test_discovers_all_files_recursively(messy_project):
    found = discover_assets(messy_project)
    relpaths = {f.relpath for f in found}
    assert "final.png" in relpaths
    assert "source/campaign_master.psd" in relpaths


def test_flags_source_folder_membership(messy_project):
    found = {f.relpath: f for f in discover_assets(messy_project)}
    assert found["source/campaign_master.psd"].in_source_folder is True
    assert found["final.png"].in_source_folder is False


def test_unsupported_file_is_flagged_not_dropped(test_cases_dir):
    project = test_cases_dir / "corrupted_and_unsupported"
    found = {f.relpath: f for f in discover_assets(project)}
    assert found["project_notes.txt"].is_supported is False
    assert found["archive.rar"].is_supported is False
    # still present in results -- never silently dropped
    assert "project_notes.txt" in found


def test_refuses_nonexistent_project_path(tmp_path):
    with pytest.raises(UnsafePathError):
        discover_assets(tmp_path / "does_not_exist")


def test_refuses_path_traversal_root(tmp_path):
    with pytest.raises(UnsafePathError):
        discover_assets("/etc")
