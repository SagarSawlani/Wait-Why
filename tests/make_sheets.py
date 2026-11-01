import argparse, os
import cv2
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--video", required=True)
ap.add_argument("--start", type=int, default=0)
ap.add_argument("--end", type=int, default=10**9)   # inclusive
ap.add_argument("--step", type=int, default=2)
ap.add_argument("--cols", type=int, default=4)
ap.add_argument("--per_sheet", type=int, default=12)
ap.add_argument("--cell_w", type=int, default=480)
ap.add_argument("--out", default="sheets")
args = ap.parse_args()

os.makedirs(args.out, exist_ok=True)
for old in os.listdir(args.out):
    if old.endswith(".jpg"):
        os.remove(os.path.join(args.out, old))

# read sequentially so frame numbers are 0-based and exact
cap = cv2.VideoCapture(args.video)
frames, i = {}, 0
while True:
    ok, f = cap.read()
    if not ok or i > args.end:
        break
    if i >= args.start and (i - args.start) % args.step == 0:
        frames[i] = f
    i += 1
cap.release()
idxs = sorted(frames)
print(f"kept {len(idxs)} frames: {idxs[0]}..{idxs[-1]} (step {args.step})")

FONT = cv2.FONT_HERSHEY_SIMPLEX

def make_cell(frame, idx):
    h, w = frame.shape[:2]
    cw = args.cell_w
    ch = int(h * cw / w)
    c = cv2.resize(frame, (cw, ch), interpolation=cv2.INTER_AREA)
    scale = cw / 480 * 1.6
    label = str(idx)
    (tw, th), _ = cv2.getTextSize(label, FONT, scale, 3)
    cv2.rectangle(c, (0, 0), (tw + 16, th + 16), (0, 0, 0), -1)
    cv2.putText(c, label, (8, th + 8), FONT, scale, (255, 255, 255), 3, cv2.LINE_AA)
    cv2.rectangle(c, (0, 0), (cw - 1, ch - 1), (255, 255, 0), 1)
    return c

for s in range(0, len(idxs), args.per_sheet):
    chunk = idxs[s:s + args.per_sheet]
    cells = [make_cell(frames[k], k) for k in chunk]
    ch, cw = cells[0].shape[:2]
    while len(cells) % args.cols:
        cells.append(np.zeros((ch, cw, 3), np.uint8))
    rows = [np.hstack(cells[r:r + args.cols]) for r in range(0, len(cells), args.cols)]
    sheet = np.vstack(rows)
    path = os.path.join(args.out, f"sheet_{chunk[0]:04d}_{chunk[-1]:04d}.jpg")
    cv2.imwrite(path, sheet, [cv2.IMWRITE_JPEG_QUALITY, 92])
    print("saved", path, sheet.shape[1], "x", sheet.shape[0])