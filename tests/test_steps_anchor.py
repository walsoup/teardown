"""Regression tests for anchor verification in teardown.steps.parse_steps.

The bug these pin down: a step whose anchor_quote was empty skipped
verification entirely (the old guard was `if chunks and anchor`), so
unverifiable steps shipped in guides. Verification must fail closed:
empty anchor -> drop; quote found nowhere -> drop; quote found in another
window -> re-anchor; every step dropped -> ValueError.
"""
import json
import unittest

from teardown.steps import parse_steps

WINDOWS = [
    {"t": 0.0, "text": "First disconnect any power and pull the battery"},
    {"t": 30.0, "text": "pull this plastic tab up and pop the drive out"},
    {"t": 60.0, "text": "use the black sticks on the RAM springs"},
]


def plan(steps):
    return json.dumps({"device": "laptop", "tools_summary": [], "steps": steps})


def step(t, quote, title="Do the thing"):
    return {"t": t, "anchor_quote": quote, "part": "part", "title": title,
            "tool": "fingers", "fasteners": "", "connectors": "",
            "caution": "", "instruction": "Do it."}


class AnchorVerificationTest(unittest.TestCase):
    def test_empty_anchor_drops_step(self):
        out = parse_steps(plan([step(0.0, ""), step(30.0, "pop the drive out")]),
                          90.0, WINDOWS)
        self.assertEqual([s["title"] for s in out["steps"]],
                         ["Do the thing"])
        self.assertEqual(len(out["steps"]), 1)
        self.assertEqual(out["steps"][0]["t"], 30.0)

    def test_all_empty_anchors_raise(self):
        with self.assertRaises(ValueError):
            parse_steps(plan([step(0.0, ""), step(30.0, "")]), 90.0, WINDOWS)

    def test_missing_anchor_key_drops_step(self):
        s = step(0.0, "")
        del s["anchor_quote"]
        out = parse_steps(plan([s, step(0.0, "pull the battery")]), 90.0, WINDOWS)
        self.assertEqual(len(out["steps"]), 1)

    def test_verbatim_anchor_in_window_kept(self):
        out = parse_steps(plan([step(0.0, "pull the battery")]), 90.0, WINDOWS)
        self.assertEqual(len(out["steps"]), 1)
        self.assertEqual(out["steps"][0]["t"], 0.0)

    def test_anchor_elsewhere_reanchors(self):
        # The quote is only in the t=60 window. A neighboring window must not
        # keep the claimed time or inherit the hit.
        out = parse_steps(plan([step(0.0, "RAM springs")]), 90.0, WINDOWS)
        self.assertEqual(out["steps"][0]["t"], 60.0)

    def test_anchor_nowhere_drops_step(self):
        out = parse_steps(plan([step(0.0, "replace the thermal paste"),
                                step(60.0, "RAM springs")]), 90.0, WINDOWS)
        self.assertEqual(len(out["steps"]), 1)
        self.assertEqual(out["steps"][0]["t"], 60.0)

    def test_untimed_transcript_skips_verification(self):
        out = parse_steps(plan([step(12.0, "anything at all")]), 90.0, None)
        self.assertEqual(len(out["steps"]), 1)


if __name__ == "__main__":
    unittest.main()
