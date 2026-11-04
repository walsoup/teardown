"""Cookies, CSRF, path checks, and request metadata."""
import hashlib
import hmac
import json
import os
import re
from urllib.parse import urlparse

from config import ALLOWED_FILE_EXT, COOKIE_KEY, DATA, YOUTUBE_HOSTS

def _sign_ids(ids):
    return hmac.new(COOKIE_KEY, ".".join(ids).encode(), hashlib.sha256).hexdigest()[:32]

def _valid_cookie_ids(header):
    for part in (header or "").split(";"):
        part = part.strip()
        if part.startswith("td_jobs="):
            segs = part[8:].split(".")
            if len(segs) >= 2:
                ids, sig = segs[:-1], segs[-1]
                expected = _sign_ids(ids)
                if (all(re.fullmatch(r"[0-9a-f]{32}", x) for x in ids)
                        and len(sig) == len(expected)
                        and hmac.compare_digest(expected, sig)):
                    return ids
    return []


def cookie_header(ids):
    """Set-Cookie value. Secure only when the process is not bound to loopback."""
    payload = ".".join(ids) + "." + _sign_ids(ids)
    flags = "Path=/; Max-Age=86400; HttpOnly; SameSite=Lax"
    host = os.environ.get("HOST", "127.0.0.1")
    if host not in ("127.0.0.1", "localhost", "::1"):
        flags += "; Secure"
    return f"td_jobs={payload}; {flags}"


def youtube_url_ok(url):
    parsed = urlparse(url or "")
    return (parsed.scheme == "https" and parsed.hostname in YOUTUBE_HOSTS
            and not parsed.username and not parsed.password)
def csrf_token():
    return hmac.new(COOKIE_KEY, b"teardown-csrf-v1", hashlib.sha256).hexdigest()


def redact(msg):
    text = str(msg)
    key = os.environ.get("MODEL_API_KEY") or ""
    if key and len(key) >= 8 and key in text:
        text = text.replace(key, "[redacted]")
    return text[:300]


def client_ip(handler):
    """Peer address, unless the peer is an explicitly trusted proxy."""
    peer = handler.client_address[0]
    trusted = {p.strip() for p in os.environ.get("TEARDOWN_TRUSTED_PROXY", "").split(",") if p.strip()}
    if peer in trusted:
        forwarded = (handler.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        if forwarded:
            return forwarded
    return peer


def json_for_script(payload):
    """JSON that cannot close a surrounding script tag."""
    return (json.dumps(payload)
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("&", "\\u0026"))


def safe_job_path(job_id, rel, data_root=None):
    """Resolved file inside the job directory, or None.

    Rejects `..`, absolute paths, and extensions that are not guide artifacts.
    The first directory under the data root must be the authorized job id.
    """
    root = os.path.realpath(data_root or DATA)
    if not job_id or not re.fullmatch(r"[\w-]+", job_id):
        return None
    if rel is None or rel == "" or rel.startswith(("/", "\\")) or "\\" in rel:
        return None
    parts = rel.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return None
    if os.path.splitext(parts[-1])[1].lower() not in ALLOWED_FILE_EXT:
        return None
    job_root = os.path.realpath(os.path.join(root, job_id))
    target = os.path.realpath(os.path.join(job_root, *parts))
    try:
        if os.path.commonpath([target, root]) != root:
            return None
        if os.path.commonpath([job_root, root]) != root:
            return None
        if os.path.commonpath([target, job_root]) != job_root:
            return None
    except ValueError:
        return None
    relative = os.path.relpath(target, root)
    if relative.split(os.sep)[0] != job_id:
        return None
    return target if os.path.isfile(target) else None


def parse_byte_range(header, size):
    """Return ('full'|'partial'|'unsat', start, end) for one Range header."""
    if size <= 0:
        return "unsat", None, None
    if not header:
        return "full", 0, size - 1
    match = re.match(r"bytes=(\d*)-(\d*)$", header.strip())
    if not match or not (match.group(1) or match.group(2)):
        return "full", 0, size - 1
    if match.group(1):
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else size - 1
    else:
        start = max(0, size - int(match.group(2)))
        end = size - 1
    if start >= size or start > end:
        return "unsat", None, None
    return "partial", start, min(end, size - 1)


def origin_ok(handler):
    """Same-origin POSTs only. `Origin: null` (sent by some Android WebViews
    and sandboxed/privacy contexts on genuine same-site form posts) and a
    missing Origin fall through to the loopback allowance; the HMAC form
    token checked after this remains the cross-site gate, and a cross-site
    page cannot strip its real Origin the way these contexts do. A cross-site
    sandboxed iframe can force `null`, but its Referer still leaks and the
    token check still rejects it."""
    origin = handler.headers.get("Origin")
    host = handler.headers.get("Host", "")
    if origin and origin != "null":
        parsed = urlparse(origin)
        return parsed.netloc == host and parsed.scheme in ("http", "https")
    ref = handler.headers.get("Referer")
    if origin == "null" and ref:
        parsed = urlparse(ref)
        if parsed.netloc != host or parsed.scheme not in ("http", "https"):
            return False
    return handler.client_address[0] in ("127.0.0.1", "::1")


def csrf_ok(header_value, form_value=""):
    expected = csrf_token()
    supplied = header_value or form_value or ""
    if len(supplied) != len(expected):
        return False
    return hmac.compare_digest(expected, supplied)
