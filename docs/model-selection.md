# Model Selection

This document records the model evaluation for the one AI-reasoning step in
the pipeline: **cluster-level version/finality analysis** (see
[`architecture-decision.md`](architecture-decision.md) §4 and §6). It is the
only place in the system where a language model is called.

## What the model actually needs to do

Given a small group of files (2–6) that deterministic filename clustering
flagged as a possible version family, plus their metadata and (where
available) one representative image, return a structured, confidence-scored
opinion on:

- whether the group is really a version family, a duplicate set, or unrelated
- which member looks final vs. intermediate/source
- a short neutral visual summary and creative type

This is a **small, bounded, structured-output task** — not open-ended
chat, not long-context document reasoning, not agentic tool use. That framing
drove the evaluation more than any general leaderboard.

## Models considered

| Model | Vision quality for UI/asset-style images | Structured JSON reliability | Notes |
|---|---|---|---|
| **Claude Sonnet (current generation)** | Strong — consistently reliable at describing layout, text regions, and comparing near-duplicate images | High when the prompt demands JSON-only output; respects "don't claim certainty" instructions well in practice | Chosen. Good balance of quality/cost/latency for a per-cluster call; integrates with a single `HTTP Request` node against the standard Messages API |
| GPT-5-class models | Strong vision quality; native structured-output/JSON mode is a genuine strength | Very strong | Reasonable alternative. Not chosen only because the rest of this portfolio and Anthropic's own tooling already standardize on the Claude API, and the HTTP Request node is provider-agnostic by design (swapping providers is a body/header change, not a workflow redesign) |
| Gemini 2.x/3.x Flash-class models | Good vision quality, very low cost/latency | Generally good, occasionally needs stricter prompting for strict schemas | Worth considering for high-volume agencies processing hundreds of clusters/day where cost dominates; noted as the first thing to benchmark if this moved to production at scale |
| Smaller open-weight VLMs (self-hosted) | Materially weaker at fine-grained UI/layout comparison in informal testing | Requires more prompt engineering to hold a strict schema | Rejected for this use case: the accuracy loss on "is this the same creative, cropped/recolored?" judgments wasn't worth the self-hosting operational cost for a workflow this small |

## Decision

**Claude Sonnet (vision-capable), called via plain `HTTP Request`** to the
Anthropic Messages API, is the default in both `python/src/ai_client.py` and
the n8n AI sub-workflow.

This is a **provider-agnostic integration pattern on purpose** — see
`architecture-decision.md` §4 for why a plain HTTP Request node was chosen
over n8n's built-in AI Agent / Structured Output Parser (LangChain) nodes.
Switching providers means changing the URL, auth header, and request/response
mapping in one node (or one Python function) — not restructuring the
workflow, the schema, or the human-review logic.

## Why not the n8n AI Agent node

n8n's `AI Agent` node with a `Structured Output Parser` is a good fit for
open-ended, tool-using chat agents. For this workload — a single, bounded,
schema-constrained classification call — it adds LangChain machinery
(explicitly out of scope for this project, see the brief's tooling
principle) without adding reliability: this project's own hand-rolled JSON
Schema check (`python/src/schemas.py`, ported to the n8n Code node in the AI
sub-workflow) enforces the exact same contract with zero extra
dependencies and is fully visible on the canvas.

## Limitations, honestly stated

- **No model is asked to make the final call.** Every AI response is one
  weighted input into `classification.py`'s deterministic scoring function,
  and every response the model returns includes an explicit confidence score
  it's instructed never to max out to 1.0-certainty language.
- **Only one representative image per cluster** is sent to the model in the
  n8n path (see `n8n/README.md` → "Known simplifications"). The local
  Python path (`ai_client.py`) sends up to 4.
- **Video content is not visually analyzed.** Cluster reasoning for video
  members relies on filename + metadata only — no frame extraction. This
  is a deliberate scope boundary (see `docs/limitations.md`).
- **Cost/latency were not benchmarked with a live account in this session**
  (no API key is provisioned in this build; see `.env.example` and the mock
  mode described in `architecture-decision.md` §10). Based on typical Sonnet
  pricing and a ~1–2K token prompt with one image, a single cluster call is
  inexpensive (fractions of a cent) and fast (low single-digit seconds) —
  but this should be re-verified against current published pricing before
  relying on it for budgeting.
