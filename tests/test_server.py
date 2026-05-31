"""Smoke tests for mcp-safe-fetch's URL validation and SSRF block.

These tests do NOT spin up the actual MCP server. They exercise
_validate_url and _is_private_host directly. Network calls inside
_is_private_host (DNS resolution) are mocked via monkeypatch so the
suite stays hermetic.
"""

from __future__ import annotations

import socket
from unittest.mock import patch

import pytest

from mcp_safe_fetch import server as srv

# ── URL scheme + structure ──────────────────────────────────────────


@pytest.mark.parametrize(
    "url, expected_fragment",
    [
        ("file:///etc/passwd", "unsupported scheme"),
        ("ftp://example.com/", "unsupported scheme"),
        ("javascript:alert(1)", "unsupported scheme"),
        ("data:text/html,foo", "unsupported scheme"),
        ("http://", "no host"),
        ("not a url", "unsupported scheme"),
    ],
)
def test_validate_url_rejects_bad_schemes_and_structures(url: str, expected_fragment: str) -> None:
    err = srv._validate_url(url)
    assert err is not None
    assert expected_fragment in err.lower()


# ── SSRF: literal IP block ──────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://10.0.0.5/",
        "http://172.16.0.1/",
        "http://192.168.1.1/",
        "http://169.254.169.254/",  # AWS metadata service
        "http://[::1]/",
    ],
)
def test_validate_url_blocks_direct_private_ips(url: str) -> None:
    err = srv._validate_url(url)
    assert err is not None
    assert "private" in err.lower() or "internal" in err.lower()


# ── SSRF: reserved hostnames ────────────────────────────────────────


def test_validate_url_blocks_localhost_literal() -> None:
    err = srv._validate_url("http://localhost/foo")
    assert err is not None
    assert "private" in err.lower() or "internal" in err.lower()


# ── SSRF: DNS resolution to private IP ──────────────────────────────


def _fake_getaddrinfo(addr_str: str):
    """Return a fake getaddrinfo result tuple list."""

    def _impl(*_args, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (addr_str, 0))]

    return _impl


def test_validate_url_blocks_dns_resolution_to_private_ip() -> None:
    # evil-rebind.example resolves (via fake) to 192.168.1.1
    with patch("mcp_safe_fetch.server.socket.getaddrinfo", _fake_getaddrinfo("192.168.1.1")):
        err = srv._validate_url("http://evil-rebind.example/")
    assert err is not None
    assert "private" in err.lower() or "internal" in err.lower()


def test_validate_url_accepts_public_dns_resolution() -> None:
    # Resolves to a public IP — should pass validation.
    with patch("mcp_safe_fetch.server.socket.getaddrinfo", _fake_getaddrinfo("93.184.216.34")):
        err = srv._validate_url("http://example.com/")
    assert err is None


# ── Redirect handler ────────────────────────────────────────────────


def test_redirect_handler_rejects_private_redirect() -> None:
    import urllib.error

    handler = srv._ValidatingRedirectHandler()
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        handler.redirect_request(None, None, 302, "Found", {}, "http://127.0.0.1/")
    assert excinfo.value.code == 403
