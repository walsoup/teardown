"""Stage 4: draw the guide look with OpenCV.

Per step: dim everything except the segmented part, trace the part
outline, drop a numbered badge, and add a 2x zoom inset of the part.
"""

from __future__ import annotations

import numpy as np

_cv2 = None
def _cv():
    global _cv2
    if _cv2 is None:
        import cv2
        _cv2 = cv2
    return _cv2

ACCENT = (200, 130, 0)      # iFixit-ish blue, BGR
BADGE = (60, 60, 220)       # red-ish badge, BGR


def full_frame_mask(shape: tuple[int, int], box: tuple[int, int, int, int], mask: np.ndarray) -> np.ndarray:
    """Place the HxW part raster at the box position in a full-frame mask."""
    h, w = shape
    full = np.zeros((h, w), dtype=np.uint8)
    x1, y1, x2, y2 = box
    mh, mw = mask.shape[:2]
    x1c, y1c = max(0, x1), max(0, y1)
    x2c, y2c = min(x1 + mw, w), min(y1 + mh, h)
    if x2c <= x1c or y2c <= y1c:
        return full
    full[y1c:y2c, x1c:x2c] = mask[y1c - y1: y2c - y1, x1c - x1: x2c - x1]
    return full


def annotate(frame_path: str, box: tuple[int, int, int, int], mask: np.ndarray,
             step_no: int, out_path: str, part_name: str = "",
             instances: list | None = None, highlighted: bool = True) -> str:
    """Draw the guide frame.

    `instances`, when set, is every accepted mask for the noun, not only the
    highest-scoring one. `highlighted=False` stamps a clean frame as
    "not highlighted" so a miss is not drawn as a finished outline.
    """
    cv = _cv()
    frame = cv.imread(frame_path)
    if frame is None:
        raise RuntimeError(f"could not read frame {frame_path}")
    height, width = frame.shape[:2]
    part = np.zeros((height, width), dtype=np.uint8)
    boxes: list[tuple[int, int, int, int]] = []
    if highlighted:
        pieces = instances if instances else [{"bounds": box, "mask": mask}]
        for piece in pieces:
            piece_box = tuple(piece["bounds"])
            piece_mask = piece["mask"]
            if piece_mask is None or getattr(piece_mask, "size", 0) == 0:
                continue
            placed = full_frame_mask((height, width), piece_box, piece_mask)
            if int(placed.max()) == 0:
                continue
            part = np.maximum(part, placed)
            boxes.append(piece_box)
    if not highlighted or int(part.max()) == 0:
        out = frame.copy()
        _banner(out, "not highlighted")
        _badge(out, step_no, avoid_mask=part)
        if part_name:
            _caption(out, part_name, None)
        if not cv.imwrite(out_path, out):
            raise RuntimeError(f"could not write {out_path}")
        return out_path

    dimmed = (frame * 0.35).astype(np.uint8)
    out = np.where(part[..., None] > 0, frame, dimmed)
    contours, _ = cv.findContours(part, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
    cv.drawContours(out, contours, -1, ACCENT, thickness=max(2, width // 400))
    _inset(out, frame, part, boxes)
    _badge(out, step_no, avoid_mask=part)
    if part_name:
        anchor = boxes[0] if boxes else None
        _caption(out, part_name, anchor)
    if not cv.imwrite(out_path, out):
        raise RuntimeError(f"could not write {out_path}")
    return out_path


def _banner(image: np.ndarray, text: str) -> None:
    cv = _cv()
    height, width = image.shape[:2]
    cv.rectangle(image, (0, height - 36), (width, height), (255, 255, 255), -1)
    cv.putText(image, text, (12, height - 12), cv.FONT_HERSHEY_SIMPLEX,
               0.6, BADGE, 2, cv.LINE_AA)


def _badge(image: np.ndarray, step_no: int, avoid_mask: np.ndarray | None = None) -> None:
    cv = _cv()
    height, width = image.shape[:2]
    cx, cy = 44, 44
    if avoid_mask is not None and avoid_mask.shape[0] >= 90 and avoid_mask.shape[1] >= 90:
        if int(avoid_mask[:90, :90].max()) > 0:
            cx = max(44, width - 44)
    radius = 30
    cv.circle(image, (cx, cy), radius, BADGE, -1)
    cv.circle(image, (cx, cy), radius, (255, 255, 255), 2)
    label = str(step_no)
    scale = 1.1 if len(label) == 1 else (0.8 if len(label) == 2 else 0.55)
    (tw, th), _ = cv.getTextSize(label, cv.FONT_HERSHEY_SIMPLEX, scale, 2)
    cv.putText(image, label, (cx - tw // 2, cy + th // 2), cv.FONT_HERSHEY_SIMPLEX,
               scale, (255, 255, 255), 2, cv.LINE_AA)
    del height


def _caption(image: np.ndarray, text: str, box: tuple[int, int, int, int] | None) -> None:
    cv = _cv()
    height, width = image.shape[:2]
    label = text.strip()[:42]
    if not label:
        return
    (tw, th), _ = cv.getTextSize(label, cv.FONT_HERSHEY_SIMPLEX, 0.55, 1)
    if box is None:
        x, y = 12, 28
    else:
        x = min(max(0, box[0]), max(0, width - tw - 8))
        y = max(th + 6, box[1] - 8)
        if y > height - 8:
            y = max(th + 6, height - 8)
    cv.rectangle(image, (x - 4, y - th - 6), (x + tw + 6, y + 6), (255, 255, 255), -1)
    cv.putText(image, label, (x, y), cv.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20), 1, cv.LINE_AA)


def _inset(image: np.ndarray, frame: np.ndarray, part: np.ndarray,
           boxes: list[tuple[int, int, int, int]]) -> None:
    """2x crop placed on the opposite side of the mask, clamped to the frame."""
    cv = _cv()
    height, width = frame.shape[:2]
    if not boxes:
        return
    x1 = min(box[0] for box in boxes)
    y1 = min(box[1] for box in boxes)
    x2 = max(box[2] for box in boxes)
    y2 = max(box[3] for box in boxes)
    pad = int(0.15 * max(1, max(x2 - x1, y2 - y1)))
    cx1, cy1 = max(0, x1 - pad), max(0, y1 - pad)
    cx2, cy2 = min(width, x2 + pad), min(height, y2 + pad)
    if cx2 <= cx1 or cy2 <= cy1:
        return
    crop = frame[cy1:cy2, cx1:cx2].copy()
    crop_mask = part[cy1:cy2, cx1:cx2]
    if crop.size == 0:
        return
    contours, _ = cv.findContours(crop_mask, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
    cv.drawContours(crop, contours, -1, ACCENT, thickness=max(1, crop.shape[1] // 200))
    zoom = cv.resize(crop, None, fx=2, fy=2, interpolation=cv.INTER_CUBIC)
    zh, zw = zoom.shape[:2]
    max_w, max_h = max(1, width // 3), max(1, height // 3)
    scale = min(max_w / zw, max_h / zh, 1.0)
    if scale < 1.0:
        zoom = cv.resize(zoom, None, fx=scale, fy=scale)
        zh, zw = zoom.shape[:2]
    ys, xs = np.where(part > 0)
    center_x = float(xs.mean()) if len(xs) else width / 2
    ox = 12 if center_x > width / 2 else width - zw - 12
    oy = height - zh - 12
    ox = max(0, min(ox, width - zw))
    oy = max(0, min(oy, height - zh))
    cv.rectangle(image, (max(0, ox - 3), max(0, oy - 3)),
                 (min(width - 1, ox + zw + 3), min(height - 1, oy + zh + 3)), ACCENT, 2)
    image[oy:oy + zh, ox:ox + zw] = zoom


