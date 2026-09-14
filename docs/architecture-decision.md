# Architecture Decision Record — Creative Asset Handoff Intelligence

**Status:** Frozen for implementation
**Date:** 2026-08-17
**Owner:** AI Automation Engineering (portfolio project 5 of 5)

This document is written *before* implementation and is treated as frozen once
implementation starts. Any change during build is noted in "Deviations from
freeze" at the bottom rather than silently rewritten.

---

## 1. Problem framing

A creative agency finishes a campaign with a folder full of `final_v2.png`,
`final_FINAL.png`, duplicate exports, stray source files, and no reliable way
to tell what's actually deliverable without a human opening every file. The
mechanical 80% of that cleanup (hashing, dimension checks, format checks,
grouping likely versions) is measurable and does not need a language model.
The remaining 20% (“is `logo_newest.svg` actually the replacement for
`logo.svg`, or a different lockup?”) is genuinely ambiguous and benefits from
a vision-capable model plus a human's final call.

The system is a **decision-support and packaging pipeline**, not an
autonomous file manager. It never deletes or moves originals; it only
**copies** into a new delivery folder after a human has had the chance to
review anything uncertain.

## 2. Chosen n8n architecture

**n8n is the orchestrator.** It owns: triggering the run, sequencing stages,
branching on confidence, looping over ambiguous assets for AI calls,
validating AI output, running the human-review Form step, and invoking the
delivery/report build. n8n does **not** try to reimplement perceptual
hashing, ffprobe parsing, or image pixel decoding in Code nodes — those are
delegated to a Python CLI (see §3) via `Execute Command`.

Two workflow files ship in `n8n/`:

| File | Role |
|---|---|
| `creative-asset-handoff.json` | Main orchestration workflow (the primary artifact) |
| `creative-asset-handoff-ai-subworkflow.json` | Sub-workflow: analyzes one ambiguous asset with the vision model and returns validated, schema-checked JSON. Called once per ambiguous asset from a Loop node in the main workflow via `Execute Workflow`. |

The AI-analysis step is the **only** sub-workflow. Everything else stays in
the main canvas because splitting it further would add navigation overhead
without adding clarity (the brief explicitly warns against sub-workflows for
their own sake).

Main workflow stages (also see `docs/diagrams/workflow.mmd`):

1. **INPUT** — Manual Trigger + Set node holding `project_path`,
   `manifest_path`, `output_dir`.
2. **DISCOVERY + METADATA + HASHING + DUPLICATES + DETERMINISTIC VALIDATION**
   — one `Execute Command` call into the Python pipeline (`pipeline.py run-deterministic`).
   This single call is intentional: these sub-steps share the same file
   handles and libraries (Pillow, imagehash, ffprobe), so chaining them
   through five separate n8n round-trips would only add fragile
   file-marshalling without adding orchestration value. n8n reads the
   resulting `assets.json` back with `Read/Write Files from Disk` + `Code`.
3. **CLASSIFICATION SPLIT** — a `Code` node applies the deterministic scoring
   rules (§7) and an `IF` node splits assets into "confident" (skip AI) vs
   "needs AI opinion" (ambiguous version/final-ness signals).
4. **AI ANALYSIS LOOP** — `Loop Over Items` iterates the ambiguous subset;
   each iteration calls the AI sub-workflow (`Execute Workflow`), which does:
   `HTTP Request` to the vision model → `Code` (schema validation via a hand
   rolled JSON Schema check, no LangChain parser — see §4) → `IF` retry once
   on malformed output → mark `AI_ANALYSIS_FAILED` if still invalid.
5. **MERGE** — results merge back onto the full asset list.
6. **VALIDATION ENGINE** — `Code` node applies deterministic technical rules
   + optional manifest comparison (§8) and produces final status per asset.
7. **REVIEW SPLIT** — `IF` node: assets with `requires_review = false` and
   `status != NEEDS_REVIEW` go straight to delivery staging; everything else
   goes to the review queue.
8. **HUMAN REVIEW** — `n8n Form Trigger` node renders the review queue as a
   web form (one screen, all queued assets, each with an approve / reject /
   mark-final / mark-duplicate / exclude choice). The workflow **pauses**
   here (this is n8n's native human-in-the-loop mechanism — no bespoke
   webhook server needed). Submission resumes the workflow with the
   decisions attached.
9. **APPLY DECISIONS + DELIVERY BUILD** — `Execute Command` calls
   `pipeline.py deliver` with the merged (auto + human) decisions, which
   copies approved files into `delivery/<category>/`.
10. **MANIFEST + REPORT** — `Execute Command` calls `pipeline.py manifest`
    and `pipeline.py report`, then `Read/Write Files` exposes the two HTML
    outputs and the JSON manifest.
11. **ERROR HANDLING** — every `Execute Command` node has
    `Continue On Fail = true` wired to a small "log + continue" branch that
    appends to an `errors[]` array rather than stopping the run; the report
    stage surfaces that array under "Errors" (see §9).

Sticky notes on the canvas correspond 1:1 to the section numbers above so the
workflow reads top-to-bottom / left-to-right without opening any node.

## 3. Why Python exists, specifically

n8n Code nodes run sandboxed JavaScript/Python (via Pyodide) with **no**
access to native libraries, the filesystem beyond the current item, or
subprocess execution. This project needs:

- Pillow for real pixel dimensions and safe image decoding
- `imagehash` (perceptual hashing / pHash) for near-duplicate detection
- `ffprobe` (via subprocess) for video duration/codec/container
- SHA-256 streaming hashing over potentially large binary files
- Recursive, path-traversal-safe directory walking
- Byte-for-byte file copy for delivery packaging

None of that is reliable inside n8n's expression engine or Code node
sandbox. A small, tested, dependency-pinned Python CLI is the right tool for
exactly these operations — nothing else. Python does **not** own
orchestration, branching, the AI call, or the human-review step; n8n owns
all of those. This keeps the split honest: *Python = deterministic file
science, n8n = workflow logic.*

The CLI is invoked with `Execute Command` (n8n running in a self-hosted
container with local filesystem + Python 3.11 available — documented in
`n8n/README.md`). No persistent Python server, queue, or database is
introduced.

## 4. AI integration pattern (and why not the LangChain Agent node)

Research during this session (n8n's own docs and multiple 2026 practitioner
write-ups) confirms a known pattern: n8n's `AI Agent` + `Structured Output
Parser` (LangChain) combination is convenient for chat-style agents but is
documented as unreliable for enforcing a strict JSON schema on the *first*
call, and it pulls in LangChain machinery this project intentionally avoids
(the brief explicitly rules out LangChain/CrewAI/MCP for this workflow).

**Decision:** call the model directly with a plain `HTTP Request` node
against the provider's standard messages API, ask for JSON-only output in
the system prompt, and validate the response in a `Code` node against a hand
-written JSON Schema (`python/src/schemas.py` mirrors the same schema used
in the n8n Code node, kept in sync manually and documented). On schema
failure, retry once with a stricter reminder prompt; on second failure, mark
the asset `AI_ANALYSIS_FAILED` and route it into the human review queue
instead of blocking the run. This is fewer moving parts, fully inspectable
on the canvas, and matches the project's "avoid unnecessary frameworks"
constraint.

Model selection reasoning is in `docs/model-selection.md`. Short version:
**Claude Sonnet (vision)** is the default for asset/document-style image
understanding and structured-output discipline; the HTTP Request node is
provider-agnostic by design, so swapping to another vision API only means
changing the URL/headers/body-mapping in one node, not the workflow shape.

## 5. Duplicate detection strategy

Two independent, deterministic layers — never combined into one score, so a
recruiter reading the report can see *why* something was flagged:

1. **Exact duplicate:** SHA-256 of the full file. Any two assets with the
   same hash are byte-identical regardless of filename → `EXACT_DUPLICATE`.
2. **Near-duplicate / visual similarity (images only):** perceptual hash
   (`imagehash.phash`, 64-bit) with Hamming distance threshold. Distance
   ≤ 5 → `VISUAL_DUPLICATE`; distance 6–12 → `VISUALLY_SIMILAR` (weaker
   signal, feeds version analysis but does not by itself flag duplicate).
   Threshold values live in `python/src/config.py` as named constants, not
   magic numbers, so they're easy to defend/tune.

Videos are not perceptually hashed in this build (would require frame
extraction + a second hashing pass — real but out of scope per the "smallest
practical stack" instruction). Video duplicate detection uses exact hash
plus metadata match (duration + resolution + codec) as a coarser
`POSSIBLE_DUPLICATE` signal, clearly labeled as lower-confidence in the
report.

## 6. Version-relationship strategy

Deterministic filename-pattern clustering runs first (strips known suffixes
— `_final`, `_v\d+`, `_FINAL`, `_new`, `_latest`, `_revised`, `(\d+)` — and
groups files that share a normalized stem). This produces *candidate*
version families with zero API cost. The AI step is only invoked for
families where deterministic evidence is ambiguous (e.g., two different
normalized stems that are visually near-duplicate, or a family where the
"which one is final" signal is unclear). The model is explicitly prompted to
return a confidence score and is told **not** to claim certainty — see the
schema in §4 and `docs/deterministic-vs-ai.md`.

## 7. Final-asset classification

Combined, weighted, deterministic scoring function (`classification.py`) —
not an LLM decision alone:

```
score =
    + 0.35 if filename matches a "final-like" pattern
    + 0.20 if it is the most recently modified file in its version family
    + 0.15 if it matches an expected deliverable in the manifest (size/format)
    + 0.10 if it is NOT flagged as any kind of duplicate
    + 0.20 * ai_confidence   (only if AI analysis ran and succeeded)
    - 0.30 if it is an EXACT_DUPLICATE of another asset
    - 0.20 if filename matches an "intermediate-like" pattern (_draft, _v1, _wip, _old)
```

Thresholds: `score ≥ 0.72` → `LIKELY_FINAL`; `0.40–0.72` → `NEEDS_REVIEW`;
`< 0.40` and matches source patterns → `LIKELY_INTERMEDIATE`; source-folder
or proprietary-format assets → `LIKELY_SOURCE`. Every asset also carries
`requires_review` which is `true` whenever score sits within ±0.08 of a
threshold boundary, whenever AI analysis failed, or whenever the asset is
part of an unresolved duplicate/version cluster — this is what feeds the
Human Review form. **The AI's confidence is one weighted input, never the
decision.**

## 8. Validation engine

Deterministic, rule-based, no AI:

- Format allow-list per asset type
- Dimension checks (exact match or aspect-ratio tolerance) against
  `project_manifest.json` expected deliverables, when provided
- File-integrity check (image opens and decodes; video has a readable
  ffprobe stream; zero-byte file → `INVALID`)
- Oversized-file warning (configurable threshold, default 50 MB image / 500
  MB video)
- Missing-deliverable detection: any manifest entry with no matching asset
  is reported as `MISSING_DELIVERABLE` in the report, not silently dropped

The workflow **runs fully without a manifest** — validation then only
performs the non-manifest checks (integrity, format, size, duplicates) and
the report notes "no project manifest supplied; deliverable-completeness
checks skipped."

## 9. Error handling strategy

- Per-asset: any exception during inspection is caught inside the Python
  pipeline, the asset is marked `INSPECTION_FAILED` with the error message
  preserved, and processing continues for all other assets (never a
  process-wide crash for one bad file).
- Per-node (n8n): every `Execute Command` / `HTTP Request` node sets
  `Continue On Fail = true` and routes its error output into an
  `Collect Errors` `Code` node that appends a structured record; the run
  keeps going.
- AI failure: schema-invalid or unreachable API → one retry → mark
  `AI_ANALYSIS_FAILED`, asset auto-routes to human review instead of
  blocking.
- Delivery build never deletes or overwrites source files; it only ever
  copies into a fresh, timestamped `delivery/` output directory.
- The final `processing_report.html` has a dedicated "Errors & Warnings"
  section so failures are visible, not hidden.

## 10. Human review mechanism

n8n **Form Trigger** node (native, no custom frontend, no webhook server to
stand up separately) renders the queued items with radio-button decisions.
This satisfies "a simple n8n approval step, form, webhook, or lightweight
review mechanism is sufficient" directly. The demo mode (no live n8n
instance available in this sandbox) ships an equivalent static
`examples/test_cases/human_review_decisions.json` so the delivery/report
generators are fully testable without a human sitting at a form during
automated test runs — documented clearly as a stand-in for the live Form
step, not a replacement for it.

## 11. Output structure

```
delivery/
├── Images/            (only created if it will contain files)
├── Videos/
├── Social/             (assets matched to a manifest "instagram_*"/"social" deliverable)
├── Web/
├── Brand_Assets/       (logos, brand marks)
├── Source/             (explicitly approved source handoff, rare)
└── REVIEW_REQUIRED/    (anything a human excluded from auto-delivery but chose to keep visible)
delivery_manifest.json
delivery_manifest.html
processing_report.html
```

## 12. Explicit non-goals (kept out on purpose)

No DAM, no cloud storage integration, no autonomous deletion, no
Photoshop/PSD deep parsing, no multi-agent framework, no vector DB, no
queue/broker, no LangChain/CrewAI/MCP. Confirmed against the brief's scope
boundary before writing any code.

## Deviations from freeze

*(Filled in only if implementation forces a change. See bottom of this file
after build — kept empty at freeze time.)*

- None. Implementation followed this document as written.
