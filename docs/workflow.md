# The n8n Workflow, Node by Node

This walks through `n8n/creative-asset-handoff.json` (the primary artifact)
and `n8n/creative-asset-handoff-ai-subworkflow.json` in execution order. See
[`diagrams/workflow.mmd`](diagrams/workflow.mmd) for the visual version, and
`n8n/README.md` for import/setup instructions.

## Main workflow — 37 nodes across 9 labeled sections

### ① Input
- **Start: Manual Trigger** — begins the run.
- **Project Configuration** (Set) — the only place you edit paths:
  `project_path`, `manifest_path`, `output_dir`, `project_name`,
  `python_bin`, `pipeline_script`, `ai_mode`.

### ② Discovery, metadata, hashing, duplicates & deterministic validation
- **Run Deterministic Pipeline (Python)** (Execute Command) — one call into
  `pipeline.py run-deterministic`. `Continue On Fail: true`.
- **Deterministic Stage Succeeded?** (IF, checks `exitCode == 0`) —
  false branch → **Build Aborted Run Notice** (Code) → **Run Aborted**
  (NoOp), a clean, explained stop rather than a cryptic crash.
- **Read Deterministic Output** (Read/Write Files From Disk, read) +
  **Parse Deterministic JSON** (Code) — loads the stage-1 asset ledger back
  into the workflow.

### ③ Identify ambiguous clusters
- **Prepare AI Cluster Batches** (Code) — emits one n8n item per version
  cluster that couldn't be resolved deterministically (see
  `docs/deterministic-vs-ai.md`).

### ④ AI analysis
- **AI Asset Analysis — Per Cluster (Sub-workflow)** (Execute Workflow,
  per-item mode) — calls the AI sub-workflow once for each ambiguous
  cluster and fans the results back in. See "The AI sub-workflow" below.
- **Merge AI Results Onto Asset List** (Code) — reattaches each cluster's
  AI verdict to its member assets, and resolves the trivial
  (all-exact-duplicate) clusters deterministically without ever having sent
  them to the sub-workflow.

### ⑤ Classification
- **Classify Assets (Deterministic Scoring)** (Code) — the n8n-side port of
  `classification.py`'s weighted scoring function. Cross-tested for exact
  parity with the Python implementation (see `docs/architecture-decision.md`
  §7 and the repo's test notes).
- **Flatten Assets To Items** (Code) — turns the single scored list back
  into one n8n item per asset so the next IF can branch per-asset.

### ⑥ Review split
- **Requires Human Review?** (IF, on `classification.requires_review`) —
  splits into the confident path and the review path.

### ⑦ Human review
- **Auto-Resolve Confident Asset** (Code, per item) — confident assets get
  `approved_auto` or `excluded_auto` with no human involved.
- **Aggregate Review Queue** (Code, all items) — builds the HTML table +
  JSON decision template shown on the form.
- **Human Review Form** (Wait, Resume: On Form Submitted) — pauses the
  execution; see `docs/human-review.md`.
- **Parse & Apply Human Decisions** (Code, all items) — applies the
  submitted decisions, failing safe (`pending_review`) for anything left
  blank or invalid.

### ⑧ Delivery builder
- **Combine Confident + Reviewed Assets** (Merge, append) — the two
  branches reconverge into one asset stream.
- **Collect Final Asset List** → **Convert to JSON File** → **Write Final
  Assets JSON** — serializes the fully-resolved ledger back to disk so
  Python can build the delivery package from it.
- **Build Delivery Package (Python)** (Execute Command) — copy-only file
  operations into `delivery/<category>/`.

### ⑨ Manifest + report
- **Generate Delivery Manifest (Python)** and **Generate Processing Report
  (Python)** (Execute Command, run in parallel from the same upstream node) —
  both read the same final asset ledger, so they can always be
  cross-checked against each other.
- **Build Completion Summary** (Code) → **✅ Run Complete** (NoOp).

### Error handling pattern (sticky note ⚠)
Every `Execute Command` node uses `Continue On Fail: true`. The full
guarded check-then-log pattern (`IF` → `Build Aborted Run Notice`) is wired
explicitly on the Discovery step; the same pattern applies uniformly to the
later Python calls and is not repeated node-for-node on the canvas, to keep
it readable — see the sticky note on the canvas for this explanation.

## The AI sub-workflow — 15 nodes

Triggered once per ambiguous cluster via `Execute Workflow` (per-item mode):

1. **AI Analysis Input** (Execute Workflow Trigger) — receives
   `{cluster_id, members, project_root, ai_mode}`.
2. **Select Representative Image + Build Text Payload** (Code) — picks the
   first raster image member (if any) and builds the metadata-only text
   portion of the prompt.
3. **Has Representative Image?** (IF) branches to:
   - **Read Representative Image** (Read/Write Files, read) →
     **Attach Image To Request Body** (Code) — vision call.
   - **Finalize Text-Only Request Body** (Code) — metadata-only call.
4. **Call Vision Model (Anthropic)** (HTTP Request) — both branches above
   converge here. `Continue On Fail: true`.
5. **Extract & Validate JSON Schema** (Code) — hand-rolled schema check
   mirroring `python/src/schemas.py` exactly (cross-tested — see
   `docs/architecture-decision.md` §4).
6. **Schema Valid?** (IF):
   - **true** → **Format Cluster Result (Success)** — sub-workflow output.
   - **false** → **Retry Attempted Already?** (IF):
     - **true** → **Mark AI Analysis Failed** — `ai_mode: "failed"`,
       `recommended_review: true`, sub-workflow output.
     - **false** → **Build Retry Request Body** (Code, text-only retry with
       a stricter formatting hint) → loops back to **Call Vision Model**.

This bounds every cluster to at most 2 model calls, matching
`python/src/ai_client.py`'s `MAX_RETRIES`.

## Known simplifications (stated on the canvas and here)

- Only **one** representative image per cluster is sent to the vision
  model in the n8n path, not every member (the local Python path sends up
  to four). Keeps the sub-workflow's node graph static instead of needing a
  dynamic per-image loop.
- The retry attempt is **text-only** — it doesn't re-read or re-send the
  image, on the assumption that a schema-validation failure is a formatting
  problem, not a vision-content problem.
- The full guarded error-check-and-log pattern is shown once (Discovery
  step) rather than repeated identically after every single `Execute
  Command` node.

Both are also called out inline via sticky notes on the n8n canvas itself.
