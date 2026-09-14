#!/usr/bin/env python3
"""Creative Asset Handoff Intelligence — deterministic processing CLI.

This is the component the n8n workflow calls via `Execute Command` (see
n8n/README.md). Each subcommand is a discrete stage so the n8n canvas can
branch, loop, and inject the AI + human-review steps *between* Python
calls rather than Python owning the whole pipeline end-to-end.

`full-run` chains every stage locally and exists for local testing / the
portfolio demo, where no live n8n instance is available to click through
interactively. It is not a replacement for the n8n workflow — see
docs/architecture-decision.md §2 and §10.

Usage:
    python3 pipeline.py run-deterministic --project DIR [--manifest FILE] --out FILE
    python3 pipeline.py ai-analyze --assets FILE --project DIR --out FILE [--mock|--live]
    python3 pipeline.py finalize --assets FILE --out FILE
    python3 pipeline.py review --assets FILE --decisions FILE --out FILE
    python3 pipeline.py deliver --assets FILE --project DIR --delivery-dir DIR --out FILE
    python3 pipeline.py manifest --assets FILE --project-name NAME --delivery-summary FILE --manifest-compare FILE --out-dir DIR
    python3 pipeline.py report --assets FILE --errors FILE --manifest-compare FILE --delivery-summary FILE --project-name NAME --out-dir DIR
    python3 pipeline.py full-run --project DIR [--manifest FILE] --out-dir DIR [--mock-ai] [--decisions FILE]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Optional

from discovery import discover_assets
from metadata import inspect_file, metadata_to_dict
from duplicates import run_all_duplicate_detection
from version_analysis import build_version_clusters, annotate_clusters
from validation import run_validation
from classification import classify_all
from review import apply_review, build_review_queue
from delivery import build_delivery
from manifest import write_manifest
from report import write_report
from security import validate_project_root, UnsafePathError


def _asset_id(relpath: str) -> str:
    return "a-" + hashlib.sha1(relpath.encode("utf-8")).hexdigest()[:12]


def _load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _dump_json(data: Any, path: str | Path) -> None:
    Path(path).write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def _needs_ai(cluster_asset_ids: list[str], by_id: dict[str, dict[str, Any]]) -> bool:
    """A cluster needs an AI opinion unless deterministic evidence already
    fully explains it (every member is byte-identical to another member,
    i.e. the cluster is a trivial duplicate set). See architecture-decision.md §6."""
    hashes = {by_id[i].get("sha256") for i in cluster_asset_ids if by_id[i].get("sha256")}
    return len(hashes) > 1


# ---------------------------------------------------------------------------
# Stage: run-deterministic
# ---------------------------------------------------------------------------
def cmd_run_deterministic(args: argparse.Namespace) -> None:
    project_root = validate_project_root(args.project)
    errors: list[dict[str, Any]] = []

    discovered = discover_assets(project_root)
    assets: list[dict[str, Any]] = []

    for f in discovered:
        if not f.is_supported:
            assets.append({
                "id": _asset_id(f.relpath), "filename": f.absolute_path.name, "relpath": f.relpath,
                "extension": f.extension.lstrip("."), "asset_type": "unsupported", "mime": None,
                "size_bytes": f.absolute_path.stat().st_size if f.absolute_path.exists() else 0,
                "in_source_folder": f.in_source_folder, "inspection_ok": False,
                "inspection_error": "unsupported_format", "sha256": None, "perceptual_hash": None,
                "width": None, "height": None, "duration_seconds": None, "codec": None,
                "container": None, "modified_at": None,
            })
            continue
        try:
            meta = inspect_file(f.absolute_path, f.relpath, f.extension, f.in_source_folder)
            asset = metadata_to_dict(meta)
            asset["id"] = _asset_id(f.relpath)
            if not asset["inspection_ok"]:
                errors.append({"stage": "metadata_extraction", "asset": f.relpath, "message": asset["inspection_error"]})
            assets.append(asset)
        except Exception as exc:  # noqa: BLE001
            errors.append({"stage": "metadata_extraction", "asset": f.relpath, "message": str(exc)})
            assets.append({
                "id": _asset_id(f.relpath), "filename": f.absolute_path.name, "relpath": f.relpath,
                "extension": f.extension.lstrip("."), "asset_type": "unsupported",
                "size_bytes": 0, "in_source_folder": f.in_source_folder, "inspection_ok": False,
                "inspection_error": str(exc)[:300], "sha256": None, "perceptual_hash": None,
                "width": None, "height": None, "duration_seconds": None, "codec": None,
                "container": None, "modified_at": None, "mime": None,
            })

    run_all_duplicate_detection(assets)
    clusters = build_version_clusters(assets)
    annotate_clusters(assets, clusters)

    manifest_data = _load_json(args.manifest) if args.manifest else None
    manifest_compare = run_validation(assets, manifest_data)

    by_id = {a["id"]: a for a in assets}
    clusters_needing_ai = {cid: ids for cid, ids in clusters.items() if _needs_ai(ids, by_id)}
    clusters_trivial = {cid: ids for cid, ids in clusters.items() if cid not in clusters_needing_ai}

    # Trivial (all-exact-duplicate) clusters get a deterministic pseudo-AI record
    # so classification.py can treat them uniformly, clearly labeled ai_mode=deterministic.
    for cid, ids in clusters_trivial.items():
        rep = by_id[ids[0]]
        record = {
            "cluster_id": cid, "relationship": "likely_duplicate_set", "confidence": 1.0,
            "creative_type": "unknown",
            "visual_summary": "All members are byte-identical (SHA-256 match); no AI opinion needed.",
            "reason": "Deterministic: every member of this cluster shares an identical file hash.",
            "recommended_review": False, "ai_mode": "deterministic", "ai_error": None,
            "members": [{"asset_id": i, "likely_role": "duplicate" if i != ids[0] else "final",
                         "role_confidence": 1.0, "differs_visually": False} for i in ids],
        }
        for i in ids:
            by_id[i]["ai"] = record

    out = {
        "project_root": str(project_root),
        "assets": assets,
        "version_clusters": clusters,
        "clusters_needing_ai": clusters_needing_ai,
        "manifest_compare": manifest_compare,
        "errors": errors,
    }
    _dump_json(out, args.out)
    print(f"[run-deterministic] {len(assets)} assets discovered, "
          f"{len(clusters)} version cluster(s) ({len(clusters_needing_ai)} need AI review), "
          f"{len(errors)} error(s). Wrote {args.out}")


# ---------------------------------------------------------------------------
# Stage: ai-analyze
# ---------------------------------------------------------------------------
def cmd_ai_analyze(args: argparse.Namespace) -> None:
    from ai_client import analyze_cluster

    data = _load_json(args.assets)
    assets = data["assets"]
    by_id = {a["id"]: a for a in assets}
    project_root = Path(data["project_root"]) if not args.project else validate_project_root(args.project)
    mode = "mock" if args.mock else ("live" if args.live else "auto")

    analyzed = 0
    for cluster_id, member_ids in data.get("clusters_needing_ai", {}).items():
        members = [by_id[i] for i in member_ids if i in by_id]
        if not members:
            continue
        result = analyze_cluster(cluster_id, members, project_root, mode=mode)
        for i in member_ids:
            if i in by_id:
                by_id[i]["ai"] = result
        analyzed += 1
        if result.get("ai_mode") == "failed":
            data.setdefault("errors", []).append({
                "stage": "ai_analysis", "asset": cluster_id, "message": result.get("ai_error") or "unknown AI error"
            })

    _dump_json(data, args.out)
    print(f"[ai-analyze] analyzed {analyzed} cluster(s). Wrote {args.out}")


# ---------------------------------------------------------------------------
# Stage: finalize (classification)
# ---------------------------------------------------------------------------
def cmd_finalize(args: argparse.Namespace) -> None:
    data = _load_json(args.assets)
    classify_all(data["assets"])
    _dump_json(data, args.out)
    n_review = sum(1 for a in data["assets"] if a.get("classification", {}).get("requires_review"))
    print(f"[finalize] classified {len(data['assets'])} asset(s); {n_review} flagged for human review. Wrote {args.out}")


# ---------------------------------------------------------------------------
# Stage: review-queue (helper: dump what the n8n Form node should render)
# ---------------------------------------------------------------------------
def cmd_review_queue(args: argparse.Namespace) -> None:
    data = _load_json(args.assets)
    queue = build_review_queue(data["assets"])
    _dump_json({"review_queue": queue}, args.out)
    print(f"[review-queue] {len(queue)} item(s) require human review. Wrote {args.out}")


# ---------------------------------------------------------------------------
# Stage: review (apply decisions)
# ---------------------------------------------------------------------------
def cmd_review(args: argparse.Namespace) -> None:
    data = _load_json(args.assets)
    decisions_raw = _load_json(args.decisions) if args.decisions else {}
    decisions = decisions_raw.get("decisions", decisions_raw) if isinstance(decisions_raw, dict) else {}
    apply_review(data["assets"], decisions)
    _dump_json(data, args.out)
    n_auto = sum(1 for a in data["assets"] if a.get("final_status") == "approved_auto")
    n_reviewed = sum(1 for a in data["assets"] if a.get("final_status") == "approved_reviewed")
    n_pending = sum(1 for a in data["assets"] if a.get("final_status") == "pending_review")
    print(f"[review] approved_auto={n_auto} approved_reviewed={n_reviewed} pending_review={n_pending}. Wrote {args.out}")


# ---------------------------------------------------------------------------
# Stage: deliver
# ---------------------------------------------------------------------------
def cmd_deliver(args: argparse.Namespace) -> None:
    data = _load_json(args.assets)
    project_root = validate_project_root(args.project)
    delivery_root = Path(args.delivery_dir).expanduser().resolve()
    delivery_root.mkdir(parents=True, exist_ok=True)
    summary = build_delivery(data["assets"], project_root, delivery_root)
    data["delivery_summary"] = summary
    _dump_json(data, args.out)
    print(f"[deliver] copied {len(summary['copied'])} file(s) into {len(summary['categories_created'])} "
          f"categor{'y' if len(summary['categories_created'])==1 else 'ies'} at {delivery_root}")


# ---------------------------------------------------------------------------
# Stage: manifest
# ---------------------------------------------------------------------------
def cmd_manifest(args: argparse.Namespace) -> None:
    data = _load_json(args.assets)
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path, html_path = write_manifest(
        args.project_name, data["assets"], data.get("delivery_summary", {}),
        data.get("manifest_compare", {}), out_dir,
    )
    print(f"[manifest] wrote {json_path} and {html_path}")


# ---------------------------------------------------------------------------
# Stage: report
# ---------------------------------------------------------------------------
def cmd_report(args: argparse.Namespace) -> None:
    data = _load_json(args.assets)
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    path = write_report(
        data["assets"], data.get("errors", []), data.get("manifest_compare", {}),
        data.get("delivery_summary", {}), args.project_name, out_dir,
    )
    print(f"[report] wrote {path}")


# ---------------------------------------------------------------------------
# full-run: chain everything (local demo / testing convenience)
# ---------------------------------------------------------------------------
def cmd_full_run(args: argparse.Namespace) -> None:
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / "pipeline_stages"
    work.mkdir(exist_ok=True)
    (work / "README.md").write_text(
        "# Pipeline Stage Snapshots\n\n"
        "Each file here is the full asset ledger as it existed after one CLI stage, "
        "in run order. Kept for transparency/debugging -- open 01 through 06 in order "
        "to watch classification, AI analysis, and human review decisions accumulate "
        "onto each asset record. See docs/architecture-decision.md for what each stage does.\n\n"
        "01_deterministic.json  -- discovery + metadata + hashing + duplicates + version clusters + validation\n"
        "02_ai.json             -- + AI cluster analysis (mock or live, see each asset's ai.ai_mode)\n"
        "03_finalized.json      -- + deterministic classification scoring\n"
        "04_review_queue.json   -- the review queue as the n8n Form node would render it\n"
        "05_reviewed.json       -- + human review decisions applied\n"
        "06_delivered.json      -- + delivery copy results (delivery_summary)\n",
        encoding="utf-8",
    )

    ns = argparse.Namespace(project=args.project, manifest=args.manifest, out=str(work / "01_deterministic.json"))
    cmd_run_deterministic(ns)

    ns = argparse.Namespace(assets=str(work / "01_deterministic.json"), project=args.project,
                             out=str(work / "02_ai.json"), mock=args.mock_ai, live=args.live_ai)
    cmd_ai_analyze(ns)

    ns = argparse.Namespace(assets=str(work / "02_ai.json"), out=str(work / "03_finalized.json"))
    cmd_finalize(ns)

    ns = argparse.Namespace(assets=str(work / "03_finalized.json"), out=str(work / "04_review_queue.json"))
    cmd_review_queue(ns)

    ns = argparse.Namespace(assets=str(work / "03_finalized.json"), decisions=args.decisions,
                             out=str(work / "05_reviewed.json"))
    cmd_review(ns)

    delivery_dir = out_dir / "delivery"
    ns = argparse.Namespace(assets=str(work / "05_reviewed.json"), project=args.project,
                             delivery_dir=str(delivery_dir), out=str(work / "06_delivered.json"))
    cmd_deliver(ns)

    project_name = args.project_name or Path(args.project).name
    ns = argparse.Namespace(assets=str(work / "06_delivered.json"), project_name=project_name, out_dir=str(out_dir))
    cmd_manifest(ns)
    cmd_report(ns)

    print(f"\n[full-run] complete. See {out_dir}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Creative Asset Handoff Intelligence — deterministic pipeline")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("run-deterministic")
    s.add_argument("--project", required=True)
    s.add_argument("--manifest")
    s.add_argument("--out", required=True)
    s.set_defaults(func=cmd_run_deterministic)

    s = sub.add_parser("ai-analyze")
    s.add_argument("--assets", required=True)
    s.add_argument("--project")
    s.add_argument("--out", required=True)
    s.add_argument("--mock", action="store_true")
    s.add_argument("--live", action="store_true")
    s.set_defaults(func=cmd_ai_analyze)

    s = sub.add_parser("finalize")
    s.add_argument("--assets", required=True)
    s.add_argument("--out", required=True)
    s.set_defaults(func=cmd_finalize)

    s = sub.add_parser("review-queue")
    s.add_argument("--assets", required=True)
    s.add_argument("--out", required=True)
    s.set_defaults(func=cmd_review_queue)

    s = sub.add_parser("review")
    s.add_argument("--assets", required=True)
    s.add_argument("--decisions")
    s.add_argument("--out", required=True)
    s.set_defaults(func=cmd_review)

    s = sub.add_parser("deliver")
    s.add_argument("--assets", required=True)
    s.add_argument("--project", required=True)
    s.add_argument("--delivery-dir", required=True)
    s.add_argument("--out", required=True)
    s.set_defaults(func=cmd_deliver)

    s = sub.add_parser("manifest")
    s.add_argument("--assets", required=True)
    s.add_argument("--project-name", required=True)
    s.add_argument("--out-dir", required=True)
    s.set_defaults(func=cmd_manifest)

    s = sub.add_parser("report")
    s.add_argument("--assets", required=True)
    s.add_argument("--project-name", required=True)
    s.add_argument("--out-dir", required=True)
    s.set_defaults(func=cmd_report)

    s = sub.add_parser("full-run")
    s.add_argument("--project", required=True)
    s.add_argument("--manifest")
    s.add_argument("--out-dir", required=True)
    s.add_argument("--project-name")
    s.add_argument("--mock-ai", action="store_true")
    s.add_argument("--live-ai", action="store_true")
    s.add_argument("--decisions")
    s.set_defaults(func=cmd_full_run)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
        return 0
    except UnsafePathError as exc:
        print(f"[security] refused: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"[error] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
