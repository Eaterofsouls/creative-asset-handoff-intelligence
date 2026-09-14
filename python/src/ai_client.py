"""Stage 5: AI cluster analysis.

Called once per *ambiguous* version cluster (not per asset, not for every
file — see docs/architecture-decision.md §6). This module is the Python-side
equivalent of what the n8n AI sub-workflow does with an HTTP Request node;
it exists here so the full pipeline is runnable and testable end-to-end
without a live n8n instance (docs/architecture-decision.md §10).

Two modes:
  * real  — calls the Anthropic Messages API (vision) if ANTHROPIC_API_KEY
            is set. Provider-agnostic pattern: swap the URL/body mapping to
            point at another vision API without changing the pipeline shape.
  * mock  — deterministic, offline stand-in used for CI/tests/demo when no
            credentials are available. Clearly labeled in every output it
            produces (`"ai_mode": "mock"`), never silently pretends to be
            a real model call.
"""
from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from typing import Any, Optional

from schemas import validate_ai_response

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = "claude-sonnet-4-6"  # see docs/model-selection.md
MAX_RETRIES = 2
REQUEST_TIMEOUT_SECONDS = 30

SYSTEM_PROMPT = """You are an operational asset-management assistant for a creative agency \
delivery pipeline. You will be shown a group of files that a deterministic filename-matching \
step flagged as a possible "version family" (the same creative exported or revised multiple \
times), plus their technical metadata.

Your job is ONLY to reason about:
- whether these files likely represent versions of the same creative, a set of duplicates, \
or unrelated files that happen to share a similar name
- which file, if any, looks like the final/delivery-ready version vs. an intermediate/draft/source file
- the general creative type (e.g. instagram_post, logo, reel_cover, banner, print_asset, unknown)
- a short, neutral visual summary (subject/layout only)
- whether any pair of members appears visually different despite the similar filename

You must NOT:
- comment on artistic/design quality
- claim certainty — always return a confidence between 0 and 1
- invent members not given to you

Respond with ONLY a single JSON object, no markdown fences, no prose, matching exactly this \
shape (all fields required):
{
  "cluster_id": string,
  "relationship": "likely_version_family" | "likely_duplicate_set" | "unrelated_similar" | "unclear",
  "confidence": number 0-1,
  "creative_type": string,
  "visual_summary": string (<=400 chars, neutral, no quality judgement),
  "reason": string (<=400 chars),
  "recommended_review": boolean,
  "members": [
    {"asset_id": string, "likely_role": "final"|"intermediate"|"source"|"duplicate"|"unknown",
     "role_confidence": number 0-1, "differs_visually": boolean}
  ]
}"""


def _build_user_payload(cluster_id: str, members: list[dict[str, Any]]) -> str:
    slim = [
        {
            "asset_id": m["id"],
            "filename": m["filename"],
            "relpath": m["relpath"],
            "asset_type": m["asset_type"],
            "width": m.get("width"),
            "height": m.get("height"),
            "size_bytes": m.get("size_bytes"),
            "modified_at": m.get("modified_at"),
            "is_exact_duplicate_of_another_member": bool(m.get("exact_duplicate_of")),
            "visual_similarity_notes": m.get("visually_similar_to", []) + m.get("visual_duplicate_of", []),
        }
        for m in members
    ]
    return json.dumps({"cluster_id": cluster_id, "members": slim}, indent=2)


def _encodable_images(members: list[dict[str, Any]], project_root: Path, max_images: int = 4) -> list[dict[str, str]]:
    """Base64-encode up to `max_images` member images for the vision call.
    Skips SVG (not a raster format the Messages API accepts as an image
    block) and anything that failed inspection."""
    blocks = []
    for m in members:
        if len(blocks) >= max_images:
            break
        if m.get("asset_type") != "image" or m.get("extension") == "svg" or not m.get("inspection_ok", True):
            continue
        fpath = project_root / m["relpath"]
        try:
            data = fpath.read_bytes()
        except OSError:
            continue
        media_type = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                      "webp": "image/webp", "tif": "image/tiff", "tiff": "image/tiff"}.get(m.get("extension"), "image/png")
        blocks.append({"asset_id": m["id"], "media_type": media_type, "data": base64.b64encode(data).decode("ascii")})
    return blocks


def _call_anthropic(api_key: str, cluster_id: str, members: list[dict[str, Any]], project_root: Path,
                     retry_hint: str = "") -> dict[str, Any]:
    import urllib.request
    import urllib.error

    content: list[dict[str, Any]] = [{"type": "text", "text": _build_user_payload(cluster_id, members) + retry_hint}]
    for img in _encodable_images(members, project_root):
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": img["media_type"], "data": img["data"]},
        })

    body = json.dumps({
        "model": ANTHROPIC_MODEL,
        "max_tokens": 1024,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": content}],
    }).encode("utf-8")

    req = urllib.request.Request(
        ANTHROPIC_API_URL, data=body, method="POST",
        headers={"content-type": "application/json", "x-api-key": api_key, "anthropic-version": "2023-06-01"},
    )
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
        raw = json.loads(resp.read())
    text = "".join(block.get("text", "") for block in raw.get("content", []) if block.get("type") == "text")
    return json.loads(text)


def _mock_analysis(cluster_id: str, members: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic, rule-based stand-in for the model, used when
    ANTHROPIC_API_KEY is unset. Mirrors the *shape* of a real response and
    applies simple, explainable heuristics so demo output is meaningful
    rather than random. Always labeled ai_mode=mock downstream."""
    import re as _re

    def role_for(m: dict[str, Any]) -> tuple[str, float]:
        # See classification._normalize_for_word_match: underscores/hyphens
        # block \b, so normalize separators to spaces before whole-word matching.
        name = _re.sub(r"[_\-.]+", " ", m["filename"].lower())
        if m.get("exact_duplicate_of"):
            return "duplicate", 0.9
        if _re.search(r"final final|approved|delivered", name):
            return "final", 0.78
        if _re.search(r"\bfinal\b|\blatest\b", name):
            return "final", 0.68
        if _re.search(r"\bdraft\b|\bwip\b|\bold\b|\btemp\b|\bv0*1\b", name):
            return "intermediate", 0.7
        return "unknown", 0.5

    members_out = []
    for m in members:
        role, conf = role_for(m)
        members_out.append({
            "asset_id": m["id"], "likely_role": role, "role_confidence": round(conf, 2),
            "differs_visually": bool(m.get("visually_similar_to")) and not bool(m.get("visual_duplicate_of")),
        })

    # Note: by construction (see pipeline.py `_needs_ai`), any cluster reaching
    # this function already has more than one distinct file hash among its
    # members, so it is a *mixed* cluster (never a pure duplicate set — those
    # are resolved deterministically upstream without an AI call). It may
    # still contain an internal duplicate pair, which is reflected per-member
    # via likely_role="duplicate" above rather than at the cluster level.
    relationship = "likely_version_family"
    return {
        "cluster_id": cluster_id,
        "relationship": relationship,
        "confidence": 0.62,
        "creative_type": "unknown",
        "visual_summary": (
            "Mock analysis (no ANTHROPIC_API_KEY set): filenames and metadata suggest related "
            "exports of the same creative; visual content was not inspected in mock mode."
        ),
        "reason": "Rule-based mock reasoning over filename patterns and duplicate/similarity signals only.",
        "recommended_review": True,
        "members": members_out,
    }


def analyze_cluster(cluster_id: str, members: list[dict[str, Any]], project_root: Path,
                     mode: str = "auto") -> dict[str, Any]:
    """Returns a validated dict with an extra `ai_mode` and `ai_error` key.
    Never raises. On unrecoverable failure returns a payload with
    ai_mode="failed" so the caller can route the cluster to human review."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    use_mock = (mode == "mock") or (mode == "auto" and not api_key)

    if use_mock:
        result = _mock_analysis(cluster_id, members)
        result["ai_mode"] = "mock"
        result["ai_error"] = None
        return result

    last_error: Optional[str] = None
    hint = ""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            raw = _call_anthropic(api_key, cluster_id, members, project_root, retry_hint=hint)
            ok, err = validate_ai_response(raw)
            if ok:
                raw["ai_mode"] = "live"
                raw["ai_error"] = None
                return raw
            last_error = err
            hint = f"\n\nYour previous response was invalid ({err}). Return ONLY the JSON object, matching the schema exactly."
        except Exception as exc:  # noqa: BLE001 - network/parse failures must not crash the batch
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(0.5)

    fallback = _mock_analysis(cluster_id, members)
    fallback["ai_mode"] = "failed"
    fallback["ai_error"] = last_error
    fallback["recommended_review"] = True
    return fallback
