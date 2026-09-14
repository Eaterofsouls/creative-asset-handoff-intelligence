# Limitations

Stated plainly, because a system like this is only trustworthy if its
boundaries are honest.

## What this system does not do

- **It does not autonomously delete, move, or overwrite source files.**
  Every operation on the original project folder is read-only; delivery is
  copy-only. This is a design guarantee, not a tuning parameter.
- **It does not guarantee correct final-asset detection.** Filename
  conventions vary by agency, client, and sometimes by which designer
  exported the file. The scoring weights in `classification.py` /
  `config.py` were tuned against the demo project's naming conventions and
  are a reasonable starting point, not a universal model of how every
  agency names files. Expect to retune the thresholds for a real studio's
  conventions.
- **It does not visually analyze video content.** Version/finality
  reasoning for video assets relies on filename + metadata only (duration,
  resolution, codec, exact-hash/metadata-based possible-duplicate
  detection). Frame extraction + visual comparison for video was
  deliberately left out of scope (see `architecture-decision.md` §5) —
  a real extension would sample frames with `ffmpeg` and run the same
  vision step used for images.
- **It does not deep-parse proprietary source formats** (PSD, AI, INDD,
  Sketch, Figma exports, EPS). These are recognized, hashed, and sized, but
  their internal structure (layers, artboards, etc.) is not inspected — the
  brief explicitly calls this out as an acceptable boundary rather than
  pulling in a large parsing dependency for a single format.
- **It is not a DAM.** There's no persistent asset library, no search, no
  versioning database across multiple runs — each run processes one project
  folder end-to-end and produces one delivery package. Running it again on
  the same folder does not remember previous decisions.
- **The n8n AI sub-workflow sends only one representative image per
  cluster** to the vision model (the local Python path sends up to four).
  This keeps the n8n canvas static and legible but means the model's visual
  judgment for larger clusters is based on a sample, not every member. See
  `n8n/README.md` → "Known simplifications".
- **The AI retry is text-only.** If the model's first response fails schema
  validation, the retry drops the image and resends metadata + a stricter
  formatting instruction. This assumes the failure was a formatting issue,
  not a vision-content issue — a reasonable bet in practice, but not
  guaranteed.
- **Duplicate/similarity thresholds are fixed constants**, not learned or
  auto-tuned. A studio with very high-resolution photography or heavy color
  grading between "duplicate" exports may need to adjust the perceptual
  hash distance thresholds in `config.py`.
- **This has not been run against a live Anthropic API key in this
  session** — the AI step ships with a fully offline, clearly-labeled mock
  mode (see `architecture-decision.md` §10) and was validated end-to-end in
  that mode, plus targeted parity/schema tests against representative
  request/response shapes. Live-key behavior should be smoke-tested before
  relying on it in production.
- **Node parameter names in the n8n JSON were verified against n8n's public
  documentation and community-shared workflow exports, not a live n8n
  instance** (this sandbox has no n8n runtime available to import into).
  The JSON is schema-valid, every Code node's JavaScript was parsed with a
  real JS engine, and the classification/schema-validation logic was
  cross-tested against the Python reference implementation — but minor
  node-parameter naming can drift slightly between n8n versions. See
  `n8n/README.md` → "Before you run this" for what to check on first import.

## What would be the natural next increment

Roughly in order of value if this became a real internal tool:

1. Retune `classification.py` scoring weights against a real agency's
   historical "what we actually shipped" folders.
2. Extend the AI sub-workflow to loop over all cluster images (not just one
   representative) using n8n's native per-item looping once the pattern is
   proven.
3. Add a lightweight persistence layer (even just a JSON log file) so
   re-running on an updated project folder can recognize "we already
   reviewed this asset last time."
4. Add video frame-sampling + vision analysis for video version clusters.
