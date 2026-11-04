"""Offline checks for anchoring, the budget meter, and the web guards."""

import json
import os
from types import SimpleNamespace
from urllib.parse import unquote

import numpy as np
import pytest

from teardown.guide import build_guide
from teardown.meta_api import plan_windows
from teardown.segment import evaluate_mask
from teardown.steps import _frame_choice, parse_steps


def _plan(steps, tools=None, device="laptop"):
    return json.dumps({
        "device": device,
        "tools_summary": [] if tools is None else tools,
        "steps": steps,
    })


def _step(t, quote, title="Do the thing", **extra):
    body = {
        "t": t,
        "anchor_quote": quote,
        "part": "part",
        "title": title,
        "tool": "fingers",
        "instruction": "Do it.",
    }
    body.update(extra)
    return body


def test_plan_windows_merges_subsecond_tail_and_overlaps():
    long = plan_windows(1140.02)
    assert len(long) == 38
    assert long[0] == (0.0, 31.0)
    assert long[-1][0] == 1110.0
    assert plan_windows(30.02) == [(0.0, 30.02)]
    assert plan_windows(90) == [(0.0, 31.0), (30.0, 31.0), (60.0, 30.0)]


def test_snap_to_window_that_contains_the_quote():
    windows = [{"t": 270.0, "text": "keep the cover on"},
               {"t": 300.0, "text": "now remove the screws on the hinge"}]
    out = parse_steps(_plan([_step(250, "remove the screws on the hinge")]), 600, windows)
    assert out["steps"][0]["t"] == 300.0

    only_30 = [{"t": 0.0, "text": "open the case"},
               {"t": 30.0, "text": "pull the battery tab straight up"},
               {"t": 60.0, "text": "set the battery aside"}]
    out = parse_steps(_plan([_step(60, "pull the battery tab")]), 90, only_30)
    assert out["steps"][0]["t"] == 30.0


def test_normalization_and_word_boundaries():
    windows = [{"t": 0.0, "text": "pull the battery. please don’t lift the cell"}]
    out = parse_steps(_plan([
        _step(0, "pull the battery"),
        _step(0, "don't lift the cell"),
    ]), 30, windows)
    assert len(out["steps"]) == 2
    diagram = [{"t": 0.0, "text": "look at the diagram carefully"}]
    out = parse_steps(_plan([
        _step(0, "a", title="Tiny"),
        _step(0, "ram", title="Inside"),
        _step(0, "the diagram", title="Kept"),
    ]), 30, diagram)
    assert [step["title"] for step in out["steps"]] == ["Kept"]


def test_repeated_quote_stays_on_its_own_occurrence():
    windows = [
        {"t": 0.0, "text": "first remove the screws on the cover"},
        {"t": 300.0, "text": "now remove the screws on the hinge"},
    ]
    out = parse_steps(_plan([
        _step(10, "remove the screws", title="Cover"),
        _step(290, "remove the screws", title="Hinge"),
    ]), 600, windows)
    assert [step["t"] for step in out["steps"]] == [0.0, 300.0]


def test_split_quote_credits_only_the_earlier_window():
    windows = [
        {"t": 0.0, "text": "start here"},
        {"t": 30.0, "text": "lift the latch and pull the"},
        {"t": 60.0, "text": "battery connector slowly"},
    ]
    split = parse_steps(_plan([_step(0, "pull the battery connector")]), 90, windows)
    assert split["steps"][0]["t"] == 30.0
    whole = parse_steps(_plan([_step(0, "battery connector slowly")]), 90, windows)
    assert whole["steps"][0]["t"] == 60.0


def test_salvage_coverage_and_empty_transcript():
    windows = [{"t": 0.0, "text": "pull the battery out of the bay"}]
    out = parse_steps(_plan([
        {"t": "soon", "anchor_quote": "pull the battery", "title": "Bad", "instruction": "nope"},
        _step(0, "pull the battery", title="Good"),
    ]), 200, windows)
    assert [step["title"] for step in out["steps"]] == ["Good"]
    assert out["coverage_warning"] is True
    near_end = parse_steps(_plan([_step(180, "pull the battery")]), 200, [
        {"t": 180.0, "text": "pull the battery out of the bay"},
    ])
    assert near_end["coverage_warning"] is False
    with pytest.raises(ValueError):
        parse_steps(_plan([_step(0, "pull the battery")]), 30, [])
    tools = parse_steps(_plan([_step(0, "pull the battery")], tools="one spudger"), 30, windows)
    assert tools["tools_summary"] == ["one spudger"]
    part = parse_steps(_plan([_step(0, "pull the battery", part=None)]), 30, windows)
    assert part["steps"][0]["part"] == "part"


def test_frame_choice_prefers_the_named_number():
    assert _frame_choice("There are 5 frames; pick 3", 7) == 2
    assert _frame_choice("nothing useful", 4) is None


def test_pick_frame_stacks_seven_tiles(tmp_path):
    cv2 = pytest.importorskip("cv2")
    from teardown.steps import pick_frame

    paths = []
    for index in range(7):
        path = tmp_path / f"{index}.png"
        cv2.imwrite(str(path), np.zeros((30, 40, 3), dtype=np.uint8))
        paths.append((float(index), str(path)))

    class Api:
        def respond(self, *args, **kwargs):
            return "There are 5 frames; pick 3"

    assert pick_frame(Api(), paths, "battery", "Remove the battery") == 2


def test_evaluate_mask_floors():
    good = np.ones((10, 20), dtype=np.uint8)
    assert evaluate_mask(good, (0, 0, 20, 10), 0.9)
    assert not evaluate_mask(good, (0, 0, 20, 10), 0.2)
    assert not evaluate_mask(good, (0, 0, 20, 10), None)
    assert not evaluate_mask(good, (0, 0, 19, 10), 0.9)
    assert not evaluate_mask(np.zeros((10, 20), dtype=np.uint8), (0, 0, 20, 10), 0.9)
    speck = np.zeros((10, 20), dtype=np.uint8)
    speck[0, 0] = 255
    assert not evaluate_mask(speck, (0, 0, 20, 10), 0.9)


def test_build_guide_escapes_and_keeps_dollars(tmp_path):
    image = tmp_path / "step.png"
    image.write_bytes(b"\x89PNG\r\nnot-really")
    plan = {
        "device": "<phone> & $100",
        "tools_summary": ["<spudger>"],
        "steps": [{
            "t": 5,
            "part": "battery",
            "title": "<Remove>",
            "instruction": "do <it>",
            "source": "pull the <battery>",
            "lines": [{"type": "caution", "text": "don't bend <it>"}],
            "segmented": False,
        }],
    }
    out = tmp_path / "guide.html"
    build_guide(plan, [str(image)], str(out), source_attribution="Ada & <lab>")
    text = out.read_text(encoding="utf-8")
    assert "<phone>" not in text
    assert "&lt;phone&gt;" in text
    assert "$100" in text
    assert "&lt;Remove&gt;" in text
    assert "&lt;spudger&gt;" in text
    assert "Standard precaution, not from this video" in text
    assert "about 00:05" in text
    assert "Part not highlighted" in text
    assert "Ada &amp; &lt;lab&gt;" in text
    with pytest.raises(ValueError):
        build_guide(plan, [], str(tmp_path / "short.html"))


def test_budget_meter_keeps_estimates_and_does_not_double_count(monkeypatch):
    import budget

    monkeypatch.setattr(budget, "TOKEN", "")
    state = {"spent_usd": 19.0, "reserved": {"other": 0.8, "me": 5.0}}
    assert budget.call_fits(state, "me", 0.2, cap=20)
    assert not budget.call_fits(state, "me", 0.21, cap=20)
    assert budget.settle_amount(1.5, 0.4) == 1.1
    assert budget.settle_amount(0.2, 0.5) == 0
    history = {"history": [
        {"job": "a", "overage_usd": 0.2},
        {"job": "a", "overage_usd": 0.1},
        {"job": "b", "overage_usd": 5},
    ]}
    assert budget.posted_overage(history, "a") == pytest.approx(0.3)
    assert budget.job_reservation(90, 6, "muse-spark-1.3") > 0
    assert budget.expire_stale() is None

    meter = budget.JobMeter("job", 50, "muse-spark-1.3")
    assert meter._usage_tokens(None) is None
    assert meter._usage_tokens({"input_tokens": 0, "output_tokens": 0}) is None
    assert meter._usage_tokens({"input_tokens": 10, "output_tokens": 2, "cached_tokens": 50}) == (10, 2, 10)
    est = meter.spark_before(1000, 100)
    meter.spark_after(est, {"input_tokens": 0, "output_tokens": 0})
    assert meter.actual == pytest.approx(est)
    video = budget.JobMeter("job2", 50, "muse-spark-1.3")
    video.spark_after(1.0, {"input_tokens": 12, "output_tokens": 4})
    assert video.actual == pytest.approx(1.0)


def test_web_guards(tmp_path, monkeypatch):
    import web.app as app

    data = tmp_path / "data"
    job = "abc123"
    (data / job).mkdir(parents=True)
    (data / job / "video.mp4").write_bytes(b"0123456789")
    victim = data / "victim"
    victim.mkdir()
    (victim / "video.mp4").write_bytes(b"secret")
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"nope")
    (data / job / "leak.mp4").symlink_to(outside)

    assert app.safe_job_path(job, "video.mp4", data_root=str(data))
    assert app.safe_job_path(job, "../victim/video.mp4", data_root=str(data)) is None
    assert app.safe_job_path(job, "..\\victim\\video.mp4", data_root=str(data)) is None
    assert app.safe_job_path(job, "/etc/passwd", data_root=str(data)) is None
    assert app.safe_job_path(job, "notes.txt", data_root=str(data)) is None
    assert app.safe_job_path(job, "leak.mp4", data_root=str(data)) is None
    assert app.safe_job_path("nope", "video.mp4", data_root=str(data)) is None

    assert app.parse_byte_range(None, 100) == ("full", 0, 99)
    assert app.parse_byte_range("bytes=0-10", 100) == ("partial", 0, 10)
    assert app.parse_byte_range("bytes=-5", 100) == ("partial", 95, 99)
    assert app.parse_byte_range("bytes=-0", 100)[0] == "unsat"
    assert app.parse_byte_range("bytes=200-210", 100)[0] == "unsat"
    assert app.parse_byte_range(None, 0)[0] == "unsat"

    sid, cookie = app.new_session_cookie()
    stub = SimpleNamespace(headers={"Cookie": cookie.split(";", 1)[0]})
    token = app.csrf_token(sid)
    assert app.csrf_ok(stub, token)
    assert not app.csrf_ok(stub, "x" * len(token))
    assert not app.csrf_ok(stub, token[:-1])
    other_sid, _ = app.new_session_cookie()
    assert not app.csrf_ok(stub, app.csrf_token(other_sid))
    anon = SimpleNamespace(headers={})
    assert not app.csrf_ok(anon, token)
    script = app.json_for_script({"fasteners": "</script><img>"})
    assert "<" not in script
    assert "\\u003c" in script

    job_id = "ab" * 16
    monkeypatch.setenv("HOST", "127.0.0.1")
    header = app.cookie_header([job_id])
    assert "HttpOnly" in header
    assert "Secure" not in header
    assert app._valid_cookie_ids(header) == [job_id]
    assert app._valid_cookie_ids(f"td_jobs={job_id}.abcd") == []
    monkeypatch.setenv("HOST", "0.0.0.0")
    assert "Secure" in app.cookie_header([job_id])

    assert app.youtube_url_ok("https://www.youtube.com/watch?v=abc")
    assert app.youtube_url_ok("https://youtu.be/abc")
    assert not app.youtube_url_ok("http://www.youtube.com/watch?v=abc")
    assert not app.youtube_url_ok("https://evil.example/watch")
    assert not app.youtube_url_ok("https://user:pass@www.youtube.com/watch?v=abc")
    assert not app.youtube_url_ok("https://youtube.com.evil.com/watch")

    def handler(origin, host, ip, forwarded=None):
        headers = {"Host": host}
        if origin is not None:
            headers["Origin"] = origin
        if forwarded is not None:
            headers["X-Forwarded-For"] = forwarded
        return SimpleNamespace(headers=headers, client_address=(ip, 9))

    assert app.origin_ok(handler("http://127.0.0.1:8377", "127.0.0.1:8377", "10.0.0.8"))
    assert app.origin_ok(handler(None, "127.0.0.1:8377", "127.0.0.1"))
    assert not app.origin_ok(handler(None, "127.0.0.1:8377", "10.0.0.8"))
    assert not app.origin_ok(handler("https://evil.example", "127.0.0.1:8377", "127.0.0.1"))
    monkeypatch.delenv("TEARDOWN_TRUSTED_PROXY", raising=False)
    assert app.client_ip(handler(None, "h", "127.0.0.1", "1.2.3.4")) == "127.0.0.1"
    monkeypatch.setenv("TEARDOWN_TRUSTED_PROXY", "127.0.0.1")
    assert app.client_ip(handler(None, "h", "127.0.0.1", "1.2.3.4, 5.6.7.8")) == "1.2.3.4"
    monkeypatch.setenv("MODEL_API_KEY", "secret-key-value")
    assert "secret-key-value" not in app.redact("boom secret-key-value")


def test_http_admission_and_traversal(monkeypatch):
    import threading
    from http.server import ThreadingHTTPServer

    import handler
    import jobs
    from http_util import csrf_token, session_id

    jobs.JOBS.clear()
    jobs.RATE.clear()
    monkeypatch.setattr(handler, "run_job", lambda *args, **kwargs: None)

    server = ThreadingHTTPServer(("127.0.0.1", 0), handler.H)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        import http.client

        def request(method, path, body=b"", headers=None):
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            payload = response.read()
            result = response.status, response.getheader("Location"), dict(response.getheaders()), payload
            conn.close()
            return result

        status, _location, home_headers, body = request("GET", "/")
        headers = home_headers
        assert status == 200
        text = body.decode()
        assert "__CSRF__" not in text
        assert "contributor" in text
        assert "no-store" in headers.get("Cache-Control", "")
        assert "frame-ancestors 'none'" in headers.get("Content-Security-Policy", "")
        assert request("HEAD", "/")[0] == 200

        session_pair = home_headers.get("Set-Cookie", "").split(";", 1)[0]
        sid = session_id(session_pair)
        assert sid
        token = csrf_token(sid)
        boundary = "----tdboundary"
        bad = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="csrf"\r\n\r\nwrong\r\n'
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="rights"\r\n\r\nyes\r\n'
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="video"; filename="clip.mp4"\r\n'
            "Content-Type: video/mp4\r\n\r\n"
            "not-a-video\r\n"
            f"--{boundary}--\r\n"
        ).encode()
        common = {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Origin": f"http://127.0.0.1:{port}",
            "Host": f"127.0.0.1:{port}",
            "Cookie": session_pair,
        }

        def post(payload, extra=None):
            hdrs = dict(common)
            hdrs["Content-Length"] = str(len(payload))
            if extra:
                hdrs.update(extra)
            return request("POST", "/jobs", payload, hdrs)

        status, location, _headers, _body = post(bad)
        assert status == 303
        assert "form token" in unquote(location or "")
        assert jobs.JOBS == {}

        good = bad.replace(b"wrong", token.encode())
        status, location, headers, _body = post(good, {"X-Forwarded-For": "8.8.8.8"})
        assert status == 303
        assert location and location.startswith("/jobs/")
        assert "HttpOnly" in headers.get("Set-Cookie", "")
        assert "Secure" not in headers.get("Set-Cookie", "")
        status, location, _headers, _body = post(good, {"X-Forwarded-For": "9.9.9.9"})
        assert "slow down" in unquote(location or "")

        owned = next(iter(jobs.JOBS))
        other = "b" * 32
        folder = os.path.join(os.environ["TEARDOWN_DATA"], owned)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "video.mp4"), "wb") as fh:
            fh.write(b"\x00\x00\x00\x18ftypisom")
        stolen = os.path.join(os.environ["TEARDOWN_DATA"], other)
        os.makedirs(stolen, exist_ok=True)
        with open(os.path.join(stolen, "video.mp4"), "wb") as fh:
            fh.write(b"secret")
        cookie = headers.get("Set-Cookie", "").split(";", 1)[0]
        status, _location, _headers, body = request(
            "GET", f"/jobs/{owned}/../{other}/video.mp4", headers={"Cookie": cookie})
        assert status == 404
        assert b"secret" not in body
        status, _location, range_headers, body = request(
            "GET", f"/jobs/{owned}/video.mp4",
            headers={"Cookie": cookie, "Range": "bytes=0-3"})
        assert status == 206
        assert body == b"\x00\x00\x00\x18"
        assert range_headers.get("Content-Range") == "bytes 0-3/12"

        foreign = {
            "Content-Type": common["Content-Type"],
            "Content-Length": str(len(good)),
            "Origin": "https://evil.example",
            "Host": f"127.0.0.1:{port}",
        }
        status, location, _headers, _body = request("POST", "/jobs", good, foreign)
        assert "did not come from this site" in unquote(location or "")
    finally:
        server.shutdown()
        server.server_close()
