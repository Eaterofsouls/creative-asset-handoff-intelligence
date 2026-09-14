# Security

Kept practical and scoped to what this project actually touches: local
filesystem paths, one outbound API call, and generated HTML.

## Path safety

- Every CLI entry point that accepts `--project` validates the path exists,
  is a directory, and is not a bare system root (`security.py:
  validate_project_root`) before touching anything.
- Discovery does not follow symlinks (`discovery.py`), so a crafted symlink
  inside a project folder can't be used to read or hash files outside it.
- `security.resolve_within()` is available for any future code path that
  needs to resolve a user-supplied relative path against a root and refuse
  anything that escapes it (path traversal via `..`, absolute overrides, or
  symlink tricks) — used defensively even though the current CLI surface
  doesn't take untrusted relative paths directly from a remote caller.
- Generated JSON/HTML output never embeds absolute host filesystem paths —
  everything user-facing uses `relpath` (POSIX-relative to the project
  root), via `security.safe_relpath`.

## Secrets

- No API key is hardcoded anywhere in this repository (checked before
  packaging — see the repo-wide grep in the final validation pass).
- `ANTHROPIC_API_KEY` is read from the environment only
  (`ai_client.py: os.environ.get(...)`); if it's unset, the pipeline falls
  back to clearly-labeled mock mode rather than failing or prompting for one.
- `.env.example` documents every environment variable the project uses —
  copy it to `.env` and fill in real values; `.env` itself is git-ignored.
- The n8n AI sub-workflow's HTTP Request node uses an n8n **credential**
  (HTTP Header Auth), not a hardcoded header value — see `n8n/README.md`.

## Untrusted input handling

- **AI output is never trusted as-is.** Every response is parsed and
  validated against a strict JSON Schema (`schemas.py`, and the JS port in
  the n8n sub-workflow) before any field of it is used. Malformed output is
  rejected, retried once, then routed to human review — never executed,
  never used to pick a file path, never interpolated into a shell command.
- **Human review decisions are validated too**: any `action` value outside
  the known set (`approve/reject/mark_final/mark_duplicate/exclude/
  rename_category`) fails safe to `exclude` rather than being trusted
  (`review.py: VALID_ACTIONS`) — a malformed or malicious form submission
  can't cause an asset to be silently delivered.
- The Execute Command calls in the n8n workflow interpolate only values from
  the `Project Configuration` Set node (operator-controlled, not
  user-uploaded content) and internally-generated file paths — never raw
  AI output or raw form text — into shell command strings.

## File operations

- **Delivery is copy-only.** `delivery.py` never calls anything that
  deletes or moves a source file; the worst-case failure mode is a missing
  copy, not data loss. Verified by
  `tests/test_review_and_delivery.py::test_delivery_never_deletes_or_moves_source`.
- Delivery never silently overwrites a same-named file within a delivery
  category — it appends a short id suffix instead of clobbering.

## Generated HTML

- `render.py` escapes every dynamic value with `html.escape()` before
  interpolating it into the report/manifest templates
  (`render.py: esc()`), since filenames are attacker-influenceable in
  principle (a project folder could contain a file named e.g.
  `<script>...</script>.png`).

## Out of scope for this project

No authentication/authorization layer, no multi-tenant isolation, no
network hardening beyond "don't hardcode secrets" — this is a local,
single-operator workflow tool, not a hosted multi-user service. If it were
productionized for multiple agencies/clients, the natural next steps would
be per-project access control and sandboxing the Execute Command calls
(e.g. a restricted service account, not the n8n host's own user).
