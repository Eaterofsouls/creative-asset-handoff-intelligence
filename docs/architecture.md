# Architecture Overview

For the *decision log* (what was chosen, why, and what alternatives were
rejected), see [`architecture-decision.md`](architecture-decision.md). This
document is the shorter, diagram-first overview.

## System shape

```
MESSY PROJECT FOLDER (+ optional project_manifest.json)
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│                      n8n (orchestrator)                    │
│                                                             │
│  INPUT → DISCOVERY/METADATA/DEDUP/VALIDATION (Python) →    │
│  AI ANALYSIS (per ambiguous cluster, sub-workflow) →        │
│  CLASSIFICATION (deterministic scoring, n8n Code) →         │
│  REVIEW SPLIT → HUMAN REVIEW (n8n Form) →                   │
│  DELIVERY BUILD (Python) → MANIFEST + REPORT (Python)       │
└───────────────────────────────────────────────────────────┘
        │
        ▼
   delivery/ + delivery_manifest.(json|html) + processing_report.html
```

See [`diagrams/architecture.mmd`](diagrams/architecture.mmd) for the
rendered version.

## The two runtimes, and why

| Runtime | Owns | Does NOT own |
|---|---|---|
| **n8n** | Triggering, sequencing, branching, the AI HTTP call + schema validation, the human review Form/Wait step, error routing, calling Python at each stage boundary | Pixel decoding, hashing, ffprobe parsing, file copying internals |
| **Python** (`python/src/`) | Discovery, metadata extraction, hashing (exact + perceptual), duplicate detection, filename-based version clustering, deterministic technical validation, delivery file copying, manifest/report rendering | Orchestration, the human-in-the-loop pause, branching logic, the live AI HTTP call (n8n path) |

The **deterministic classification scoring** logic is intentionally
implemented **twice**, once in `python/src/classification.py` and once as an
n8n Code node — kept byte-for-byte equivalent and cross-tested (see
`docs/deterministic-vs-ai.md`). This is a deliberate exception to
"don't duplicate logic": it lets the n8n canvas itself perform real
decision-making rather than being a thin wrapper around Python, which is the
entire point of this portfolio piece. Every other deterministic step
(hashing, ffprobe, file I/O) lives in exactly one place.

## Data flow between stages

Every stage boundary is a plain JSON file under `output/pipeline_stages/`
(see that folder's own `README.md` after running the demo). This makes the
pipeline:

- **Inspectable** — open any stage file and see exactly what the asset
  ledger looked like at that point.
- **Resumable** — any stage can be re-run against a saved intermediate file
  without re-running everything upstream (useful for iterating on the
  classification weights or the AI prompt without re-hashing every file).
- **Portable between environments** — the same `pipeline.py` subcommands
  work identically whether called from n8n's `Execute Command` node or from
  a terminal for local testing (see `python/README.md`).

## Where each requirement from the brief lands

| Requirement | Where |
|---|---|
| Deterministic logic | `python/src/{discovery,metadata,hashing,duplicates,version_analysis,validation}.py` + n8n `Classify Assets` Code node |
| AI reasoning | `python/src/ai_client.py` (local/test path) + n8n AI sub-workflow (`n8n/creative-asset-handoff-ai-subworkflow.json`) |
| Branching | n8n `IF` nodes: deterministic-stage success, human-review requirement, schema validity, retry-exhausted |
| File operations | `python/src/delivery.py` (copy-only) via n8n `Execute Command` |
| Human review | n8n `Wait` node (Resume: On Form Submitted) — see `docs/human-review.md` |
| Reporting | `python/src/{manifest,report}.py` → `delivery_manifest.(json|html)`, `processing_report.html` |
| Workflow orchestration | `n8n/creative-asset-handoff.json` |
