import argparse, base64, json, os, sys, time, uuid
import cv2
import numpy as np
import requests
from dotenv import load_dotenv

load_dotenv()

JEV_URL = "https://api.typesafe.ai/v1/systemone"
JEV_MODELS = ["jev-1.14.0", "jev-preview"]
FONT = cv2.FONT_HERSHEY_SIMPLEX

QUESTIONS = {
    "release": "`sheet` is a grid of video frames from one cricket delivery, in time order, left to right, "
               "top to bottom. Each cell has its frame number printed in white on a black box at the top-left. "
               "In which frame has the ball first left the bowler's hand?",
    "ball_past_bat": "`sheet` is a grid of video frames from one cricket delivery, in time order, left to right, "
                     "top to bottom. Each cell has its frame number printed in white on a black box at the top-left. "
                     "In which frame does the ball first get past the batter's bat?",
    "stumps_hit": "`sheet` is a grid of video frames from one cricket delivery, in time order, left to right, "
                  "top to bottom. Each cell has its frame number printed in white on a black box at the top-left. "
                  "In which frame does the ball first hit the stumps at the batter's end?",
}


def build_sheet(video, start, end, step, cols, cell_w):
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
    if not idxs:
        sys.exit("No frames in that range.")
    cells = []
    for k in idxs:
        h, w = frames[k].shape[:2]
        c = cv2.resize(frames[k], (cell_w, int(h * cell_w / w)), interpolation=cv2.INTER_AREA)
        scale = cell_w / 480 * 1.4
        (tw, th), _ = cv2.getTextSize(str(k), FONT, scale, 3)
        cv2.rectangle(c, (0, 0), (tw + 16, th + 16), (0, 0, 0), -1)
        cv2.putText(c, str(k), (8, th + 8), FONT, scale, (255, 255, 255), 3, cv2.LINE_AA)
        cv2.rectangle(c, (0, 0), (c.shape[1] - 1, c.shape[0] - 1), (255, 255, 0), 1)
        cells.append(c)
    while len(cells) % cols:
        cells.append(np.zeros_like(cells[0]))
    sheet = np.vstack([np.hstack(cells[r:r + cols]) for r in range(0, len(cells), cols)])
    return sheet, idxs


def jev_call(jpg, questions, api_key):
    asset = uuid.uuid4().hex[:8] + "-sheet"
    headers = {"Authorization": f"Bearer {api_key}",
               "TypeSafe-Danger-Zone-Images": "true",
               "Content-Type": "application/json"}
    last = None
    for model in JEV_MODELS:
        body = {"model": model, "state": {"sheet": asset},
                "assets": {asset: {"type": "image", "format": "jpg",
                                   "data_base64": base64.b64encode(jpg).decode()}},
                "questions": questions}
        for attempt in range(4):
            r = requests.post(JEV_URL, headers=headers, json=body, timeout=180)
            if r.status_code == 200:
                return model, r.json()
            if r.status_code in (401, 403):
                sys.exit("Authentication failed: check TYPESAFE_API_KEY.")
            if r.status_code in (429, 500, 502, 503):
                time.sleep(2 ** attempt * 2)
                continue
            last = f"{model}: HTTP {r.status_code} {r.text[:400]}"
            break
        print("   Jev error ->", last)
    sys.exit(f"All Jev models failed. Last error: {last}")


def parse_kv(s):
    return {k.strip(): int(v) for k, v in (p.split("=") for p in s.split(","))} if s else {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--start", type=int, required=True)
    ap.add_argument("--end", type=int, required=True)
    ap.add_argument("--step", type=int, default=1)
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--cell_w", type=int, default=640)
    ap.add_argument("--truth", help='e.g. "release=4,ball_past_bat=14,stumps_hit=17"')
    ap.add_argument("--out", default="grid1")
    args = ap.parse_args()

    api_key = os.environ.get("TYPESAFE_API_KEY")
    if not api_key:
        sys.exit("Set TYPESAFE_API_KEY first.")
    os.makedirs(args.out, exist_ok=True)

    sheet, idxs = build_sheet(args.video, args.start, args.end, args.step, args.cols, args.cell_w)
    cv2.imwrite(os.path.join(args.out, "sheet.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 92])


    options = {f"frame {k}": f"the cell whose printed frame number is {k}" for k in idxs}
    options["none"] = "the moment is not visible in any cell"
    questions = {name: {"type": "choice", "instructions": text +
                        " Choose the frame number printed on that cell. Choose none if it is not visible in any cell.",
                        "criteria": options}
                 for name, text in QUESTIONS.items()}

    print(f"sheet {sheet.shape[1]}x{sheet.shape[0]}, frames {idxs}")
    model, resp = None, None
    for side in (2048, 1600, 1280, 1024):
        img = sheet
        s = side / max(sheet.shape[:2])
        if s < 1:
            img = cv2.resize(sheet, (int(sheet.shape[1] * s), int(sheet.shape[0] * s)),
                             interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92])
        try:
            model, resp = jev_call(buf.tobytes(), questions, api_key)
            cell = img.shape[1] // args.cols
            print(f"accepted at {img.shape[1]}x{img.shape[0]} (each cell about {cell}px wide)")
            break
        except SystemExit as e:
            if "dimensions" in str(e):
                print(f"   {img.shape[1]}x{img.shape[0]} rejected, trying smaller")
                continue
            raise
    if resp is None:
        sys.exit("Jev rejected every size tried.")
    json.dump(resp, open(os.path.join(args.out, "raw.json"), "w"), indent=2)
    truth = parse_kv(args.truth)

    results = {}
    for name in QUESTIONS:
        a = (resp.get("answers") or {}).get(name) or {}
        probs = a.get("probabilities") or {}
        top = sorted(probs.items(), key=lambda kv: -kv[1])[:3]
        choice = a.get("choice")
        frame = int(choice.split()[1]) if isinstance(choice, str) and choice.startswith("frame ") else None
        res = {"choice": choice, "frame": frame, "confidence": a.get("confidence"),
               "top3": [(k, round(v, 2)) for k, v in top]}
        if frame is not None and name in truth:
            res["error_vs_truth"] = frame - truth[name]
        results[name] = res
        print(f"{name:14s} {res}")

    json.dump({"model": model, "frames": idxs, "results": results},
              open(os.path.join(args.out, "grid_result.json"), "w"), indent=2)
    if not any(r["choice"] for r in results.values()):
        print("\nNo choices parsed. Paste grid1/raw.json to me.")
    print(f"\nSaved {args.out}/sheet.jpg, raw.json, grid_result.json")


if __name__ == "__main__":
    main()