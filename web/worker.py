"""Metered pipeline worker for one accepted job."""
import json
import os
import subprocess
import sys

import budget
from config import DATA, KEY_FILE, MAX_DURATION_S, MAX_STEPS, PIPELINE
from http_util import redact
from jobs import ACTIVE_LOCK, JOBS, _write_status, set_stage
from youtube import _download

def probe_duration(video_path):
    r = subprocess.run(
        ["ffprobe", "-protocol_whitelist", "file,crypto,pipe", "-v", "quiet",
         "-show_entries", "format=duration", "-of", "csv=p=0", video_path],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    return float(r.stdout.strip())


class MeteredApi:
    # Wraps teardown.meta_api.MetaApi; every billable call reserves its
    # worst-case cost before it runs and settles actuals after.
    def __init__(self, meter):
        from teardown.meta_api import MetaApi
        self._inner = MetaApi()
        self.meter = meter
        orig_chunk = self._inner._transcribe_chunk

        def metered_chunk(wav_path):
            dur = 30.0
            try:
                dur = float(subprocess.run(
                    ["ffprobe", "-protocol_whitelist", "file,crypto,pipe",
                     "-v", "quiet", "-show_entries",
                     "format=duration", "-of", "csv=p=0", wav_path],
                    capture_output=True, text=True, timeout=60).stdout.strip())
            except Exception:
                pass
            est = self.meter.asr_before(dur)
            try:
                return orig_chunk(wav_path)
            finally:
                self.meter.asr_after(dur, est)

        self._inner._transcribe_chunk = metered_chunk

    def respond(self, model, content, **extra):
        max_out = extra.get("max_output_tokens") or 2000
        if max_out > 4000:
            est_in = budget.EST["planner_input_tokens"]
            est_out = int(max_out * 1.06)
        else:
            est_in = budget.EST["pick_input_tokens"]
            est_out = int(max_out * 1.25)
        est = self.meter.spark_before(est_in, est_out)
        try:
            return self._inner.respond(model, content, **extra)
        finally:
            # a failed call still gets charged at estimate - overcounting is
            # safe, undercounting is not
            self.meter.spark_after(est, self._inner.last_usage)

    def respond_stream(self, model, content, **extra):
        est = self.meter.sam_before()
        try:
            for ev in self._inner.respond_stream(model, content, **extra):
                yield ev
        finally:
            self.meter.sam_after(est)

    def upload_file(self, path, purpose="user_data"):
        return self._inner.upload_file(path, purpose)  # files API: not billed

    def transcribe_timed(self, wav_path, window_s=30.0, progress=None, **extra):
        return self._inner.transcribe_timed(wav_path, window_s, progress=progress, **extra)
def run_job(job_id, video_path, url, ip):
    """Worker: download (if a link), probe, reserve budget, run the pipeline.
    Everything before reserve() is free; failures settle nothing."""
    try:
        if url:
            JOBS[job_id]["status"] = "downloading"
            set_stage(job_id, "downloading the video", 0)
            if not _download(job_id, url, video_path):
                return
        set_stage(job_id, "checking the video")
        try:
            duration = probe_duration(video_path)
        except Exception:
            raise ValueError(
                "couldn't read that video - is it a standard video file (mp4, mov, webm)?")
        if not duration or duration > MAX_DURATION_S:
            raise ValueError(
                f"that video is about {round(duration / 60)} minutes - this demo handles up to 20")
        from teardown.ingest import is_ebml, looks_like_container, remux_to_mp4
        if not looks_like_container(video_path):
            raise ValueError("that file is not an mp4, mov, or webm")
        if is_ebml(video_path):
            # Meta's files API rejects video/webm; the same streams in an mp4
            # wrapper are accepted, and a copy-remux costs seconds.
            set_stage(job_id, "converting the video for the model")
            video_path = remux_to_mp4(video_path)
        JOBS[job_id]["duration"] = duration
        if ACTIVE_LOCK.locked():
            set_stage(job_id, "waiting for another guide to finish",
                      detail="one build at a time on this free server")
        if not ACTIVE_LOCK.acquire(timeout=3600):
            raise ValueError("the demo stayed busy too long - try again later")
        try:
            set_stage(job_id, "reserving api budget")
            reservation = budget.job_reservation(
                duration, MAX_STEPS, os.environ["TEARDOWN_SPARK_MODEL"])
            try:
                ok = budget.reserve(job_id, reservation)
            except budget.LedgerUnavailable:
                raise ValueError("demo is paused - its budget ledger is unreachable")
            if not ok:
                raise ValueError("the demo's shared API budget is spent - no more guides for now")
            JOBS[job_id]["reservation"] = reservation
            run_pipeline(job_id, video_path)
        finally:
            ACTIVE_LOCK.release()
    except Exception as e:
        message = redact(e)
        if job_id in JOBS:
            JOBS[job_id].update(status="error", error=message, pct=None)
        print(f"[job {job_id[:8]}] failed before pipeline: {message}", flush=True)
def run_pipeline(job_id, video_path):
    JOBS[job_id]["status"] = "processing"
    meter = budget.JobMeter(job_id, JOBS[job_id]["reservation"],
                            os.environ["TEARDOWN_SPARK_MODEL"])
    JOBS[job_id]["_meter"] = meter
    try:
        sys.path.insert(0, PIPELINE)
        from teardown import ingest, orchestrate, render
        from teardown import steps as steps_mod
        from teardown import segment as segment_mod
        if not os.environ.get("MODEL_API_KEY"):
            with open(KEY_FILE, encoding="utf-8") as fh:
                os.environ["MODEL_API_KEY"] = fh.read().strip()
        api = MeteredApi(JOBS[job_id]["_meter"])
        out = os.path.join(DATA, job_id)
        os.makedirs(os.path.join(out, "steps"), exist_ok=True)
        _write_status(job_id, status="processing", stage="extracting the audio")
        set_stage(job_id, "extracting the audio")

        def _asr_progress(i, n):
            set_stage(job_id, f"transcribing the narration (window {i} of {n})",
                      round(10 + 35 * i / max(n, 1), 1))
            _write_status(job_id, status="processing", stage=f"transcribing {i} of {n}")

        transcript = orchestrate.ensure_transcript(api, video_path, out, progress=_asr_progress)
        if not any((c.get("text") or "").strip() for c in transcript):
            raise ValueError(
                "no narration detected in this video - teardown needs narrated "
                "footage; without speech the guide's steps and times can't be verified")
        set_stage(job_id, "sending the video to the model")
        duration = ingest.probe_duration(video_path)

        def plan_fn(client, video_id, timed, dur):
            set_stage(job_id, "watching the video and planning steps",
                      detail="planning has no sub-progress - this is the slow part")
            plan = steps_mod.plan_steps(client, video_id, timed, dur)
            if len(plan["steps"]) > MAX_STEPS:
                plan["steps"] = plan["steps"][:MAX_STEPS]
                plan["truncated"] = True
            plan["attribution"] = JOBS[job_id].get("attribution") or ""
            return plan

        plan = orchestrate.ensure_plan(api, video_path, transcript, duration, out, plan_fn)
        plan["duration"] = duration
        n = len(plan["steps"])

        def on_step(i, total):
            set_stage(job_id, f"illustrating step {i + 1} of {total}",
                      round(55 + 35 * (i + 1) / max(total, 1), 1))

        orchestrate.illustrate(
            api, video_path, plan, out,
            segment_part=segment_mod.segment_part,
            annotate=render.annotate,
            pick_frame=steps_mod.pick_frame,
            on_step=on_step,
        )
        tmp_plan = os.path.join(out, "plan.json.tmp")
        with open(tmp_plan, "w", encoding="utf-8") as fh:
            json.dump(plan, fh, indent=1)
        os.replace(tmp_plan, os.path.join(out, "plan.json"))
        _write_status(job_id, status="done", stage="done")
        JOBS[job_id].update(status="done", device=plan["device"], steps=n, pct=100,
                            truncated=bool(plan.get("truncated")))
    except Exception as e:
        message = redact(e)
        JOBS[job_id].update(status="error", error=message, pct=None)
        _write_status(job_id, status="error", error=message)
        print(f"[job {job_id[:8]}] pipeline failed: {message}", flush=True)
    finally:
        JOBS[job_id]["spent"] = round(meter.actual, 6)
        try:
            budget.settle(job_id, meter.actual)
        except Exception:
            pass  # reservation stands until it expires; new jobs fail closed
