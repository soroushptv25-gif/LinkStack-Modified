# Part of the Digital Business Card module.
# Shared network safety helpers, used by both the inbound data sources and the
# outbound publish targets so they enforce the exact same rules.
import ipaddress
import socket
from urllib.parse import urlparse

from odoo.exceptions import UserError

# Hard cap on any fetched/sent HTTP body, to keep a hostile or huge peer from
# exhausting memory.
MAX_HTTP_BYTES = 5 * 1024 * 1024  # 5 MB


def assert_url_allowed(url, allow_private=False):
    """SSRF guard: only http(s), and (unless explicitly allowed) refuse any
    host that resolves to a private/internal address."""
    parsed = urlparse(url or '')
    if parsed.scheme not in ('http', 'https'):
        raise UserError("Only http:// and https:// URLs are allowed.")
    host = parsed.hostname
    if not host:
        raise UserError("Invalid URL: no host found.")
    if allow_private:
        return
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise UserError("Could not resolve host '%s': %s" % (host, e))
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise UserError(
                "Refusing to connect to internal address %s. Tick "
                "'Allow internal addresses' if this is intentional." % ip)
