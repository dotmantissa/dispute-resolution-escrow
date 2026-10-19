"""Public evidence fetching with DNS validation and connection-level address pinning."""
from dataclasses import dataclass
import hashlib
import http.client
import ipaddress
import re
import socket
import ssl
import time
from urllib.parse import urljoin, urlsplit

MAX_DOCUMENT_BYTES = 32768
_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_URL = re.compile(r"https://(" + _LABEL + r"(?:\." + _LABEL + r")+)(/[^\s#]*)?")
_LOCAL_SUFFIXES = ('.localhost', '.local', '.internal', '.test', '.invalid', '.home',
                   '.localdomain', '.onion', '.arpa')


def validate_url(url: str) -> str:
    if not isinstance(url, str) or len(url) > 2048:
        raise ValueError('Invalid evidence URL')
    match = _URL.fullmatch(url)
    if match is None:
        raise ValueError('Use a public HTTPS DNS URL without ports, userinfo or fragments')
    host = match.group(1).lower()
    if len(host) > 253 or re.fullmatch(r'[a-z]{2,63}', host.rsplit('.', 1)[1]) is None:
        raise ValueError('Use an alphabetic public DNS suffix, not an IP representation')
    if host.endswith(_LOCAL_SUFFIXES):
        raise ValueError('Use a public DNS hostname')
    return host


def _public_addresses(host: str) -> list[str]:
    addresses = list(dict.fromkeys(item[4][0] for item in socket.getaddrinfo(
        host, 443, type=socket.SOCK_STREAM)))
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ValueError('Evidence DNS must resolve exclusively to public global addresses')
    return addresses


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, address: str, timeout: float):
        super().__init__(host, port=443, timeout=timeout, context=ssl.create_default_context())
        self._pinned_address = address

    def connect(self):
        # DNS is not repeated by the connection. TLS still verifies the original host.
        sock = socket.create_connection((self._pinned_address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except BaseException:
            sock.close()
            raise


@dataclass(frozen=True)
class Document:
    """A public HTTPS location and SHA-256 of its exact raw UTF-8 response bytes."""
    url: str
    sha256: str

    def __post_init__(self):
        validate_url(self.url)
        if not isinstance(self.sha256, str) or not re.fullmatch(r'[0-9a-f]{64}', self.sha256):
            raise ValueError('SHA-256 must be 64 lowercase hexadecimal characters')

    @classmethod
    def from_bytes(cls, url: str, content: bytes):
        if not 0 < len(content) <= MAX_DOCUMENT_BYTES:
            raise ValueError('Document must contain 1..32768 bytes')
        text = content.decode('utf-8')
        if not text.strip() or '\x00' in text:
            raise ValueError('Document must be nonempty UTF-8 text without NUL')
        return cls(url, hashlib.sha256(content).hexdigest())

    @classmethod
    def fetch(cls, url: str, timeout: float = 30, max_redirects: int = 5):
        if timeout <= 0 or not 0 <= max_redirects <= 10:
            raise ValueError('Invalid evidence fetch limits')
        original = url
        deadline = time.monotonic() + timeout
        for hop in range(max_redirects + 1):
            host = validate_url(url)
            addresses = _public_addresses(host)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Evidence request exceeded its time budget')
            parsed = urlsplit(url)
            target = parsed.path or '/'
            if parsed.query:
                target += '?' + parsed.query
            redirected = False
            last_error = None
            for index, address in enumerate(addresses):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('Evidence request exceeded its time budget')
                per_address = min(remaining, max(1.0, remaining / (len(addresses) - index)))
                connection = _PinnedHTTPSConnection(host, address, per_address)
                try:
                    connection.request('GET', target, headers={
                        'Host': host, 'User-Agent': 'genlayer-dispute-escrow/2.0',
                        'Accept-Encoding': 'identity', 'Connection': 'close'})
                    response = connection.getresponse()
                    if response.status in (301, 302, 303, 307, 308):
                        location = response.getheader('Location')
                        if not location or hop == max_redirects:
                            raise ValueError('Evidence redirect limit exceeded or missing location')
                        url = urljoin(url, location)
                        validate_url(url)
                        redirected = True
                        break
                    if response.status != 200:
                        raise ValueError(f'Evidence returned HTTP {response.status}')
                    length = response.getheader('Content-Length')
                    if length and int(length) > MAX_DOCUMENT_BYTES:
                        raise ValueError('Document exceeds 32768 bytes')
                    body = bytearray()
                    while len(body) <= MAX_DOCUMENT_BYTES:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError('Evidence request exceeded its time budget')
                        if connection.sock is not None:
                            connection.sock.settimeout(remaining)
                        chunk = response.read1(min(4096, MAX_DOCUMENT_BYTES + 1 - len(body)))
                        if not chunk:
                            return cls.from_bytes(original, bytes(body))
                        body.extend(chunk)
                    raise ValueError('Document exceeds 32768 bytes')
                except (OSError, http.client.HTTPException) as error:
                    last_error = error
                finally:
                    connection.close()
            if not redirected:
                raise last_error or TimeoutError('No public evidence address responded')
        raise ValueError('Evidence redirect limit exceeded')
