"""Fetching a link that came from a scraped post or from the AI agent, without letting it reach this
laptop or the home network (SSRF).

A post's apply link is written by whoever posted it. Opened blindly, "http://192.168.1.1/..." or a
link that redirects to "http://localhost:5000/api/clear" would make this app talk to the router or
to itself. Here every hop of a redirect chain is checked before it is requested: http(s) only, and
the host must resolve to public internet addresses only.

Left over (stated, not hidden): the name is looked up once for the check and again by requests for
the connection, so a server that changes its DNS answer in between could still slip through. Closing
that needs pinning the IP into the connection, which breaks HTTPS name checks; the risk left is small
because the attacker would have to own a domain *and* time the change.
"""
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests

MAX_REDIRECTS = 6


class BlockedAddress(requests.RequestException):
    """The link (or one of its redirects) points at a private, local or non-http address."""


def _ip_ok(text: str) -> bool:
    ip = ipaddress.ip_address(text.split("%", 1)[0])
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def public_host(url: str) -> bool:
    """True only for http(s) URLs whose host resolves to public addresses (no localhost, LAN,
    carrier NAT, link-local / cloud metadata, reserved)."""
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            return False
        if p.username or p.password:          # "http://good.com@10.0.0.1/" tricks
            return False
        port = p.port or (443 if p.scheme == "https" else 80)
        infos = socket.getaddrinfo(p.hostname, port, proto=socket.IPPROTO_TCP)
        return bool(infos) and all(_ip_ok(info[4][0]) for info in infos)
    except (ValueError, OSError, UnicodeError):
        return False


def safe_get(url: str, *, headers=None, timeout: float = 12.0, stream: bool = True, session=None):
    """requests.get that follows redirects by hand, checking every hop with public_host.
    Returns (response, chain); raises BlockedAddress for a private hop. The caller closes the response."""
    getter = session.get if session is not None else requests.get
    chain = []
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        if not public_host(current):
            raise BlockedAddress(f"refused a non-public address: {urlparse(current).hostname or current}")
        r = getter(current, headers=headers, timeout=timeout, allow_redirects=False, stream=stream)
        chain.append(current)
        if r.is_redirect and r.headers.get("location"):
            nxt = urljoin(current, r.headers["location"])
            r.close()
            current = nxt
            continue
        return r, chain
    raise requests.TooManyRedirects(f"more than {MAX_REDIRECTS} redirects")
