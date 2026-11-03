"""Resume-aware pipeline: transcript, plan, then per-step frames.

Each stage is written to disk before the next one starts. A second run of
the same output directory skips work that already succeeded, including a
step whose marker file is present. API calls stay in the caller-supplied
client so the web app can meter them and the CLI can pass a plain client.
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np

from . import ingest


class NarrationMissing(ValueError):
    """The clip has no speech, so step times cannot be checked."""


def atomic_json(path: str, payload) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    os.replace(tmp, path)


def read_json(path: str):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def ensure_transcript(api, video_path: str, out_dir: str, progress=None) -> list[dict]:
    """Return timed windows, reusing transcript.json when it is already complete."""
    final = os.path.join(out_dir, "transcript.json")
    if os.path.isfile(final):
        data = read_json(final)
        if isinstance(data, list):
            return data
    wav_path = os.path.join(out_dir, "audio.wav")
    wav = ingest.extract_audio(video_path, wav_path)
    if not wav or not ingest.has_speech(wav):
        atomic_json(final, [])
        return []
    offset = ingest.probe_audio_start(video_path)
    windows = api.transcribe_timed(
        wav,
        checkpoint_path=os.path.join(out_dir, "transcript.partial.json"),
        progress=progress,
        offset=offset,
    )
    atomic_json(final, windows)
    return windows


def ensure_plan(api, video_path: str, transcript, duration: float, out_dir: str, plan_fn) -> dict:
    """Return the plan, uploading the video only when no file id is saved yet."""
    partial = os.path.join(out_dir, "plan.partial.json")
    if os.path.isfile(partial):
        plan = read_json(partial)
        if isinstance(plan, dict) and plan.get("steps"):
            return plan
    upload_path = os.path.join(out_dir, "upload.json")
    if os.path.isfile(upload_path):
        video_id = read_json(upload_path)["file_id"]
    else:
        video_id = api.upload_file(video_path)
        atomic_json(upload_path, {"file_id": video_id})
    plan = plan_fn(api, video_id, transcript, duration)
    atomic_json(partial, plan)
    return plan


def illustrate(api, video_path: str, plan: dict, out_dir: str, *,
               segment_part, annotate, pick_frame, workers: int | None = None,
               on_step=None) -> dict:
    """Extract, pick, segment, and draw each step. Finished steps are skipped."""
    steps = plan.get("steps") or []
    steps_dir = os.path.join(out_dir, "steps")
    os.makedirs(steps_dir, exist_ok=True)
    duration = float(plan.get("duration") or 0.0)
    count = len(steps)

    def one(index: int, step: dict) -> None:
        marker_path = os.path.join(steps_dir, f"step-{index + 1}.json")
        if os.path.isfile(marker_path):
            saved = read_json(marker_path)
            if isinstance(saved, dict) and saved.get("image"):
                step.update(saved)
                return
        offsets = (-8, -4, 0, 4, 8)
        times = []
        paths = []
        seen = set()
        for j, delta in enumerate(offsets):
            moment = min(max(0.0, float(step["t"]) + delta), max(0.0, duration - 0.5))
            key = round(moment, 3)
            if key in seen:
                continue
            seen.add(key)
            path = os.path.join(steps_dir, f"cand-{index + 1}-{j}.png")
            times.append(moment)
            paths.append(path)
        try:
            ingest.extract_frames(video_path, times, paths)
        except Exception as exc:
            step["segmented"] = False
            step["image"] = ""
            step["step_error"] = str(exc)[:200]
            step["candidates"] = []
            atomic_json(marker_path, _marker(step))
            return
        candidates = [(t, p) for t, p in zip(times, paths)
                      if os.path.isfile(p) and os.path.getsize(p) > 0]
        if not candidates:
            step["segmented"] = False
            step["image"] = ""
            step["step_error"] = "no usable candidate frames"
            step["candidates"] = []
            atomic_json(marker_path, _marker(step))
            return
        try:
            pick = pick_frame(api, candidates, step.get("part") or "part", step.get("title") or "")
        except Exception as exc:
            if exc.__class__.__name__ == "BudgetExhausted":
                raise
            pick = len(candidates) // 2
        if not isinstance(pick, int) or not (0 <= pick < len(candidates)):
            pick = len(candidates) // 2
        frame = candidates[pick][1]
        final = os.path.join(steps_dir, f"step-{index + 1}.png")
        try:
            hit = segment_part(api, frame, step.get("part") or "part")
            if hit:
                annotate(frame, tuple(hit["bounds"]), hit["mask"], index + 1, final,
                         part_name=step.get("part") or "", instances=hit.get("instances"),
                         highlighted=True)
                step["segmented"] = True
                step["confidence"] = hit.get("confidence")
                step["retried"] = bool(hit.get("retried"))
                step["prompt"] = hit.get("prompt") or step.get("part") or ""
            else:
                annotate(frame, (0, 0, 0, 0), np.zeros((1, 1), dtype=np.uint8), index + 1, final,
                         part_name=step.get("part") or "", highlighted=False)
                step["segmented"] = False
            step["image"] = os.path.relpath(final, out_dir).replace(os.sep, "/")
            step["step_error"] = ""
        except Exception as exc:
            if exc.__class__.__name__ == "BudgetExhausted":
                raise
            step["segmented"] = False
            step["image"] = os.path.relpath(frame, out_dir).replace(os.sep, "/")
            step["step_error"] = str(exc)[:200]
        step["candidates"] = [os.path.relpath(path, out_dir).replace(os.sep, "/")
                              for _t, path in candidates]
        atomic_json(marker_path, _marker(step))

    if workers is None:
        workers = int(os.environ.get("TEARDOWN_STEP_WORKERS", "4"))
    workers = max(1, min(workers, count or 1))
    if workers == 1 or count <= 1:
        for index, step in enumerate(steps):
            one(index, step)
            if on_step:
                on_step(index, count)
        return plan
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one, index, step) for index, step in enumerate(steps)]
        finished = 0
        for future in as_completed(futures):
            future.result()
            finished += 1
            if on_step:
                on_step(finished - 1, count)
    return plan


def _marker(step: dict) -> dict:
    return {
        "image": step.get("image") or "",
        "segmented": bool(step.get("segmented")),
        "step_error": step.get("step_error") or "",
        "candidates": step.get("candidates") or [],
        "confidence": step.get("confidence"),
        "retried": bool(step.get("retried")),
        "prompt": step.get("prompt") or "",
    }
