import cv2, numpy as np, os

W, H, FPS = 854, 480, 30
OUT = "/tmp/synth-frames"
os.makedirs(OUT, exist_ok=True)

BG = (245, 245, 247)
BODY = (120, 125, 130)
COVER = (90, 95, 100)
BOARD = (40, 110, 180)
BATT = (230, 190, 40)
CONN = (240, 240, 240)
SCREW = (30, 30, 30)
TXT = (20, 20, 20)

DX, DY, DW, DH = 177, 90, 500, 300   # device body rect
BX, BY, BW, BH = 257, 220, 300, 110  # battery rect
CX, CY, CW, CH = 420, 180, 60, 36    # connector rect

def base():
    img = np.full((H, W, 3), BG, np.uint8)
    cv2.rectangle(img, (DX, DY), (DX + DW, DY + DH), BODY, -1)
    return img

def internals(img, batt_off=(0, 0), conn_gap=0):
    cv2.rectangle(img, (DX + 20, DY + 20), (DX + DW - 20, DY + DH - 20), BOARD, -1)
    bx, by = BX + batt_off[0], BY + batt_off[1]
    cv2.rectangle(img, (bx, by), (bx + BW, by + BH), BATT, -1)
    cv2.putText(img, "BATTERY", (bx + 90, by + 62), cv2.FONT_HERSHEY_SIMPLEX, 1.0, TXT, 2)
    cy = CY - conn_gap
    cv2.rectangle(img, (CX, cy), (CX + CW, cy + CH), CONN, -1)
    cv2.rectangle(img, (CX, cy), (CX + CW, cy + CH), (60, 60, 60), 2)
    return img

def caption(img, text):
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
        cv2.imwrite(f"{OUT}/f{n:05d}.png", img)
        n += 1

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
# Scene 6: reassemble in reverse (11s)
img = base(); internals(img, conn_gap=40, batt_off=(0, -160))
cv2.putText(img, "BATTERY", (BX + 90, DY + DH + 60), cv2.FONT_HERSHEY_SIMPLEX, 1.0, TXT, 2)
cv2.rectangle(img, (BX, DY + DH + 15), (BX + BW, DY + DH + 15 + BH // 2), BATT, -1)
caption(img, "Step 6: Reassemble in reverse order")
emit(img, FPS * 11)
print("frames:", n)
