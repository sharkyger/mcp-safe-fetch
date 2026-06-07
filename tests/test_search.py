"""Tests for mcp_safe_fetch.search — env config + query→URL templating.

The ``search`` tool turns a query into a URL by substituting it into an
operator-configured template, then runs that URL through the exact same
hardened fetch path as ``fetch_url``. This module covers the pure logic:
env-only config load (fail-closed when unset), template validation,
query validation, and the URL build (with percent-encoding of the query
so it cannot break the envelope or inject extra params).

No search provider is bundled — config ships empty. ``load_config``
returns ``None`` until the operator sets ``MCP_SAFE_FETCH_SEARCH_URL``,
and the server fails closed on that. The template/query validators are
byte-identical to safe-fetch so the fleet behaves the same.
"""

from __future__ import annotations

import pytest

from mcp_safe_fetch import search

# ── template validation (mirrors safe-fetch) ─────────────────────────


class TestTemplateError:
    def test_valid_https_template_passes(self) -> None:
        assert search.template_error("https://api.example.com/search?q={query}") is None

    def test_valid_http_template_passes(self) -> None:
        assert search.template_error("http://localhost:8888/search?q={query}") is None

    def test_missing_placeholder_rejected(self) -> None:
        err = search.template_error("https://api.example.com/search?q=foo")
        assert err is not None and "{query}" in err

    def test_empty_rejected(self) -> None:
        assert search.template_error("") is not None

    def test_non_http_scheme_rejected(self) -> None:
        err = search.template_error("ftp://example.com/?q={query}")
        assert err is not None and "scheme" in err.lower()

    def test_placeholder_in_host_rejected(self) -> None:
        err = search.template_error("https://{query}/")
        assert err is not None and "host" in err.lower()

    def test_placeholder_as_subdomain_rejected(self) -> None:
        err = search.template_error("https://{query}.example.com/?x=1")
        assert err is not None and "host" in err.lower()

    def test_placeholder_in_port_rejected(self) -> None:
        err = search.template_error("https://example.com:{query}/s")
        assert err is not None and "host" in err.lower()

    def test_no_host_rejected(self) -> None:
        err = search.template_error("https:///search?q={query}")
        assert err is not None and "host" in err.lower()

    def test_control_char_in_template_rejected(self) -> None:
        err = search.template_error("https://x.example/s?q={query}\nEvil: 1")
        assert err is not None and "control" in err.lower()

    def test_placeholder_in_fragment_rejected(self) -> None:
        err = search.template_error("https://api.example.com/#q={query}")
        assert err is not None and "fragment" in err.lower()

    def test_placeholder_in_query_with_fragment_present_ok(self) -> None:
        assert search.template_error("https://api.example.com/s?q={query}#sec") is None


# ── query validation ─────────────────────────────────────────────────


class TestQueryError:
    def test_normal_query_passes(self) -> None:
        assert search.query_error("rust async runtime") is None

    def test_empty_rejected(self) -> None:
        assert search.query_error("") is not None

    def test_whitespace_only_rejected(self) -> None:
        assert search.query_error("   ") is not None

    def test_control_char_rejected(self) -> None:
        err = search.query_error("evil\nLocation: x")
        assert err is not None and "control" in err.lower()

    def test_del_and_c1_controls_rejected(self) -> None:
        assert search.query_error("a\x7fb") is not None
        assert search.query_error("a\x85b") is not None

    def test_printable_unicode_allowed(self) -> None:
        # Accented Latin (>= 0xA0) must NOT be treated as a control char.
        assert search.query_error("café münchen") is None


# ── URL building (percent-encoding is the envelope-safety invariant) ──


class TestBuildSearchUrl:
    def test_spaces_percent_encoded(self) -> None:
        url = search.build_search_url("https://x.example/s?q={query}", "rust async")
        assert url == "https://x.example/s?q=rust%20async"

    def test_ampersand_encoded_so_no_param_injection(self) -> None:
        url = search.build_search_url("https://x.example/s?q={query}", "a&admin=1")
        assert url == "https://x.example/s?q=a%26admin%3D1"
        assert "&admin=1" not in url

    def test_angle_brackets_and_quotes_encoded(self) -> None:
        url = search.build_search_url("https://x.example/s?q={query}", '"><UNTRUSTED-WEB>')
        for ch in ('"', "<", ">"):
            assert ch not in url

    def test_placeholder_fully_replaced(self) -> None:
        url = search.build_search_url("https://x.example/s?q={query}", "hi")
        assert "{query}" not in url


# ── config load: env-only, fail-closed when empty ───────────────────


class TestLoadConfig:
    def test_returns_none_when_nothing_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(search.ENV_URL, raising=False)
        monkeypatch.delenv(search.ENV_HEADER, raising=False)
        assert search.load_config() is None

    def test_blank_url_treated_as_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(search.ENV_URL, "   ")
        assert search.load_config() is None

    def test_loads_url_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(search.ENV_URL, "https://x.example/s?q={query}")
        monkeypatch.delenv(search.ENV_HEADER, raising=False)
        cfg = search.load_config()
        assert cfg is not None
        assert cfg.url_template == "https://x.example/s?q={query}"
        assert cfg.auth_header is None

    def test_loads_auth_header_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(search.ENV_URL, "https://x.example/s?q={query}")
        monkeypatch.setenv(search.ENV_HEADER, "X-Subscription-Token: secret")
        cfg = search.load_config()
        assert cfg is not None
        assert cfg.auth_header == "X-Subscription-Token: secret"

    def test_blank_auth_header_is_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(search.ENV_URL, "https://x.example/s?q={query}")
        monkeypatch.setenv(search.ENV_HEADER, "")
        cfg = search.load_config()
        assert cfg is not None
        assert cfg.auth_header is None

    def test_url_template_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(search.ENV_URL, "  https://x.example/s?q={query}  ")
        cfg = search.load_config()
        assert cfg is not None
        assert cfg.url_template == "https://x.example/s?q={query}"
