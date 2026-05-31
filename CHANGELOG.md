# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning per [SemVer 2.0](https://semver.org/), with the fleet rule
that `v0.x.y` means "pre-stable" until the first reliably-tested
stable is announced. `v1.0` is reserved.

## [0.1.0] - 2026-05-31

### Theme

**First-honest pre-stable.** Atomic-replaces a v1.0.0 TypeScript draft
that shipped without a sanitizer, without dogfood, and with unsigned
commits. v0.1.0 is the actual baseline for this project.

### Added

- **MCP server** in Python using the official `mcp` SDK (pinned to
  `1.27.1` — past 14-day freshness hold, CVE-clean). Exposes one tool:
  `fetch_url(url)`.
- **Layer-2 sanitizer** vendored from
  [safe-fetch](https://github.com/sharkyger/safe-fetch). Strips
  invisible Unicode, HTML injection vectors, encoded payloads,
  exfiltration URLs, LLM template delimiters, and any literal
  `<UNTRUSTED-*>` sequence (envelope-breakout defense).
- **`<UNTRUSTED-WEB url="...">` wrap tag** on every response. Tag
  name is shared with safe-fetch so the model rule applies uniformly
  across the fleet.
- **SSRF protection** — three-layer block: IP literal pattern match,
  reserved hostname check, DNS resolution check. Redirect handler
  re-validates every hop.
- **Docker image** based on `python:3.12-slim` with sha256 digest pin
  (`@sha256:090ba77...`). Non-root user baked in; recommended host
  flags `--cap-drop=ALL --read-only --network=bridge` documented in
  README.
- **20 KB output cap** matching safe-fetch.
- **Atomic project docs** — README, SCOPE, CHANGELOG, LICENSE,
  NOTICE, PLAN. The PLAN doc is tracked from the start so the
  architecture rationale is part of the public artifact.
- **Tooling floor** — ruff, mypy, bandit, pip-audit, pytest with
  asyncio mode. CI matrix on py3.10 / 3.11 / 3.12 + static analysis
  + Docker build smoke.

### Changed

- **Implementation language:** TypeScript → Python. Reason: lets us
  reuse safe-fetch's tested sanitizer verbatim instead of re-porting
  and re-testing 530 lines of adversarial-HTML parsing. Both ship in
  Docker so user-facing install friction is identical.
- **Version line:** dropped `v1.0.0` (historical draft) for `v0.1.0`
  per the fleet pre-stable versioning rule. `v1.0` is reserved for
  the first reliably-tested stable.

### Removed

- The v1.0.0 TypeScript draft (entire `src/index.ts`, `package.json`,
  `tsconfig.json`, npm artifacts). The draft wrapped responses but
  did **not** sanitize them, which is half the protection. The GHCR
  image for v1.0.0 has been yanked; do not pull it.

### Verification

- Cross-distro dogfood planned before tag push (ubuntu / debian /
  almalinux / RHEL UBI9 — same matrix safe-fetch uses).
- Tier 1 review (CodeRabbit + Vibe CLI on full codebase) planned
  before tag push.

### Notes on the v1.0.0 draft

The v1.0.0 image that was briefly published was the work of a parallel
session that the operator stopped before it shipped to real users. The
project's stargazer count, PR count, and issue count were all zero at
the time of yank. No production rollback is expected. This entry
documents the audit trail so future contributors aren't confused by
the gap in tag history.
