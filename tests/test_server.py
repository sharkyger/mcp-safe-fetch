"""Tests for mcp-safe-fetch's URL validation and resolve-then-pin SSRF.

These tests do NOT make real network calls. ``_validate_url`` is pure
(no DNS). ``_resolve_and_validate`` resolves via ``socket.getaddrinfo``,
which is monkeypatched so the suite stays hermetic.
"""

from __future__ import annotations

import ipaddress
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


# ── SSRF: IP-literal block (canonical + obfuscated) ─────────────────


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://10.0.0.5/",
        "http://172.16.0.1/",
        "http://192.168.1.1/",
        "http://169.254.169.254/",  # AWS metadata service
        "http://8.8.8.8/",  # even a PUBLIC IP literal is refused
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",  # IPv4-mapped IPv6 literal
        "http://2130706433/",  # decimal form of 127.0.0.1
        "http://0x7f.0.0.1/",  # hex-octet form
        "http://0177.0.0.1/",  # octal-octet form
    ],
)
def test_validate_url_blocks_ip_literals(url: str) -> None:
    err = srv._validate_url(url)
    assert err is not None
    assert "ip-literal" in err.lower()


def test_validate_url_blocks_localhost_literal() -> None:
    err = srv._validate_url("http://localhost/foo")
    assert err is not None
    assert "private" in err.lower() or "internal" in err.lower()


def test_validate_url_accepts_plain_hostname() -> None:
    # _validate_url is DNS-free; a normal hostname passes the pre-flight.
    assert srv._validate_url("http://example.com/path?q=1") is None
    assert srv._validate_url("https://sub.example.org/") is None


# ── _is_ip_literal helper ───────────────────────────────────────────


@pytest.mark.parametrize(
    "host, is_literal",
    [
        ("127.0.0.1", True),
        ("::1", True),
        ("2130706433", True),
        ("0x7f000001", True),
        ("0177.0.0.1", True),
        ("example.com", False),
        ("sub.example.org", False),
        ("123.example.com", False),  # numeric LABEL but a real hostname
        ("my-host123", False),
    ],
)
def test_is_ip_literal(host: str, is_literal: bool) -> None:
    assert srv._is_ip_literal(host) is is_literal


# ── _ip_is_private helper (incl. IPv4-mapped IPv6) ──────────────────


@pytest.mark.parametrize(
    "ip, private",
    [
        ("127.0.0.1", True),
        ("10.1.2.3", True),
        ("169.254.169.254", True),
        ("100.64.0.1", True),  # CGNAT
        ("::1", True),
        ("fe80::1", True),
        ("fc00::1", True),
        ("::ffff:127.0.0.1", True),  # mapped loopback must be caught
        ("8.8.8.8", False),
        ("93.184.216.34", False),
        ("2606:2800:220:1:248:1893:25c8:1946", False),
    ],
)
def test_ip_is_private(ip: str, private: bool) -> None:
    assert srv._ip_is_private(ipaddress.ip_address(ip)) is private


# ── resolve-then-pin: _resolve_and_validate ─────────────────────────


def _fake_getaddrinfo(*addrs: str):
    """Fake getaddrinfo returning one SOCK_STREAM record per address."""

    def _impl(*_args, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, 0)) for a in addrs]

    return _impl


def test_resolve_and_validate_blocks_private_resolution() -> None:
    with (
        patch("mcp_safe_fetch.server.socket.getaddrinfo", _fake_getaddrinfo("192.168.1.1")),
        pytest.raises(srv.FetchError, match="private/internal"),
    ):
        srv._resolve_and_validate("evil-rebind.example", 80)


def test_resolve_and_validate_rejects_mixed_public_and_private() -> None:
    # Split-horizon: a public AND a private record. Must refuse, not
    # cherry-pick the public one.
    with (
        patch("mcp_safe_fetch.server.socket.getaddrinfo", _fake_getaddrinfo("93.184.216.34", "10.0.0.1")),
        pytest.raises(srv.FetchError, match="private/internal"),
    ):
        srv._resolve_and_validate("mixed.example", 80)


def test_resolve_and_validate_returns_pinned_public_ip() -> None:
    with patch("mcp_safe_fetch.server.socket.getaddrinfo", _fake_getaddrinfo("93.184.216.34")):
        assert srv._resolve_and_validate("example.com", 443) == "93.184.216.34"


def test_resolve_and_validate_raises_on_dns_failure() -> None:
    def _boom(*_a, **_k):
        raise socket.gaierror("name or service not known")

    with (
        patch("mcp_safe_fetch.server.socket.getaddrinfo", _boom),
        pytest.raises(srv.FetchError, match="DNS resolution failed"),
    ):
        srv._resolve_and_validate("nope.invalid", 80)


# ── redirect re-validation (the manual loop uses _validate_url) ──────


@pytest.mark.parametrize(
    "redirect_target",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://127.0.0.1/",
        "file:///etc/passwd",
        "http://10.0.0.1/",
    ],
)
def test_redirect_targets_are_rejected_by_validation(redirect_target: str) -> None:
    # _fetch re-runs _validate_url on every hop; a malicious Location
    # therefore fails the same pre-flight as the original URL.
    assert srv._validate_url(redirect_target) is not None
