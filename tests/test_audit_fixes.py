"""Regression tests for the teardown audit-fix batch (findings F1-F11 + (a)).

Each test reproduces the original fault against the fixed code:
it fails on the pre-fix implementation and passes after the fix.
Offline: no API keys, no network, no Chrome.
"""

import html as html_mod
import json
import os
import re
import subprocess
import sys
import threading

import pytest

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
if WEB not in sys.path:
    sys.path.insert(0, WEB)


# F1: missing/blank MODEL_API_KEY must be a catchable Exception, not SystemExit.
def test_missing_key_raises_exception_not_systemexit(monkeypatch):
    from teardown.meta_api import MetaApi, MissingApiKey

    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    with pytest.raises(MissingApiKey):
        MetaApi()
    # ...so except-Exception pipeline handlers mark the job failed.
    try:
        MetaApi()
    except Exception as exc:  # noqa: BLE001 - the point is it must be caught here
        assert isinstance(exc, MissingApiKey)
    else:
        pytest.fail("MissingApiKey escaped except Exception")


def test_blank_key_rejected(monkeypatch):
    from teardown.meta_api import MetaApi, MissingApiKey

    monkeypatch.setenv("MODEL_API_KEY", "   ")
    with pytest.raises(MissingApiKey):
        MetaApi()


# F2: truncated PDFs must not be cached as final; incomplete bytes rejected.
def test_is_complete_pdf_rejects_truncated(tmp_path):
    from pdf import is_complete_pdf

    trunc = tmp_path / "t.pdf"
    trunc.write_bytes(b"%PDF-1.4\n" + b"x" * 2000)  # >1000 bytes, no trailer
    assert not is_complete_pdf(str(trunc))
    full = tmp_path / "f.pdf"
    full.write_bytes(b"%PDF-1.4\n" + b"x" * 2000 + b"\n%%EOF\n")
    assert is_complete_pdf(str(full))
    tiny = tmp_path / "s.pdf"
    tiny.write_bytes(b"%PDF-1.4 tiny %%EOF")
    assert not is_complete_pdf(str(tiny))
    assert not is_complete_pdf(str(tmp_path / "missing.pdf"))


def test_pdf_module_promotes_only_complete_pdfs():
    import pdf as pdf_mod

    src = open(pdf_mod.__file__, encoding="utf-8").read()
    assert "> 1000" not in src or "is_complete_pdf" in src
    # No size-only promotion of the partial file remains.
    assert "os.path.getsize(partial) > 0" not in src


# F3: CLI must remux EBML (webm/mkv) before the model upload, like the worker.
def test_cli_remuxes_webm_before_upload(tmp_path):
    pytest.importorskip("cv2")
    import shutil

    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is not installed")
    webm = tmp_path / "clip.webm"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=160x120:d=1",
                    "-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p", str(webm)],
                   check=True, capture_output=True)
    from teardown import cli, ingest

    assert ingest.is_ebml(str(webm))
    out = tmp_path / "out"
    out.mkdir()
    import argparse

    args = argparse.Namespace(video=str(webm), out=str(out), attribution=None,
                              mock=False, allow_long=True, i_accept_api_cost=True)
    seen = {}
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("teardown.cli._real_run",
                   lambda a, duration: (seen.setdefault("video", a.video),
                                        seen.setdefault("duration", duration),
                                        (_ for _ in ()).throw(RuntimeError("stop before spend"))))
        with pytest.raises(RuntimeError, match="stop before spend"):
            cli._run(args)
    assert seen["video"].endswith(".mp4")
    assert not ingest.is_ebml(seen["video"])
    assert seen["duration"] > 0


# F4: resume caches are keyed to video identity.
def _fake_ingest(monkeypatch):
    import teardown.ingest as ingest

    monkeypatch.setattr(ingest, "extract_audio",
                        lambda vp, wp: (open(wp, "wb").write(b"w"), wp)[1])
    monkeypatch.setattr(ingest, "has_speech", lambda w: True)
    monkeypatch.setattr(ingest, "probe_audio_start", lambda v: 0.0)


def _fake_api():
    class FakeApi:
        def __init__(self):
            self.calls = []

        def transcribe_timed(self, wav, checkpoint_path=None, progress=None, offset=0.0):
            self.calls.append("asr")
            return [{"t": 0.0, "text": "hi"}]

        def upload_file(self, path, purpose="user_data"):
            self.calls.append("upload")
            return "fid"

    return FakeApi()


def test_resume_caches_keyed_to_video(tmp_path, monkeypatch):
    from teardown import orchestrate

    _fake_ingest(monkeypatch)
    out = tmp_path / "out"
    out.mkdir()
    va = tmp_path / "a.mp4"
    va.write_bytes(b"A" * 100)
    vb = tmp_path / "b.mp4"
    vb.write_bytes(b"B" * 200)
    api = _fake_api()
    orchestrate.ensure_transcript(api, str(va), str(out))
    orchestrate.ensure_plan(api, str(va), [], 60.0, str(out),
                            lambda c, vid, t, dur: {"device": "d", "steps": [{"t": 1}], "vid": vid})
    other = _fake_api()
    orchestrate.ensure_transcript(other, str(vb), str(out))
    plan = orchestrate.ensure_plan(other, str(vb), [], 60.0, str(out),
                                   lambda c, vid, t, dur: {"device": "d2", "steps": [{"t": 2}], "vid": vid})
    assert other.calls.count("asr") == 1
    assert other.calls.count("upload") == 1
    assert plan["device"] == "d2"
    # Same video again: full resume, zero API calls.
    third = _fake_api()
    orchestrate.ensure_transcript(third, str(vb), str(out))
    orchestrate.ensure_plan(third, str(vb), [], 60.0, str(out),
                            lambda *a: (_ for _ in ()).throw(AssertionError("must not run on resume")))
    assert third.calls == []


def test_step_markers_not_reused_across_videos(tmp_path, monkeypatch):
    from unittest.mock import patch

    import numpy as np

    from teardown import orchestrate

    cv2 = pytest.importorskip("cv2")
    out = tmp_path / "out"
    (out / "steps").mkdir(parents=True)
    va = tmp_path / "a.mp4"
    va.write_bytes(b"A" * 100)
    vb = tmp_path / "b.mp4"
    vb.write_bytes(b"B" * 200)

    def fake_extract(vp, times, paths):
        for p in paths:
            cv2.imwrite(p, np.zeros((8, 8, 3), np.uint8))
        return paths

    seen_parts = []

    def seg(api, frame, part):
        seen_parts.append(part)
        return {"bounds": (0, 0, 4, 4), "mask": np.ones((4, 4), np.uint8), "confidence": 0.9}

    def fake_annotate(frame, bounds, mask, index, final, **kw):
        cv2.imwrite(final, np.zeros((8, 8, 3), np.uint8))

    plan_a = {"steps": [{"t": 1.0, "part": "battery", "title": "T"}], "duration": 60.0}
    with patch.object(orchestrate.ingest, "extract_frames", side_effect=fake_extract):
        orchestrate.illustrate(None, str(va), plan_a, str(out), segment_part=seg,
                               annotate=fake_annotate, pick_frame=lambda *a: 0, workers=1)
    assert os.path.isfile(os.path.join(str(out), plan_a["steps"][0]["image"]))
    plan_b = {"steps": [{"t": 1.0, "part": "screen", "title": "U"}], "duration": 60.0}
    with patch.object(orchestrate.ingest, "extract_frames", side_effect=fake_extract):
        orchestrate.illustrate(None, str(vb), plan_b, str(out), segment_part=seg,
                               annotate=fake_annotate, pick_frame=lambda *a: 0, workers=1)
    # vb's run re-segmented its own part instead of reusing va's marker...
    assert seen_parts == ["battery", "screen"]
    # ...and vb's step image exists on disk.
    assert os.path.isfile(os.path.join(str(out), plan_b["steps"][0]["image"]))


# F5: CLI settles the budget reservation even on failure; RuntimeError handled.
def test_real_run_settles_on_failure(tmp_path, monkeypatch):
    from teardown import cli

    settled = []
    monkeypatch.setattr(cli, "_settle", lambda meter: settled.append(meter))
    monkeypatch.setattr(cli, "_maybe_meter", lambda duration: "meter")

    class FakeApi:
        def _transcribe_chunk(self, wav_path):
            return ""

    monkeypatch.setattr("teardown.meta_api.MetaApi", lambda *a, **k: FakeApi())
    monkeypatch.setattr("teardown.orchestrate.ensure_transcript",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("asr blew up")))
    import argparse

    args = argparse.Namespace(video="v.mp4", out=str(tmp_path), attribution=None)
    with pytest.raises(RuntimeError):
        cli._real_run(args, 10.0)
    assert settled == ["meter"]


def test_main_handles_frame_extract_runtimeerror(capsys):
    from teardown import cli

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(cli, "_run",
                        lambda args: (_ for _ in ()).throw(RuntimeError("could not extract any frames")))
    try:
        assert cli.main(["x.mp4"]) == 1
        assert "could not finish" in capsys.readouterr().err
    finally:
        monkeypatch.undo()


# F6: per-thread usage attribution under concurrency.
def test_last_usage_is_thread_isolated(monkeypatch):
    import time

    from teardown.meta_api import MetaApi

    monkeypatch.setenv("MODEL_API_KEY", "test-key")
    api = MetaApi()
    orig_post = api.session.post

    def fake_post(url, **kw):
        tid = threading.current_thread().name
        time.sleep(0.01 if tid.endswith("t0") else 0.0)

        class R:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self_inner):
                time.sleep(0.02)
                return {"output": [], "usage": {"marker": tid}}

        return R()

    monkeypatch.setattr(api.session, "post", fake_post)
    results = {}

    def work(name):
        api.respond("model", [{"x": 1}])
        time.sleep(0.005)
        results[name] = dict(api.last_usage)

    threads = [threading.Thread(target=work, args=(f"t{i}",), name=f"thr-t{i}") for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(results) == 4
    for name, usage in results.items():
        assert usage == {"marker": "thr-" + name}, f"{name} mis-attributed: {usage}"
    assert orig_post is not None


# F7: transient segmentation miss is retryable; clean zero-match stays cached.
def _illustrate_setup(tmp_path):
    from unittest.mock import patch

    import numpy as np

    from teardown import orchestrate

    cv2 = pytest.importorskip("cv2")
    out = tmp_path / "out"
    (out / "steps").mkdir(parents=True)
    vid = tmp_path / "v.mp4"
    vid.write_bytes(b"x" * 100)

    def fake_extract(vp, times, paths):
        for p in paths:
            cv2.imwrite(p, np.zeros((8, 8, 3), np.uint8))
        return paths

    ctx = patch.object(orchestrate.ingest, "extract_frames", side_effect=fake_extract)
    return orchestrate, np, out, vid, ctx


def test_transient_miss_retried_on_resume(tmp_path):
    from teardown.segment import SegmentTransient

    orchestrate, np, out, vid, ctx = _illustrate_setup(tmp_path)
    plan = {"steps": [{"t": 1.0, "part": "battery", "title": "T"}], "duration": 60.0}

    def boom(api, frame, part):
        raise SegmentTransient("api down")

    with ctx:
        orchestrate.illustrate(None, str(vid), plan, str(out), segment_part=boom,
                               annotate=lambda *a, **k: None, pick_frame=lambda *a: 0, workers=1)
    marker = json.loads((out / "steps" / "step-1.json").read_text(encoding="utf-8"))
    assert marker.get("segment_retryable") is True
    assert marker.get("image")  # clean frame kept
    calls = []

    def good(api, frame, part):
        calls.append(part)
        return {"bounds": (0, 0, 4, 4), "mask": np.ones((4, 4), np.uint8), "confidence": 0.9}

    plan2 = {"steps": [{"t": 1.0, "part": "battery", "title": "T"}], "duration": 60.0}
    with ctx:
        orchestrate.illustrate(None, str(vid), plan2, str(out), segment_part=good,
                               annotate=lambda *a, **k: None, pick_frame=lambda *a: 0, workers=1)
    assert len(calls) == 1
    assert plan2["steps"][0].get("segmented") is True


def test_clean_zero_match_stays_cached(tmp_path):
    orchestrate, np, out, vid, ctx = _illustrate_setup(tmp_path)
    plan = {"steps": [{"t": 1.0, "part": "battery", "title": "T"}], "duration": 60.0}

    def write_final(*a, **k):
        with open(a[4], "wb") as fh:  # annotate contract: write the final frame
            fh.write(b"x")

    with ctx:
        orchestrate.illustrate(None, str(vid), plan, str(out), segment_part=lambda *a: None,
                               annotate=write_final, pick_frame=lambda *a: 0, workers=1)
    calls = []
    plan2 = {"steps": [{"t": 1.0, "part": "battery", "title": "T"}], "duration": 60.0}

    def counting(*a):
        calls.append(1)
        return None

    with ctx:
        orchestrate.illustrate(None, str(vid), plan2, str(out), segment_part=counting,
                               annotate=lambda *a, **k: None, pick_frame=lambda *a: 0, workers=1)
    assert calls == []


# F8: empty plan is rejected on both timed and untimed paths.
def test_empty_steps_rejected():
    from teardown.steps import parse_steps

    tt = [{"t": 0.0, "text": "talking here about stuff"}]
    with pytest.raises(ValueError, match="no usable steps"):
        parse_steps(json.dumps({"device": "d", "tools_summary": [], "steps": []}), 60, tt)
    with pytest.raises(ValueError, match="no usable steps"):
        parse_steps(json.dumps({"device": "d", "tools_summary": [], "steps": []}), 60, None)


# F9: token-looking model text survives template substitution literally.
def test_template_tokens_not_reexpanded():
    import handler
    import pages

    subs = {
        "__STEPHARDWARE__": "[]",
        "__STEPTIMES__": "[]",
        "__CSS__": "",
        "__DEVICE__": html_mod.escape("Phone __PROGRESS__ model"),
        "__NSTEPS__": "1",
        "__JOB__": "j",
        "__POSTER__": "",
        "__TOOLS__": "",
        "__PARTS__": "",
        "__TRUNCATION__": "",
        "__ATTRIBUTION__": "",
        "__STEPS__": "",
        "__RAIL__": "",
        "__PROGRESS__": "<SEGS>",
    }
    resp = re.sub(r"__(?:STEPHARDWARE|STEPTIMES|CSS|DEVICE|NSTEPS|JOB|POSTER|TOOLS|PARTS|TRUNCATION|ATTRIBUTION|STEPS|RAIL|PROGRESS)__",
                  lambda m: subs[m.group(0)], pages.GUIDE)
    assert "Phone __PROGRESS__ model" in resp
    assert "Phone <SEGS> model" not in resp
    assert "subs[match.group(0)]" in open(handler.__file__, encoding="utf-8").read()


# F10: JSON null title/instruction drops the step instead of rendering "None".
def test_null_title_instruction_dropped():
    from teardown.steps import parse_steps

    tt = [{"t": 0.0, "text": "pull the battery out now please"}]
    out = parse_steps(json.dumps({"device": "d", "tools_summary": [], "steps": [
        {"t": 0, "anchor_quote": "pull the battery", "part": "battery",
         "title": "Remove it", "tool": "fingers", "instruction": "Do it now"},
        {"t": 0, "anchor_quote": "pull the battery", "part": "battery",
         "title": None, "tool": "fingers", "instruction": None},
    ]}), 60, tt)
    assert [(s["title"], s["instruction"]) for s in out["steps"]] == [("Remove it", "Do it now")]
    assert all(s["title"] != "None" and s["instruction"] != "None" for s in out["steps"])


# F11: NaN/inf step times dropped at parse; approx_clock never crashes.
def test_nan_time_dropped_and_clock_safe():
    from teardown.present import approx_clock
    from teardown.steps import parse_steps

    tt = [{"t": 0.0, "text": "pull the battery out now please"}]
    out = parse_steps(json.dumps({"device": "d", "tools_summary": [], "steps": [
        {"t": float("nan"), "anchor_quote": "pull the battery", "part": "p",
         "title": "Bad", "tool": "f", "instruction": "x"},
        {"t": 0, "anchor_quote": "pull the battery", "part": "p",
         "title": "Good", "tool": "f", "instruction": "x"},
    ]}), 60, tt)
    assert [s["title"] for s in out["steps"]] == ["Good"]
    assert approx_clock(float("nan")) == "about 00:00 (±30s)"
    assert approx_clock(float("inf")) == "about 00:00 (±30s)"
    assert approx_clock(95) == "about 01:35 (±30s)"


# Suspicion (a): malformed hand-edited plan.json is rejected, not rendered.
def test_load_plan_rejects_unrenderable_steps(tmp_path, monkeypatch):
    import jobs

    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(jobs, "DATA", str(data))
    (data / "badjob").mkdir()
    (data / "badjob" / "plan.json").write_text(
        json.dumps({"device": "x", "steps": [{"foo": 1}]}), encoding="utf-8")
    assert jobs.load_plan("badjob") is None
    (data / "goodjob").mkdir()
    (data / "goodjob" / "plan.json").write_text(
        json.dumps({"device": "x", "steps": [{"title": "T", "t": 1.0, "image": "s.png"}]}),
        encoding="utf-8")
    assert jobs.load_plan("goodjob") is not None


# --- second audit round (G1-G8) ---

def _job_dir(tmp_path, monkeypatch, name):
    import jobs

    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    monkeypatch.setattr(jobs, "DATA", str(data))
    (data / name).mkdir(exist_ok=True)
    return data / name


# G1: steps without an image path are malformed -> None -> 404, not a 500.
def test_load_plan_rejects_steps_without_image(tmp_path, monkeypatch):
    import jobs

    d = _job_dir(tmp_path, monkeypatch, "noimg")
    (d / "plan.json").write_text(
        json.dumps({"device": "x", "steps": [{"title": "T", "t": 1.0}]}), encoding="utf-8")
    assert jobs.load_plan("noimg") is None


def test_guide_poster_tolerates_missing_image(tmp_path, monkeypatch):
    import threading
    from http.client import HTTPConnection
    from http.server import ThreadingHTTPServer

    import handler
    import jobs
    from http_util import cookie_header

    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(jobs, "DATA", str(data))
    monkeypatch.setattr("config.DATA", str(data))
    job = "ab" * 16
    (data / job).mkdir()
    (data / job / "plan.json").write_text(
        json.dumps({"device": "x", "steps": [
            {"title": "T", "t": 1.0, "image": "steps/step-1.png"}]}),
        encoding="utf-8")
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler.H)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        cookie = cookie_header([job]).split(";", 1)[0]
        conn = HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", f"/jobs/{job}", headers={"Cookie": cookie})
        resp = conn.getresponse()
        assert resp.status == 200
        assert b"stepTimes" in resp.read()
        conn.close()
    finally:
        server.shutdown()
        server.server_close()


# G7: non-finite t and empty step lists are malformed.
def test_load_plan_rejects_nan_t_and_empty_steps(tmp_path, monkeypatch):
    import jobs

    d = _job_dir(tmp_path, monkeypatch, "nanjob")
    (d / "plan.json").write_text(
        '{"device": "x", "steps": [{"title": "T", "t": NaN, "image": "s.png"}]}',
        encoding="utf-8")
    assert jobs.load_plan("nanjob") is None
    e = _job_dir(tmp_path, monkeypatch, "emptyjob")
    (e / "plan.json").write_text(
        json.dumps({"device": "x", "steps": []}), encoding="utf-8")
    assert jobs.load_plan("emptyjob") is None


# G2: the reservation covers the planner's JSON-repair retry (2 calls).
def test_reservation_covers_planner_repair_retry(monkeypatch):
    import budget

    monkeypatch.setattr(budget, "TOKEN", "")
    res = budget.job_reservation(90, 6, "muse-spark-1.3")
    planner_one = (budget.EST["planner_input_tokens"] * budget.spark_rates("muse-spark-1.3")[0]
                   + budget.EST["planner_output_tokens"] * budget.spark_rates("muse-spark-1.3")[1])
    assert res >= 2 * planner_one
    meter = budget.JobMeter("job", res, "muse-spark-1.3")
    for _ in range(2):
        est = meter.spark_before(budget.EST["planner_input_tokens"],
                                 budget.EST["planner_output_tokens"])
        meter.spark_after(est, None)
    assert meter.actual == pytest.approx(2 * planner_one)


# G3: concurrent check/add pairs cannot overspend the reservation.
def test_meter_atomic_under_concurrency(monkeypatch):
    import budget

    monkeypatch.setattr(budget, "TOKEN", "")
    meter = budget.JobMeter("job", 0.002, "muse-spark-1.3")
    est = meter.spark_before(100, 100)
    meter.spark_after(est, None)
    meter2 = budget.JobMeter("job2", 0.002, "muse-spark-1.3")
    e = 100 * meter2.rin + 100 * meter2.rout
    assert e > 0
    outcomes = []

    def work():
        try:
            got = meter2.spark_before(100, 100)
            import time as _time
            _time.sleep(0.02)
            meter2.spark_after(got, None)
            outcomes.append(True)
        except budget.BudgetExhausted:
            outcomes.append(False)

    threads = [threading.Thread(target=work) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert outcomes.count(True) * e <= 0.002 + 1e-9
    assert meter2.actual <= 0.002 + 1e-9
    # Sequential semantics preserved: under-estimate charges actual...
    seq = budget.JobMeter("seq", 50, "muse-spark-1.3")
    s_est = seq.spark_before(1000, 100)
    seq.spark_after(s_est, {"input_tokens": 0, "output_tokens": 0})
    assert seq.actual == pytest.approx(s_est)
    # ...and unpaired _add still moves actual (test_hardening compat).
    seq2 = budget.JobMeter("seq2", 50, "muse-spark-1.3")
    seq2.spark_after(1.0, {"input_tokens": 12, "output_tokens": 4})
    assert seq2.actual == pytest.approx(1.0)


# G4: deleting a finished step PNG forces re-segmentation on resume.
def test_resume_rebuilds_missing_step_image(tmp_path, monkeypatch):
    import os

    import numpy as np
    from unittest.mock import patch

    from teardown import orchestrate

    cv2 = pytest.importorskip("cv2")
    out = tmp_path / "out"
    (out / "steps").mkdir(parents=True)
    vid = tmp_path / "v.mp4"
    vid.write_bytes(b"x" * 100)

    def fake_extract(vp, times, paths):
        for p in paths:
            cv2.imwrite(p, np.zeros((8, 8, 3), np.uint8))
        return paths

    def seg(api, frame, part):
        return {"bounds": (0, 0, 4, 4), "mask": np.ones((4, 4), np.uint8), "confidence": 0.9}

    def ann(frame, bounds, mask, index, final, **kw):
        cv2.imwrite(final, np.zeros((8, 8, 3), np.uint8))

    plan = {"steps": [{"t": 1.0, "part": "battery", "title": "T"}], "duration": 60.0}
    with patch.object(orchestrate.ingest, "extract_frames", side_effect=fake_extract):
        orchestrate.illustrate(None, str(vid), plan, str(out), segment_part=seg,
                               annotate=ann, pick_frame=lambda *a: 0, workers=1)
    os.remove(os.path.join(str(out), plan["steps"][0]["image"]))
    calls = []

    def counting(api, frame, part):
        calls.append(part)
        return seg(api, frame, part)

    plan2 = {"steps": [{"t": 1.0, "part": "battery", "title": "T"}], "duration": 60.0}
    with patch.object(orchestrate.ingest, "extract_frames", side_effect=fake_extract):
        orchestrate.illustrate(None, str(vid), plan2, str(out), segment_part=counting,
                               annotate=ann, pick_frame=lambda *a: 0, workers=1)
    assert calls == ["battery"]
    assert os.path.isfile(os.path.join(str(out), plan2["steps"][0]["image"]))


# G6: threaded progress reports the finished step's own index.
def test_threaded_on_step_reports_step_index(tmp_path):
    import time

    import numpy as np
    from unittest.mock import patch

    from teardown import orchestrate

    cv2 = pytest.importorskip("cv2")
    out = tmp_path / "out"
    (out / "steps").mkdir(parents=True)
    vid = tmp_path / "v.mp4"
    vid.write_bytes(b"y" * 100)

    with patch.object(orchestrate.ingest, "extract_frames",
                      side_effect=lambda vp, ts, ps: [
                          cv2.imwrite(p, np.zeros((8, 8, 3), np.uint8)) or p for p in ps]):
        plan = {"steps": [{"t": float(i), "part": ("SLOW" if i == 0 else f"F{i}"),
                           "title": f"T{i}"} for i in range(4)], "duration": 60.0}

        def seg(api, frame, part):
            time.sleep(0.3 if part == "SLOW" else 0.01)
            return {"bounds": (0, 0, 4, 4), "mask": np.ones((4, 4), np.uint8),
                    "confidence": 0.9}

        seen = []
        orchestrate.illustrate(
            None, str(vid), plan, str(out), segment_part=seg,
            annotate=lambda f, b, m, i, fin, **k: cv2.imwrite(
                fin, np.zeros((8, 8, 3), np.uint8)),
            pick_frame=lambda *a: 0, workers=4, on_step=lambda i, n: seen.append(i))
    assert sorted(seen) == [0, 1, 2, 3]
    assert seen[0] != 0  # the slow step 0 cannot finish first


# G5: webm remux replaces video.mp4 in place, no sidecar litter.
def test_worker_remux_replaces_video_mp4(tmp_path):
    pytest.importorskip("cv2")
    import shutil
    import subprocess

    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is not installed")
    webm = tmp_path / "clip.webm"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=64x64:d=1",
                    "-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p", str(webm)],
                   check=True, capture_output=True)
    from teardown.ingest import is_ebml, remux_to_mp4

    assert is_ebml(str(webm))
    jobdir = tmp_path / "job"
    jobdir.mkdir()
    video_path = str(jobdir / "video.mp4")
    shutil.copy(str(webm), video_path)
    remuxed = remux_to_mp4(video_path)
    os.replace(remuxed, video_path)  # same swap worker.py performs
    assert not is_ebml(video_path)
    assert sorted(os.listdir(jobdir)) == ["video.mp4"]


# G8: a non-numeric TEARDOWN_MAX_DURATION exits 1 cleanly.
def test_cli_bad_max_duration_clean_exit(tmp_path, monkeypatch, capsys):
    import shutil
    import subprocess

    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is not installed")
    video = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=64x64:d=1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)],
                   check=True, capture_output=True)
    from teardown import cli

    monkeypatch.setenv("TEARDOWN_MAX_DURATION", "abc")
    assert cli.main([str(video), "--mock", "--out", str(tmp_path / "o")]) == 1
    err = capsys.readouterr().err
    assert "TEARDOWN_MAX_DURATION" in err
    assert "Traceback" not in err


def test_cli_missing_key_clean_message(capsys, monkeypatch):
    """Missing key exits 1 with the operator message, not a traceback (F1 CLI side)."""
    from teardown import cli
    from teardown.meta_api import MissingApiKey

    def boom(args):
        raise MissingApiKey("MODEL_API_KEY is not set.")

    monkeypatch.setattr(cli, "_run", boom)
    assert cli.main(["x.mp4", "--i-accept-api-cost"]) == 1
    err = capsys.readouterr().err
    assert "MODEL_API_KEY is not set." in err
    assert "Traceback" not in err
