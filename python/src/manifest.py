"""Stage 9a: delivery manifest generation (JSON + HTML).

Reports what actually shipped in delivery/, grouped and numbered because a
manifest IS a real sequential inventory (unlike a stats panel) — numbering
here encodes real information for whoever is checking the box against the
folder. See docs/architecture-decision.md §11.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from render import page_shell, badge, esc, stat_block


def _delivery_status(asset: dict[str, Any]) -> str:
    fs = asset.get("final_status")
    if fs == "approved_auto":
        return "APPROVED (AUTOMATIC)"
    if fs == "approved_reviewed":
        return "REVIEWED / APPROVED"
    if fs == "pending_review":
        return "AWAITING REVIEW"
    return "NOT INCLUDED"


def build_manifest_json(project_name: str, assets: list[dict[str, Any]], delivery_summary: dict[str, Any],
                         manifest_compare: dict[str, Any]) -> dict[str, Any]:
    delivered = [a for a in assets if a.get("final_status") in ("approved_auto", "approved_reviewed", "pending_review")
                 and a.get("delivered_path")]
    warnings = []
    if manifest_compare.get("missing_deliverables"):
        warnings.append(
            f"{len(manifest_compare['missing_deliverables'])} expected deliverable(s) from the project "
            f"manifest were not found among the delivered assets."
        )
    reviewed_count = sum(1 for a in assets if (a.get("review_decision") or {}).get("by") == "human")
    if reviewed_count:
        warnings.append(f"{reviewed_count} asset(s) required a manual human review decision before delivery.")
    pending = sum(1 for a in assets if a.get("final_status") == "pending_review")
    if pending:
        warnings.append(f"{pending} asset(s) are still awaiting human review and were staged into REVIEW_REQUIRED/, not a final category.")

    status = "READY"
    if pending or manifest_compare.get("missing_deliverables"):
        status = "READY WITH WARNINGS"
    if not delivered:
        status = "NOT READY"

    return {
        "project": project_name,
        "delivery_status": status,
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "asset_count": len(delivered),
        "categories": delivery_summary.get("categories_created", []),
        "warnings": warnings,
        "assets": [
            {
                "index": i + 1,
                "id": a["id"],
                "filename": a["filename"],
                "delivery_category": a.get("delivery_category"),
                "type": a.get("asset_type"),
                "deliverable_type": (a.get("validation") or {}).get("matched_deliverable"),
                "dimensions": f"{a.get('width')}x{a.get('height')}" if a.get("width") and a.get("height") else None,
                "duration_seconds": a.get("duration_seconds"),
                "size_bytes": a.get("size_bytes"),
                "status": _delivery_status(a),
                "classification": a.get("classification", {}).get("status"),
                "sha256": a.get("sha256"),
            }
            for i, a in enumerate(delivered)
        ],
        "missing_deliverables": manifest_compare.get("missing_deliverables", []),
    }


def build_manifest_html(manifest: dict[str, Any]) -> str:
    status_key = "ok" if manifest["delivery_status"] == "READY" else ("warn" if "WARNING" in manifest["delivery_status"] else "bad")

    rows = "".join(f"""<tr>
      <td class="mono">{a['index']:02d}</td>
      <td><strong>{esc(a['filename'])}</strong><div class="mono" style="color:var(--ink-soft);font-size:11px">{esc(a['sha256'][:16] if a['sha256'] else '')}&hellip;</div></td>
      <td>{esc(a['deliverable_type'] or a['type'])}</td>
      <td class="mono">{esc(a['dimensions'] or ('%.1fs' % a['duration_seconds'] if a['duration_seconds'] else '&mdash;'))}</td>
      <td>{esc(a['delivery_category'])}</td>
      <td>{badge(a['status'], a['status'].split(' ')[0])}</td>
    </tr>""" for a in manifest["assets"]) or '<tr><td colspan="6" class="empty">No assets were included in this delivery.</td></tr>'

    missing_rows = "".join(
        f"<li><strong>{esc(m.get('type'))}</strong> &mdash; expected {esc(m.get('format'))}, {esc(m.get('dimensions'))}</li>"
        for m in manifest["missing_deliverables"]
    )
    missing_section = f"""<section>
      <h2><span class="idx">//</span> Missing Deliverables</h2>
      <ul class="reasons">{missing_rows}</ul>
    </section>""" if missing_rows else ""

    warnings_html = "".join(f"<li>{esc(w)}</li>" for w in manifest["warnings"]) or "<li>None.</li>"

    body = f"""
<header class="masthead">
  <div>
    <div class="eyebrow">Delivery Manifest</div>
    <h1>{esc(manifest['project'])}</h1>
    <div class="sub">{manifest['asset_count']} asset(s) across {len(manifest['categories'])} categor{'y' if len(manifest['categories'])==1 else 'ies'}: {esc(', '.join(manifest['categories']) or '&mdash;')}</div>
  </div>
  <div class="stamp {status_key}">{esc(manifest['delivery_status'])}</div>
</header>
<div class="tick-rule"></div>

<section>
  <h2><span class="idx">01</span> Assets</h2>
  <table><thead><tr><th>#</th><th>File</th><th>Deliverable</th><th>Dimensions / Duration</th><th>Category</th><th>Status</th></tr></thead>
  <tbody>{rows}</tbody></table>
</section>

{missing_section}

<section>
  <h2><span class="idx">02</span> Warnings</h2>
  <ul class="reasons">{warnings_html}</ul>
</section>
"""
    return page_shell(f"Delivery Manifest — {manifest['project']}", "Delivery Manifest", body)


def write_manifest(project_name: str, assets: list[dict[str, Any]], delivery_summary: dict[str, Any],
                    manifest_compare: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    data = build_manifest_json(project_name, assets, delivery_summary, manifest_compare)
    json_path = out_dir / "delivery_manifest.json"
    html_path = out_dir / "delivery_manifest.html"
    json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    html_path.write_text(build_manifest_html(data), encoding="utf-8")
    return json_path, html_path
