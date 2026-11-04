"""Process entry: reload finished guides, expire stale reservations, serve."""
import os
import shutil
import threading
import time
from http.server import ThreadingHTTPServer

import budget
from config import DATA, JOB_TTL_S
from handler import H
from jobs import JOBS, load_plan

def reaper():
    while True:
        time.sleep(900)
        now = time.time()
        for d in os.listdir(DATA):
            p = os.path.join(DATA, d)
            active = JOBS.get(d, {}).get("status") in ("queued", "downloading", "processing")
            try:
                if os.path.isdir(p) and not active and now - os.path.getmtime(p) > JOB_TTL_S:
                    shutil.rmtree(p, ignore_errors=True)
                    JOBS.pop(d, None)
            except OSError:
                pass


def main():
    host = os.environ.get("HOST", "127.0.0.1")
    if host not in ("127.0.0.1", "localhost", "::1") and not os.environ.get("TD_COOKIE_SECRET"):
        raise SystemExit("TD_COOKIE_SECRET is required when HOST is not loopback")
    os.makedirs(DATA, exist_ok=True)
    try:
        expired = budget.expire_stale()
        if expired:
            print(f"expired {expired} stale budget reservations", flush=True)
    except Exception as exc:
        print(f"budget expire skipped: {exc}", flush=True)
    if os.path.isdir(DATA):
        for name in os.listdir(DATA):
            plan = load_plan(name)
            if plan:
                JOBS[name] = {"status": "done", "device": plan.get("device") or "device",
                              "steps": len(plan.get("steps") or [])}
    threading.Thread(target=reaper, daemon=True).start()
    port = int(os.environ.get("PORT", "8377"))
    print(f"serving on http://{host}:{port}")
    ThreadingHTTPServer((host, port), H).serve_forever()
