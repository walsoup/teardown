"""teardown - repair footage in, illustrated repair guide out.

Usage:
    python -m teardown path/to/clip.mp4 [--out output] [--mock]

--mock runs the whole pipeline with canned steps and a synthetic mask, so
you can test ingest, rendering and the guide page without spending API
credit. The real run needs MODEL_API_KEY set.
"""

from __future__ import annotations

import argparse
import json
import os

import numpy as np

from . import ingest, render, guide


def main() -> None:
    parser = argparse.ArgumentParser(prog="teardown", description=__doc__)
    parser.add_argument("video", help="repair/disassembly video; long videos supported via chunked audio transcription (tested up to ~20 min)")
    parser.add_argument("--out", default="output", help="output directory")
    parser.add_argument("--attribution", default=None,
                        help="source footage credit line shown in the guide footer")
    parser.add_argument("--mock", action="store_true",
                        help="no API calls: canned steps + synthetic masks")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    duration = ingest.probe_duration(args.video)
    print(f"clip: {duration:.1f}s")

    if args.mock:
        plan = _mock_plan(duration)
        results = [None] * len(plan["steps"])
    else:
        from .meta_api import MetaApi
        from . import steps as steps_mod
        from . import segment as segment_mod

        api = MetaApi()
        wav = ingest.extract_audio(args.video, os.path.join(args.out, "audio.wav"))
        transcript = api.transcribe_timed(wav) if wav else []
        print(f"transcript: {len(transcript)} chars")

        video_id = api.upload_file(args.video)
        plan = steps_mod.plan_steps(api, video_id, transcript, duration)
        print(f"plan: {len(plan['steps'])} steps on a {plan['device']}")

        results = []
        for i, step in enumerate(plan["steps"]):
            frame = os.path.join(args.out, f"frame-{i + 1}.png")
            ingest.extract_frame(args.video, step["t"], frame)
            hit = segment_mod.segment_part(api, frame, step["part"])
            print(f"step {i + 1}: '{step['part']}' -> {'segmented' if hit else 'no match'}")
            results.append(hit)

    plan_path = os.path.join(args.out, "plan.json")
    with open(plan_path, "w") as fh:
        json.dump(plan, fh, indent=2)

    images = []
    for i, (step, hit) in enumerate(zip(plan["steps"], results)):
        frame = os.path.join(args.out, f"frame-{i + 1}.png")
        if args.mock:
            ingest.extract_frame(args.video, step["t"], frame)
            hit = _mock_mask(frame)
        out_img = os.path.join(args.out, f"step-{i + 1}.png")
        if hit is None:  # no mask: use the clean frame rather than dropping the step
            images.append(frame)
        else:
            render.annotate(frame, hit["bounds"], hit["mask"], i + 1, out_img)
            images.append(out_img)

    page = guide.build_guide(plan, images, os.path.join(args.out, "guide.html"),
                             source_attribution=args.attribution)
    print(f"guide: {page}")


def _mock_plan(duration: float) -> dict:
    n = 6
    return {
        "device": "test device (mock)",
        "steps": [
            {
                "t": round(duration * (i + 0.5) / n, 2),
                "part": "main component",
                "title": f"Mock step {i + 1}",
                "instruction": "This is a mock instruction used to test the pipeline without API calls.",
            }
            for i in range(n)
        ],
    }


def _mock_mask(frame_path: str) -> dict:
    """Synthetic ellipse 'part' in the frame center for --mock runs."""
    import cv2

    frame = cv2.imread(frame_path)
    h, w = frame.shape[:2]
    rw, rh = w // 4, h // 4
    x1, y1 = w // 2 - rw, h // 2 - rh
    mask = np.zeros((2 * rh, 2 * rw), dtype=np.uint8)
    cv2.ellipse(mask, (rw, rh), (rw - 6, rh - 6), 0, 0, 360, 1, -1)
    return {"bounds": (x1, y1, x1 + 2 * rw, y1 + 2 * rh), "mask": mask, "confidence": 1.0}

