# Pipeline Stage Snapshots

Each file here is the full asset ledger as it existed after one CLI stage, in run order. Kept for transparency/debugging -- open 01 through 06 in order to watch classification, AI analysis, and human review decisions accumulate onto each asset record. See docs/architecture-decision.md for what each stage does.

01_deterministic.json  -- discovery + metadata + hashing + duplicates + version clusters + validation
02_ai.json             -- + AI cluster analysis (mock or live, see each asset's ai.ai_mode)
03_finalized.json      -- + deterministic classification scoring
04_review_queue.json   -- the review queue as the n8n Form node would render it
05_reviewed.json       -- + human review decisions applied
06_delivered.json      -- + delivery copy results (delivery_summary)
