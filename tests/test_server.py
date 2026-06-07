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

from mcp_safe_fetch import search
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
        "http://127.0.0.1./",  # trailing-dot FQDN form
    ],
)
def test_validate_url_blocks_ip_literals(url: str) -> None:
    err = srv._validate_url(url)
    assert err is not None
    assert "ip-literal" in err.lower()


@pytest.mark.parametrize("url", ["http://example.com:99999/", "http://example.com:abc/"])
def test_validate_url_rejects_invalid_port(url: str) -> None:
    err = srv._validate_url(url)
    assert err is not None
    assert "port" in err.lower()


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
        ("224.0.0.1", True),  # multicast
        ("240.0.0.1", True),  # reserved (240/4)
        ("255.255.255.255", True),  # broadcast
        ("0.0.0.0", True),  # unspecified  # noqa: S104
        ("ff02::1", True),  # IPv6 multicast
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


# ── search auth-header parsing (fail-closed, CRLF-safe) ──────────────


class TestParseSearchHeader:
    def test_none_and_blank_return_none(self) -> None:
        assert srv._parse_search_header(None) is None
        assert srv._parse_search_header("   ") is None

    def test_valid_header_parsed(self) -> None:
        assert srv._parse_search_header("Authorization: Bearer tok") == ("Authorization", "Bearer tok")

    def test_value_may_contain_colons(self) -> None:
        # Only the first ':' splits name from value.
        assert srv._parse_search_header("X-Time: 12:30:00") == ("X-Time", "12:30:00")

    def test_malformed_no_colon_raises(self) -> None:
        with pytest.raises(srv.FetchError, match="malformed"):
            srv._parse_search_header("no-colon-here")

    def test_empty_name_raises(self) -> None:
        with pytest.raises(srv.FetchError, match="malformed"):
            srv._parse_search_header(": value-without-name")

    def test_crlf_injection_dropped(self) -> None:
        # An injected CRLF + second header line must be dropped entirely,
        # so a crafted credential cannot smuggle extra request headers.
        name, value = srv._parse_search_header("X-Key: abc\r\nX-Evil: 1")
        assert name == "X-Key"
        assert value == "abc"
        assert "Evil" not in value


# ── search credential handling in _fetch (cross-origin + cleartext) ──


class _FakeResp:
    """Minimal stand-in for http.client.HTTPResponse."""

    def __init__(self, status: int, *, location: str | None = None, body: bytes = b"", reason: str = "OK") -> None:
        self.status = status
        self.reason = reason
        self._location = location
        self._body = body

    def getheader(self, name: str) -> str | None:
        return self._location if name == "Location" else None

    def read(self, _n: int) -> bytes:
        return self._body

    def close(self) -> None:  # pragma: no cover - not exercised
        pass


class _FakeConn:
    def __init__(self, resp: _FakeResp, sink: list[dict[str, str]]) -> None:
        self._resp = resp
        self._sink = sink

    def request(self, _method: str, _target: str, headers: dict[str, str]) -> None:
        self._sink.append(dict(headers))

    def getresponse(self) -> _FakeResp:
        return self._resp

    def close(self) -> None:
        pass


def _patch_fetch(monkeypatch: pytest.MonkeyPatch, responses: list[_FakeResp]) -> list[dict[str, str]]:
    """Patch _fetch's connection + DNS layers; return the list of header
    dicts sent per hop (so tests can assert what reached the wire)."""
    sent: list[dict[str, str]] = []
    it = iter(responses)

    def _fake_make_connection(_scheme: str, _host: str, _port: int, _pinned_ip: str) -> _FakeConn:
        return _FakeConn(next(it), sent)

    monkeypatch.setattr(srv, "_make_connection", _fake_make_connection)
    monkeypatch.setattr(srv, "_resolve_and_validate", lambda _h, _p: "93.184.216.34")
    return sent


def test_fetch_without_credential_sends_no_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = _patch_fetch(monkeypatch, [_FakeResp(200, body=b"ok")])
    assert srv._fetch("https://good.example/") == b"ok"
    assert sent[0]["User-Agent"].startswith("mcp-safe-fetch/")
    assert "X-Token" not in sent[0]


def test_fetch_sends_credential_on_original_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = _patch_fetch(monkeypatch, [_FakeResp(200, body=b"ok")])
    srv._fetch("https://good.example/s?q=x", auth_header=("X-Token", "secret"))
    assert sent[0].get("X-Token") == "secret"


def test_fetch_keeps_credential_on_same_origin_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = _patch_fetch(
        monkeypatch,
        [_FakeResp(302, location="https://good.example/other"), _FakeResp(200, body=b"ok")],
    )
    assert srv._fetch("https://good.example/s?q=x", auth_header=("X-Token", "secret")) == b"ok"
    assert sent[0].get("X-Token") == "secret"
    assert sent[1].get("X-Token") == "secret"


def test_fetch_drops_credential_on_cross_origin_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = _patch_fetch(
        monkeypatch,
        [_FakeResp(302, location="https://evil.example/"), _FakeResp(200, body=b"ok")],
    )
    assert srv._fetch("https://good.example/s?q=x", auth_header=("X-Token", "secret")) == b"ok"
    assert sent[0].get("X-Token") == "secret"  # original origin: sent
    assert "X-Token" not in sent[1]  # cross-origin: dropped


def test_fetch_refuses_credential_over_http(monkeypatch: pytest.MonkeyPatch) -> None:
    # Cleartext refusal: a credential must never be sent over plain http.
    monkeypatch.setattr(srv, "_resolve_and_validate", lambda _h, _p: "93.184.216.34")
    monkeypatch.setattr(srv, "_make_connection", lambda *_a: pytest.fail("must not open a connection before refusing"))
    with pytest.raises(srv.FetchError, match="cleartext"):
        srv._fetch("http://good.example/s?q=x", auth_header=("X-Token", "secret"))


# ── search tool handler dispatch ─────────────────────────────────────


async def test_handle_search_unconfigured_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(search.ENV_URL, raising=False)
    monkeypatch.delenv(search.ENV_HEADER, raising=False)
    out = await srv._handle_search({"query": "rust"})
    assert "no search backend configured" in out[0].text


async def test_handle_search_missing_query() -> None:
    out = await srv._handle_search({})
    assert "missing or invalid 'query'" in out[0].text


async def test_handle_search_rejects_control_char_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(search.ENV_URL, "https://api.example/s?q={query}")
    out = await srv._handle_search({"query": "evil\nLocation: x"})
    assert "control" in out[0].text.lower()


async def test_handle_search_happy_path_wraps_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(search.ENV_URL, "https://api.example/s?q={query}")
    monkeypatch.delenv(search.ENV_HEADER, raising=False)
    _patch_fetch(monkeypatch, [_FakeResp(200, body=b"<html>results</html>")])
    out = await srv._handle_search({"query": "rust async"})
    text = out[0].text
    assert "<UNTRUSTED-WEB" in text
    # the percent-encoded query is what reached the backend URL
    assert "rust%20async" in text
