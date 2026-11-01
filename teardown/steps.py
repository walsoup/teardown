"""Stage 2: turn the video into structured, detailed guide steps with Muse Spark.

Spark watches the video (uploaded via the Files API) and reads a TIMED
transcript (30-second windows with [mm:ss] markers), then anchors every
guide step to a verbatim narration quote. Spark cannot reliably judge
time from video alone - an earlier version of this stage fed it an
untimed transcript and it allocated step times evenly, producing frames
that did not match the action. parse_steps now verifies every anchor
quote against the claimed window and re-anchors or drops failures.
"""

from __future__ import annotations

import json
import re

import os

from .meta_api import MetaApi

SPARK_MODEL = os.environ.get("TEARDOWN_SPARK_MODEL", "muse-spark-1.3")

PROMPT = """You are writing an illustrated, iFixit-style repair guide from a disassembly video ({duration:.0f} seconds long).

Below is the video's narration transcript in {window_s:.0f}-second windows. Each window starts at the [mm:ss] marker shown. These markers are the ONLY source of truth for timing: you cannot reliably judge time from the video itself, so every step's time must come from the window containing the narration it is based on.

\"\"\"{transcript}\"\"\"

Turn every distinct action into a guide step: each group of screws, each part removed, disconnected, opened, cleaned, or installed. A full disassembly typically needs 15-40 steps; do not stop early or summarize ranges - the final step must come from near the end of the video.

Return ONLY JSON (no markdown fences) in exactly this shape:
{{
  "device": "<what is being taken apart>",
  "tools_summary": ["<every tool actually used in the video>"],
  "steps": [
    {{
      "t": <time in seconds: the start of the transcript window this step is based on>,
      "anchor_quote": "<verbatim words copied exactly from that transcript window>",
      "part": "<short concrete noun phrase for the ONE main part visible at this moment, e.g. 'battery', 'logic board' - this is sent to a segmentation model, so keep it visual and concrete>",
      "title": "<short step title, e.g. 'Remove the battery'>",
      "tool": "<the tool used in this step, e.g. 'Phillips #1 screwdriver', or 'fingers'>",
      "fasteners": "<screw/clip detail ONLY if seen or narrated, e.g. 'two Phillips screws on the battery bay'; empty string if not stated or visible>",
      "connectors": "<cable/connector detail ONLY if seen or narrated, e.g. 'ribbon cable with a flip-up locking tab'; empty string if none>",
      "caution": "<one sentence of warning ONLY if the narrator gives one or a risk is clearly visible, e.g. 'the display cable is still attached - do not lift the panel away'; empty string otherwise>",
      "instruction": "<2-5 sentences telling the reader exactly what to do, in order. Use only what the video or narration shows or says: real actions, real fastener locations, real technique. If detail is not in the source, write less - never invent specifics. Narrated case context (whose device it is, what fault it has) is not an instruction: phrase it as context, e.g. 'In this video the unit is ...'.>"
    }}
  ]
}}

Rules:
- steps must follow the narration order; t values must increase monotonically
- t must be within [0, {duration:.0f}]
- do NOT space steps evenly: base each step on where the narration actually moves to a new action
- anchor_quote must be an exact substring of the transcript above
- NEVER invent fastener counts, screw sizes, connector names, or warnings. An empty field is better than a guessed one.
"""


def plan_steps(api: MetaApi, video_file_id: str, transcript, duration: float,
               window_s: float = 30.0) -> dict:
    """Plan guide steps grounded in a timed transcript.

    transcript: either a plain string (legacy, untimed - NOT recommended,
    the model cannot ground times in it) or a list of {"t", "text"} windows
    from MetaApi.transcribe_timed. Timed windows make every step timestamp
    verifiable against the narration.
    """
    if isinstance(transcript, str):
        lines = transcript or "(no narration)"
    else:
        lines = "\n".join(
            f"[{int(c['t'] // 60)}:{int(c['t'] % 60):02d}] {c['text']}" for c in transcript
        ) or "(no narration)"
    text = api.respond(
        SPARK_MODEL,
        [
            {"type": "input_text", "text": PROMPT.format(
                transcript=lines, duration=duration, window_s=window_s)},
            {"type": "input_file", "file_id": video_file_id},
        ],
        max_output_tokens=16000,
    )
    return parse_steps(text, duration,
                       transcript if not isinstance(transcript, str) else None,
                       window_s)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower()).strip()


def parse_steps(text: str, duration: float, timed_transcript=None,
                window_s: float = 30.0) -> dict:
    """Tolerant JSON extraction plus mechanical anchor verification.

    When a timed transcript is given, every step's anchor_quote must appear
    within one window of its claimed timestamp. A quote found elsewhere
    re-anchors the step to the window where it actually appears; a quote
    found nowhere drops the step (fail-closed: an unverifiable step is
    worse than a missing one).
    """
    cleaned = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    data = json.loads(cleaned)
    chunks = None
    if timed_transcript:
        chunks = [(float(c["t"]), _norm(c["text"])) for c in timed_transcript]
    steps = []
    for s in data["steps"]:
        t = min(max(float(s["t"]), 0.0), duration)
        anchor = _norm(str(s.get("anchor_quote", "")))
        if chunks and anchor:
            near = " ".join(txt for ct, txt in chunks if t - window_s <= ct <= t + window_s)
            if anchor not in near:
                real = None
                for i, (ct, txt) in enumerate(chunks):
                    seg = txt
                    if i + 1 < len(chunks):
                        seg = seg + " " + chunks[i + 1][1]
                    if anchor in seg:
                        real = ct
                        break
                if real is None:
                    continue  # unverifiable step: drop
                t = real
        steps.append(
            {
                "t": t,
                "part": str(s["part"]),
                "title": str(s["title"]),
                "instruction": str(s["instruction"]),
                "tool": str(s.get("tool", "")),
                "fasteners": str(s.get("fasteners", "")),
                "connectors": str(s.get("connectors", "")),
                "caution": str(s.get("caution", "")),
                "source": str(s.get("anchor_quote", "")),
            }
        )
    steps.sort(key=lambda s: s["t"])
    tools = [str(x) for x in data.get("tools_summary", [])]
    return {"device": str(data.get("device", "device")), "tools_summary": tools, "steps": steps}


def pick_frame(api: MetaApi, candidates: list[tuple[float, str]], part: str, title: str) -> int:
    """Choose which candidate frame best shows `part` during `title`.

    candidates: list of (t, png_path). Returns the index into candidates.
    Spark sees the candidates as one labeled contact sheet (multi-image
    input is not reliable); reasoning models need real output-token budget.
    Falls back to the middle candidate on any failure.
    """
    import base64
    import tempfile

    import cv2
    import numpy as np

    middle = len(candidates) // 2
    try:
        tiles = []
        for j, (_, path) in enumerate(candidates):
            img = cv2.imread(path)
            img = cv2.resize(img, (480, 270))
            cv2.rectangle(img, (0, 0), (46, 34), (255, 255, 255), -1)
            cv2.putText(img, str(j + 1), (10, 26), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
            tiles.append(img)
        top = np.hstack(tiles[:3])
        bottom_row = tiles[3:] + [np.zeros_like(tiles[0])] * (3 - len(tiles[3:]))
        sheet = np.vstack([top, np.hstack(bottom_row)])
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            cv2.imwrite(tmp.name, sheet)
            sheet_path = tmp.name
        with open(sheet_path, "rb") as fh:
            data_url = "data:image/png;base64," + base64.b64encode(fh.read()).decode()
        n = len(candidates)
        text = api.respond(
            SPARK_MODEL,
            [
                {"type": "input_text", "text": (
                    f"This contact sheet shows {n} numbered frames (left to right, top row first) from a "
                    f"repair video around the step '{title}'. Reply with ONLY the number (1-{n}) of the "
                    f"frame where '{part}' is most clearly visible in a useful action state: in focus, "
                    "not blocked by hands, showing the actual work. Judge usefulness for a repair guide."
                )},
                {"type": "input_image", "image_url": data_url},
            ],
            max_output_tokens=2000,
        )
        m = re.search(r"\d+", text)
        if m:
            idx = int(m.group()) - 1
            if 0 <= idx < len(candidates):
                return idx
    except Exception:
        pass
    return middle

