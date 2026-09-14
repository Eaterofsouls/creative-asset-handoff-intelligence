"""Shared HTML rendering helpers for the two generated report surfaces
(processing_report.html, delivery_manifest.html).

Design language: a print-production "light table / proof sheet" aesthetic —
deliberately not the generic cream+terracotta or dark+neon defaults. See
python/README.md for the token rationale. This module only formats strings;
it has no business logic.
"""
from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Any

STATUS_COLORS = {
    "LIKELY_FINAL": "ok",
    "approved_auto": "ok",
    "approved_reviewed": "ok",
    "NEEDS_REVIEW": "warn",
    "pending_review": "warn",
    "LIKELY_INTERMEDIATE": "warn",
    "DUPLICATE": "bad",
    "INVALID": "bad",
    "excluded": "bad",
    "excluded_auto": "muted",
    "LIKELY_SOURCE": "muted",
    "UNKNOWN": "muted",
}

BASE_CSS = """
:root{
  --paper:#F1F1EC; --panel:#FBFBF8; --ink:#12171C; --ink-soft:#4B5560;
  --line:#C9CCC3; --ok:#1C7F5C; --ok-bg:#DCEEE4; --warn:#B9791A; --warn-bg:#F6E7CB;
  --bad:#B23A2E; --bad-bg:#F5DAD4; --muted:#767F73; --muted-bg:#E4E4DC;
  --accent:#C77A2E; --mono: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
  --display: "Space Grotesk", ui-sans-serif, system-ui, sans-serif;
  --body: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--body);
  line-height:1.5; background-image:
    linear-gradient(var(--paper) 39px, rgba(0,0,0,0.035) 40px);
  background-size: 100% 40px;}
.wrap{max-width:1080px;margin:0 auto;padding:48px 32px 96px}
header.masthead{display:flex;justify-content:space-between;align-items:flex-start;
  border-bottom:3px solid var(--ink);padding-bottom:20px;margin-bottom:8px;gap:24px;flex-wrap:wrap}
.eyebrow{font-family:var(--mono);text-transform:uppercase;letter-spacing:.14em;
  font-size:12px;color:var(--ink-soft)}
h1{font-family:var(--display);font-weight:700;font-size:34px;letter-spacing:-.01em;margin:6px 0 4px}
.sub{color:var(--ink-soft);font-size:15px;max-width:56ch}
.meta{font-family:var(--mono);font-size:12px;color:var(--ink-soft);text-align:right}
.stamp{border:3px double var(--ink);border-radius:3px;padding:10px 18px;transform:rotate(-3deg);
  font-family:var(--display);font-weight:700;text-transform:uppercase;letter-spacing:.08em;
  font-size:13px;white-space:nowrap;background:var(--panel)}
.stamp.ok{color:var(--ok);border-color:var(--ok)}
.stamp.warn{color:var(--warn);border-color:var(--warn)}
.stamp.bad{color:var(--bad);border-color:var(--bad)}
.stats{display:flex;flex-wrap:wrap;gap:1px;
  background:var(--line);border:1px solid var(--line);margin:28px 0 36px}
.stat{background:var(--panel);padding:16px 18px;flex:1 1 140px;min-width:140px}
.stat .n{font-family:var(--mono);font-size:26px;font-weight:600;display:block}
.stat .l{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--ink-soft)}
section{margin:40px 0}
h2{font-family:var(--display);font-size:19px;letter-spacing:-.005em;
  border-bottom:1px solid var(--line);padding-bottom:8px;margin-bottom:16px;
  display:flex;align-items:baseline;gap:10px}
h2 .idx{font-family:var(--mono);color:var(--accent);font-size:14px}
table{width:100%;border-collapse:collapse;background:var(--panel);font-size:13.5px}
th{text-align:left;font-family:var(--mono);text-transform:uppercase;font-size:10.5px;
  letter-spacing:.06em;color:var(--ink-soft);border-bottom:2px solid var(--ink);
  padding:8px 10px;background:var(--panel)}
td{padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}
tr:hover td{background:#00000006}
.mono{font-family:var(--mono);font-size:12.5px}
.badge{display:inline-block;font-family:var(--mono);font-size:10.5px;font-weight:600;
  text-transform:uppercase;letter-spacing:.05em;padding:2px 8px;border-radius:2px;border:1px solid}
.badge.ok{color:var(--ok);background:var(--ok-bg);border-color:var(--ok)}
.badge.warn{color:var(--warn);background:var(--warn-bg);border-color:var(--warn)}
.badge.bad{color:var(--bad);background:var(--bad-bg);border-color:var(--bad)}
.badge.muted{color:var(--muted);background:var(--muted-bg);border-color:var(--muted)}
.reasons{font-size:12px;color:var(--ink-soft)}
.reasons li{margin:2px 0}
.callout{border-left:3px solid var(--accent);background:var(--panel);padding:12px 16px;
  font-size:13.5px;color:var(--ink-soft)}
.footer-note{margin-top:56px;padding-top:16px;border-top:1px solid var(--line);
  font-family:var(--mono);font-size:11px;color:var(--ink-soft)}
.tick-rule{height:14px;background-image:repeating-linear-gradient(90deg,var(--ink) 0 1px,transparent 1px 12px);
  opacity:.35;margin:4px 0 28px}
.empty{color:var(--ink-soft);font-style:italic;font-size:13px;padding:14px}
"""

FONT_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&'
    'family=IBM+Plex+Mono:wght@400;600&display=swap" rel="stylesheet">'
)


def esc(value: Any) -> str:
    return html.escape(str(value)) if value is not None else ""


def badge(text: str, key: str) -> str:
    css_class = STATUS_COLORS.get(key, "muted")
    return f'<span class="badge {css_class}">{esc(text)}</span>'


def page_shell(title: str, eyebrow: str, body: str, extra_head: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
{FONT_LINK}
<style>{BASE_CSS}{extra_head}</style>
</head>
<body>
<div class="wrap">
{body}
<div class="footer-note">Generated by Creative Asset Handoff Intelligence &middot; {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
&middot; This report is decision support, not an autonomous delivery action. A human retains final approval authority.</div>
</div>
</body>
</html>"""


def stat_block(number: Any, label: str) -> str:
    return f'<div class="stat"><span class="n">{esc(number)}</span><span class="l">{esc(label)}</span></div>'
