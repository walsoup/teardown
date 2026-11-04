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
import os
import re
import unicodedata

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
      "instruction": "<2-5 sentences telling the reader exactly what to do, in order. Use only what the video or narration shows or says: real actions, real fastener locations, real technique. If detail is not in the source, write less - never invent specifics. Narrated case context (whose device it is, what fault it has) is not an instruction: phrase it as context, e.g. 'In this video the unit is ...'.>",
      "lines": [
        {{"type": "action", "text": "<one thing to do, in order>"}},
        {{"type": "note", "text": "<optional context the narrator actually gave; omit the object if there is none>"}},
        {{"type": "caution", "text": "<only if the narrator warns or a risk is clearly visible; omit otherwise>"}}
      ]
    }}
  ]
}}

Rules:
- steps must follow the narration order; t values must increase monotonically
- t must be within [0, {duration:.0f}]
- do NOT space steps evenly: base each step on where the narration actually moves to a new action
- anchor_quote must be an exact substring of the transcript above, at least a few words long, copied without paraphrase
- lines are the same facts as instruction, split into short bullets. type is action, note, or caution. Do not add a caution bullet unless caution is non-empty.
- NEVER invent fastener counts, screw sizes, connector names, or warnings. An empty field is better than a guessed one.
- when the narrator makes a safety or efficacy claim (e.g. 'this will not damage the device'), attribute it in the instruction (e.g. 'The narrator says ...; that is the creator's claim, not verified guidance') - never state such claims as fact.
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
    prompt = PROMPT.format(transcript=lines, duration=duration, window_s=window_s)
    timed = None if isinstance(transcript, str) else transcript
    text = api.respond(
        SPARK_MODEL,
        [
            {"type": "input_text", "text": prompt},
            {"type": "input_file", "file_id": video_file_id},
        ],
        max_output_tokens=16000,
        timeout=900,
    )
    try:
        return parse_steps(text, duration, timed, window_s)
    except (ValueError, KeyError, TypeError) as first_err:
        last_err: Exception = first_err
    repaired = _relax_json(text)
    if repaired and repaired != text.strip():
        try:
            return parse_steps(repaired, duration, timed, window_s)
        except (ValueError, KeyError, TypeError) as repair_err:
            last_err = repair_err
    # One text-only retry. Do not send the video again to fix bad JSON.
    repair_prompt = (
        prompt
        + "\n\nYour previous reply failed validation: "
        + str(last_err)
        + "\nPrevious reply:\n"
        + (text or "")[:8000]
        + "\nReturn ONLY corrected JSON. Keep every anchor_quote as a verbatim transcript substring."
    )
    text = api.respond(
        SPARK_MODEL,
        [{"type": "input_text", "text": repair_prompt}],
        max_output_tokens=16000,
        timeout=900,
    )
    try:
        return parse_steps(text, duration, timed, window_s)
    except (ValueError, KeyError, TypeError) as last_err:
        raise ValueError(f"plan_steps failed after 2 attempts: {last_err}") from last_err


_MIN_ANCHOR_CHARS = 8


def _norm(s: str) -> str:
    """Casefold, NFKC, unify apostrophes, and drop punctuation for matching."""
    text = unicodedata.normalize("NFKC", s or "")
    text = (text.replace("\u2019", "'").replace("\u2018", "'")
            .replace("\u201c", '"').replace("\u201d", '"'))
    text = text.lower()
    text = re.sub(r"[^\w\s']", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _contains(anchor: str, text: str) -> bool:
    """Word-boundary substring. Short anchors and 'ram' inside 'diagram' fail."""
    if len(anchor) < _MIN_ANCHOR_CHARS:
        return False
    return re.search(r"(?<!\w)" + re.escape(anchor) + r"(?!\w)", text) is not None


def _quote_hits(anchor: str, chunks: list[tuple[float, str]]) -> list[float]:
    """Window starts that contain the quote.

    A quote that sits wholly inside a window is credited only to that window.
    A quote split across a boundary is credited to the earlier window. The
    earlier window is not a candidate just because the next one matches.
    """
    hits: list[float] = []
    for index, (start, text) in enumerate(chunks):
        if _contains(anchor, text):
            hits.append(start)
            continue
        if index + 1 < len(chunks):
            _next_start, nxt = chunks[index + 1]
            if _contains(anchor, nxt):
                continue
            if _contains(anchor, text + " " + nxt):
                hits.append(start)
    return hits


def _relax_json(text: str) -> str:
    """Strip fences and trailing commas so a nearly-valid plan can be parsed."""
    cleaned = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.MULTILINE).strip()
    if not cleaned.startswith("{"):
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end > start:
            cleaned = cleaned[start:end + 1]
    return re.sub(r",\s*([}\]])", r"\1", cleaned)


def _step_lines(raw) -> list[dict]:
    lines: list[dict] = []
    if not isinstance(raw, list):
        return lines
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        kind = str(item.get("type") or "action")
        if kind not in ("action", "caution", "note"):
            kind = "action"
        lines.append({"type": kind, "text": text})
    return lines


def _as_tools(raw) -> list[str]:
    if isinstance(raw, str):
        return [raw] if raw.strip() else []
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item).strip()]
    return []


def parse_steps(text: str, duration: float, timed_transcript=None,
                window_s: float = 30.0) -> dict:
    """Tolerant JSON extraction plus mechanical anchor verification.

    A timed transcript (including an empty list) makes every step prove its
    quote. The step's timestamp snaps to the window that actually contains
    the quote. A quote found nowhere, or a quote too short to be distinctive,
    drops that step only. One malformed step does not discard the rest.
    `timed_transcript=None` is the legacy untimed path and skips the check.
    """
    cleaned = _relax_json(text)
    data = json.loads(cleaned)
    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list):
        raise ValueError("steps must be a list")
    # None means "do not verify". An empty list is a transcript with no speech
    # and must fail closed rather than skip the check.
    chunks = None
    if timed_transcript is not None:
        chunks = [(float(chunk["t"]), _norm(chunk["text"])) for chunk in timed_transcript]
    steps = []
    for raw in raw_steps:
        if not isinstance(raw, dict):
            continue
        try:
            claimed = float(raw["t"])
        except (TypeError, ValueError, KeyError):
            continue
        claimed = min(max(claimed, 0.0), duration)
        anchor = _norm(str(raw.get("anchor_quote", "")))
        if chunks is not None:
            if not anchor or len(anchor) < _MIN_ANCHOR_CHARS:
                continue
            hits = _quote_hits(anchor, chunks)
            if not hits:
                continue
            claimed = min(hits, key=lambda found: (abs(found - claimed), found))
        try:
            title = str(raw["title"]).strip()
            instruction = str(raw["instruction"]).strip()
        except KeyError:
            continue
        if not title or not instruction:
            continue
        part = str(raw.get("part") or "").strip()
        if not part or part == "None":
            part = "part"
        caution = str(raw.get("caution") or "")
        if caution == "None":
            caution = ""
        lines = _step_lines(raw.get("lines"))
        if not lines:
            lines = [{"type": "action", "text": instruction}]
        if caution.strip() and not any(item["type"] == "caution" for item in lines):
            lines.append({"type": "caution", "text": caution.strip()})
        steps.append(
            {
                "t": claimed,
                "part": part,
                "title": title,
                "instruction": instruction,
                "tool": str(raw.get("tool") or ""),
                "fasteners": str(raw.get("fasteners") or ""),
                "connectors": str(raw.get("connectors") or ""),
                "caution": caution,
                "source": str(raw.get("anchor_quote") or ""),
                "lines": lines,
            }
        )
    steps.sort(key=lambda step: step["t"])
    if chunks is not None and raw_steps and not steps:
        raise ValueError("plan failed anchor verification: no step survived")
    coverage_warning = False
    if chunks and steps and duration - steps[-1]["t"] > window_s * 2:
        coverage_warning = True
    return {
        "device": str(data.get("device") or "device"),
        "tools_summary": _as_tools(data.get("tools_summary")),
        "steps": steps,
        "coverage_warning": coverage_warning,
    }


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
    sheet_path = None
    try:
        tiles = []
        for j, (_, path) in enumerate(candidates):
            img = cv2.imread(path)
            if img is None:
                img = np.zeros((270, 480, 3), dtype=np.uint8)
            else:
                # letterbox into 480x270 without squashing aspect ratio
                h0, w0 = img.shape[:2]
                scale = min(480 / w0, 270 / h0)
                img = cv2.resize(img, (max(1, int(w0 * scale)), max(1, int(h0 * scale))))
                tile = np.zeros((270, 480, 3), dtype=np.uint8)
                th, tw = img.shape[:2]
                y0, x0 = (270 - th) // 2, (480 - tw) // 2
                tile[y0:y0 + th, x0:x0 + tw] = img
                img = tile
            cv2.rectangle(img, (0, 0), (46, 34), (255, 255, 255), -1)
            cv2.putText(img, str(j + 1), (10, 26), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
            tiles.append(img)
        if not tiles:
            return middle
        rows = []
        blank = np.zeros_like(tiles[0])
        for start in range(0, len(tiles), 3):
            row = tiles[start:start + 3]
            if len(row) < 3:
                row = row + [blank] * (3 - len(row))
            rows.append(np.hstack(row))
        sheet = np.vstack(rows)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            sheet_path = tmp.name
        if not cv2.imwrite(sheet_path, sheet):
            return middle
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
        chosen = _frame_choice(text or "", n)
        if chosen is not None:
            return chosen
    except Exception as exc:
        if exc.__class__.__name__ == "BudgetExhausted":
            raise
        return middle
    finally:
        if sheet_path:
            try:
                os.unlink(sheet_path)
            except OSError:
                pass
    return middle


def _frame_choice(text: str, count: int) -> int | None:
    """Pick a 1-based frame number without taking an unrelated earlier digit.

    "There are 5 frames; pick 3" must select 3, not 5.
    """
    named = re.search(r"(?:pick|choose|frame|number)\D{0,16}(\d+)", text, re.I)
    if named:
        index = int(named.group(1)) - 1
        if 0 <= index < count:
            return index
    for token in reversed(re.findall(r"\d+", text)):
        index = int(token) - 1
        if 0 <= index < count:
            return index
    return None


