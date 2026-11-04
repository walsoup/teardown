"""Spend cutoff for the public teardown demo.

Meta's Model API has no hard cap (verified: key creation has no budget
field, and https://dev.meta.ai/help/billing/spend-limit-alert says
"Meta Model API doesn't currently offer a spending limit that places a
hard cap on usage"). So every API call's cost is reserved at a
conservative worst case BEFORE the call and settled at actuals after.

The ledger is a JSON document in the private GitHub repo on a dedicated
`budget-ledger` branch (never the deploy branch, so ledger writes don't
trigger redeploys). Writes are compare-and-swap on the contents API blob
sha: a concurrent writer gets a 409 and must reload. A crashed job leaves
its reservation standing, so failures over-count, never under-count.

Rates: https://dev.meta.ai/docs/pricing-rate-limits (read 2026-11-02).
"""

import base64
import json
import os
import threading
import time
import urllib.error
import urllib.request

RATES = {
    "spark_standard_input": 1.25 / 1_000_000,    # per token
    "spark_standard_output": 4.25 / 1_000_000,
    "spark_contributor_input": 0.10 / 1_000_000,
    "spark_contributor_output": 0.20 / 1_000_000,
    "asr_second": 0.18 / 3600.0,                 # billed per whole second
    "sam_image": 2.50 / 1000.0,                  # per image segmented
}

# Conservative per-call worst cases. Estimates must be upper bounds; when a
# call's actual exceeds its estimate the overage is committed immediately
# and the job aborts (see JobMeter).
EST = {
    "planner_input_tokens": 3_000_000,   # video file + transcript + prompt
    "planner_output_tokens": 17_000,     # max_output_tokens is 16000
    "pick_input_tokens": 30_000,         # 5 candidate frames + prompt
    "pick_output_tokens": 2_500,         # max_output_tokens is 2000
    "sam_image": 1,
    "asr_window_seconds_pad": 1.0,       # whole-second billing, rounded up
}

CAP_USD = float(os.environ.get("BUDGET_CAP_USD", "20.00"))
# Reservations are checked against the soft cap; the gap absorbs a
# single-call estimate breach without crossing the real cap.
SOFT_CAP_USD = CAP_USD - 0.50

REPO = os.environ.get("LEDGER_REPO", "walsoup/teardown")
BRANCH = os.environ.get("LEDGER_BRANCH", "budget-ledger")
PATH = os.environ.get("LEDGER_PATH", "ledger.json")
TOKEN = os.environ.get("LEDGER_GITHUB_TOKEN", "")

_lock = threading.Lock()


class BudgetExhausted(Exception):
    pass


class LedgerUnavailable(Exception):
    pass


def _api(method, url, body=None):
    req = urllib.request.Request(
        f"https://api.github.com{url}",
        method=method,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "teardown-budget-ledger",
        },
        data=json.dumps(body).encode() if body is not None else None,
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def _initial_state():
    return {"cap_usd": CAP_USD, "spent_usd": 0.0, "reserved": {}, "history": []}


def _ensure_branch():
    st, repo = _api("GET", f"/repos/{REPO}")
    if st != 200:
        raise LedgerUnavailable(f"repo read failed: {st}")
    st, ref = _api("GET", f"/repos/{REPO}/git/ref/heads/{repo['default_branch']}")
    if st != 200:
        raise LedgerUnavailable(f"default ref read failed: {st}")
    st, _ = _api("POST", f"/repos/{REPO}/git/refs",
                 {"ref": f"refs/heads/{BRANCH}", "sha": ref["object"]["sha"]})
    if st not in (201, 422):  # 422 = already exists
        raise LedgerUnavailable(f"branch create failed: {st}")


def _read():
    st, body = _api("GET", f"/repos/{REPO}/contents/{PATH}?ref={BRANCH}")
    if st == 404:
        return _initial_state(), None
    if st != 200:
        raise LedgerUnavailable(f"ledger read failed: {st}")
    raw = base64.b64decode(body["content"])
    return json.loads(raw), body["sha"]


def _write(state, sha):
    body = {
        "message": f"budget ledger: spent ${state['spent_usd']:.4f}, "
                   f"{len(state['reserved'])} reserved",
        "content": base64.b64encode(
            json.dumps(state, indent=1).encode()).decode(),
        "branch": BRANCH,
    }
    if sha:
        body["sha"] = sha
    st, resp = _api("PUT", f"/repos/{REPO}/contents/{PATH}", body)
    if st == 409:
        return False
    if st not in (200, 201):
        raise LedgerUnavailable(f"ledger write failed: {st} {resp}")
    return True


def _cas(fn):
    """Read-modify-write with compare-and-swap. fn(state) -> note or None.

    Returns fn's note. Aborts (LedgerUnavailable) after repeated conflicts.
    """
    if not TOKEN:
        raise LedgerUnavailable("LEDGER_GITHUB_TOKEN is not set")
    _ensure_branch()  # idempotent; contents PUT needs the branch to exist
    last = None
    for attempt in range(6):
        state, sha = _read()
        note = fn(state)
        if note is None:
            return None  # fn declined; nothing to write
        if _write(state, sha):
            return note
        last = "conflict"
        time.sleep(0.3 * (attempt + 1))
    raise LedgerUnavailable(f"ledger CAS failed after retries: {last}")


def reserve(job_id, amount):
    """Reserve worst-case cost for a job. Returns False when over budget."""
    def fn(state):
        outstanding = sum(state["reserved"].values())
        if state["spent_usd"] + outstanding + amount > SOFT_CAP_USD:
            return None
        state["reserved"][job_id] = round(amount, 6)
        state.setdefault("reserved_at", {})[job_id] = int(time.time())
        return amount
    return _cas(fn) is not None


def call_fits(state, job_id, estimate, cap=None):
    """True when this call still fits under the hard cap.

    Other jobs' reservations count. This job's own reservation does not,
    because `estimate` is the in-flight slice of that reservation.
    """
    limit = CAP_USD if cap is None else cap
    others = sum(value for key, value in state.get("reserved", {}).items() if key != job_id)
    return state.get("spent_usd", 0.0) + others + float(estimate) <= limit + 1e-9


def ensure_call_headroom(job_id, estimate):
    """Read the ledger and refuse a call that would cross the hard cap."""
    if not TOKEN:
        return True
    state, _ = _read()
    return call_fits(state, job_id, estimate)


_STALE_RESERVATION_S = int(os.environ.get("TEARDOWN_RESERVATION_TTL_S", str(6 * 3600)))


def expire_stale(max_age_s=None):
    """Settle reservations older than max_age_s at the reserved amount.

    A crashed job never reaches settle, so its reservation would block the
    demo forever. Overage already posted for that job is not added again.
    Returns the number of reservations expired, or None when there is no ledger.
    """
    if not TOKEN:
        return None
    limit = _STALE_RESERVATION_S if max_age_s is None else max_age_s

    def fn(state):
        now = int(time.time())
        stamps = state.setdefault("reserved_at", {})
        expired = []
        for job_id, amount in list(state.get("reserved", {}).items()):
            stamp = stamps.get(job_id)
            if stamp is None or now - int(stamp) > limit:
                expired.append((job_id, float(amount)))
        if not expired:
            return None
        for job_id, amount in expired:
            state["reserved"].pop(job_id, None)
            stamps.pop(job_id, None)
            add = settle_amount(amount, posted_overage(state, job_id))
            state["spent_usd"] = round(max(0.0, state["spent_usd"] + add), 6)
            state["history"].append(
                {"job": job_id, "expired_reservation_usd": round(add, 6), "ts": now})
        state["history"] = state["history"][-200:]
        return len(expired)

    return _cas(fn)


def posted_overage(state, job_id):
    """Overage already committed for this job, so settle does not add it twice."""
    total = 0.0
    for row in state.get("history") or []:
        if row.get("job") == job_id and "overage_usd" in row:
            total += float(row["overage_usd"])
    return total


def settle_amount(actual, already_posted):
    """Spend still to commit. Never negative."""
    return max(0.0, round(float(actual) - float(already_posted), 6))


def settle(job_id, actual):
    """Commit a job's actual spend and release its reservation.

    Overage rows already added to spent_usd are subtracted so a call that
    beat its estimate is not billed twice.
    """
    def fn(state):
        add = settle_amount(actual, posted_overage(state, job_id))
        state["reserved"].pop(job_id, None)
        state.setdefault("reserved_at", {}).pop(job_id, None)
        state["spent_usd"] = round(max(0.0, state["spent_usd"] + add), 6)
        state["history"].append(
            {"job": job_id, "actual_usd": round(float(actual), 6), "ts": int(time.time())})
        state["history"] = state["history"][-200:]
        return add
    _cas(fn)


def add_overage(job_id, amount):
    """Commit spend above a job's reservation immediately (estimate breach)."""
    def fn(state):
        state["spent_usd"] = round(state["spent_usd"] + amount, 6)
        state["history"].append(
            {"job": job_id, "overage_usd": round(amount, 6), "ts": int(time.time())})
        state["history"] = state["history"][-200:]
        return amount
    _cas(fn)


def status():
    state, _ = _read()
    outstanding = sum(state["reserved"].values())
    return {
        "basis": "conservative in-app estimate (worst-case reservations, settled per job); not provider-billed spend",
        "cap_usd": CAP_USD,
        "spent_usd": state["spent_usd"],
        "reserved_usd": outstanding,
        "remaining_usd": max(0.0, SOFT_CAP_USD - state["spent_usd"] - outstanding),
        "jobs": len(state["history"]),
    }


def spark_rates(model):
    if model.endswith("-contributor"):
        return RATES["spark_contributor_input"], RATES["spark_contributor_output"]
    return RATES["spark_standard_input"], RATES["spark_standard_output"]


def job_reservation(duration_s, max_steps, spark_model):
    """Worst-case cost of one full pipeline run, in USD."""
    rin, rout = spark_rates(spark_model)
    n_windows = max(1, int(-(-duration_s // 30)))
    asr = (duration_s + n_windows * EST["asr_window_seconds_pad"]) * RATES["asr_second"]
    # plan_steps retries once with a text-only repair call on bad JSON, so
    # the reservation covers up to 2 planner-sized spends.
    planner = 2 * (EST["planner_input_tokens"] * rin
                   + EST["planner_output_tokens"] * rout)
    per_step = (EST["pick_input_tokens"] * rin
                + EST["pick_output_tokens"] * rout
                + EST["sam_image"] * RATES["sam_image"])
    return asr + planner + max_steps * per_step


class JobMeter:
    """In-process accounting for one running job.

    Before every API call: the call's worst-case estimate must fit inside
    the job's remaining reservation, otherwise the job aborts. After every
    call: actual cost is added; any excess over the estimate is committed
    to the ledger immediately so other jobs see it.
    """

    def __init__(self, job_id, reservation, spark_model):
        self.job_id = job_id
        self.reservation = reservation
        self.actual = 0.0
        self.overage_posted = 0.0
        self.rin, self.rout = spark_rates(spark_model)
        self._lock = threading.Lock()
        self._inflight = 0.0
        self._asr_headroom_checks = 0

    def _check(self, est, headroom=True):
        # Atomically reserve the estimate: the provisional amount lands in
        # _inflight under the same lock as the fit test, so concurrent
        # threads cannot all pass the check before any of them is charged.
        # _add releases the hold and charges the real cost.
        if est < 0:
            est = 0.0
        with self._lock:
            if self.actual + self._inflight + est > self.reservation + 1e-9:
                raise BudgetExhausted(
                    "job aborted: cost estimate exceeded its reservation")
            self._inflight += est
        if headroom and not ensure_call_headroom(self.job_id, est):
            with self._lock:
                self._inflight -= est
            raise BudgetExhausted("call would exceed the shared budget cap")

    def _add(self, est, actual):
        actual = max(0.0, float(actual))
        est = max(0.0, float(est))
        extra = actual - est if actual > est else 0.0
        if extra > 0:
            add_overage(self.job_id, extra)
        with self._lock:
            # Release this call's hold and charge its real cost; a call
            # that came in under estimate returns the difference.
            self._inflight = max(0.0, self._inflight - est)
            self.actual += actual
            if extra > 0:
                self.overage_posted += extra

    @staticmethod
    def _usage_tokens(usage):
        """Token counts only when the payload has the fields we bill on.

        Missing or zeroed fields keep the pre-call estimate. A cached-token
        count is clamped so it cannot drive the cost negative.
        """
        if not isinstance(usage, dict):
            return None
        if "input_tokens" not in usage or "output_tokens" not in usage:
            return None
        try:
            in_t = int(usage["input_tokens"])
            out_t = int(usage["output_tokens"])
        except (TypeError, ValueError):
            return None
        if in_t < 0 or out_t < 0 or (in_t == 0 and out_t == 0):
            return None
        details = usage.get("input_tokens_details") or {}
        cached = usage.get("cached_tokens", details.get("cached_tokens", 0))
        try:
            cached = int(cached)
        except (TypeError, ValueError):
            cached = 0
        cached = max(0, min(cached, in_t))
        return in_t, out_t, cached

    def spark_before(self, est_in, est_out):
        est = est_in * self.rin + est_out * self.rout
        self._check(est)
        return est

    def spark_after(self, est, usage):
        actual = est  # no usable usage: keep the (higher) estimate
        toks = self._usage_tokens(usage)
        if toks:
            in_t, out_t, cached = toks
            cached_rate = self.rin * 0.12
            computed = max(0.0, (in_t - cached) * self.rin + cached * cached_rate
                           + out_t * self.rout)
            # A video-sized call that reports a handful of tokens is not
            # believable. Keep the estimate rather than recording it as free.
            if est >= 0.05 and computed < est * 0.05 and in_t < 10_000:
                computed = est
            actual = computed
        self._add(est, actual)

    def asr_before(self, window_s):
        est = (window_s + EST["asr_window_seconds_pad"]) * RATES["asr_second"]
        # ASR windows are cheap and numerous. Check the shared cap on the
        # first window; every window still has to fit this job's reservation.
        with self._lock:
            self._asr_headroom_checks += 1
            check_cap = self._asr_headroom_checks == 1
        self._check(est, headroom=check_cap)
        return est

    def asr_after(self, window_s, est):
        import math
        # billed whole seconds, rounded down per docs; the pad overcounts
        actual = max(1, math.floor(window_s + 1)) * RATES["asr_second"]
        self._add(est, actual)

    def sam_before(self):
        est = EST["sam_image"] * RATES["sam_image"]
        self._check(est)
        return est

    def sam_after(self, est):
        self._add(est, est)
