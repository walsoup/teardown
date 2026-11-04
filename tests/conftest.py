"""Keep the suite offline and point imports at the repo."""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
for path in (WEB, ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

os.environ.pop("LEDGER_GITHUB_TOKEN", None)
os.environ.pop("MODEL_API_KEY", None)
os.environ.setdefault("HOST", "127.0.0.1")
os.environ.setdefault("TEARDOWN_DATA", tempfile.mkdtemp(prefix="teardown-test-"))
