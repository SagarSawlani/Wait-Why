import json, os
import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

VIDEO = r"C:\dream11_project\videos\clip.mp4"
ROI = (895, 345, 80, 150)      # x, y, w, h in FRAME 0 pixels
OUT = "out"
os.makedirs(OUT, exist_ok=True)

cap = cv2.VideoCapture(VIDEO)
FPS = cap.get(cv2.CAP_PROP_FPS)
W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
grays = []
while True:
    ok, f = cap.read()
    if not ok:
        break
    grays.append(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY))
cap.release()
N = len(grays)
print(f"{N} frames, {W}x{H}, {FPS} fps")

# ignore the scorebug and the logo when matching features
mask = np.full((H, W), 255, np.uint8)
mask[980:, :] = 0
mask[:220, :420] = 0

sift = cv2.SIFT_create(nfeatures=3000)
bf = cv2.BFMatcher(cv2.NORM_L2)
kps, des = [], []
for g in grays:
    k, d = sift.detectAndCompute(g, mask)
    kps.append(k)
    des.append(d)

# M[i] maps points in frame i to frame-0 coordinates
M = [np.eye(3)]
inliers_per_frame = [0]
for i in range(1, N):
    Hm, n_in = None, 0
    if des[i] is not None and des[i - 1] is not None and len(kps[i]) > 10 and len(kps[i - 1]) > 10:
        matches = bf.knnMatch(des[i], des[i - 1], k=2)
        good = [m[0] for m in matches if len(m) == 2 and m[0].distance < 0.75 * m[1].distance]
        if len(good) >= 12:
            src = np.float32([kps[i][m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
            dst = np.float32([kps[i - 1][m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
            Hm, inl = cv2.findHomography(src, dst, cv2.RANSAC, 3.0)
            if Hm is not None:
                n_in = int(inl.sum())
    if Hm is None:
        Hm = np.eye(3)
    M.append(M[-1] @ Hm)
    inliers_per_frame.append(n_in)

zoom = [float(1.0 / np.sqrt(abs(np.linalg.det(m[:2, :2])))) for m in M]

# motion inside the stump box, measured after aligning every frame to frame 0
rx, ry, rw, rh = ROI
ones = np.full((H, W), 255, np.uint8)
crops = []
for i in range(N):
    wg = cv2.warpPerspective(grays[i], M[i], (W, H))
    wm = cv2.warpPerspective(ones, M[i], (W, H))
    crop = cv2.GaussianBlur(wg[ry:ry + rh, rx:rx + rw], (5, 5), 0)
    valid = bool((wm[ry:ry + rh, rx:rx + rw] > 250).all())
    crops.append((crop, valid))

energy = [np.nan]
for i in range(1, N):
    if crops[i][1] and crops[i - 1][1]:
        energy.append(float(np.mean(cv2.absdiff(crops[i][0], crops[i - 1][0]))))
    else:
        energy.append(np.nan)
energy = np.array(energy)

peak = int(np.nanargmax(energy))
ratio = float(energy[peak] / (np.nanmedian(energy) + 1e-6))

report = {
    "frames": N,
    "zoom_min": round(min(zoom), 2),
    "zoom_max": round(max(zoom), 2),
    "min_inliers": int(min(inliers_per_frame[1:])) if N > 1 else 0,
    "frames_with_under_30_inliers": [i for i, n in enumerate(inliers_per_frame) if i > 0 and n < 30],
    "stabilized_peak_frame": peak,
    "stabilized_peak_vs_median": round(ratio, 1),
}
with open(f"{OUT}/report2.json", "w") as fh:
    json.dump(report, fh, indent=2)
print(json.dumps(report, indent=2))

fig, ax = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
ax[0].plot(zoom); ax[0].set_ylabel("camera zoom (1.0 = frame 0)")
ax[1].plot(inliers_per_frame); ax[1].set_ylabel("matched features (quality)")
ax[2].plot(energy); ax[2].set_ylabel("motion in stump box (stabilized)")
ax[2].axvline(peak, ls="--", color="red", alpha=0.6)
ax[2].set_xlabel("frame (0-based)")
plt.tight_layout(); plt.savefig(f"{OUT}/signals2.png", dpi=120); plt.close()

# debug video: the green box is the frame-0 stump box projected into every frame
corners = np.float32([[rx, ry], [rx + rw, ry], [rx + rw, ry + rh], [rx, ry + rh]]).reshape(-1, 1, 2)
cap = cv2.VideoCapture(VIDEO)
vw = cv2.VideoWriter(f"{OUT}/debug2.mp4", cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
for i in range(N):
    ok, frame = cap.read()
    if not ok:
        break
    proj = cv2.perspectiveTransform(corners, np.linalg.inv(M[i])).astype(np.int32)
    cv2.polylines(frame, [proj], True, (0, 255, 0), 2)
    cv2.putText(frame, f"frame {i}  zoom {zoom[i]:.2f}", (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
    vw.write(frame)
vw.release(); cap.release()
print("Saved: out/report2.json, out/signals2.png, out/debug2.mp4")