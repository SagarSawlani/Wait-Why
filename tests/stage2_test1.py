import json, os, sys
import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from ultralytics import YOLO

# ---------------- settings ----------------
VIDEO = r"C:\dream11_project\videos\clip.mp4"      # your frozen clip
ROI = (915, 205, 70, 130)             # (x, y, w, h) in pixels: box around the stumps being hit
OUT = "out"
BALL_IMGSZ = 1280       # bigger = better for a tiny ball, slower
# ------------------------------------------

os.makedirs(OUT, exist_ok=True)
cap = cv2.VideoCapture(VIDEO)
if not cap.isOpened():
    sys.exit(f"Cannot open {VIDEO}")
FPS = cap.get(cv2.CAP_PROP_FPS)
W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
cap.release()
print(f"{VIDEO}: {W}x{H}, {FPS:.3f} fps")

# ---- step 1: save a gridded first frame so you can read the ROI ----
if ROI is None:
    cap = cv2.VideoCapture(VIDEO)
    ok, f = cap.read()
    cap.release()
    for gx in range(0, W, 100):
        cv2.line(f, (gx, 0), (gx, H), (0, 255, 255), 1)
        cv2.putText(f, str(gx), (gx + 3, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
    for gy in range(0, H, 100):
        cv2.line(f, (0, gy), (W, gy), (0, 255, 255), 1)
        cv2.putText(f, str(gy), (3, gy - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
    cv2.imwrite(f"{OUT}/first_frame_grid.png", f)
    sys.exit("Open out/first_frame_grid.png, read the stump box, set ROI=(x, y, w, h), run again.")

rx, ry, rw, rh = ROI
pose_model = YOLO("yolov8n-pose.pt")
ball_model = YOLO("yolov8m.pt")   # COCO model; class 32 = "sports ball"

# ---- pass 1: compute signals frame by frame (frame index is 0-based) ----
energy, raised, ball, wrists = [], [], [], []
prev = None
cap = cv2.VideoCapture(VIDEO)
while True:
    ok, frame = cap.read()
    if not ok:
        break

    # (a) motion energy inside the stump box
    g = cv2.GaussianBlur(cv2.cvtColor(frame[ry:ry + rh, rx:rx + rw], cv2.COLOR_BGR2GRAY), (5, 5), 0)
    energy.append(float(np.mean(cv2.absdiff(g, prev))) if prev is not None else 0.0)
    prev = g

    # (b) raised wrists (wrist above nose) for every person found
    wr = []
    pr = pose_model(frame, verbose=False)[0]
    if pr.keypoints is not None and pr.keypoints.conf is not None:
        kxy = pr.keypoints.xy.cpu().numpy()
        kc = pr.keypoints.conf.cpu().numpy()
        for p in range(len(kxy)):
            if kc[p][0] < 0.5:
                continue
            nose_y = kxy[p][0][1]
            for wi in (9, 10):                       # left / right wrist
                if kc[p][wi] > 0.5 and kxy[p][wi][1] < nose_y:
                    wr.append((float(kxy[p][wi][0]), float(kxy[p][wi][1])))
    wrists.append(wr)
    raised.append(1 if wr else 0)

    # (c) ball: best "sports ball" detection, small boxes only
    b = None
    br = ball_model(frame, imgsz=BALL_IMGSZ, conf=0.03, classes=[32], verbose=False)[0]
    if len(br.boxes) > 0:
        k = int(br.boxes.conf.argmax())
        cx, cy, bw, bh = br.boxes.xywh[k].tolist()
        if bw < 60 and bh < 60:
            b = (cx, cy, float(br.boxes.conf[k]))
    ball.append(b)

    if len(energy) % 25 == 0:
        print("processed", len(energy), "frames")
cap.release()
N = len(energy)

# ---- analysis ----
energy = np.array(energy)
e = np.convolve(energy, np.ones(3) / 3, mode="same")
hit = int(np.argmax(e))
hit_ratio = float(e[hit] / (np.median(e[1:]) + 1e-6))   # how much the peak stands out

min_run = max(3, int(FPS * 0.3))
runs, start = [], None
for i in range(N + 1):
    on = i < N and raised[i] == 1
    if on and start is None:
        start = i
    elif not on and start is not None:
        runs.append((start, i - start))
        start = None
signal = next((s for s, l in runs if l >= min_run and s >= hit), None)

idx = np.array([i for i in range(N) if ball[i] is not None], dtype=float)
coverage = len(idx) / N if N else 0.0
longest, cur = 0, 0
for i in range(N):
    cur = cur + 1 if ball[i] is not None else 0
    longest = max(longest, cur)

ball_first, bounce = None, None
ys = np.array([])
if len(idx) >= 8:
    ball_first = int(idx[0])
    ys = np.array([ball[int(i)][1] for i in idx])
    ys_s = np.convolve(ys, np.ones(3) / 3, mode="same")
    vel = np.gradient(ys_s, idx)
    flips = np.where(np.sign(vel[:-1]) * np.sign(vel[1:]) < 0)[0]
    if len(flips) > 0:
        best = max(flips, key=lambda k: abs(vel[k + 1] - vel[k]))
        bounce = int(idx[best])

marks = {"ball_first": ball_first, "bounce?": bounce, "stumps_hit": hit, "signal": signal}
vals = [v for v in marks.values() if v is not None]
order_ok = vals == sorted(vals)

report = {
    "fps": FPS, "frames": N, "roi": list(ROI),
    "stumps_hit": {"frame": hit, "peak_vs_median": round(hit_ratio, 1)},
    "signal": {"frame": signal, "raised_runs(start,len)": runs, "min_run": min_run},
    "ball": {"coverage": round(coverage, 2), "longest_streak": longest,
             "first_frame": ball_first, "bounce_candidate": bounce},
    "order_ok": order_ok,
}
with open(f"{OUT}/report.json", "w") as fh:
    json.dump(report, fh, indent=2)

# ---- plot ----
fig, ax = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
ax[0].plot(e); ax[0].set_ylabel("motion in stump box")
ax[1].plot(raised); ax[1].set_ylabel("arm raised (any person)")
if len(idx):
    ax[2].plot(idx, ys, ".-")
ax[2].invert_yaxis(); ax[2].set_ylabel("ball y (px, up = up)")
ax[2].set_xlabel("frame (0-based)")
for a in ax:
    for name, fr in marks.items():
        if fr is not None:
            a.axvline(fr, ls="--", color="red", alpha=0.6)
plt.tight_layout(); plt.savefig(f"{OUT}/signals.png", dpi=120); plt.close()

# ---- pass 2: debug video ----
vw = cv2.VideoWriter(f"{OUT}/debug.mp4", cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
cap = cv2.VideoCapture(VIDEO)
trail = []
for i in range(N):
    ok, frame = cap.read()
    if not ok:
        break
    cv2.rectangle(frame, (rx, ry), (rx + rw, ry + rh), (0, 255, 0), 2)
    cv2.putText(frame, f"frame {i}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
    if ball[i] is not None:
        trail.append((int(ball[i][0]), int(ball[i][1])))
    trail = trail[-15:]
    for p in trail:
        cv2.circle(frame, p, 4, (0, 165, 255), -1)
    for (wx, wy) in wrists[i]:
        cv2.circle(frame, (int(wx), int(wy)), 12, (0, 0, 255), 2)
    row = 80
    for name, fr in marks.items():
        if fr is not None and fr <= i < fr + int(FPS * 0.5):
            cv2.putText(frame, f"{name} @ {fr}", (20, row), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
            row += 35
    vw.write(frame)
vw.release(); cap.release()

print(json.dumps(report, indent=2))
print("Saved: out/report.json, out/signals.png, out/debug.mp4")