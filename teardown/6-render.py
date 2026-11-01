"""Stage 4: draw the guide look with OpenCV.

Per step: dim everything except the segmented part, trace the part
outline, drop a numbered badge, and add a 2x zoom inset of the part.
"""

from __future__ import annotations

import cv2
import numpy as np

ACCENT = (200, 130, 0)      # iFixit-ish blue, BGR
BADGE = (60, 60, 220)       # red-ish badge, BGR


def full_frame_mask(shape: tuple[int, int], box: tuple[int, int, int, int], mask: np.ndarray) -> np.ndarray:
    """Place the HxW part raster at the box position in a full-frame mask."""
    h, w = shape
    full = np.zeros((h, w), dtype=np.uint8)
    x1, y1, x2, y2 = box
    mh, mw = mask.shape[:2]
    x2c, y2c = min(x1 + mw, w), min(y1 + mh, h)
    if x2c <= x1 or y2c <= y1:
        return full
    full[y1:y2c, x1:x2c] = mask[: y2c - y1, : x2c - x1]
    return full


def annotate(frame_path: str, box: tuple[int, int, int, int], mask: np.ndarray,
             step_no: int, out_path: str) -> str:
    frame = cv2.imread(frame_path)
    if frame is None:
        raise RuntimeError(f"could not read frame {frame_path}")
    h, w = frame.shape[:2]
    part = full_frame_mask((h, w), box, mask)

    # Dim the background, keep the part bright.
    dimmed = (frame * 0.35).astype(np.uint8)
    out = np.where(part[..., None] > 0, frame, dimmed)

    # Outline the part.
    contours, _ = cv2.findContours(part, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(out, contours, -1, ACCENT, thickness=max(2, w // 400))

    # 2x zoom inset of the part, bottom-right corner.
    x1, y1, x2, y2 = box
    pad = int(0.15 * max(x2 - x1, y2 - y1))
    cx1, cy1 = max(0, x1 - pad), max(0, y1 - pad)
    cx2, cy2 = min(w, x2 + pad), min(h, y2 + pad)
    crop = frame[cy1:cy2, cx1:cx2]
    if crop.size:
        zoom = cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        zh, zw = zoom.shape[:2]
        max_w, max_h = w // 3, h // 3
        scale = min(max_w / zw, max_h / zh, 1.0)
        if scale < 1.0:
            zoom = cv2.resize(zoom, None, fx=scale, fy=scale)
            zh, zw = zoom.shape[:2]
        ox, oy = w - zw - 12, h - zh - 12
        cv2.rectangle(out, (ox - 3, oy - 3), (ox + zw + 3, oy + zh + 3), ACCENT, 3)
        out[oy:oy + zh, ox:ox + zw] = zoom

    # Step number badge, top-left.
    cv2.circle(out, (44, 44), 30, BADGE, -1)
    cv2.circle(out, (44, 44), 30, (255, 255, 255), 2)
    cv2.putText(out, str(step_no), (44, 56), cv2.FONT_HERSHEY_SIMPLEX, 1.1,
                (255, 255, 255), 3, cv2.LINE_AA)

    cv2.imwrite(out_path, out)
    return out_path
