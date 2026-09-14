# Deterministic vs. AI: What Goes Where, and Why

This is the single most important engineering judgment in this project.
The rule applied everywhere:

> **If a value can be measured or computed exactly, it is computed exactly.
> AI is used only for the narrow slice of judgment calls that genuinely
> require weighing ambiguous, qualitative evidence.**

## Deterministic (no AI involved, ever)

| Decision | How | Where |
|---|---|---|
| File extension / MIME / format validity | Extension allow-list, `mimetypes` | `metadata.py` |
| Image dimensions | Pillow decode | `metadata.py` |
| Video duration/codec/container | `ffprobe` | `metadata.py` |
| File size / "unusually large" | Byte count vs. named threshold | `validation.py` |
| Exact duplicate | SHA-256 equality | `duplicates.py` |
| Near-duplicate / visual similarity | Perceptual hash Hamming distance | `duplicates.py` |
| Candidate version-family grouping | Filename suffix stripping + stem match | `version_analysis.py` |
| Manifest deliverable matching | Format + dimension comparison | `validation.py` |
| **Whether a cluster needs an AI opinion at all** | If every member shares one file hash, it's a trivial duplicate set — no AI call is made | `pipeline.py: _needs_ai` / n8n `Merge AI Results` node |
| Final classification status + score | Weighted rule-based scoring function | `classification.py` (+ n8n Code node) |

## AI-assisted (Claude Sonnet, vision, one call per ambiguous cluster only)

| Question | Why it needs judgment, not just measurement |
|---|---|
| Do `final.png` / `final_v2.png` / `final_FINAL.png` represent the same creative at different stages? | Filenames *suggest* a relationship; confirming it (vs. three unrelated files that happen to share a generic name) benefits from actually looking at them |
| Which member of an ambiguous cluster looks delivery-ready vs. a draft? | No single metric settles this — it's a mix of recency, filename convention, and visual completeness |
| What kind of creative is this (post / logo / reel cover / banner)? | Not derivable from file format alone |
| Do two visually-similar files actually differ in a way that matters? | Requires actually comparing pixel content, not just a similarity score |

**The AI never decides alone.** Its confidence score is one weighted term
in `classification.py`'s scoring function (see
`architecture-decision.md` §7) — worth at most 0.20 of a 1.0 scale, and
only when the model rates a member "final". A test enforces this
explicitly: `tests/test_classification.py::test_ai_confidence_alone_cannot_force_likely_final`.

## What happens when AI analysis fails or is unavailable

- No `ANTHROPIC_API_KEY` configured → automatic, clearly-labeled mock mode
  (`ai_mode: "mock"`), never silently pretending to be a real model call.
- Malformed/non-schema-conforming response → one retry with a stricter
  prompt, then `ai_mode: "failed"` and the asset is force-routed to human
  review (`recommended_review: true`), never silently skipped.
- Network/API error → same fallback path, caught and logged, run continues.

This mirrors the brief's instruction precisely: *"If the model produces
malformed output: retry or mark the asset AI_ANALYSIS_FAILED. Do not crash
the entire workflow."*
