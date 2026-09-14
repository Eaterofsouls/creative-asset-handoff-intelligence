# Tool Map

Only tools actually used in this build are listed. See
`docs/architecture-decision.md` for the reasoning behind each choice.

| Layer | Technology | Purpose |
|---|---|---|
| Workflow orchestration | **n8n** (self-hosted) | Sequencing, branching, human-in-the-loop, calling Python, calling the AI model |
| File discovery & metadata | **Python 3.11+ / Pillow** | Recursive discovery, image dimensions, safe decode-and-verify |
| Video metadata | **ffmpeg / ffprobe** (via `subprocess`) | Duration, codec, container, resolution |
| Exact duplicate detection | **hashlib (SHA-256)**, stdlib | Byte-identical file detection |
| Perceptual/near-duplicate detection | **imagehash (pHash)** | Visual similarity between raster images |
| PDF inspection | **pypdf** | Page count / page dimensions for document-type deliverables |
| AI structured reasoning | **Anthropic Messages API** (Claude Sonnet, vision) via plain `HTTP Request` | Version-family / final-asset reasoning for ambiguous clusters only |
| AI output validation | **jsonschema** (Python) / hand-rolled JS validator (n8n Code node) | Enforces the AI response contract; never trusts raw model text |
| Human review | **n8n Wait node** (Resume: On Form Submitted) | Native human-in-the-loop, no external server |
| Delivery packaging | **Python `shutil`** | Copy-only file operations into categorized delivery folders |
| Reporting | **Plain HTML + inline CSS** (Python string templates, `python/src/render.py`) | `delivery_manifest.html`, `processing_report.html` |
| Testing | **pytest** | 64 tests across every deterministic module + end-to-end CLI runs |
| Diagrams | **Mermaid** (`.mmd`) + hand-built SVG | Architecture / workflow / decision-flow diagrams |

## Explicitly not used, and why

Per the brief's tooling principle, these were deliberately kept out even
though they're common in n8n/AI projects generally:

- **LangChain / LangChain-based n8n AI Agent node** — adds an abstraction
  layer and a dependency for a task (one bounded structured-output call)
  that a plain HTTP Request + hand-rolled schema check already solves
  reliably and transparently. See `architecture-decision.md` §4.
- **CrewAI / multi-agent frameworks** — this is a single-purpose
  classification call, not a multi-agent reasoning task.
- **MCP** — no external tool-calling is needed inside the AI step itself;
  the model receives metadata and returns JSON.
- **Vector database** — nothing here requires semantic search or embedding
  retrieval; version relationships come from filename clustering +
  perceptual hashing, both exact/deterministic techniques.
- **Redis / Postgres / a job queue** — the workflow is a single bounded run
  over one project folder, not a high-throughput service; n8n's own
  execution persistence handles the Wait/resume state.
- **Kubernetes / any container orchestration** — a single self-hosted n8n
  instance with Python + ffmpeg installed is sufficient; see `n8n/README.md`.
