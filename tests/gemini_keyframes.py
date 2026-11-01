"""
Gemini key-frame extraction for cricket delivery clips.

For every video:
  1. Extract all frames to <out>/<clip>/frames/00000.jpg ... (0-based frame numbers).
  2. Detect hard camera cuts and report them. All frames are kept unless --segment says otherwise.
  3. Build contact sheets from every Nth frame (default every 2nd), frame number printed on each cell.
  4. Send the sheets to Gemini with a system prompt, several runs, and take the median answer per moment.
  5. Save the results, plus a strip of the chosen key frames so you can check them by eye.

Usage:
  python gemini_keyframes.py --videos "C:\\dream11_project\\videos" --out runs
  python gemini_keyframes.py --videos clip1.mp4 clip2.mp4 --manifest manifest.json --runs 3

Optional manifest.json (per-clip hints and truth frames, all fields optional):
  {
    "clip.mp4": {"event": "Bowled", "truth": {"stumps_hit": 17, "stumps_disturbed_visible": 21}},
    "wide1.mp4": {"event": "Wide"}
  }
"""
import argparse, csv, glob, json, os, sys, time
import cv2
import numpy as np
from PIL import Image
from google import genai
from google.genai import types
from dotenv import load_dotenv
load_dotenv()

MODEL = "PASTE-YOUR-GEMINI-MODEL"
FONT = cv2.FONT_HERSHEY_SIMPLEX
VIDEO_EXT = (".mp4", ".mov", ".mkv", ".avi", ".webm")

MOMENTS = ["release", "ball_at_batter", "bat_contact_or_miss",
           "stumps_hit", "stumps_disturbed_visible", "umpire_signal"]

SYSTEM_PROMPT = """You are a cricket video analyst. You receive contact sheets made from one broadcast clip
of a single delivery. Your job is to find the frame numbers of key moments, for a replay that explains
the umpire's decision to fans.

How to read the input:
- The sheets are in time order. Inside a sheet, cells go left to right, then top to bottom.
- Each cell is one video frame. Its frame number is printed in white on a black box at the top-left.
- Cells are a fixed number of frames apart (stated in the request). Frames between cells are not shown.
- Always answer with a frame number that is printed on a cell. Never invent or interpolate numbers.

Rules:
- Judge each moment by what is visible, not by what usually happens.
- If a moment does not happen, or is not visible in any cell, set its frame to null. Do not guess.
- Use the cell closest to the moment. If the moment falls between two cells, pick the earlier one
  unless the later one is clearly closer.
- Moments must be in time order where they exist: release, ball_at_batter, bat_contact_or_miss,
  stumps_hit, stumps_disturbed_visible, umpire_signal.
- The clip may cut to other camera angles. Later live shots still count, for example the umpire signalling.
- Ignore replays, graphics and crowd shots. Moments of the delivery itself must come from its live footage.
- evidence is one short literal sentence about what you see in that cell.
- confidence is a number from 0 to 1.

Always return only JSON in the requested shape."""

MOMENT_DEFS = """Moments to find:
- release: the first frame in which the ball has left the bowler's hand.
- ball_at_batter: the first frame in which the ball is level with the batter's bat or pads.
- bat_contact_or_miss: the frame in which the ball passes the bat. Also say what happened:
  "missed", "edged", "hit", "hit_pad" or "unclear".
- stumps_hit: the first frame in which the ball reaches or touches the stumps at the batter's end.
- stumps_disturbed_visible: the first frame in which the stumps are visibly disturbed or a bail is in the air.
- umpire_signal: the first frame in which the umpire is clearly signalling a decision.
Also list camera_cuts (frames where the picture changes abruptly) and give decision_guess
(for example "bowled", "wide", "caught", "lbw", "no decision visible")."""

SHAPE = """Return only JSON:
{"moments": {
  "release": {"frame": 0, "confidence": 0.0, "evidence": ""},
  "ball_at_batter": {"frame": 0, "confidence": 0.0, "evidence": ""},
  "bat_contact_or_miss": {"frame": 0, "outcome": "missed", "confidence": 0.0, "evidence": ""},
  "stumps_hit": {"frame": 0, "confidence": 0.0, "evidence": ""},
  "stumps_disturbed_visible": {"frame": 0, "confidence": 0.0, "evidence": ""},
  "umpire_signal": {"frame": 0, "confidence": 0.0, "evidence": ""}
 },
 "camera_cuts": [],
 "decision_guess": ""}"""


# ---------------- video ----------------
def extract_frames(video, frames_dir):
    os.makedirs(frames_dir, exist_ok=True)
    for f in glob.glob(os.path.join(frames_dir, "*.jpg")):
        os.remove(f)
    cap = cv2.VideoCapture(video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    frames, i = [], 0
    while True:
        ok, f = cap.read()
        if not ok:
            break
        cv2.imwrite(os.path.join(frames_dir, f"{i:05d}.jpg"), f, [cv2.IMWRITE_JPEG_QUALITY, 95])
        frames.append(f)
        i += 1
    cap.release()
    return frames, fps


def detect_cuts(frames, thr):
    """Hard cuts via colour-histogram correlation between consecutive frames."""
    hists = []
    for f in frames:
        hsv = cv2.cvtColor(cv2.resize(f, (320, 180)), cv2.COLOR_BGR2HSV)
        h = cv2.calcHist([hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
        cv2.normalize(h, h)
        hists.append(h)
    cuts = []
    for i in range(1, len(frames)):
        if cv2.compareHist(hists[i - 1], hists[i], cv2.HISTCMP_CORREL) < thr:
            cuts.append(i)
    return cuts


def choose_segment(n, cuts, mode):
    """Returns (start, end) inclusive. 'first' keeps the segment before the first cut,
    'longest' keeps the longest segment, 'none' keeps everything."""
    if mode == "none" or not cuts:
        return 0, n - 1
    bounds = [0] + cuts + [n]
    segs = [(bounds[i], bounds[i + 1] - 1) for i in range(len(bounds) - 1)]
    if mode == "first":
        return segs[0]
    return max(segs, key=lambda s: s[1] - s[0])


def build_sheets(frames, start, end, step, cols, per_sheet, cell_w, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    for f in glob.glob(os.path.join(out_dir, "*.jpg")):
        os.remove(f)
    idxs = list(range(start, end + 1, step))
    paths = []
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
        p = os.path.join(out_dir, f"sheet_{chunk[0]:05d}_{chunk[-1]:05d}.jpg")
        cv2.imwrite(p, sheet, [cv2.IMWRITE_JPEG_QUALITY, 92])
        paths.append(p)
    return idxs, paths


# ---------------- gemini ----------------
def ask_gemini(client, model, sheet_paths, step, event_hint):
    imgs = [Image.open(p) for p in sheet_paths]
    hint = f"Context from match data: {event_hint}\n" if event_hint else ""
    user = f"{hint}Cells are {step} frame(s) apart.\n\n{MOMENT_DEFS}\n\n{SHAPE}"
    try:
        resp = client.models.generate_content(
            model=model,
            contents=[user] + imgs,
            config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT,
                                               response_mime_type="application/json"),
        )
    except Exception as e:
        msg = str(e).lower()
        if not any(w in msg for w in ("system", "instruction", "json", "mime",
                                      "invalid_argument", "invalid argument")):
            raise
        # some models (e.g. Gemma) reject a separate system prompt or JSON mode:
        # put the system prompt at the top of the message and parse the JSON from plain text
        print(f"  retrying with plain-text prompt: {str(e)[:120]}")
        resp = client.models.generate_content(
            model=model,
            contents=[SYSTEM_PROMPT + "\n\n" + user] + imgs,
        )
    return parse_json(resp.text)


def parse_json(text):
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON in reply: {text[:200]}")
    return json.loads(text[start:end + 1])


def frame_of(m, key):
    v = (m or {}).get(key)
    if isinstance(v, dict):
        v = v.get("frame")
    return v if isinstance(v, int) else None


def order_ok(row):
    vals = [row[k] for k in MOMENTS if row.get(k) is not None]
    return vals == sorted(vals)


def combine(runs, valid_idxs):
    out = {}
    for k in MOMENTS:
        vals = [r[k] for r in runs if r.get(k) is not None]
        if not vals or len(vals) < len(runs) / 2:     # most runs said null -> null
            out[k] = {"frame": None, "values": vals, "spread": None}
            continue
        med = float(np.median(vals))
        frame = min(valid_idxs, key=lambda x: abs(x - med))   # snap to a frame that was shown
        out[k] = {"frame": frame, "values": vals, "spread": max(vals) - min(vals)}
    return out


def keyframe_strip(frames, combined, path, cell_w=480):
    cells = []
    for k in MOMENTS:
        f = combined[k]["frame"]
        if f is None:
            continue
        h, w = frames[f].shape[:2]
        c = cv2.resize(frames[f], (cell_w, int(h * cell_w / w)))
        label = f"{k} @ {f}"
        cv2.rectangle(c, (0, 0), (cell_w, 34), (0, 0, 0), -1)
        cv2.putText(c, label, (8, 24), FONT, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
        cells.append(c)
    if not cells:
        return
    cols = 4
    while len(cells) % cols:
        cells.append(np.zeros_like(cells[0]))
    cv2.imwrite(path, np.vstack([np.hstack(cells[i:i + cols]) for i in range(0, len(cells), cols)]))


# ---------------- main ----------------
def collect_videos(items):
    vids = []
    for it in items:
        if os.path.isdir(it):
            vids += sorted(p for p in glob.glob(os.path.join(it, "*")) if p.lower().endswith(VIDEO_EXT))
        elif os.path.isfile(it):
            vids.append(it)
        else:
            print(f"skipping {it}: not found")
    return vids


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--videos", nargs="+", required=True, help="video files and/or folders")
    ap.add_argument("--out", default="runs")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--step", type=int, default=2, help="use every Nth frame in the sheets")
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--per_sheet", type=int, default=12)
    ap.add_argument("--cell_w", type=int, default=480)
    ap.add_argument("--runs", type=int, default=1, help="Gemini runs per clip; the median is used")
    ap.add_argument("--segment", choices=["first", "longest", "none"], default="none",
                    help="part of the clip to send if hard cuts are found; none sends every frame")
    ap.add_argument("--cut_thr", type=float, default=0.6, help="lower = fewer cuts detected")
    ap.add_argument("--manifest", help="JSON with per-clip event hints and truth frames")
    args = ap.parse_args()

    if args.model.startswith("PASTE"):
        sys.exit("Set MODEL at the top of the script, or pass --model.")
    videos = collect_videos(args.videos)
    if not videos:
        sys.exit("No videos found.")
    manifest = json.load(open(args.manifest)) if args.manifest else {}
    client = genai.Client()
    os.makedirs(args.out, exist_ok=True)
    summary_rows = []

    for video in videos:
        name = os.path.splitext(os.path.basename(video))[0]
        info = manifest.get(os.path.basename(video), {})
        cdir = os.path.join(args.out, name)
        print(f"\n===== {name} =====")

        frames, fps = extract_frames(video, os.path.join(cdir, "frames"))
        if not frames:
            print("  could not read frames, skipping")
            continue
        cuts = detect_cuts(frames, args.cut_thr)
        start, end = choose_segment(len(frames), cuts, args.segment)
        print(f"  {len(frames)} frames @ {fps:.2f} fps, hard cuts at {cuts or 'none'}, using frames {start}..{end}")

        idxs, sheets = build_sheets(frames, start, end, args.step, args.cols, args.per_sheet,
                                    args.cell_w, os.path.join(cdir, "sheets"))
        print(f"  {len(sheets)} sheet(s), {len(idxs)} cells")

        runs, raw = [], []
        for r in range(args.runs):
            data = None
            for attempt in range(4):
                try:
                    data = ask_gemini(client, args.model, sheets, args.step, info.get("event"))
                    break
                except Exception as e:
                    print(f"  run {r + 1} attempt {attempt + 1} failed: {str(e)[:200]}")
                    time.sleep(15 * (attempt + 1))
            if data is None:
                continue
            m = data.get("moments", {})
            row = {k: frame_of(m, k) for k in MOMENTS}
            row = {k: (v if v in idxs else None) for k, v in row.items()}   # drop numbers not on a cell
            row["outcome"] = (m.get("bat_contact_or_miss") or {}).get("outcome")
            row["decision_guess"] = data.get("decision_guess")
            row["camera_cuts"] = data.get("camera_cuts", [])
            row["order_ok"] = order_ok(row)
            runs.append(row)
            raw.append(data)
            print(f"  run {r + 1}: " + "  ".join(f"{k}={row[k]}" for k in MOMENTS)
                  + f"  outcome={row['outcome']}  decision={row['decision_guess']}  order_ok={row['order_ok']}")
            time.sleep(4)

        good = [r for r in runs if r["order_ok"]] or runs
        if not good:
            print("  no successful runs")
            continue
        combined = combine(good, idxs)
        truth = info.get("truth", {})
        for k, v in combined.items():
            if v["frame"] is not None and k in truth:
                v["error_vs_truth"] = v["frame"] - truth[k]

        result = {"video": video, "fps": fps, "frames": len(frames), "hard_cuts": cuts,
                  "segment": [start, end], "step": args.step, "model": args.model,
                  "event_hint": info.get("event"), "moments": combined,
                  "decision_guess": [r["decision_guess"] for r in runs],
                  "outcome": [r["outcome"] for r in runs],
                  "runs_used": len(good), "runs_total": len(runs)}
        with open(os.path.join(cdir, "result.json"), "w") as fh:
            json.dump(result, fh, indent=2)
        with open(os.path.join(cdir, "gemini_raw.json"), "w") as fh:
            json.dump(raw, fh, indent=2)
        keyframe_strip(frames, combined, os.path.join(cdir, "keyframes.jpg"))

        print("  --- combined ---")
        for k, v in combined.items():
            print(f"  {k:26s} frame={v['frame']}  spread={v['spread']}  values={v['values']}"
                  + (f"  error={v['error_vs_truth']}" if "error_vs_truth" in v else ""))

        row = {"clip": name}
        for k, v in combined.items():
            row[k] = v["frame"]
            row[f"{k}_spread"] = v["spread"]
            if "error_vs_truth" in v:
                row[f"{k}_error"] = v["error_vs_truth"]
        summary_rows.append(row)

    if summary_rows:
        keys = sorted({k for r in summary_rows for k in r}, key=lambda k: (k != "clip", k))
        with open(os.path.join(args.out, "summary.csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=keys)
            w.writeheader()
            w.writerows(summary_rows)
        print(f"\nSaved per-clip folders in {args.out}/ and {args.out}/summary.csv")


if __name__ == "__main__":
    main()