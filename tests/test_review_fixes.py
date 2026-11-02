"""Tests for the dual-review fix batch (agy + Muse Spark audit, 2026-11-02)."""
import numpy as np

from teardown import steps as steps_mod
from teardown import render


def _plan_text(ts):
    import json
    return json.dumps({
        "device": "laptop",
        "tools_summary": [],
        "steps": ts,
    })


def test_reanchor_picks_nearest_occurrence_not_earliest():
    # "remove the screws" appears at t=0 and t=300; a step claiming t=250
    # (outside both +/-30s windows) must anchor to 300 (nearest), not 0 (earliest).
    tt = [
        {"t": 0.0, "text": "first we remove the screws on the cover"},
        {"t": 300.0, "text": "now remove the screws on the hinge"},
    ]
    plan = steps_mod.parse_steps(_plan_text([
        {"t": 250, "anchor_quote": "remove the screws", "part": "hinge",
         "title": "Remove hinge screws", "instruction": "do it"}
    ]), timed_transcript=tt, duration=600)
    assert plan["steps"][0]["t"] == 300.0


def test_parse_tolerates_prose_around_json():
    text = "Here is the plan you asked for.\n" + _plan_text([
        {"t": 5, "anchor_quote": "", "part": "battery",
         "title": "Remove battery", "instruction": "lift it"}
    ]) + "\nHope that helps!"
    plan = steps_mod.parse_steps(text, timed_transcript=None, duration=600)
    assert plan["steps"][0]["title"] == "Remove battery"


def test_full_frame_mask_negative_box_origin_clamped():
    full = render.full_frame_mask((100, 200), (-10, -5, 40, 45),
                                  np.ones((50, 50), dtype=np.uint8) * 255)
    # top-left 40x45 region filled, no wraparound at the far edges
    assert full[0, 0] == 255
    assert full[44, 39] == 255
    assert full[45, :].max() == 0
    assert full[:, 40:].max() == 0
    assert full[99, 199] == 0


def test_full_frame_mask_fully_offscreen_returns_zero():
    full = render.full_frame_mask((100, 200), (-500, -500, -400, -400),
                                  np.ones((50, 50), dtype=np.uint8) * 255)
    assert full.max() == 0


def test_clamped_out_of_range_t_still_verifiable():
    # t beyond duration clamps to duration; anchor there still re-verifies.
    tt = [{"t": 90.0, "text": "finally remove the battery"}]
    plan = steps_mod.parse_steps(_plan_text([
        {"t": 9999, "anchor_quote": "remove the battery", "part": "battery",
         "title": "Remove battery", "instruction": "lift"}
    ]), timed_transcript=tt, duration=95)
    # clamped to duration, and the anchor verifies against the t=90 window
    # within the +/-30s near window, so the step survives at t=95
    assert len(plan["steps"]) == 1
    assert plan["steps"][0]["t"] == 95
