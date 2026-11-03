"""Process configuration for the teardown web app."""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get("TEARDOWN_DATA", os.path.join(ROOT, "data"))
PIPELINE = os.environ.get("TEARDOWN_PKG", os.path.join(ROOT, ".."))
KEY_FILE = os.environ.get("TEARDOWN_KEY_FILE")
RATE_LIMIT_PER_HOUR = int(os.environ.get("TEARDOWN_RATE_PER_HOUR", "2"))
MAX_UPLOAD_BYTES = int(os.environ.get("TEARDOWN_MAX_UPLOAD_MB", "150")) * 1024**2
MAX_DURATION_S = float(os.environ.get("TEARDOWN_MAX_DURATION", "1200"))
MAX_STEPS = int(os.environ.get("TEARDOWN_MAX_STEPS", "35"))
JOB_TTL_S = int(os.environ.get("TEARDOWN_JOB_TTL_H", "3")) * 3600
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com",
                 "music.youtube.com", "youtu.be"}
# Contributor tier keeps a shared public budget alive longer. The upload page
# says that Meta may train on submitted footage when this model is selected.
os.environ.setdefault("TEARDOWN_SPARK_MODEL", "muse-spark-1.3-contributor")
if PIPELINE not in sys.path:
    sys.path.insert(0, PIPELINE)
COOKIE_KEY = (os.environ.get("TD_COOKIE_SECRET") or os.urandom(24).hex()).encode()
ALLOWED_FILE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".mp4", ".pdf"}


