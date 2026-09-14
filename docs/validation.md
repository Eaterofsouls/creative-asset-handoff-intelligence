# Validation

All validation described here is deterministic (`python/src/validation.py`
+ `classification.py`'s manifest-match term). No AI is involved in
validation — see `docs/deterministic-vs-ai.md`.

## Technical validation (always runs)

| Check | Rule |
|---|---|
| Format allow-list | Extension must be a known image/video/document/source format (`config.py`) |
| Inspection integrity | Image must decode (`Image.verify()`); video must produce a valid `ffprobe` stream; zero-byte files are always invalid |
| Oversized file | Image > 50 MB or video > 500 MB → warning (thresholds in `config.py`, not magic numbers) |
| Dimension readability | Image dimensions must be determinable (fails for corrupt/truncated files) |

## Manifest validation (runs only if `project_manifest.json` is supplied)

For each `expected_deliverables` entry (`type`, `format`, `dimensions`):

1. Any asset matching `format` exactly and `dimensions` (exact match, or
   within a 2% aspect-ratio tolerance) gets
   `validation.matched_deliverable = <type>`.
2. Any asset matching the `format` but **not** the dimensions gets an
   explicit issue appended: `"format matches expected deliverable 'X' but
   dimensions WxH != expected ..."` — this is the brief's canonical example:

   ```
   EXPECTED: Instagram Reel, 1080x1920 MP4
   ACTUAL:   reel_v1_draft.mp4, 720x1280 MP4
   ⚠ INVALID DIMENSIONS
   ```

3. Any manifest entry with **no** matching asset at all is reported under
   `missing_deliverables` in both the JSON manifest and the HTML report —
   never silently dropped.

## Running without a manifest

The workflow **must** function without `project_manifest.json` (explicit
requirement in the brief). When no manifest is supplied:

- `manifest_compare.manifest_supplied = false`
- Deliverable-completeness checks are skipped entirely
- Technical validation (format, integrity, size, duplicates) still runs on
  every asset, unchanged
- The processing report states plainly: *"No project manifest was supplied
  for this run — deliverable-completeness checks were skipped."*

Verified in `tests/test_pipeline_end_to_end.py::test_full_run_without_manifest_still_succeeds`.

## Failed inspection never aborts the run

A corrupted, zero-byte, or unreadable file is marked `inspection_ok: false`
with a captured `inspection_error`, and processing continues for every other
asset. The processing report has a dedicated "Files That Failed Inspection"
section listing exactly which files and why. See
`docs/architecture-decision.md` §9 and
`tests/test_metadata.py::test_corrupted_image_flagged_not_crashed`.
