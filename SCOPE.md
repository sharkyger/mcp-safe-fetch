# Scope

`mcp-safe-fetch` provides one capability for one client class: a
Layer-2-sanitized, `<UNTRUSTED-WEB>`-wrapped fetch tool for Claude
Desktop (and any other MCP client) so indirect prompt injection in
fetched web content does not reach the model as instructions.

## Carve-outs (what this project does NOT do)

Five hard boundaries. Feature requests outside these lanes will be
politely closed with a pointer to the appropriate cousin project.

1. **Not a secrets vault.** Token storage, vaulting, rotation, and
   per-tool secret scoping belong to
   [vault](https://github.com/vaultmcp/vault). We don't touch your
   MCP auth.

2. **Not a network proxy.** Outbound traffic scanning, DNS-layer
   filtering, and protocol-aware policy belong to
   [pipelock](https://github.com/luckyPipewrench/pipelock). We don't
   intercept anything the host or other processes do; we only fetch
   URLs we're asked to fetch, and we only sanitize content we
   ourselves return.

3. **Not extra process containment beyond Docker.** seccomp / AppArmor
   / SELinux profiles are out of scope. The SSRF boundary lives in the
   **app code that ships in the image** (resolve-then-pin: reject
   IP-literals, validate every resolved address, pin the socket to the
   validated IP, re-validate each redirect hop), so a flag-free `docker
   run` is already safe. Container egress hardening (`--cap-drop=ALL
   --read-only`, or a restricted network / `NET_ADMIN` iptables egress
   policy) is **optional defense-in-depth** — useful but not required,
   and deliberately not baked in because it would force a runtime
   `--cap-add` the user must paste. If that's not enough for your threat
   model, layer in additional sandboxing at the runtime level.

4. **Not LLM-runtime detection.** We do not analyze the model's
   reasoning, output, or tool-call decisions. We only sanitize the
   data that reaches the model from web fetches. What the model does
   with cleaned content is the model's lane.

5. **Not multi-protocol scanning.** We do http and https only. No
   ftp, no smb, no file://, no custom application protocols. The MCP
   surface is intentionally narrow.

## How feature requests are evaluated

Four-step filter:

1. **Is it inside the carve-outs above?** If not, close with a
   pointer to the right tool.
2. **Does it raise the indirect-injection defense bar?** If yes,
   triage by effort + risk. If no (e.g. "add browser automation"),
   close as out-of-scope.
3. **Does it complicate the install or runtime surface?** If yes,
   the bar for accepting it is higher — we trade more vector
   coverage for more attack surface, and the project's premise is
   that the trade only makes sense for vectors the operator actually
   sees in the wild.
4. **Is there an existing project that does it better?** If yes,
   point users there. Composing > monolithizing.

## Planned phase scope

- **v0.1.0** (this release) — `fetch_url` tool with the safe-fetch
  Layer-2 sanitizer, SSRF block, redirect re-validation, `<UNTRUSTED-WEB>`
  wrap.
- **v0.2.0** — proxy mode: spawn another MCP server as a child
  process, sanitize all responses flowing back to the model. Same
  wrap tag, same model rule, same install pattern.
- **v0.3.0+** — TBD; deferred until v0.2.0 ships and user feedback
  surfaces real needs. Likely candidates: configurable output cap,
  configurable timeout, proxy-everything-by-default ergonomics.

## What "stable" means here

`v1.0.0` is reserved for the first reliably-tested stable. Stable
means: production-grade dogfooding across realistic distros and
clients, full Tier 1 + Tier 2 + Tier 3 review history clean, no
known critical security findings, and a documented support window.
The historical v1.0.0 tag on this repo (from the pre-yank parallel
session) did not meet these criteria; current versioning starts at
`v0.1.0`.
