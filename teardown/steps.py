"""Stage 2: turn the video into structured, detailed guide steps with Muse Spark.

Spark watches the video (uploaded via the Files API) and reads the
transcript, then picks the moments that should become guide steps and
writes source-grounded detail for each: fasteners, connectors, cautions
and technique - only where the video or narration actually supports it.
"""

from __future__ import annotations

import json
import re

import os

from .meta_api import MetaApi

SPARK_MODEL = os.environ.get("TEARDOWN_SPARK_MODEL", "muse-spark-1.3")

PROMPT = """You are writing an illustrated, iFixit-style repair guide from a disassembly video.

Transcript of the narration (may be empty):
\"\"\"{transcript}\"\"\"

Watch the ENTIRE video from start to finish and turn every distinct action into a guide step: each group of screws, each part removed, disconnected, opened, cleaned, or installed. A full disassembly typically needs 15-40 steps; do not stop early or summarize ranges - the final step must come from near the end of the video.

Return ONLY JSON (no markdown fences) in exactly this shape:
{{
  "device": "<what is being taken apart>",
  "tools_summary": ["<every tool actually used in the video>"],
  "steps": [
    {{
      "t": <time in seconds, number>,
      "part": "<short concrete noun phrase for the ONE main part visible at this moment, e.g. 'battery', 'logic board' - this is sent to a segmentation model, so keep it visual and concrete>",
      "title": "<short step title, e.g. 'Remove the battery'>",
      "tool": "<the tool used in this step, e.g. 'Phillips #1 screwdriver', or 'fingers'>",
      "fasteners": "<screw/clip detail ONLY if seen or narrated, e.g. 'two Phillips screws on the battery bay'; empty string if not stated or visible>",
      "connectors": "<cable/connector detail ONLY if seen or narrated, e.g. 'ribbon cable with a flip-up locking tab'; empty string if none>",
      "caution": "<one sentence of warning ONLY if the narrator gives one or a risk is clearly visible, e.g. 'the display cable is still attached - do not lift the panel away'; empty string otherwise>",
      "instruction": "<2-5 sentences telling the reader exactly what to do, in order. Use only what the video or narration shows or says: real actions, real fastener locations, real technique. If detail is not in the source, write less - never invent specifics.>"
    }}
  ]
}}

Rules:
- steps must be ordered by time
- t must be within [0, {duration:.0f}]
- pick moments where the part is clearly visible, not mid-motion blur
- NEVER invent fastener counts, screw sizes, connector names, or warnings. An empty field is better than a guessed one.
"""


def plan_steps(api: MetaApi, video_file_id: str, transcript: str, duration: float) -> dict:
    text = api.respond(
        SPARK_MODEL,
        [
            {"type": "input_text", "text": PROMPT.format(transcript=transcript or "(no narration)", duration=duration)},
            {"type": "input_file", "file_id": video_file_id},
        ],
        max_output_tokens=16000,
    )
    return parse_steps(text, duration)


def parse_steps(text: str, duration: float) -> dict:
    """Tolerant JSON extraction: Spark is asked for raw JSON but be forgiving."""
    cleaned = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    data = json.loads(cleaned)
    steps = []
    for s in data["steps"]:
        t = min(max(float(s["t"]), 0.0), duration)
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
