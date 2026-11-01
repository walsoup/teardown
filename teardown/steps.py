"""Stage 2: turn the clip into structured guide steps with Muse Spark.

Spark watches the video (uploaded via the Files API) and reads the
transcript, then picks the moments that should become guide steps.
We ask for strict JSON so the rest of the pipeline stays dumb.
"""

from __future__ import annotations

import json
import re

import os

from .meta_api import MetaApi

SPARK_MODEL = os.environ.get("TEARDOWN_SPARK_MODEL", "muse-spark-1.3")

PROMPT = """You are planning an illustrated, iFixit-style repair guide from a disassembly video.

Transcript of the narration (may be empty):
\"\"\"{transcript}\"\"\"

Watch the video and pick 6-8 key moments that would make good guide steps: the moments where a part is removed, disconnected, or installed.

Return ONLY JSON (no markdown fences) in exactly this shape:
{{
  "device": "<what is being taken apart>",
  "steps": [
    {{
      "t": <time in seconds, number>,
      "part": "<short concrete noun phrase for the ONE main part visible at this moment, e.g. 'battery', 'logic board', 'display cable' - this is sent to a segmentation model, so keep it visual and concrete>",
      "title": "<short step title, e.g. 'Remove the battery'>",
      "instruction": "<one sentence telling the reader what to do>"
    }}
  ]
}}

Rules:
- steps must be ordered by time
- t must be within [0, {duration:.0f}]
- pick moments where the part is clearly visible, not mid-motion blur
"""


def plan_steps(api: MetaApi, video_file_id: str, transcript: str, duration: float) -> dict:
    text = api.respond(
        SPARK_MODEL,
        [
            {"type": "input_text", "text": PROMPT.format(transcript=transcript or "(no narration)", duration=duration)},
            {"type": "input_file", "file_id": video_file_id},
        ],
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
            }
        )
    steps.sort(key=lambda s: s["t"])
    return {"device": str(data.get("device", "device")), "steps": steps}
