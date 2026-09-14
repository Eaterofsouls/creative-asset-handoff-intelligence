# Python Component — Deterministic Processing Engine

## Why this exists

n8n orchestrates; this does the file science n8n can't do reliably on its
own — image decoding, perceptual hashing, `ffprobe` parsing, and safe
recursive file I/O. See
[`../docs/architecture-decision.md`](../docs/architecture-decision.md) §3
for the full reasoning. This is **not** a standalone application with an
n8n screenshot on top — every stage here is a discrete CLI subcommand
designed to be called once per n8n workflow step, so n8n keeps control of
sequencing, branching, and the human-review pause.

## Install

```bash
python3 -m venv .venv && source .venv/bin/activate     # optional but recommended
pip install -r requirements.txt --break-system-packages  # drop the flag inside a venv
```

Also requires `ffmpeg`/`ffprobe` on `PATH` for video metadata (`apt install
ffmpeg` on Debian/Ubuntu, `brew install ffmpeg` on macOS).

## CLI reference

Every subcommand reads/writes plain JSON files so each stage can be run,
inspected, and re-run independently — matching how the n8n workflow calls
them one at a time between its own branching/AI/review steps.

```bash
cd python/src

# Stage 1: discovery + metadata + hashing + duplicates + version clusters + validation
python3 pipeline.py run-deterministic \
  --project ../../examples/messy_project \
  --manifest ../../examples/project_manifest.json \
  --out /tmp/01_deterministic.json

# Stage 2: AI cluster analysis (mock mode -- no API key needed)
python3 pipeline.py ai-analyze \
  --assets /tmp/01_deterministic.json \
  --project ../../examples/messy_project \
  --out /tmp/02_ai.json --mock

# ...or with a live key: export ANTHROPIC_API_KEY=sk-... first, then --live

# Stage 3: deterministic classification scoring
python3 pipeline.py finalize --assets /tmp/02_ai.json --out /tmp/03_finalized.json

# Stage 4: see what a human reviewer would be shown
python3 pipeline.py review-queue --assets /tmp/03_finalized.json --out /tmp/04_queue.json

# Stage 5: apply review decisions (or omit --decisions to auto-resolve only the confident items)
python3 pipeline.py review \
  --assets /tmp/03_finalized.json \
  --decisions ../../examples/test_cases/human_review_decisions.json \
  --out /tmp/05_reviewed.json

# Stage 6: build the delivery package (copy-only)
python3 pipeline.py deliver \
  --assets /tmp/05_reviewed.json \
  --project ../../examples/messy_project \
  --delivery-dir /tmp/delivery \
  --out /tmp/06_delivered.json

# Stage 7: manifest + report
python3 pipeline.py manifest --assets /tmp/06_delivered.json --project-name "Demo" --out-dir /tmp
python3 pipeline.py report   --assets /tmp/06_delivered.json --project-name "Demo" --out-dir /tmp
```

## `full-run`: the whole pipeline in one command

This is the convenience command used to generate this repository's own
`output/` folder, and to drive the automated end-to-end tests. It chains
every stage above locally, so the full pipeline is verifiable without a
live n8n instance — **it does not replace the n8n workflow**; n8n calls the
same underlying subcommands one at a time, with its own branching and the
real human-review Form step in between. See
`docs/architecture-decision.md` §2 and §10.

```bash
python3 pipeline.py full-run \
  --project ../../examples/messy_project \
  --manifest ../../examples/project_manifest.json \
  --decisions ../../examples/test_cases/human_review_decisions.json \
  --out-dir ../../output \
  --mock-ai \
  --project-name "Maison Living — Autumn Campaign"
```

Omit `--decisions` to see what happens with zero human input (confident
assets still auto-resolve; everything else stays `pending_review` and is
staged under `delivery/REVIEW_REQUIRED/`, never silently delivered).

## Module map

| File | Responsibility |
|---|---|
| `config.py` | Every threshold/weight/pattern used anywhere, named and documented — no magic numbers |
| `security.py` | Path validation / traversal protection |
| `discovery.py` | Recursive, symlink-safe file discovery |
| `metadata.py` | Per-file inspection (Pillow / ffprobe / pypdf / SVG regex); never raises |
| `hashing.py` | SHA-256 + perceptual hash (`imagehash`) |
| `duplicates.py` | Exact + near-duplicate detection (images), possible-duplicate detection (video) |
| `version_analysis.py` | Filename-based version-family clustering |
| `schemas.py` | JSON Schema + validator for AI responses |
| `ai_client.py` | Anthropic API call (live) + deterministic mock fallback |
| `classification.py` | Weighted deterministic scoring (ported 1:1 into the n8n Code node — see `docs/architecture-decision.md` §7) |
| `validation.py` | Technical validation + manifest comparison |
| `review.py` | Review-queue construction + human-decision merge |
| `delivery.py` | Copy-only delivery packaging |
| `render.py` | Shared HTML rendering helpers |
| `manifest.py` / `report.py` | `delivery_manifest.(json|html)` / `processing_report.html` generation |
| `pipeline.py` | CLI entry point tying every stage together |

## Tests

```bash
cd ../..            # repo root
python3 -m pytest tests/ -v
```

64 tests covering every module above plus full end-to-end CLI runs (with
and without a manifest, with and without human decisions, and a guard
against unsafe project paths).
