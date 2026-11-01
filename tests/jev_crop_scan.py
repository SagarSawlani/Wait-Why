"""
Crop-based moment detection with Jev.

For each action:
  1. Ask Jev for a box around the actor (bowler / batter / stumps) every few frames,
     and interpolate the box for the frames in between (the camera zooms, so the box must follow).
  2. Crop around that box with padding and enlarge it, so the actor fills the image.
  3. Ask one yes/no question per crop ("has the ball left the hand?", ...).
  4. Find the frame where the answer jumps from no to yes.

Each action is one entry in ACTIONS. Adding a moment (or a sport) means adding an entry.
"""
import argparse, base64, json, os, sys, time, uuid
import cv2
import numpy as np
import requests
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from dotenv import load_dotenv

load_dotenv()

JEV_URL = "https://api.typesafe.ai/v1/systemone"
JEV_MODELS = ["jev-1.14.0", "jev-preview"]
SEND_MAX_SIDE = 1280      # Jev accepted 1280, rejected 1600
CROP_SIDE = 768           # crops are resized so their longest side is this

ACTIONS = {
    "release": {
        "window": [0, 12],
        "crop_target": "the bowler, including both arms",
        "pad": 0.35,
        "question": "In `photo`, has the cricket ball already left the bowler's hand? "
                    "Answer yes if the bowling arm has swung through and the hand is empty.",
        "compare": False,
    },
    "ball_past_bat": {
        "window": [8, 22],
        "crop_target": "the batter at the far end of the pitch, including the bat",
        "pad": 0.5,
        "question": "In `photo`, has the small red cricket ball already gone past the batter's bat, "
                    "so that it is behind the bat towards the stumps, or at the stumps?",
        "compare": False,
    },
    "stumps_hit": {
        "window": [10, 22],
        "crop_target": "the three wooden stumps at the far end of the pitch where the batter stands",
        "pad": 1.0,
        "question": "In `photo`, are the stumps disturbed: a stump knocked out of line, "
                    "or a bail off the stumps or in the air?",
        "compare": True,
        "compare_question": "Compared with `reference`, have the stumps in `photo` changed: "
                            "a stump moved, or a bail lifted off or flying?",
    },
}
GEMINI_KEYS = {"release": "release", "ball_past_bat": "ball_at_batter", "stumps_hit": "stumps_hit"}
STATE = {"model": None}


class JevError(Exception):
    def __init__(self, status, text):
        super().__init__(f"HTTP {status}: {text[:400]}")
        self.status = status


def to_jpg(img, max_side=None):
    if max_side:
        h, w = img.shape[:2]
        s = max_side / max(h, w)
        if s < 1:
            img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return buf.tobytes()


def jev_post(images, questions, api_key):
    """images: {state_name: jpg_bytes}. Each state name can be referenced as `name` in questions."""
    state, assets = {}, {}
    for name, jpg in images.items():
        aid = uuid.uuid4().hex[:8] + "-" + name
        state[name] = aid
        assets[aid] = {"type": "image", "format": "jpg", "data_base64": base64.b64encode(jpg).decode()}
    headers = {"Authorization": f"Bearer {api_key}",
               "TypeSafe-Danger-Zone-Images": "true",
               "Content-Type": "application/json"}
    models = [STATE["model"]] if STATE["model"] else JEV_MODELS
    last = None
    for model in models:
        body = {"model": model, "state": state, "assets": assets, "questions": questions}
        for attempt in range(4):
            r = requests.post(JEV_URL, headers=headers, json=body, timeout=180)
            if r.status_code == 200:
                STATE["model"] = model
                return r.json()
            if r.status_code in (401, 403):
                sys.exit("Authentication failed: check TYPESAFE_API_KEY.")
            if r.status_code in (429, 500, 502, 503):
                time.sleep(2 ** attempt * 2)
                continue
            last = JevError(r.status_code, r.text)
            break
    raise last


def answer(resp, name):
    return (resp.get("answers") or {}).get(name)


def noul(resp, name):
    a = answer(resp, name)
    return float(a["noul"]) if isinstance(a, dict) and a.get("noul") is not None else None


def parse_box(a):
    if not isinstance(a, dict) or not isinstance(a.get("box"), dict):
        return None
    try:
        b = a["box"]
        t, bt, l, r = (float(b[k]) for k in ("top", "bottom", "left", "right"))
    except Exception:
        return None
    if not (0 <= t < bt <= 1 and 0 <= l < r <= 1):
        return None
    return (t, bt, l, r)


def read_frames(video, last):
    cap = cv2.VideoCapture(video)
    frames = []
    while len(frames) <= last:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(f)
    cap.release()
    return frames


def track_boxes(frames, w0, w1, desc, every, api_key, log):
    keys = list(range(w0, w1 + 1, every))
    if keys[-1] != w1:
        keys.append(w1)
    found = {}
    for f in keys:
        try:
            resp = jev_post({"photo": to_jpg(frames[f], SEND_MAX_SIDE)},
                            {"box": {"type": "box", "instructions": f"{desc} in `photo`"}}, api_key)
            b = parse_box(answer(resp, "box"))
        except JevError as e:
            print(f"   box error at frame {f}: {e}")
            b = None
        log.append({"frame": f, "target": desc, "box": b})
        if b:
            found[f] = np.array(b)
        print(f"   box @ {f}: {'ok' if b else 'NONE'}")
    if not found:
        return None
    ks = sorted(found)
    boxes = {}
    for f in range(w0, w1 + 1):
        if f <= ks[0]:
            boxes[f] = found[ks[0]]
        elif f >= ks[-1]:
            boxes[f] = found[ks[-1]]
        else:
            a = max(k for k in ks if k <= f)
            b = min(k for k in ks if k >= f)
            t = 0 if a == b else (f - a) / (b - a)
            boxes[f] = (1 - t) * found[a] + t * found[b]   # linear interpolation between key boxes
    return boxes


def crop(frame, box, pad):
    H, W = frame.shape[:2]
    t, b, l, r = box
    x1, x2, y1, y2 = l * W, r * W, t * H, b * H
    bw, bh = x2 - x1, y2 - y1
    side = max(bw, bh) * (1 + 2 * pad)
    side = max(side, 96)
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    X1, Y1 = int(max(0, cx - side / 2)), int(max(0, cy - side / 2))
    X2, Y2 = int(min(W, cx + side / 2)), int(min(H, cy + side / 2))
    c = frame[Y1:Y2, X1:X2]
    s = CROP_SIDE / max(c.shape[:2])
    return cv2.resize(c, (int(c.shape[1] * s), int(c.shape[0] * s)),
                      interpolation=cv2.INTER_CUBIC if s > 1 else cv2.INTER_AREA)


def find_jump(fr, p, k=2):
    best = None
    for s in range(1, len(p)):
        before, after = p[max(0, s - k):s], p[s:s + k]
        d = float(np.mean(after) - np.mean(before))
        if best is None or d > best[1]:
            best = (fr[s], d, float(np.mean(after)))
    return best


def contact_sheet(crops, path, cols=5, cell=256):
    cells = []
    for f, c in crops:
        im = cv2.resize(c, (cell, int(c.shape[0] * cell / c.shape[1])))
        im = cv2.copyMakeBorder(im, 0, max(0, cell - im.shape[0]), 0, 0, cv2.BORDER_CONSTANT)[:cell]
        cv2.rectangle(im, (0, 0), (60, 32), (0, 0, 0), -1)
        cv2.putText(im, str(f), (6, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cells.append(im)
    while len(cells) % cols:
        cells.append(np.zeros_like(cells[0]))
    rows = [np.hstack(cells[i:i + cols]) for i in range(0, len(cells), cols)]
    cv2.imwrite(path, np.vstack(rows))


def parse_kv(s):
    return {k.strip(): int(v) for k, v in (p.split("=") for p in s.split(","))} if s else {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", default="crop1")
    ap.add_argument("--every", type=int, default=3, help="get a fresh box every N frames")
    ap.add_argument("--only", help="comma list of actions, e.g. ball_past_bat,stumps_hit")
    ap.add_argument("--no_compare", action="store_true")
    ap.add_argument("--gemini", help="moments.json from the Gemini run")
    ap.add_argument("--truth", help='e.g. "release=4,ball_past_bat=16,stumps_hit=17"')
    args = ap.parse_args()

    api_key = os.environ.get("TYPESAFE_API_KEY")
    if not api_key:
        sys.exit("Set TYPESAFE_API_KEY first.")
    os.makedirs(os.path.join(args.out, "crops"), exist_ok=True)

    actions = {k: v for k, v in ACTIONS.items() if not args.only or k in args.only.split(",")}
    last = max(a["window"][1] for a in actions.values())
    frames = read_frames(args.video, last)
    print(f"read {len(frames)} frames")

    gem = json.load(open(args.gemini)) if args.gemini and os.path.exists(args.gemini) else {}
    truth = parse_kv(args.truth)
    results, box_log, all_rows = {}, [], {}

    for name, cfg in actions.items():
        w0, w1 = cfg["window"]
        w1 = min(w1, len(frames) - 1)
        print(f"\n== {name}: frames {w0}..{w1}, crop target: {cfg['crop_target']}")
        boxes = track_boxes(frames, w0, w1, cfg["crop_target"], args.every, api_key, box_log)
        if boxes is None:
            print("   no box found for any key frame, skipping")
            continue

        compare = cfg.get("compare") and not args.no_compare
        ref = crop(frames[w0], boxes[w0], cfg["pad"]) if compare else None
        rows, crops = [], []
        for f in range(w0, w1 + 1):
            c = crop(frames[f], boxes[f], cfg["pad"])
            cv2.imwrite(os.path.join(args.out, "crops", f"{name}_{f:03d}.jpg"), c)
            crops.append((f, c))
            qs = {"q": {"type": "noul", "instructions": cfg["question"]}}
            imgs = {"photo": to_jpg(c)}
            if compare:
                qs["cmp"] = {"type": "noul", "instructions": cfg["compare_question"]}
                imgs["reference"] = to_jpg(ref)
            try:
                resp = jev_post(imgs, qs, api_key)
            except JevError as e:
                if compare and e.status in (400, 422):
                    print(f"   two-image request rejected ({e}); continuing without the comparison")
                    compare = False
                    resp = jev_post({"photo": to_jpg(c)},
                                    {"q": {"type": "noul", "instructions": cfg["question"]}}, api_key)
                else:
                    raise
            row = {"frame": f, "q": noul(resp, "q"), "cmp": noul(resp, "cmp") if compare else None}
            vals = [v for v in (row["q"], row["cmp"]) if v is not None]
            row["p"] = float(np.mean(vals)) if vals else None
            rows.append(row)
            extra = f"  cmp={row['cmp']:.2f}" if row["cmp"] is not None else ""
            print(f"   frame {f:3d}  q={row['q']}{extra}")
        contact_sheet(crops, os.path.join(args.out, f"crops_{name}.jpg"))
        all_rows[name] = rows

        valid = [r for r in rows if r["p"] is not None]
        fr = [r["frame"] for r in valid]
        p = np.array([r["p"] for r in valid])
        jump = find_jump(fr, p) if len(p) >= 3 else None
        res = {"frame": None, "jump": None, "after_mean": None, "confidence": "low"}
        if jump:
            res.update(frame=jump[0], jump=round(jump[1], 2), after_mean=round(jump[2], 2))
            if jump[1] >= 0.3 and jump[2] >= 0.6:
                res["confidence"] = "high"
        g = gem.get(GEMINI_KEYS.get(name, name))
        res["gemini"] = g.get("frame") if isinstance(g, dict) else g
        res["truth"] = truth.get(name)
        if res["frame"] is not None and res["truth"] is not None:
            res["error_vs_truth"] = res["frame"] - res["truth"]
        results[name] = res

    if results.get("stumps_hit", {}).get("frame") is not None:
        d = results["stumps_hit"]["frame"] - 1
        results["ball_past_bat_derived"] = {"frame": d, "rule": "stumps_hit - 1 (bowled)",
                                            "truth": truth.get("ball_past_bat")}

    print("\n=== detected moments ===")
    for k, v in results.items():
        print(f"{k:22s} {v}")

    with open(os.path.join(args.out, "results.json"), "w") as fh:
        json.dump({"model": STATE["model"], "results": results, "rows": all_rows, "boxes": box_log},
                  fh, indent=2, default=lambda o: list(o) if isinstance(o, (tuple, np.ndarray)) else str(o))

    n = len(all_rows)
    if n:
        fig, axes = plt.subplots(n, 1, figsize=(10, 3 * n), squeeze=False)
        for ax, (name, rows) in zip(axes[:, 0], all_rows.items()):
            fr = [r["frame"] for r in rows]
            ax.plot(fr, [r["q"] if r["q"] is not None else np.nan for r in rows], ".-", label="question")
            if any(r["cmp"] is not None for r in rows):
                ax.plot(fr, [r["cmp"] if r["cmp"] is not None else np.nan for r in rows], ".-", label="vs reference")
            res = results.get(name, {})
            if res.get("frame") is not None:
                ax.axvline(res["frame"], ls="--", color="red", alpha=0.6, label="Jev pick")
            if res.get("truth") is not None:
                ax.axvline(res["truth"], ls=":", color="black", label="truth")
            if res.get("gemini") is not None:
                ax.axvline(res["gemini"], ls="-.", color="green", alpha=0.6, label="Gemini")
            ax.set_ylim(-0.05, 1.05)
            ax.set_title(name)
            ax.legend(fontsize=8, loc="center right")
        axes[-1, 0].set_xlabel("frame (0-based)")
        plt.tight_layout()
        plt.savefig(os.path.join(args.out, "scan_crops.png"), dpi=120)
    print(f"\nSaved {args.out}/results.json, scan_crops.png, crops_<action>.jpg, crops/")


if __name__ == "__main__":
    main()