import argparse, base64, glob, json, os, sys, uuid
import cv2
import numpy as np
import requests
from dotenv import load_dotenv

load_dotenv()

# ---------------- settings ----------------
GEMINI_MODEL = "gemini-3.8-flash"
JEV_MODELS = ["jev-1.14.0", "jev-preview"]       # tried in this order
JEV_URL = "https://api.typesafe.ai/v1/systemone"
SEND_MAX_SIDE = 1280                              # frames are downscaled to this before sending
# -------------------------------------------

# What to highlight at each moment: (short name, plain description of the target)
TARGETS = {
    "release": [
        ("bowling_arm", "the bowler's bowling arm and hand"),
        ("bowler", "the bowler"),
    ],
    "ball_at_batter": [
        ("batter", "the batter"),
        ("bat", "the cricket bat"),
        ("ball", "the small red cricket ball"),   # experimental: tiny, may fail
    ],
    "stumps_hit": [
        ("stumps", "the three wooden stumps at the far end of the pitch where the batter stands"),
    ],
    "stumps_disturbed_visible": [
        ("stumps", "the three wooden stumps at the far end of the pitch where the batter stands"),
        ("bail", "a wooden bail flying in the air above the stumps"),
    ],
}

COLORS = [(0, 255, 0), (0, 165, 255), (255, 0, 255), (255, 255, 0), (0, 0, 255)]


def ask_gemini_for_frames(sheets_dir, event_text):
    from google import genai
    from google.genai import types
    from PIL import Image

    paths = sorted(glob.glob(os.path.join(sheets_dir, "*.jpg")))
    if not paths:
        sys.exit(f"No sheets found in {sheets_dir}")
    imgs = [Image.open(p) for p in paths]
    prompt = f"""You are analysing one cricket delivery from a broadcast camera behind the bowler.
Context: {event_text}

The images are contact sheets in time order. Each cell is one video frame with its frame number
printed in white on a black box at the top-left of the cell. Always answer with a printed number.

Find these moments, each defined by what is visible. Use the labelled frame closest to the moment.
- release: the first frame in which the ball has left the bowler's hand.
- ball_at_batter: the first frame in which the ball is level with the batter's bat or pads.
- stumps_hit: the first frame in which the ball reaches or touches the stumps at the batter's end.
- stumps_disturbed_visible: the first frame in which the stumps are visibly disturbed or a bail is in the air.
If a moment is not visible in any frame, use null. Do not guess.

Return only JSON:
{{"moments": {{"release": {{"frame": 0, "evidence": ""}}, "ball_at_batter": {{"frame": 0, "evidence": ""}},
"stumps_hit": {{"frame": 0, "evidence": ""}}, "stumps_disturbed_visible": {{"frame": 0, "evidence": ""}}}}}}"""

    client = genai.Client()
    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[prompt] + imgs,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    data = json.loads(resp.text)["moments"]
    return {k: (v.get("frame") if isinstance(v, dict) else v) for k, v in data.items()}


def parse_manual(s):
    d = {}
    for part in s.split(","):
        k, v = part.split("=")
        d[k.strip()] = int(v)
    return d


def grab_frames(video, wanted):
    cap = cv2.VideoCapture(video)
    out, i = {}, 0
    last = max(wanted) if wanted else -1
    while i <= last:
        ok, f = cap.read()
        if not ok:
            break
        if i in wanted:
            out[i] = f
        i += 1
    cap.release()
    return out


def to_jpg(frame):
    h, w = frame.shape[:2]
    s = SEND_MAX_SIDE / max(h, w)
    if s < 1:
        frame = cv2.resize(frame, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return buf.tobytes()


def jev_call(jpg_bytes, questions, api_key):
    asset = uuid.uuid4().hex[:8] + "-frame"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "TypeSafe-Danger-Zone-Images": "true",
        "Content-Type": "application/json",
    }
    last = None
    for model in JEV_MODELS:
        body = {
            "model": model,
            "state": {"photo": asset},
            "assets": {asset: {"type": "image", "format": "jpg",
                               "data_base64": base64.b64encode(jpg_bytes).decode()}},
            "questions": questions,
        }
        r = requests.post(JEV_URL, headers=headers, json=body, timeout=180)
        if r.status_code == 200:
            return model, r.json()
        last = f"{model}: HTTP {r.status_code} {r.text[:500]}"
        print("   Jev error ->", last)
        if r.status_code in (401, 403):
            sys.exit("Authentication failed: check TYPESAFE_API_KEY.")
    return None, {"error": last}


def get_answer(resp, name):
    ans = resp.get("answers")
    if isinstance(ans, dict):
        return ans.get(name)
    if isinstance(ans, list):
        for a in ans:
            if isinstance(a, dict) and a.get("name") == name:
                return a
    return None


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
    return {"top": t, "bottom": bt, "left": l, "right": r, "confidence": a.get("confidence")}


def parse_presence(a):
    if not isinstance(a, dict):
        return None
    for k in ("verdict", "value", "answer", "decision", "result"):
        v = a.get(k)
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            s = v.strip().lower()
            if s in ("yes", "true", "y"):
                return True
            if s in ("no", "false", "n"):
                return False
    return None


def draw(frame, results, title):
    h, w = frame.shape[:2]
    img = frame.copy()
    for i, (name, res) in enumerate(results.items()):
        b = res["box"]
        if not b:
            continue
        x1, y1, x2, y2 = int(b["left"] * w), int(b["top"] * h), int(b["right"] * w), int(b["bottom"] * h)
        col = (160, 160, 160) if res["present"] is False else COLORS[i % len(COLORS)]
        cv2.rectangle(img, (x1, y1), (x2, y2), col, 3)
        tag = name + ("" if b.get("confidence") is None else f"  {b['confidence']}")
        if res["present"] is False:
            tag += "  (not visible?)"
        (tw, th), _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
        ty = max(y1, th + 12)
        cv2.rectangle(img, (x1, ty - th - 10), (x1 + tw + 8, ty), (0, 0, 0), -1)
        cv2.putText(img, tag, (x1 + 4, ty - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.8, col, 2, cv2.LINE_AA)
    cv2.rectangle(img, (0, 0), (min(w, 900), 54), (0, 0, 0), -1)
    cv2.putText(img, title, (12, 38), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2, cv2.LINE_AA)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", default="run1")
    ap.add_argument("--sheets", help="folder of numbered contact sheets (asks Gemini for the frames)")
    ap.add_argument("--frames", help='manual frames, e.g. "release=4,ball_at_batter=12,stumps_hit=17,stumps_disturbed_visible=21"')
    ap.add_argument("--event", default="Test cricket delivery.")
    ap.add_argument("--no_presence", action="store_true", help="skip the yes/no visibility questions")
    args = ap.parse_args()

    api_key = os.environ.get("TYPESAFE_API_KEY")
    if not api_key:
        sys.exit("Set TYPESAFE_API_KEY first.")
    for sub in ("frames", "raw", "annotated"):
        os.makedirs(os.path.join(args.out, sub), exist_ok=True)

    cap = cv2.VideoCapture(args.video)
    fps = cap.get(cv2.CAP_PROP_FPS)
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    if args.frames:
        moments = parse_manual(args.frames)
    elif args.sheets:
        print("Asking Gemini for key frames...")
        moments = ask_gemini_for_frames(args.sheets, args.event)
    else:
        sys.exit("Give --frames or --sheets.")
    print("Key frames:", moments)
    with open(os.path.join(args.out, "moments.json"), "w") as fh:
        json.dump(moments, fh, indent=2)

    wanted = {f for k, f in moments.items() if k in TARGETS and isinstance(f, int) and f >= 0}
    grabbed = grab_frames(args.video, wanted)

    plan = {"video": args.video, "fps": fps, "size": [W, H], "moments": []}
    annotated_imgs = []

    for mid, f in moments.items():
        if mid not in TARGETS:
            print(f"- {mid}: no targets defined, skipped")
            continue
        if not isinstance(f, int) or f not in grabbed:
            print(f"- {mid}: frame {f} not available, skipped")
            continue

        frame = grabbed[f]
        jpg = to_jpg(frame)
        cv2.imwrite(os.path.join(args.out, "frames", f"{mid}_{f:04d}.jpg"), frame)

        questions = {}
        for name, desc in TARGETS[mid]:
            questions[f"{name}_box"] = {"type": "box", "instructions": f"{desc} in `photo`"}
            if not args.no_presence:
                questions[f"{name}_present"] = {"type": "noul", "instructions": f"Is {desc} clearly visible in `photo`?"}

        print(f"- {mid} @ frame {f}: sending to Jev ({len(questions)} questions)...")
        model, resp = jev_call(jpg, questions, api_key)
        with open(os.path.join(args.out, "raw", f"{mid}_{f:04d}.json"), "w") as fh:
            json.dump(resp, fh, indent=2)

        results, plan_targets = {}, []
        for name, desc in TARGETS[mid]:
            box = parse_box(get_answer(resp, f"{name}_box"))
            present = None if args.no_presence else parse_presence(get_answer(resp, f"{name}_present"))
            results[name] = {"box": box, "present": present}
            plan_targets.append({"name": name, "description": desc, "present": present, "box": box})
            print(f"    {name}: box={'yes' if box else 'NONE'} present={present}")

        img = draw(frame, results, f"{mid}  frame {f}")
        cv2.imwrite(os.path.join(args.out, "annotated", f"{mid}_{f:04d}.jpg"), img)
        annotated_imgs.append(img)
        plan["moments"].append({"id": mid, "frame": f, "model": model, "targets": plan_targets})

    with open(os.path.join(args.out, "plan_boxes.json"), "w") as fh:
        json.dump(plan, fh, indent=2)

    if annotated_imgs:
        small = [cv2.resize(a, (640, int(640 * a.shape[0] / a.shape[1]))) for a in annotated_imgs]
        if len(small) % 2:
            small.append(np.zeros_like(small[0]))
        rows = [np.hstack(small[i:i + 2]) for i in range(0, len(small), 2)]
        cv2.imwrite(os.path.join(args.out, "annotated_sheet.jpg"), np.vstack(rows))
    print(f"\nDone. Look at {args.out}/annotated_sheet.jpg and {args.out}/plan_boxes.json")


if __name__ == "__main__":
    main()