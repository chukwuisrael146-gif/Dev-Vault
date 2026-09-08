"""HTTPS-only, no redirects/proxies, public DNS validation and pinned connection IP.

An outbound firewall is still required in production as defense in depth.
"""

import http.client
import ipaddress
import socket
import ssl
from urllib.parse import urlsplit

from apps.core.exceptions import DomainError
from apps.core.logging import redact_string


class UnsafeDestination(Exception):
    pass


def destination(url):
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").encode("idna").decode("ascii").lower().rstrip(".")
        if (
            parsed.scheme != "https"
            or not host
            or parsed.port not in (None, 443)
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or len(url) > 1024
            or any(ord(char) < 33 for char in url)
            or redact_string(url) != url
        ):
            raise ValueError
        if any(char not in "abcdefghijklmnopqrstuvwxyz0123456789.-:" for char in host):
            raise ValueError
    except (ValueError, UnicodeError) as exc:
        raise DomainError(
            code="validation_error",
            message="Use HTTPS on port 443 without userinfo, query, fragment, or secrets.",
        ) from exc
    return host, parsed.path or "/"


def public_address(host):
    addresses = list(
        dict.fromkeys(item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM))
    )
    if not addresses or len(addresses) > 32:
        raise UnsafeDestination()
    for value in addresses:
        address = ipaddress.ip_address(value)
        if not address.is_global or address.is_multicast or address.is_reserved:
            raise UnsafeDestination()
    return addresses[0]


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, address):
        super().__init__(host, port=443, timeout=5, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        raw = socket.create_connection((self.address, 443), timeout=self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except Exception:
            raw.close()
            raise


def post_json(url, body, headers):
    host, path = destination(url)
    connection = PinnedHTTPSConnection(host, public_address(host))
    try:
        connection.request(
            "POST",
            path,
            body=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "DevVault-Webhooks/1",
                **headers,
            },
        )
        response = connection.getresponse()
        status = response.status
        response.read(4096)  # Do not persist response bodies, headers or redirects.
        return status
    finally:
        connection.close()
