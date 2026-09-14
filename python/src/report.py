"""Stage 9b: processing_report.html — the full execution report.

Every number here is computed directly from the asset list / error log, not
re-derived from the manifest, so the report and manifest can be cross-
checked against each other. See docs/architecture-decision.md §9, §11.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from render import page_shell, badge, esc, stat_block


def _count(assets: list[dict[str, Any]], pred) -> int:
    return sum(1 for a in assets if pred(a))


def build_report_context(assets: list[dict[str, Any]], errors: list[dict[str, Any]],
                          manifest_compare: dict[str, Any], delivery_summary: dict[str, Any],
                          project_name: str) -> dict[str, Any]:
    total = len(assets)
    supported = _count(assets, lambda a: a.get("asset_type") not in ("unsupported",))
    unsupported = total - supported
    exact_dupes = _count(assets, lambda a: bool(a.get("exact_duplicate_of")))
    visual_dupes = _count(assets, lambda a: bool(a.get("visual_duplicate_of")))
    version_clusters = len({a["version_cluster_id"] for a in assets if a.get("version_cluster_id")})
    validation_failures = _count(assets, lambda a: not (a.get("validation") or {}).get("valid", True))
    ai_analyzed = _count(assets, lambda a: a.get("ai") is not None)
    ai_live = _count(assets, lambda a: (a.get("ai") or {}).get("ai_mode") == "live")
    ai_mock = _count(assets, lambda a: (a.get("ai") or {}).get("ai_mode") == "mock")
    ai_failed = _count(assets, lambda a: (a.get("ai") or {}).get("ai_mode") == "failed")
    human_decisions = _count(assets, lambda a: (a.get("review_decision") or {}).get("by") == "human")
    pending_review = _count(assets, lambda a: a.get("final_status") == "pending_review")
    final_delivered = len(delivery_summary.get("copied", []))
    inspection_failed = _count(assets, lambda a: not a.get("inspection_ok", True))

    by_status: dict[str, int] = {}
    for a in assets:
        s = a.get("classification", {}).get("status", "UNKNOWN")
        by_status[s] = by_status.get(s, 0) + 1

    return {
        "project_name": project_name,
        "total": total, "supported": supported, "unsupported": unsupported,
        "exact_dupes": exact_dupes, "visual_dupes": visual_dupes, "version_clusters": version_clusters,
        "validation_failures": validation_failures, "inspection_failed": inspection_failed,
        "ai_analyzed": ai_analyzed, "ai_live": ai_live, "ai_mock": ai_mock, "ai_failed": ai_failed,
        "human_decisions": human_decisions, "pending_review": pending_review,
        "final_delivered": final_delivered, "by_status": by_status,
        "manifest_supplied": manifest_compare.get("manifest_supplied", False),
        "missing_deliverables": manifest_compare.get("missing_deliverables", []),
        "errors": errors,
    }


def build_report_html(ctx: dict[str, Any], assets: list[dict[str, Any]]) -> str:
    stats = "".join([
        stat_block(ctx["total"], "Files Discovered"),
        stat_block(ctx["supported"], "Supported"),
        stat_block(ctx["unsupported"], "Unsupported / Flagged"),
        stat_block(ctx["exact_dupes"], "Exact Duplicates"),
        stat_block(ctx["visual_dupes"], "Visual Duplicates"),
        stat_block(ctx["version_clusters"], "Version Families"),
        stat_block(ctx["validation_failures"], "Validation Failures"),
        stat_block(ctx["final_delivered"], "Delivered Assets"),
    ])

    status_rows = "".join(
        f'<tr><td>{badge(status, status)}</td><td class="mono">{count}</td></tr>'
        for status, count in sorted(ctx["by_status"].items(), key=lambda kv: -kv[1])
    )

    ai_summary = f"""
    <ul class="reasons">
      <li>{ctx['ai_analyzed']} version cluster member(s) received an AI opinion.</li>
      <li>{ctx['ai_live']} via live model call, {ctx['ai_mock']} via offline mock mode (no ANTHROPIC_API_KEY set), {ctx['ai_failed']} failed schema validation after retry and were routed to human review.</li>
    </ul>""" if ctx["ai_analyzed"] else '<p class="empty">No version clusters required AI analysis in this run &mdash; deterministic evidence was sufficient for every asset.</p>'

    review_summary = f"""
    <ul class="reasons">
      <li>{ctx['human_decisions']} asset(s) received an explicit human decision (approve / reject / mark final / mark duplicate / exclude / recategorize).</li>
      <li>{ctx['pending_review']} asset(s) are still awaiting review and were staged separately rather than delivered.</li>
    </ul>"""

    missing = ctx["missing_deliverables"]
    manifest_section = (
        f'<ul class="reasons">{"".join(f"<li><strong>{esc(m.get(chr(39)+"type"+chr(39)))}</strong> — expected {esc(m.get(chr(39)+"format"+chr(39)))}, {esc(m.get(chr(39)+"dimensions"+chr(39)))}, not found among delivered assets.</li>" for m in missing)}</ul>'
        if ctx["manifest_supplied"] and missing else
        ('<p class="empty">Every expected deliverable in the project manifest was matched to a delivered asset.</p>' if ctx["manifest_supplied"]
         else '<p class="empty">No project manifest was supplied for this run — deliverable-completeness checks were skipped. Technical validation (format, dimensions, integrity) still ran on every asset.</p>')
    )

    error_rows = "".join(
        f"<tr><td class='mono'>{esc(e.get('stage'))}</td><td>{esc(e.get('asset', e.get('context','')))}</td><td>{esc(e.get('message'))}</td></tr>"
        for e in ctx["errors"]
    ) or '<tr><td colspan="3" class="empty">No errors were recorded during this run.</td></tr>'

    inspection_failed_rows = "".join(
        f"<tr><td>{esc(a['filename'])}</td><td class='mono'>{esc(a.get('inspection_error'))}</td></tr>"
        for a in assets if not a.get("inspection_ok", True)
    ) or '<tr><td colspan="2" class="empty">No files failed inspection.</td></tr>'

    body = f"""
<header class="masthead">
  <div>
    <div class="eyebrow">Processing Report</div>
    <h1>{esc(ctx['project_name'])}</h1>
    <div class="sub">Automated cleanup &amp; validation run over the source project folder. Every figure below is computed directly from the asset ledger for this run.</div>
  </div>
  <div class="meta">RUN SUMMARY<br>{ctx['total']} files &middot; {ctx['final_delivered']} delivered</div>
</header>
<div class="tick-rule"></div>

<div class="stats">{stats}</div>

<section>
  <h2><span class="idx">01</span> Classification Breakdown</h2>
  <table><thead><tr><th>Status</th><th>Count</th></tr></thead><tbody>{status_rows}</tbody></table>
</section>

<section>
  <h2><span class="idx">02</span> AI Analysis</h2>
  {ai_summary}
</section>

<section>
  <h2><span class="idx">03</span> Human Review</h2>
  {review_summary}
</section>

<section>
  <h2><span class="idx">04</span> Manifest Comparison</h2>
  {manifest_section}
</section>

<section>
  <h2><span class="idx">05</span> Files That Failed Inspection</h2>
  <table><thead><tr><th>File</th><th>Reason</th></tr></thead><tbody>{inspection_failed_rows}</tbody></table>
</section>

<section>
  <h2><span class="idx">06</span> Errors &amp; Warnings Log</h2>
  <table><thead><tr><th>Stage</th><th>Asset / Context</th><th>Message</th></tr></thead><tbody>{error_rows}</tbody></table>
</section>
"""
    return page_shell(f"Processing Report — {ctx['project_name']}", "Processing Report", body)


def write_report(assets: list[dict[str, Any]], errors: list[dict[str, Any]], manifest_compare: dict[str, Any],
                  delivery_summary: dict[str, Any], project_name: str, out_dir: Path) -> Path:
    ctx = build_report_context(assets, errors, manifest_compare, delivery_summary, project_name)
    html_path = out_dir / "processing_report.html"
    html_path.write_text(build_report_html(ctx, assets), encoding="utf-8")
    (out_dir / "processing_report_context.json").write_text(json.dumps(ctx, indent=2), encoding="utf-8")
    return html_path
