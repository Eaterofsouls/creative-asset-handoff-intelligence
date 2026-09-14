# Human Review

## Why review is mandatory, not optional

This system produces classifications and confidence scores, not verdicts.
Anything the deterministic scoring + AI analysis can't resolve with high
confidence is surfaced to a person — never silently auto-delivered and
never silently discarded.

## What triggers review

An asset's `classification.requires_review` flag is set `true` when **any**
of the following hold (see `architecture-decision.md` §7):

- Its score falls in the `NEEDS_REVIEW` band (0.40–0.72)
- Its score sits within ±0.08 of either threshold boundary (even if it
  technically cleared `LIKELY_FINAL`)
- It belongs to an unresolved version cluster with no successful AI opinion
- Its AI analysis failed schema validation twice (`ai_mode: "failed"`)
- It's visually similar to another asset but the AI didn't confirm a
  final-role for it

## The review mechanism

n8n's native **Wait node**, configured with **Resume: On Form Submitted**
(see `n8n/README.md`). This:

- Pauses the running execution (n8n persists it to the database — no
  polling, no external queue)
- Generates a form URL showing every queued asset: filename, status, score,
  the deterministic *and* AI reasons that flagged it, its duplicate
  relationships, and the AI's neutral visual summary
- Resumes the **same execution** the moment the form is submitted, with the
  submitted decisions available to the next node

No custom frontend, no webhook server to stand up separately, no polling
loop — this is explicitly why n8n was chosen as the orchestrator rather than
a plain Python script for this project.

## Decision vocabulary

A human can, per asset:

| Action | Effect |
|---|---|
| `approve` | Delivered as-is, in its auto-determined category |
| `reject` | Excluded from delivery |
| `mark_final` | Delivered, and its classification status is upgraded to `LIKELY_FINAL` |
| `mark_duplicate` | Excluded, classification status set to `DUPLICATE` |
| `exclude` | Excluded, no status change |
| `rename_category` | Delivered into a human-specified category folder |

Any decision with an action outside this set is **not** trusted — it's
treated as `exclude` (see `review.py: VALID_ACTIONS` and the equivalent n8n
Code node). If a queued asset receives **no** decision at all (the human
skipped it), it stays `pending_review` and is staged separately under
`delivery/REVIEW_REQUIRED/` — it is never auto-delivered by omission.

## Demo mode

This sandbox can't drive a live n8n Form submission interactively, so the
end-to-end demo and the automated tests use
`examples/test_cases/human_review_decisions.json` as a stand-in for what a
person would submit through the form. It is explicitly labeled as a stand-in
in that file's own `_comment` field and in
`architecture-decision.md` §10 — not a replacement for the real form step.
