"""In-memory job table and on-disk plan/status helpers."""
import json
import os
import threading

from config import DATA

JOBS = {}
ACTIVE_LOCK = threading.Lock()
RATE = {}
ADMIT = threading.Lock()
_ACTIVE_STATUSES = ("queued", "downloading", "processing")

def set_stage(job_id, stage, pct=None, detail=""):
    """pct is a bounded overall estimate shown only when it comes from real
    sub-progress (download %, transcript window i/n, step i/n); None renders
    an indeterminate bar."""
    j = JOBS.get(job_id)
    if j is not None:
        j.update(stage=stage, pct=pct, detail=detail)


def load_plan(job_id):
    p = os.path.join(DATA, job_id, "plan.json")
    if not os.path.isfile(p):
        return None
    try:
        with open(p, encoding="utf-8") as fh:
            plan = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(plan, dict) or not isinstance(plan.get("steps"), list):
        return None
    if not isinstance(plan.get("device"), str):
        return None
    for step in plan["steps"]:
        # The guide page indexes s["title"], s["t"], and s["image"]; a
        # hand-edited plan.json missing those would 500 in the handler.
        if not isinstance(step, dict):
            return None
        if not isinstance(step.get("title"), str) or not isinstance(step.get("t"), (int, float)):
            return None
    return plan


def _write_status(job_id, **fields):
    path = os.path.join(DATA, job_id, "status.json")
    current = {}
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                current = json.load(fh)
        except (OSError, json.JSONDecodeError):
            current = {}
    current.update(fields)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(current, fh)
    os.replace(tmp, path)
