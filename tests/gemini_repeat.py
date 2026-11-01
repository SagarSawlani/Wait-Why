"""
Stability check for Gemini key-frame detection.
Builds the step-2 contact sheets (same layout as the first pass), asks Gemini N times,
and reports how much each answer moves between runs and how far it is from your truth frames.
"""
import argparse, json, os, sys, time
import cv2
import numpy as np
from PIL import Image
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

MODEL = "gemini-3.8-flash"
EVENT = "Test cricket. The batter was bowled: the delivery hit the stumps and the stumps were disturbed."
MOMENTS = ["release", "ball_at_batter", "stumps_hit", "stumps_disturbed_visible"]
FONT = cv2.FONT_HERSHEY_SIMPLEX


def build_sheets(video, start, end, step, cols, per_sheet, cell_w, out):
    os.makedirs(out, exist_ok=True)
    cap = cv2.VideoCapture(video)
    frames, i = {}, 0
    while i <= end:
        ok, f = cap.read()
        if not ok:
            break
        if i >= start and (i - start) % step == 0:
            frames[i] = f
        i += 1
    cap.release()
    idxs = sorted(frames)
    sheets = []
    for s in range(0, len(idxs), per_sheet):
        chunk = idxs[s:s + per_sheet]
        cells = []
        for k in chunk:
            h, w = frames[k].shape[:2]
            c = cv2.resize(frames[k], (cell_w, int(h * cell_w / w)), interpolation=cv2.INTER_AREA)
            scale = cell_w / 480 * 1.6
            (tw, th), _ = cv2.getTextSize(str(k), FONT, scale, 3)
            cv2.rectangle(c, (0, 0), (tw + 16, th + 16), (0, 0, 0), -1)
            cv2.putText(c, str(k), (8, th + 8), FONT, scale, (255, 255, 255), 3, cv2.LINE_AA)
            cv2.rectangle(c, (0, 0), (c.shape[1] - 1, c.shape[0] - 1), (255, 255, 0), 1)
            cells.append(c)
        while len(cells) % cols:
            cells.append(np.zeros_like(cells[0]))
        sheet = np.vstack([np.hstack(cells[r:r + cols]) for r in range(0, len(cells), cols)])
        path = os.path.join(out, f"sheet_{chunk[0]:04d}_{chunk[-1]:04d}.jpg")
        cv2.imwrite(path, sheet, [cv2.IMWRITE_JPEG_QUALITY, 92])
        sheets.append(path)
    return idxs, sheets


def prompt(step):
    return f"""You are analysing one cricket delivery from a broadcast camera behind the bowler.
Context: {EVENT}

The images are contact sheets in time order. Each cell is one video frame with its frame number
printed in white on a black box at the top-left of the cell. Cells are {step} frame(s) apart.
Always answer with a frame number printed in a cell. Never invent numbers.

Find these moments, each defined by what is visible. Use the labelled frame closest to the moment.
- release: the first frame in which the ball has left the bowler's hand.
- ball_at_batter: the first frame in which the ball is level with the batter's bat or pads.
- stumps_hit: the first frame in which the ball reaches or touches the stumps at the batter's end.
- stumps_disturbed_visible: the first frame in which the stumps are visibly disturbed or a bail is in the air.
- camera_cuts: frames where the picture changes abruptly (a cut or a sudden jump in zoom or angle).
If a moment is not visible in any frame, use null. Do not guess.

Return only JSON:
{{"moments": {{"release": {{"frame": 0, "evidence": ""}}, "ball_at_batter": {{"frame": 0, "evidence": ""}},
"stumps_hit": {{"frame": 0, "evidence": ""}}, "stumps_disturbed_visible": {{"frame": 0, "evidence": ""}}}},
"camera_cuts": []}}"""


def parse_kv(s):
    return {k.strip(): int(v) for k, v in (p.split("=") for p in s.split(","))} if s else {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--end", type=int, default=49)
    ap.add_argument("--step", type=int, default=2)
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--truth", help='e.g. "release=4,ball_at_batter=14,stumps_hit=17,stumps_disturbed_visible=21"')
    ap.add_argument("--out", default="repeat1")
    args = ap.parse_args()

    if MODEL.startswith("PASTE"):
        sys.exit("Set MODEL at the top of the script.")
    idxs, sheets = build_sheets(args.video, args.start, args.end, args.step, 4, 12, 480,
                                os.path.join(args.out, "sheets"))
    print(f"{len(sheets)} sheets, frames {idxs[0]}..{idxs[-1]} step {args.step}")
    imgs = [Image.open(p) for p in sheets]
    client = genai.Client()
    truth = parse_kv(args.truth)

    runs = []
    for r in range(args.runs):
        for attempt in range(4):
            try:
                resp = client.models.generate_content(
                    model=MODEL, contents=[prompt(args.step)] + imgs,
                    config=types.GenerateContentConfig(response_mime_type="application/json"))
                data = json.loads(resp.text)
                break
            except Exception as e:
                print(f"   run {r + 1} attempt {attempt + 1} failed: {str(e)[:200]}")
                time.sleep(15 * (attempt + 1))
        else:
            print(f"   run {r + 1} gave up")
            continue
        m = data.get("moments", {})
        row = {k: (m.get(k) or {}).get("frame") if isinstance(m.get(k), dict) else m.get(k) for k in MOMENTS}
        row["camera_cuts"] = data.get("camera_cuts", [])
        runs.append({"frames": row, "raw": data})
        print(f"run {r + 1}: " + "  ".join(f"{k}={row[k]}" for k in MOMENTS) + f"  cuts={row['camera_cuts']}")
        time.sleep(5)

    if not runs:
        sys.exit("No successful runs.")

    print("\n=== stability ===")
    summary = {}
    for k in MOMENTS:
        vals = [r["frames"][k] for r in runs if isinstance(r["frames"][k], int)]
        s = {"values": vals, "nulls": len(runs) - len(vals)}
        if vals:
            s["median"] = float(np.median(vals))
            s["spread"] = max(vals) - min(vals)
            if k in truth:
                errs = [v - truth[k] for v in vals]
                s["errors"] = errs
                s["mean_abs_error"] = round(float(np.mean(np.abs(errs))), 2)
        summary[k] = s
        print(f"{k:26s} {s}")

    with open(os.path.join(args.out, "repeat.json"), "w") as fh:
        json.dump({"model": MODEL, "step": args.step, "summary": summary, "runs": runs}, fh, indent=2)
    print(f"\nSaved {args.out}/repeat.json")


if __name__ == "__main__":
    main()