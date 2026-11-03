"""Draw a short synthetic disassembly and optionally mux it to mp4.

Frames land in --out (default /tmp/synth-frames). Pass --video to run ffmpeg
over those frames. --no-captions omits the burned-in step labels.
"""

import argparse
import os
import subprocess
import sys

import cv2
import numpy as np

W, H, FPS = 854, 480, 30

BG = (245, 245, 247)
BODY = (120, 125, 130)
COVER = (90, 95, 100)
BOARD = (180, 100, 40)       # blue, BGR
BATT = (40, 190, 230)        # yellow, BGR
CONN = (240, 240, 240)
SCREW = (30, 30, 30)
TXT = (20, 20, 20)

DX, DY, DW, DH = 177, 90, 500, 300
BX, BY, BW, BH = 257, 220, 300, 110
CX, CY, CW, CH = 420, 180, 60, 36

DRAW_CAPTIONS = True
OUT = "/tmp/synth-frames"


def base():
    img = np.full((H, W, 3), BG, np.uint8)
    cv2.rectangle(img, (DX, DY), (DX + DW, DY + DH), BODY, -1)
    return img


def internals(img, batt_off=(0, 0), conn_gap=0, show_battery=True):
    cv2.rectangle(img, (DX + 20, DY + 20), (DX + DW - 20, DY + DH - 20), BOARD, -1)
    if show_battery:
        bx, by = BX + batt_off[0], BY + batt_off[1]
        cv2.rectangle(img, (bx, by), (bx + BW, by + BH), BATT, -1)
        cv2.putText(img, "BATTERY", (bx + 90, by + 62), cv2.FONT_HERSHEY_SIMPLEX, 1.0, TXT, 2)
    cy = CY - conn_gap
    cv2.rectangle(img, (CX, cy), (CX + CW, cy + CH), CONN, -1)
    cv2.rectangle(img, (CX, cy), (CX + CW, cy + CH), (60, 60, 60), 2)
    return img


def caption(img, text):
    if not DRAW_CAPTIONS:
        return
    cv2.rectangle(img, (0, H - 44), (W, H), (255, 255, 255), -1)
    cv2.putText(img, text, (16, H - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.9, TXT, 2)


def screws(img, n):
    for i in range(6):
        x = DX + 50 + i * 80
        if i < n:
            cv2.circle(img, (x, DY + 150), 14, SCREW, -1)
            cv2.line(img, (x - 9, DY + 150), (x + 9, DY + 150), (200, 200, 200), 3)


def cover(img, off):
    cv2.rectangle(img, (DX + off, DY), (DX + DW + off, DY + DH), COVER, -1)


n = 0


def emit(img, frames):
    global n
    for _ in range(frames):
        cv2.imwrite(os.path.join(OUT, f"f{n:05d}.png"), img)
        n += 1


def render():
    os.makedirs(OUT, exist_ok=True)
    # Scene 1: remove six screws (11s)
    for k in range(7):
        img = base(); cover(img, 0); screws(img, 6 - k); caption(img, "Step 1: Remove the six screws")
        emit(img, FPS * 11 // 7 if k < 6 else FPS * 11 - (FPS * 11 // 7) * 6)
    # Scene 2: slide off back cover (11s)
    for k in range(11):
        off = -int((DW + 40) * k / 10)
        img = base(); internals(img); cover(img, off); screws(img, 0); caption(img, "Step 2: Slide off the back cover")
        emit(img, FPS)
    # Scene 3: locate the battery (11s)
    img = base(); internals(img); caption(img, "Step 3: Locate the battery")
    emit(img, FPS * 11)
    # Scene 4: disconnect the battery connector (11s)
    for k in range(11):
        img = base(); internals(img, conn_gap=int(40 * k / 10)); caption(img, "Step 4: Disconnect the battery connector")
        emit(img, FPS)
    # Scene 5: remove the battery (11s)
    for k in range(11):
        img = base(); internals(img, conn_gap=40, batt_off=(0, -int(160 * k / 10))); caption(img, "Step 5: Remove the battery")
        emit(img, FPS)
    # Scene 6: battery is out and sitting above the caption bar, not under it.
    img = base()
    internals(img, conn_gap=40, show_battery=False)
    cv2.rectangle(img, (40, 16), (40 + BW // 2, 16 + BH // 2), BATT, -1)
    cv2.putText(img, "BATTERY", (52, 16 + BH // 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, TXT, 2)
    caption(img, "Step 6: The battery is out")
    emit(img, FPS * 11)
    print("frames:", n)


def mux(video_path):
    subprocess.run(
        ["ffmpeg", "-y", "-framerate", str(FPS), "-i", os.path.join(OUT, "f%05d.png"),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", video_path],
        check=True,
    )
    print("video:", video_path)


def main(argv=None):
    global DRAW_CAPTIONS, OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="/tmp/synth-frames", help="directory for PNG frames")
    parser.add_argument("--video", default=None, help="mux the frames to this mp4")
    parser.add_argument("--no-captions", action="store_true", help="omit burned-in step labels")
    args = parser.parse_args(argv)
    DRAW_CAPTIONS = not args.no_captions
    OUT = args.out
    render()
    if args.video:
        mux(args.video)
    return 0


if __name__ == "__main__":
    sys.exit(main())
