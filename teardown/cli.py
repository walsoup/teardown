"""teardown - repair footage in, illustrated repair guide out.

Usage:
    python -m teardown path/to/clip.mp4 [--out output] [--mock]

--mock runs the whole pipeline with canned steps and a synthetic mask, so
you can test ingest, rendering and the guide page without spending API
credit. A real run needs MODEL_API_KEY and --i-accept-api-cost.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

import numpy as np

from . import guide, ingest, orchestrate, render


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="teardown", description=__doc__)
    parser.add_argument("video", help="repair/disassembly video (mp4 or mov)")
    parser.add_argument("--out", default="output", help="output directory")
    parser.add_argument("--attribution", default=None,
                        help="source footage credit line shown in the guide footer")
    parser.add_argument("--mock", action="store_true",
                        help="no API calls: canned steps + synthetic masks")
    parser.add_argument("--allow-long", action="store_true",
                        help="allow clips longer than TEARDOWN_MAX_DURATION seconds")
    parser.add_argument("--i-accept-api-cost", action="store_true",
                        help="required for a real run; the CLI spends the MODEL_API_KEY")
    args = parser.parse_args(argv)
    try:
        return _run(args)
    except subprocess.CalledProcessError:
        print("could not read that video. Is ffmpeg installed and the file a video?",
              file=sys.stderr)
        return 1
    except FileNotFoundError:
        print("ffmpeg or ffprobe was not found on PATH.", file=sys.stderr)
        return 1


def _run(args) -> int:
    if not os.path.isfile(args.video):
        print(f"file not found: {args.video}", file=sys.stderr)
        return 1
    if not args.mock and not args.i_accept_api_cost:
        print("refusing to spend API credit without --i-accept-api-cost. "
              "The CLI does not share the web demo's ledger unless "
              "LEDGER_GITHUB_TOKEN is set, and even then you must pass the flag.",
              file=sys.stderr)
        return 2
    os.makedirs(args.out, exist_ok=True)
    if not ingest.looks_like_container(args.video):
        print("that file is not an mp4, mov, or webm.", file=sys.stderr)
        return 1
    duration = ingest.probe_duration(args.video)
    cap = float(os.environ.get("TEARDOWN_MAX_DURATION", "1200"))
    print(f"clip: {duration:.1f}s")
    if not args.mock and not args.allow_long and duration > cap:
        print(f"clip is {duration:.0f}s; the cap is {cap:.0f}s. Pass --allow-long to override.",
              file=sys.stderr)
        return 2
    model = os.environ.get("TEARDOWN_SPARK_MODEL", "muse-spark-1.3")
    if not args.mock and model.endswith("-contributor"):
        print("warning: TEARDOWN_SPARK_MODEL is a contributor model. "
              "Meta may use this footage to train its models. "
              "Only send video you have the right to share.", file=sys.stderr)

    if args.mock:
        plan = _mock_plan(duration)
        plan["attribution"] = args.attribution or ""
        images = []
        for i, step in enumerate(plan["steps"]):
            frame = os.path.join(args.out, f"frame-{i + 1}.png")
            ingest.extract_frame(args.video, step["t"], frame)
            hit = _mock_mask(frame)
            out_img = os.path.join(args.out, f"step-{i + 1}.png")
            render.annotate(frame, hit["bounds"], hit["mask"], i + 1, out_img,
                            part_name=step["part"], highlighted=True)
            step["segmented"] = True
            images.append(out_img)
    else:
        plan, images = _real_run(args, duration)

    plan_path = os.path.join(args.out, "plan.json")
    with open(plan_path, "w", encoding="utf-8") as fh:
        json.dump(plan, fh, indent=2)
    page = guide.build_guide(plan, images, os.path.join(args.out, "guide.html"),
                             source_attribution=args.attribution)
    print(f"guide: {page}")
    return 0


def _real_run(args, duration: float):
    from . import segment as segment_mod
    from . import steps as steps_mod
    from .meta_api import MetaApi

    meter = _maybe_meter(duration)
    api = _MeteredApi(MetaApi(), meter) if meter is not None else MetaApi()
    transcript = orchestrate.ensure_transcript(api, args.video, args.out)
    chars = sum(len(chunk.get("text") or "") for chunk in transcript)
    print(f"transcript: {len(transcript)} windows, {chars} chars")
    if not any((chunk.get("text") or "").strip() for chunk in transcript):
        raise SystemExit(
            "no narration detected in this video. teardown needs narrated footage; "
            "without speech the guide's steps and times can't be verified")

    def plan_fn(client, video_id, timed, dur):
        return steps_mod.plan_steps(client, video_id, timed, dur)

    plan = orchestrate.ensure_plan(api, args.video, transcript, duration, args.out, plan_fn)
    plan["duration"] = duration
    plan["attribution"] = args.attribution or ""
    print(f"plan: {len(plan['steps'])} steps on a {plan['device']}")
    orchestrate.illustrate(
        api, args.video, plan, args.out,
        segment_part=segment_mod.segment_part,
        annotate=render.annotate,
        pick_frame=steps_mod.pick_frame,
        workers=1,
    )
    images = []
    for index, step in enumerate(plan["steps"]):
        image = step.get("image") or ""
        path = os.path.join(args.out, image) if image else ""
        if not path or not os.path.isfile(path):
            frame = os.path.join(args.out, f"frame-{index + 1}.png")
            ingest.extract_frame(args.video, step["t"], frame)
            path = frame
            step["segmented"] = False
        print(f"step {index + 1}: '{step['part']}' -> "
              f"{'segmented' if step.get('segmented') else 'not highlighted'}")
        images.append(path)
    if meter is not None:
        _settle(meter)
    return plan, images


class _MeteredApi:
    """Same reserve-before-call accounting the web demo uses."""

    def __init__(self, inner, meter):
        self._inner = inner
        self.meter = meter
        orig_chunk = inner._transcribe_chunk

        def metered_chunk(wav_path):
            dur = 30.0
            try:
                dur = ingest.probe_duration(wav_path)
            except Exception:
                pass
            est = meter.asr_before(dur)
            try:
                return orig_chunk(wav_path)
            finally:
                meter.asr_after(dur, est)

        inner._transcribe_chunk = metered_chunk

    def respond(self, model, content, **extra):
        web = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
        if web not in sys.path:
            sys.path.insert(0, web)
        import budget

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
            self.meter.spark_after(est, self._inner.last_usage)

    def respond_stream(self, model, content, **extra):
        est = self.meter.sam_before()
        try:
            yield from self._inner.respond_stream(model, content, **extra)
        finally:
            self.meter.sam_after(est)

    def upload_file(self, path, purpose="user_data"):
        return self._inner.upload_file(path, purpose)

    def transcribe_timed(self, wav_path, window_s=30.0, progress=None, **extra):
        return self._inner.transcribe_timed(wav_path, window_s, progress=progress, **extra)


def _maybe_meter(duration: float):
    if not os.environ.get("LEDGER_GITHUB_TOKEN"):
        print("warning: LEDGER_GITHUB_TOKEN is not set, so this run is not on the shared ledger.",
              file=sys.stderr)
        return None
    web = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
    if web not in sys.path:
        sys.path.insert(0, web)
    import budget

    model = os.environ.get("TEARDOWN_SPARK_MODEL", "muse-spark-1.3")
    max_steps = int(os.environ.get("TEARDOWN_MAX_STEPS", "35"))
    reservation = budget.job_reservation(duration, max_steps, model)
    job_id = f"cli-{os.getpid()}"
    if not budget.reserve(job_id, reservation):
        raise SystemExit("the shared API budget is spent")
    meter = budget.JobMeter(job_id, reservation, model)
    meter.job_id = job_id
    return meter


def _settle(meter) -> None:
    web = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
    if web not in sys.path:
        sys.path.insert(0, web)
    import budget

    try:
        budget.settle(meter.job_id, meter.actual)
    except Exception as exc:
        print(f"warning: could not settle the ledger ({exc})", file=sys.stderr)


def _mock_plan(duration: float) -> dict:
    n = 6
    steps = []
    for i in range(n):
        steps.append({
            "t": round(duration * (i + 0.5) / n, 2),
            "part": "battery" if i == 0 else "main component",
            "title": f"Mock step {i + 1}",
            "instruction": "This is a mock instruction used to test the pipeline without API calls.",
            "tool": "Phillips screwdriver" if i == 0 else "fingers",
            "fasteners": "",
            "connectors": "",
            "caution": "",
            "source": "",
            "lines": [{
                "type": "action",
                "text": "This is a mock instruction used to test the pipeline without API calls.",
            }],
            "segmented": True,
        })
    return {
        "device": "test device (mock)",
        "tools_summary": ["Phillips screwdriver"],
        "steps": steps,
        "coverage_warning": False,
    }


def _mock_mask(frame_path: str) -> dict:
    """Synthetic ellipse 'part' in the frame center for --mock runs."""
    import cv2

    frame = cv2.imread(frame_path)
    if frame is None:
        raise SystemExit(f"could not decode a frame from {frame_path}")
    h, w = frame.shape[:2]
    rw, rh = max(2, w // 4), max(2, h // 4)
    x1, y1 = w // 2 - rw, h // 2 - rh
    mask = np.zeros((2 * rh, 2 * rw), dtype=np.uint8)
    cv2.ellipse(mask, (rw, rh), (max(1, rw - 6), max(1, rh - 6)), 0, 0, 360, 1, -1)
    return {"bounds": (x1, y1, x1 + 2 * rw, y1 + 2 * rh), "mask": mask, "confidence": 1.0}
