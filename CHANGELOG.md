# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning per [SemVer 2.0](https://semver.org/), with the fleet rule
that `v0.x.y` means "pre-stable" until the first reliably-tested
stable is announced. `v1.0` is reserved.

## [Unreleased]

### Added

- **GHCR publish workflow** restored (`.github/workflows/docker.yml`) —
  multi-platform (amd64 + arm64) build pushed to
  `ghcr.io/sharkyger/mcp-safe-fetch` on `main` and on `v*` tags;
  pull requests get a build-only run (no push). The workflow had been
  dropped during the Python rewrite, leaving no published image; this
  re-enables the pull-based install path. Actions are SHA-pinned.
- **`CLAUDE.md`** — fleet-rules header + what-this-repo-does, so a
  parallel session inherits the identity / versioning / container-only
  / never-test-on-host rules.
- **`.coderabbit.yaml`** — assertive review profile with
  security-critical path instructions for the sanitizer, the MCP
  server's SSRF contract, and the Dockerfile. Completes the tooling
  floor (ruff/mypy/bandit/pip-audit/CI/NOTICE were already present).

- **End-user install guides** under `docs/install/` — a step-by-step,
  non-technical macOS walkthrough (Docker Desktop → pull → Claude
  Desktop config → restart → model rule) in English (`en.md`,
  canonical), German (`de.md`), and French (`fr.md`). Translations carry
  a drift stamp pointing back to `en.md`. Linked from the README via a
  language table.

### Changed

- **README right-sized.** `Supported: macOS only` banner at the very
  top; the long internal "Why this exists" anecdote trimmed to a short
  generic threat note; usage-before-install ordering; the GHCR pull is
  now the documented install (the image is published, public, and
  dogfooded); the minimal `docker run` is shown as already-safe with the
  `--cap-drop/--read-only` flags presented as optional defense-in-depth
  (the SSRF safety lives in the image); corrected `urllib` → stdlib
  `http.client` and the SSRF description to match the resolve-then-pin
  implementation.
- **SSRF protection is now app-layer resolve-then-pin** (the safety
  travels with the image, not with `docker run` flags). The fetch path
  now: rejects IP-literal URLs in every form (canonical + obfuscated
  decimal/octal/hex/IPv4-mapped) and non-http(s) schemes; resolves the
  hostname and refuses if **any** resolved address is private/internal
  (RFC1918, loopback, link-local incl. `169.254.169.254`, CGNAT, IPv6
  ULA/link-local, multicast, reserved/broadcast, unspecified); rejects
  malformed/out-of-range ports; **pins** the connection to the validated IP so the
  address can't change between check and connect (closes the
  DNS-rebinding TOCTOU previously documented as a known limitation); and
  re-validates + re-pins on every redirect hop (manual redirects, capped
  at 5; redirect bodies are discarded unread so a giant 30x body can't
  exhaust memory). Built on stdlib `http.client` (was `urllib`) so the socket can
  be pinned. The blocking fetch now runs in a worker thread so it can't
  stall the MCP stdio event loop.
- **Container egress hardening is now optional defense-in-depth, not
  required.** Reversal of the earlier "container-only egress" plan:
  iptables egress needs `CAP_NET_ADMIN`, a runtime `--cap-add` that
  can't be baked into the image — so a minimal `docker run` would have
  needed a copy-pasted flag to be safe. App-layer is the flag-free-safe
  primary instead. README + SCOPE updated to match.

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
