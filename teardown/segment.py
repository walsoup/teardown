"""Stage 3: segment the named part on each keyframe with SAM 3.1.

One request per step: a short noun phrase plus the keyframe as a data URL.
Masks stream back in SAM's special-token grammar; the official
`meta_sam_parser` package turns the event stream into typed records and
decodes mask rasters.
"""

from __future__ import annotations

import asyncio
import base64

import numpy as np

from .meta_api import MetaApi


def segment_part(api: MetaApi, frame_png: str, part: str) -> dict | None:
    """Return {bounds, mask, confidence, prompt} for the best match, or None.

    bounds is (left, top, right, bottom) in source-frame pixels, from the
    mask record itself. The mask raster is (bottom-top) x (right-left).

    On a zero-match for a multi-word part name, retries once with the final
    noun (e.g. "battery connector" -> "connector"). A retry match is marked
    retried=True with prompt set to the simplified noun actually used, so a
    weaker or looser match is never silently presented as the original part.
    """
    hit = _segment_once(api, frame_png, part)
    if hit is None and " " in part.strip():
        simple = part.strip().split()[-1]
        if simple != part.strip():
            hit = _segment_once(api, frame_png, simple)
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

    def conf(record) -> float:
        return record.confidence if record.confidence is not None else 0.0

    best = max(masks, key=conf)
    raster = np.frombuffer(
        decode_mask_to_raster(best.mask), dtype=np.uint8
    ).reshape(best.mask.height, best.mask.width)
    b = best.bounds
    return {
        "bounds": (int(b.left), int(b.top), int(b.right), int(b.bottom)),
        "mask": raster,
        "confidence": conf(best),
        "prompt": part,
        "retried": False,
    }


async def _parse(events):
    """Feed the SSE event dicts through the official stream parser."""
    from meta_sam_parser import image_segmentation_format, parse_responses_stream

    async def event_source():
        for event in events:
            yield event

    stream = parse_responses_stream(event_source(), image_segmentation_format())
    return await stream.final_result()
