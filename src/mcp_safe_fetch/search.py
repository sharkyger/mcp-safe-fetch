"""Web-search support for mcp-safe-fetch.

A search is "fetch a URL the user templated from a query." mcp-safe-fetch
ships with **no** search provider configured — the user supplies a URL
template (and an optional auth header) for whatever search backend they
choose. The query is percent-encoded and substituted into the template;
the resulting URL is then run through the exact same hardened fetch +
Layer-2 sanitizer + ``<UNTRUSTED-WEB>`` envelope path as a plain
``fetch_url``. Search results are untrusted data, identical to a fetched
page.

This module holds the pure, host-independent logic:

- ``load_config`` — read the (optional) search backend from the
  environment.
- ``template_error`` / ``query_error`` — input validation.
- ``build_search_url`` — query→URL with percent-encoding (the first line
  of envelope-breakout defense; the in-server ``_sanitize_envelope_url``
  html-escape is the second).

Config is **env-only** here, on purpose. mcp-safe-fetch runs inside an
ephemeral, read-only container that Claude Desktop (or any MCP client)
spawns per session, so there is no persistent config file to read or
write — the backend is passed in via ``docker run -e`` from the client's
MCP server entry. The companion safe-fetch CLI, which runs on a host,
additionally supports a ``search.json`` file + setup wizard; the
validation logic below (``template_error`` / ``query_error`` /
``build_search_url``) is byte-identical to safe-fetch so the fleet
behaves the same.

There is no bundled allowlist and no bundled provider: ``load_config``
returns ``None`` until the user opts in, and the server fails closed on
that. The auth header is sent as an HTTP request header by the server,
never interpolated into the URL, so a provider key never reaches the
``<UNTRUSTED-WEB url=...>`` envelope the agent reads.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import quote, urlparse

# Query placeholder the user puts in their URL template.
QUERY_PLACEHOLDER = "{query}"

# Environment variables the search backend is configured through. The
# header var is read by the server and sent as an HTTP request header
# inside the container; it is never interpolated into the URL.
ENV_URL = "MCP_SAFE_FETCH_SEARCH_URL"
ENV_HEADER = "MCP_SAFE_FETCH_SEARCH_HEADER"


def _has_control_chars(s: str) -> bool:
    # C0 (0x00-0x1f), DEL (0x7f), and C1 (0x80-0x9f) controls — matches the
    # sanitizer's envelope-URL control class (_URL_CONTROL_RE).
    return any(ord(c) < 0x20 or 0x7F <= ord(c) <= 0x9F for c in s)


@dataclass
class SearchConfig:
    """A configured search backend. ``auth_header`` is a full header line
    (e.g. ``"X-Subscription-Token: abc"``) sent inside the container."""

    url_template: str
    auth_header: str | None = None


def load_config() -> SearchConfig | None:
    """Load the search config from the environment.

    Returns ``None`` when nothing is configured — the caller must fail
    closed. A blank/whitespace-only ``ENV_URL`` is treated as unset. A
    blank ``ENV_HEADER`` means "no auth header"; the value is otherwise
    forwarded verbatim (the server parses + validates it before use).
    """
    env_url = os.environ.get(ENV_URL, "").strip()
    if not env_url:
        return None
    env_header = (os.environ.get(ENV_HEADER) or "").strip()
    return SearchConfig(url_template=env_url, auth_header=env_header or None)


def template_error(template: str) -> str | None:
    """Return an error message if the URL template is unusable, else None.

    Beyond scheme + placeholder presence, this pins the host: the
    ``{query}`` placeholder must live in the path or query string, never
    in the scheme or netloc, so the (attacker-influenceable) query can
    never redirect the request to a different host or port.
    """
    if not template or not template.strip():
        return "search URL template is required"
    if _has_control_chars(template):
        return "search URL template contains control characters"
    if QUERY_PLACEHOLDER not in template:
        return f"search URL template must contain the {QUERY_PLACEHOLDER} placeholder"
    # Parse the raw template directly and require the placeholder to live in
    # the path/query, not the scheme or netloc — so the query can never
    # control the destination host or port.
    parsed = urlparse(template)
    if parsed.scheme not in ("http", "https"):
        return f"unsupported scheme {parsed.scheme!r}; only http/https allowed"
    if QUERY_PLACEHOLDER in parsed.scheme or QUERY_PLACEHOLDER in parsed.netloc:
        return f"the {QUERY_PLACEHOLDER} placeholder must be in the path or query string, not the host"
    if QUERY_PLACEHOLDER in parsed.fragment:
        # A fragment (#...) never leaves the client, so the query would
        # never reach the backend — every search would send no query.
        return f"the {QUERY_PLACEHOLDER} placeholder must be in the path or query string, not the URL fragment"
    if not parsed.netloc:
        return "search URL template has no host"
    return None


def query_error(query: str) -> str | None:
    """Return an error message if the query is unusable, else None."""
    if not query or not query.strip():
        return "search query is required"
    if _has_control_chars(query):
        return "query contains control characters"
    return None


def build_search_url(template: str, query: str) -> str:
    """Substitute the percent-encoded query into the template.

    ``safe=""`` encodes everything reserved — spaces, ``&``, ``<``,
    ``>``, ``"`` — so the query cannot inject extra params or smuggle
    envelope metacharacters into the URL.
    """
    return template.replace(QUERY_PLACEHOLDER, quote(query, safe=""))
