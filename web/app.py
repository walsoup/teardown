"""teardown web app - upload or paste a link, get an illustrated guide.

Run with `python web/app.py`. Sibling modules live in this directory, which is
put on sys.path so the script and `import web.app` share one copy of them.
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from http_util import (  # noqa: E402
    _sign_ids,
    _valid_cookie_ids,
    client_ip,
    cookie_header,
    csrf_ok,
    csrf_token,
    new_session_cookie,
    json_for_script,
    origin_ok,
    parse_byte_range,
    redact,
    safe_job_path,
    youtube_url_ok,
)
from server import main  # noqa: E402

__all__ = [
    "client_ip",
    "cookie_header",
    "csrf_ok",
    "csrf_token",
    "new_session_cookie",
    "json_for_script",
    "main",
    "origin_ok",
    "parse_byte_range",
    "redact",
    "safe_job_path",
    "youtube_url_ok",
    "_sign_ids",
    "_valid_cookie_ids",
]

if __name__ == "__main__":
    main()
