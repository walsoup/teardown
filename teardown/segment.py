"""Stage 3: segment the named part on each keyframe with SAM 3.1.

One request per step: a short noun phrase plus the keyframe as a data URL.
Masks stream back in SAM's special-token grammar; the official
`meta_sam_parser` package turns the event stream into typed records and
decodes mask rasters.
"""

from __future__ import annotations

import asyncio
import base64
import time

import numpy as np

from .meta_api import MetaApi

# A weak or speck-sized mask is treated as no match. Fail-closed means an
# empty record list AND a mask that is too unsure or too small to draw.
MIN_CONFIDENCE = 0.35
MIN_FOREGROUND = 48


class SegmentTransient(Exception):
    """A thrown SAM error, as opposed to a clean zero-match.

    segment_part raises this (instead of returning None) so the caller can
    record the miss as retryable: a later run may succeed where this one hit
    a transient API failure."""


def evaluate_mask(raster: np.ndarray, bounds: tuple[int, int, int, int],
                  confidence: float | None, min_confidence: float = MIN_CONFIDENCE,
                  min_foreground: int = MIN_FOREGROUND) -> bool:
    """True when a decoded mask is safe to draw.

    The raster must be the same size as the box, must contain real foreground,
    and must clear the confidence floor. A null confidence is a miss.
    """
    if confidence is None or float(confidence) < min_confidence:
        return False
    left, top, right, bottom = (int(v) for v in bounds)
    height, width = bottom - top, right - left
    if height <= 0 or width <= 0:
        return False
    if raster.ndim < 2 or raster.shape[0] != height or raster.shape[1] != width:
        return False
    if raster.size == 0 or int(raster.max()) == 0:
        return False
    return int((raster > 0).sum()) >= min_foreground


def segment_part(api: MetaApi, frame_png: str, part: str, allow_retry: bool = False) -> dict | None:
    """Return {bounds, mask, confidence, prompt} for the best match, or None.

    bounds is (left, top, right, bottom) in source-frame pixels, from the
    mask record itself. The mask raster is (bottom-top) x (right-left).

    On a zero-match for a multi-word part name, retries once with the final
    noun (e.g. "battery connector" -> "connector"). A retry match is marked
    retried=True with prompt set to the simplified noun actually used, so a
    weaker or looser match is never silently presented as the original part.
    """
    hit = None
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            hit = _segment_once(api, frame_png, part)
            last_err = None
            break
        except Exception as exc:
            if exc.__class__.__name__ == "BudgetExhausted":
                raise
            last_err = exc
            if attempt == 0:
                time.sleep(0.4)
    if last_err is not None:
        # A thrown SAM error is a transient miss, not a determinate
        # zero-match: raise so the caller can mark the step retryable
        # instead of caching the miss forever.
        raise SegmentTransient(f"segmentation failed, retryable later: {last_err}")
    # Fail closed: a loose-noun retry too often lands on the wrong instance of
    # the noun (a table cable for "display cable"), and a confident wrong
    # highlight misleads more than no highlight. Retry stays available for
    # experiments via allow_retry, but the pipeline default is direct-only.
    if hit is None and allow_retry and " " in part.strip():
        simple = part.strip().split()[-1]
        if simple != part.strip():
            try:
                hit = _segment_once(api, frame_png, simple)
            except Exception as exc:
                if exc.__class__.__name__ == "BudgetExhausted":
                    raise
                raise SegmentTransient(f"segmentation retry failed, retryable later: {exc}")
            if hit is not None:
                hit["retried"] = True
    return hit


def _segment_once(api: MetaApi, frame_png: str, part: str) -> dict | None:
    with open(frame_png, "rb") as fh:
        data_url = "data:image/png;base64," + base64.b64encode(fh.read()).decode()

    events = api.respond_stream(
        "sam-3.1",
        [
            {"type": "input_text", "text": part},
            {"type": "input_image", "image_url": data_url},
        ],
        metadata={"mask_encoding": "one_bit", "include_confidence": "true"},
    )
    result = asyncio.run(_parse(events))

    masks = [r for r in result.records if r.kind == "mask"]
    if not masks:
        return None  # zero matches is a valid outcome

    from meta_sam_parser import decode_mask_to_raster

    accepted = []
    for record in masks:
        confidence = float(record.confidence) if record.confidence is not None else None
        try:
            raster = np.frombuffer(
                decode_mask_to_raster(record.mask), dtype=np.uint8
            ).reshape(record.mask.height, record.mask.width)
        except Exception:
            continue
        bounds = record.bounds
        box = (int(bounds.left), int(bounds.top), int(bounds.right), int(bounds.bottom))
        if not evaluate_mask(raster, box, confidence):
            continue
        accepted.append({
            "bounds": box,
            "mask": raster,
            "confidence": confidence,
            "prompt": part,
            "retried": False,
            "area": int((raster > 0).sum()),
        })
    if not accepted:
        return None
    accepted.sort(key=lambda item: (item["confidence"], item["area"]), reverse=True)
    best = dict(accepted[0])
    best["instances"] = accepted
    return best


async def _parse(events):
    """Feed the SSE event dicts through the official stream parser."""
    from meta_sam_parser import image_segmentation_format, parse_responses_stream

    async def event_source():
        for event in events:
            yield event

    stream = parse_responses_stream(event_source(), image_segmentation_format())
    return await stream.final_result()
