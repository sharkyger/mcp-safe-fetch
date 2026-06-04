# CLAUDE.md — fleet rules apply

You are a parallel session working in `mcp-safe-fetch`. This repo is
part of the sharkyger / augatho OSS fleet maintained by Thorsten Beck
(a.k.a. Sharky). The orchestrator session in `~/agency-system` writes
handoff briefs for repo-specific work; you execute them. Don't write
back into `~/agency-system` — report progress via Slack #claude
(`python3 ~/agency-system/scripts/slack_check.py` to read,
`scripts/slack_post.py` to write) or wait for orchestrator observation
via `gh`.

## What this repo does

mcp-safe-fetch is an MCP server exposing a single `fetch_url` tool. It
validates the URL (http/https only, SSRF block, per-redirect re-check),
fetches via stdlib `urllib`, runs the Layer-2 prompt-injection
sanitizer (vendored from `safe-fetch`), and wraps the response in an
`<UNTRUSTED-WEB url="...">` envelope so the calling model treats the
body as data, not instructions. Companion to `safe-fetch` (same
sanitizer + same wrap tag, for Claude Code instead of MCP).

## Distribution — container only

The GHCR image (`ghcr.io/sharkyger/mcp-safe-fetch`) is the **only**
supported install + run mode. There is no host/npm run path: a bare
host process has none of the container's network isolation, which is
the SSRF boundary. The safety must travel with the image, not with the
`docker run` flags a user copy-pastes.

## Fleet rules — mandatory, no exceptions

Canonical rule texts live in the orchestrator's auto-memory dir; the
critical ones, summarized:

- **Identity** — repo git identity is `Sharky
  <51028592+sharkyger@users.noreply.github.com>`. NEVER let any of the
  operator's non-persona identities (the fingerprint denylist kept in
  the orchestrator's scope guard) reach a new commit/file/release
  (`feedback_one_canonical_repo_identity`).
- **Versioning** (`feedback_oss_versioning_rule`) — pre-stable =
  `v0.x.y` only. `v1.0` is reserved for the first reliably-tested
  stable. Halt for an operator decision before any tier promotion.
- **NEVER test on host** (`feedback_never_test_on_host`) — runtime
  smoke tests run in containers, not on the host. Host is for
  orchestration (git, gh, docker, review CLIs) only.
- **Floor first** (`feedback_professional_coding_tooling_floor`) —
  static analysis (ruff/mypy/bandit/pip-audit), CodeRabbit + Vibe
  review, CI, NOTICE before feature work.
- **One PR for everything** (`feedback_docs_ship_with_code`) — code +
  tests + README + CHANGELOG + NOTICE ship in ONE PR per phase. No
  "docs-only" follow-up splits.
- **README ordering** (`feedback_readme_usage_before_install`) — name +
  tagline → purpose → USAGE → INSTALL → config → license.
- **Dogfood before publish** (`feedback_dogfood_before_publish`) — pull
  the published image and smoke test it before announcing.

## Repo-specific

- **License:** MIT. Sanitizer vendored from safe-fetch; attribution
  chains back to the original Tim Stark TypeScript server via NOTICE.
- **Platform:** macOS is the only supported platform for now. Windows
  is not supported (WSL2 wall). Do not write/translate Windows steps.
- **Branch protection (main):** status checks `test (3.10/3.11/3.12)`,
  `static-analysis`, `docker-build`. Branch first; never commit to
  `main`.

## Orchestrator boundary

The agency-system orchestrator is PM-only — it writes briefs and
observes via `gh`, never edits files or runs git/release ops here. You
do the work. Don't write to `~/agency-system/` from this session.
