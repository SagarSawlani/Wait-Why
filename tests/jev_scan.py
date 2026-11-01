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

QUESTIONS = {
    "released": "In `photo`, has the cricket ball already left the bowler's hand? "
                "Answer yes if the bowler's arm has finished the delivery swing and the ball is travelling down the pitch.",
    "passed_bat": "In `photo`, has the cricket ball already travelled past the batter's bat, "
                  "so that it is behind the bat or at the stumps?",
    "stumps_disturbed": "In `photo`, are the three stumps at the far end of the pitch, where the batter stands, "
                        "visibly disturbed: a stump knocked out of line, or a bail off the stumps or in the air?",
    "stumps_visible": "In `photo`, are the stumps at the far end of the pitch clearly visible, "
                      "not hidden by the batter or another player?",
}
# moment name -> (question used, question used as visibility mask or None)
MOMENTS = {
    "release": ("released", None),
    "ball_past_bat": ("passed_bat", None),
    "stumps_hit": ("stumps_disturbed", "stumps_visible"),
}
GEMINI_KEYS = {"release": "release", "ball_past_bat": "ball_at_batter", "stumps_hit": "stumps_hit"}


def to_jpg(frame, max_side):
    h, w = frame.shape[:2]
    s = max_side / max(h, w)
    if s < 1:
        frame = cv2.resize(frame, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return buf.tobytes()


def jev_call(jpg, api_key, state):
    asset = uuid.uuid4().hex[:8] + "-frame"
    headers = {"Authorization": f"Bearer {api_key}",
               "TypeSafe-Danger-Zone-Images": "true",
               "Content-Type": "application/json"}
    questions = {k: {"type": "noul", "instructions": v} for k, v in QUESTIONS.items()}
    models = [state["model"]] if state.get("model") else JEV_MODELS
    last = None
    for model in models:
        body = {"model": model, "state": {"photo": asset},
                "assets": {asset: {"type": "image", "format": "jpg",
                                   "data_base64": base64.b64encode(jpg).decode()}},
                "questions": questions}
        for attempt in range(4):
            r = requests.post(JEV_URL, headers=headers, json=body, timeout=180)
            if r.status_code == 200:
                state["model"] = model          # stick with the model that worked
                return r.json()
            if r.status_code in (401, 403):
                sys.exit("Authentication failed: check TYPESAFE_API_KEY.")
            if r.status_code in (429, 500, 502, 503):
                time.sleep(2 ** attempt * 2)
                continue
            last = f"{model}: HTTP {r.status_code} {r.text[:400]}"
            break
        print("   Jev error ->", last)
    sys.exit(f"All Jev models failed. Last error: {last}")


def noul(resp, name):
    a = (resp.get("answers") or {}).get(name)
    if isinstance(a, dict) and a.get("noul") is not None:
        return float(a["noul"])
    return None


def best_split(pairs):
    """pairs: list of (frame, p). Split that best separates 'no' before from 'yes' after."""
    if len(pairs) < 3:
        return None, 0.0, "too_few_frames"
    p = np.array([q for _, q in pairs])
    n = len(p)
    scores = [np.sum(1 - p[:s]) + np.sum(p[s:]) for s in range(n + 1)]
    s = int(np.argmax(scores))
    if s == n:
        return None, 0.0, "never_yes"
    if s == 0:
        return pairs[0][0], float(np.mean(p)), "yes_from_start"
    margin = float(np.mean(p[s:]) - np.mean(p[:s]))
    return pairs[s][0], margin, "ok"


def first_stable(pairs, thr, k):
    for i in range(len(pairs) - k + 1):
        if all(pairs[i + j][1] >= thr for j in range(k)):
            return pairs[i][0]
    return None


def parse_kv(s):
    if not s:
        return {}
    return {k.strip(): int(v) for k, v in (part.split("=") for part in s.split(","))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--end", type=int, default=22)
    ap.add_argument("--step", type=int, default=1)
    ap.add_argument("--max_side", type=int, default=1280)   # Jev accepted 1280, rejected 1600
    ap.add_argument("--thr", type=float, default=0.6)
    ap.add_argument("--k", type=int, default=2)
    ap.add_argument("--vis_thr", type=float, default=0.5)
    ap.add_argument("--gemini", help="path to a moments.json from the Gemini run")
    ap.add_argument("--truth", help='e.g. "release=4,ball_past_bat=14,stumps_hit=17"')
    ap.add_argument("--out", default="scan1")
    args = ap.parse_args()

    api_key = os.environ.get("TYPESAFE_API_KEY")
    if not api_key:
        sys.exit("Set TYPESAFE_API_KEY first.")
    os.makedirs(args.out, exist_ok=True)

    rows, state = [], {}
    raw_path = os.path.join(args.out, "raw.jsonl")
    open(raw_path, "w").close()
    cap = cv2.VideoCapture(args.video)
    i = 0
    while i <= args.end:
        ok, frame = cap.read()
        if not ok:
            break
        if i >= args.start and (i - args.start) % args.step == 0:
            resp = jev_call(to_jpg(frame, args.max_side), api_key, state)
            with open(raw_path, "a") as fh:
                fh.write(json.dumps({"frame": i, "resp": resp}) + "\n")
            if not rows:
                print("First raw response (check the format):")
                print(json.dumps(resp, indent=2)[:1500])
            row = {"frame": i, **{q: noul(resp, q) for q in QUESTIONS}}
            rows.append(row)
            print(f"frame {i:3d}  " + "  ".join(
                f"{q}={row[q]:.2f}" if row[q] is not None else f"{q}=None" for q in QUESTIONS))
        i += 1
    cap.release()
    if not rows:
        sys.exit("No frames scanned. Check --start/--end and the video path.")

    gem = {}
    if args.gemini and os.path.exists(args.gemini):
        with open(args.gemini) as fh:
            gem = json.load(fh)
    truth = parse_kv(args.truth)

    results = {}
    print("\n=== detected moments ===")
    for m, (q, mask_q) in MOMENTS.items():
        # skip frames where the stumps are hidden, unless they clearly look disturbed anyway
        pairs = [(r["frame"], r[q]) for r in rows if r[q] is not None
                 and (mask_q is None
                      or (r[mask_q] is not None and r[mask_q] >= args.vis_thr)
                      or r[q] >= args.thr)]
        split, margin, status = best_split(pairs)
        stable = first_stable(pairs, args.thr, args.k)
        agree = split is not None and stable is not None and abs(split - stable) <= 1
        conf = "high" if agree and margin >= 0.4 and status == "ok" else "low"
        g = gem.get(GEMINI_KEYS[m])
        g = g.get("frame") if isinstance(g, dict) else g
        res = {"frame": split, "stable_frame": stable, "margin": round(margin, 2),
               "status": status, "confidence": conf, "gemini": g, "truth": truth.get(m)}
        if split is not None and g is not None:
            res["jev_vs_gemini"] = split - g
        if split is not None and m in truth:
            res["error_vs_truth"] = split - truth[m]
        results[m] = res
        print(f"{m:14s} {res}")

    with open(os.path.join(args.out, "scan.json"), "w") as fh:
        json.dump({"rows": rows, "moments": results, "model": state.get("model")}, fh, indent=2)

    fr = [r["frame"] for r in rows]
    plt.figure(figsize=(11, 5))
    for q in QUESTIONS:
        plt.plot(fr, [r[q] if r[q] is not None else np.nan for r in rows], ".-", label=q)
    for m, res in results.items():
        if res["frame"] is not None:
            plt.axvline(res["frame"], ls="--", alpha=0.5)
            plt.text(res["frame"], 1.03, m, rotation=45, fontsize=8)
        if res["truth"] is not None:
            plt.axvline(res["truth"], ls=":", color="black", alpha=0.6)
    plt.ylim(-0.05, 1.15)
    plt.xlabel("frame (0-based)   dashed = Jev pick, dotted = your truth")
    plt.ylabel("Jev probability of 'yes'")
    plt.legend(loc="center right", fontsize=8)
    plt.tight_layout()
    plt.savefig(os.path.join(args.out, "scan.png"), dpi=120)
    print(f"\nSaved {args.out}/scan.json, {args.out}/scan.png, {args.out}/raw.jsonl")


if __name__ == "__main__":
    main()