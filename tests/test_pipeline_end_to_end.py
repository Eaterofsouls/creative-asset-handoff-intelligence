"""End-to-end tests driving pipeline.py exactly as the n8n Execute Command
nodes do -- via subprocess, asserting on exit codes and file output, not
internal function calls."""
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PIPELINE = REPO_ROOT / "python" / "src" / "pipeline.py"


def run_cli(*args):
    return subprocess.run([sys.executable, str(PIPELINE), *args], capture_output=True, text=True)


def test_full_run_on_messy_project_succeeds(tmp_path, messy_project, examples_dir):
    out_dir = tmp_path / "output"
    result = run_cli(
        "full-run", "--project", str(messy_project),
        "--manifest", str(examples_dir / "project_manifest.json"),
        "--out-dir", str(out_dir), "--mock-ai",
        "--project-name", "Test Run",
    )
    assert result.returncode == 0, result.stderr
    assert (out_dir / "delivery_manifest.json").exists()
    assert (out_dir / "delivery_manifest.html").exists()
    assert (out_dir / "processing_report.html").exists()
    assert (out_dir / "delivery").exists()

    manifest = json.loads((out_dir / "delivery_manifest.json").read_text())
    assert manifest["asset_count"] > 0


def test_full_run_without_manifest_still_succeeds(tmp_path, messy_project):
    out_dir = tmp_path / "output_no_manifest"
    result = run_cli(
        "full-run", "--project", str(messy_project),
        "--out-dir", str(out_dir), "--mock-ai",
    )
    assert result.returncode == 0, result.stderr
    manifest = json.loads((out_dir / "delivery_manifest.json").read_text())
    assert manifest is not None


def test_full_run_with_human_decisions_resolves_review_queue(tmp_path, messy_project, examples_dir):
    out_dir = tmp_path / "output_reviewed"
    result = run_cli(
        "full-run", "--project", str(messy_project),
        "--manifest", str(examples_dir / "project_manifest.json"),
        "--decisions", str(examples_dir / "test_cases" / "human_review_decisions.json"),
        "--out-dir", str(out_dir), "--mock-ai",
    )
    assert result.returncode == 0, result.stderr
    reviewed = json.loads((out_dir / "pipeline_stages" / "05_reviewed.json").read_text())
    n_pending = sum(1 for a in reviewed["assets"] if a.get("final_status") == "pending_review")
    assert n_pending == 0  # every review-queue item in the fixture has an explicit decision


def test_refuses_unsafe_project_path(tmp_path):
    result = run_cli("run-deterministic", "--project", "/etc", "--out", str(tmp_path / "x.json"))
    assert result.returncode == 2


def test_single_bad_file_does_not_crash_whole_run(tmp_path, test_cases_dir):
    out_dir = tmp_path / "out"
    result = run_cli(
        "run-deterministic", "--project", str(test_cases_dir / "corrupted_and_unsupported"),
        "--out", str(out_dir / "assets.json"),
    )
    out_dir.mkdir(exist_ok=True)
    result = run_cli(
        "run-deterministic", "--project", str(test_cases_dir / "corrupted_and_unsupported"),
        "--out", str(out_dir / "assets.json"),
    )
    assert result.returncode == 0, result.stderr
    data = json.loads((out_dir / "assets.json").read_text())
    assert len(data["assets"]) >= 3  # corrupted.jpg, empty.png, project_notes.txt, archive.rar all present
