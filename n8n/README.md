# n8n Workflow — Setup & Import

Two workflow files ship here:

| File | What it is |
|---|---|
| `creative-asset-handoff.json` | **The main workflow.** Import this first. |
| `creative-asset-handoff-ai-subworkflow.json` | The AI cluster-analysis sub-workflow, called once per ambiguous version cluster. Import this too — the main workflow calls it. |

See [`../docs/workflow.md`](../docs/workflow.md) for a node-by-node walkthrough and
[`../docs/diagrams/workflow.mmd`](../docs/diagrams/workflow.mmd) for the visual overview.

## 1. Requirements

- A **self-hosted n8n instance** (n8n Cloud cannot run `Execute Command` or
  read arbitrary local file paths — this workflow needs both).
- **Python 3.11+** installed in the same environment n8n runs in, with this
  repo's `python/` folder available on disk to that environment (see
  `python/README.md` for dependencies — `pip install -r
  python/requirements.txt`).
- **ffmpeg / ffprobe** installed and on `PATH` (used by the Python pipeline
  for video metadata).
- An **Anthropic API key**, only if you want live AI analysis. Without one,
  the pipeline runs in a fully offline, clearly-labeled mock mode — see
  `docs/architecture-decision.md` §10.

## 2. Import order

1. **n8n UI → Workflows → Import from File** → select
   `creative-asset-handoff-ai-subworkflow.json`. Save it.
2. **Import from File** again → select `creative-asset-handoff.json`. Save it.
3. Open the main workflow, find the **"AI Asset Analysis — Per Cluster
   (Sub-workflow)"** node, and re-select the sub-workflow from its dropdown.
   n8n assigns new internal workflow IDs on import, so the reference baked
   into the exported JSON won't auto-resolve across instances — this is
   normal, one-time friction for any multi-workflow n8n project, not a bug
   in the export.

## 3. Required credential

The sub-workflow's **"Call Vision Model (Anthropic)"** HTTP Request node
uses a generic **HTTP Header Auth** credential:

- Credential name: `Anthropic API Key` (or update the node to point at
  whatever you name it)
- Header name: `x-api-key`
- Header value: your Anthropic API key

If you skip this, the sub-workflow's HTTP call will fail — that's fine, it's
wired with `Continue On Fail`, and the affected cluster will be marked
`ai_mode: "failed"` and routed to human review rather than breaking the run.
For a fully offline run, use the Python CLI's `--mock-ai` flag instead (see
`python/README.md`) rather than relying on this workflow's failure path.

## 4. Required environment / local paths

Open the **"Project Configuration"** node (the first Set node) in the main
workflow and edit:

| Field | Meaning | Demo value |
|---|---|---|
| `project_path` | Folder to process | `/data/examples/messy_project` |
| `manifest_path` | Optional expected-deliverables spec (leave blank to skip) | `/data/examples/project_manifest.json` |
| `output_dir` | Where `pipeline_stages/`, `delivery/`, and the reports get written | `/data/output` |
| `project_name` | Shown in the manifest/report headers | `Maison Living — Autumn Campaign` |
| `python_bin` | Python executable available to the n8n process | `python3` |
| `pipeline_script` | Path to `python/src/pipeline.py` as seen by n8n | `/data/python/src/pipeline.py` |
| `ai_mode` | `auto` (use live API if credential works, else mock) / `mock` / `live` | `auto` |

All paths are from the perspective of the machine/container n8n's `Execute
Command` and `Read/Write Files From Disk` nodes run on — if you're running
n8n in Docker, mount this repository into the container (e.g. at `/data`)
and use container-side paths here, not host paths.

## 5. Running the demo

1. Open the main workflow, click **Execute Workflow** on the **"Start:
   Manual Trigger"** node.
2. Watch it run through discovery → AI analysis → classification.
3. When it reaches **"Human Review Form"**, the node panel shows a form
   URL (Test URL while building, Production URL once the workflow is
   activated). Open it, review the flagged assets, edit the JSON decisions
   template, submit.
4. The execution resumes and finishes: `delivery/`, `delivery_manifest.json`,
   `delivery_manifest.html`, and `processing_report.html` land in your
   configured `output_dir`.

To see the exact same pipeline run non-interactively (useful for CI or a
quick sanity check without clicking through a form), use the Python CLI's
`full-run` command directly — see `python/README.md`. That is also how
`output/` in this repository was generated for the portfolio demo.

## 6. What each major node does

Full walkthrough: [`../docs/workflow.md`](../docs/workflow.md). Short version:

- **Execute Command** nodes call `python/src/pipeline.py` subcommands for
  every step that needs Pillow / imagehash / ffprobe / file I/O.
- **Code** nodes hold the parts that are cleaner as plain logic against
  already-fetched JSON: batching clusters for AI analysis, the deterministic
  classification scorer (ported from `classification.py`), merging results,
  and applying human decisions.
- **HTTP Request** (in the sub-workflow) calls the Anthropic Messages API
  directly — no LangChain / AI Agent node. See
  `docs/architecture-decision.md` §4 for why.
- **Wait** (Resume: On Form Submitted) is the human review gate.
- **IF** nodes handle every branch point: deterministic-stage success,
  human-review requirement, AI schema validity, retry-exhausted.

## 7. Known simplifications

Documented here, in `docs/workflow.md`, `docs/limitations.md`, and via
sticky notes directly on the canvas:

- The AI sub-workflow sends **one representative image per cluster**, not
  every member (the local Python path sends up to four).
- The AI retry attempt is **text-only** (drops the image, resends metadata +
  a stricter formatting instruction).
- The Execute-Command error-check-and-log pattern is fully wired once (on
  the Discovery step) and noted as applying uniformly to the later Python
  calls, rather than repeated node-for-node on the canvas.

## 8. Before you run this in your own n8n instance

Node parameter shapes (e.g. exact field names on the `Wait`, `Execute
Workflow`, or `Convert to File` nodes) were built against n8n's public
documentation and verified community-shared workflow exports, and every
node's JavaScript was syntax-checked with a real JS engine — but this JSON
was **not** import-tested against a live n8n instance in this build
environment (none was available). If a node shows a parameter warning on
import, it's almost always a version-specific field rename — open the node,
re-pick the relevant dropdown option, and save. See `docs/limitations.md`
for the full, honest list of what wasn't (and couldn't be) live-verified
here.
