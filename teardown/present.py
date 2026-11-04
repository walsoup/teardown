"""Shared presentation helpers for the CLI guide and the web guide."""

from __future__ import annotations


def approx_clock(t: float) -> str:
    """Human timestamp. Step times are only known to the ASR window."""
    t = max(0, int(float(t)))
    return f"about {t // 60:02d}:{t % 60:02d} (±30s)"


def standard_precaution(part: str) -> str | None:
    """A standing safety note that is explicitly not from the video.

    Narrated cautions stay in the step. This card only fills the gap when the
    part is a battery, adhesive, or a circuit board and the narrator said nothing.
    """
    text = (part or "").lower()
    if "battery" in text or "cell" in text:
        return ("Standard precaution, not from this video: a lithium battery can "
                "catch fire if it is punctured or bent. Do not pry into the cell.")
    if "adhesive" in text:
        return ("Standard precaution, not from this video: heat softens adhesive, "
                "but too much heat can damage a display or a battery.")
    if "board" in text or "logic" in text:
        return ("Standard precaution, not from this video: ground yourself before "
                "touching a circuit board so a static discharge does not damage it.")
    return None


def step_lines(step: dict) -> list[dict]:
    """Color-coded bullets. Falls back to the instruction paragraph."""
    raw = step.get("lines")
    lines: list[dict] = []
    if isinstance(raw, list):
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
    if not lines:
        instruction = str(step.get("instruction") or "").strip()
        if instruction:
            lines.append({"type": "action", "text": instruction})
    caution = str(step.get("caution") or "").strip()
    if caution and not any(item["type"] == "caution" and item["text"] == caution for item in lines):
        lines.append({"type": "caution", "text": caution})
    return lines


def unique_parts(steps: list[dict]) -> list[str]:
    seen: list[str] = []
    for step in steps:
        part = str(step.get("part") or "").strip()
        if part and part not in seen:
            seen.append(part)
    return seen
