"""Second layer: checks each detected moment on zoomed crops, then keeps, moves or removes it.
Each moment gets its chosen frame +-RADIUS, a Jev box per frame, and one enlarged image. All the images
go to Gemini in one call. If Jev fails a frame uses the full picture; if Gemini fails nothing changes."""
import base64, json, os, uuid
from concurrent.futures import ThreadPoolExecutor
import cv2
import numpy as np
import requests
import config
import sports
from pipeline import llm
from pipeline.frames import Clip

RADIUS = 3
CELL_W = 640
COLS = 3
JEV_URL = "https://api.typesafe.ai/v1/systemone"

SYSTEM = """You check key moments in a sports broadcast clip. You get one image per moment. Each image is a
grid of enlarged crops of consecutive video frames, in time order, left to right then top to bottom.
Each crop has its frame number printed at the top-left. For each moment choose the frame number that best
matches the definition. If no crop clearly shows it, answer null. The first guess may be wrong and the
moment may not be visible at all, so never pick a frame just because it is in the image.
Return only JSON."""


def target_for(sport, key):
    """What Jev should box for a moment. None means no box: small objects like the ball are not boxable."""
    targets = getattr(sports.decisions(sport), "BOX_TARGETS", None)
    if targets is not None:
        return targets.get(key)
    if "umpire" in key or "referee" in key:
        return "the umpire" if sport == "cricket" else "the referee"
    if sport == "cricket":
        if key == "release":
            return "the bowler"
        if "stumps" in key or "bails" in key or "wicket" in key:
            return "the three stumps at the batter's end"
        if key in ("bat_contact", "ball_hits_pad", "ball_past_bat", "ball_past_batter"):
            return "the batter"
        return None
    if "line" in key or "goal" in key:
        return "the goal"
    if "flag" in key or "assistant" in key:
        return "the assistant referee on the touchline"
    if any(w in key for w in ("kick", "shot", "strike", "pass", "foul", "tackle", "handball", "contact", "save")):
        return "the player closest to the ball"
    return None


def open_clip(path):
    """The clip at full size, read as needed: only the frames around each moment are decoded and kept."""
    return Clip(path)


def to_jpg(frame):
    h, w = frame.shape[:2]
    s = min(1, 1280 / max(h, w))
    small = cv2.resize(frame, (int(w * s), int(h * s)))
    return cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes()


def jev_box(frame, target):
    """Returns (top, bottom, left, right) as fractions, or None."""
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key:
        return None
    asset = uuid.uuid4().hex[:8] + "-frame"
    body = {"model": "jev-1.14.0", "state": {"photo": asset},
            "assets": {asset: {"type": "image", "format": "jpg",
                               "data_base64": base64.b64encode(to_jpg(frame)).decode()}},
            "questions": {"b": {"type": "box", "instructions": f"{target} in `photo`"}}}
    head = {"Authorization": f"Bearer {key}", "TypeSafe-Danger-Zone-Images": "true",
            "Content-Type": "application/json"}
    try:
        r = requests.post(JEV_URL, headers=head, json=body, timeout=config.CALL_TIMEOUT)
        a = r.json()["answers"]["b"]["box"]
        return float(a["top"]), float(a["bottom"]), float(a["left"]), float(a["right"])
    except Exception as e:
        print(f"  Jev failed: {str(e)[:100]}")
        return None


def crop(frame, box):
    """A 16:9 crop around the box, padded so the action around the target stays in view."""
    if box is None:
        return frame
    H, W = frame.shape[:2]
    top, bottom, left, right = box
    cx, cy = (left + right) / 2 * W, (top + bottom) / 2 * H
    h = min(max((bottom - top) * H * 1.8, (right - left) * W * 1.8 * 9 / 16, H * 0.25), H)
    w = min(h * 16 / 9, W)
    x = int(min(max(cx - w / 2, 0), W - w))
    y = int(min(max(cy - h / 2, 0), H - h))
    return frame[y:y + int(h), x:x + int(w)]


def window(centre, count):
    """The frame numbers checked around one moment."""
    return [i for i in range(centre - RADIUS, centre + RADIUS + 1) if 0 <= i < count]


def action_image(frames, idx, target, path):
    """Writes the grid for one moment from frames ({index: frame}) and returns the frame numbers in it."""
    idx = [i for i in idx if i in frames]
    if target:
        with ThreadPoolExecutor(len(idx)) as pool:
            boxes = list(pool.map(lambda i: jev_box(frames[i], target), idx))
    else:
        boxes = [None] * len(idx)
    cells = []
    for i, box in zip(idx, boxes):
        c = cv2.resize(crop(frames[i], box), (CELL_W, CELL_W * 9 // 16), interpolation=cv2.INTER_CUBIC)
        cv2.rectangle(c, (0, 0), (120, 56), (0, 0, 0), -1)
        cv2.putText(c, str(i), (8, 44), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255, 255, 255), 3, cv2.LINE_AA)
        cells.append(c)
    while len(cells) % COLS:
        cells.append(np.zeros_like(cells[0]))
    grid = np.vstack([np.hstack(cells[r:r + COLS]) for r in range(0, len(cells), COLS)])
    cv2.imwrite(path, grid, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return idx


def apply_answers(moments, answers, windows, derived, fps):
    """Returns (kept moments in time order, removed). Frames outside a moment's window are ignored,
    and a frame that would break the time order keeps its first answer."""
    kept, removed, changes, last = [], [], [], -1
    for m in moments:
        if m.get("derived"):
            continue
        if m["key"] not in windows:
            kept.append(m)
            last = max(last, m["frame"])
            continue
        reply = answers.get(m["key"]) if isinstance(answers.get(m["key"]), dict) else None
        if reply is None:
            kept.append(m)
            last = max(last, m["frame"])
            continue
        frame = reply.get("frame")
        if frame is None:
            removed.append({"key": m["key"], "frame": m["frame"], "reason": "not confirmed on zoomed crops"})
            continue
        if isinstance(frame, int) and frame in windows[m["key"]] and frame >= last and frame != m["frame"]:
            changes.append({"key": m["key"], "from": m["frame"], "to": frame})
            m = {**m, "frame": frame, "timestamp": round(frame / fps, 3)}
        if reply.get("evidence"):
            m = {**m, "evidence": str(reply["evidence"])}
        kept.append(m)
        last = max(last, m["frame"])
    for key, (source, offset) in derived.items():
        base = next((m for m in kept if m["key"] == source), None)
        old = next((m for m in moments if m["key"] == key), None)
        if base and old:
            frame = base["frame"] + offset
            kept.append({**old, "frame": frame, "timestamp": round(frame / fps, 3)})
    return sorted(kept, key=lambda m: m["frame"]), removed, changes


def verify(clip, decision, event, detections, job_dir, fps):
    """Returns the detections with moments confirmed, moved or removed, and saves the details."""
    sport = event["sport"]
    d = sports.decisions(sport).DECISIONS[decision]
    definitions = {key: definition for key, _, definition in d["moments"]}
    moments = detections["moments"]
    check_dir = os.path.join(job_dir, "check")
    os.makedirs(check_dir, exist_ok=True)
    checked = [m for m in moments if not m.get("derived") and m["key"] in definitions]
    if not checked:
        return detections
    video = open_clip(clip)
    count = len(video)
    paths, lines, windows = [], [], {}
    for m in checked:
        frames = video.read(window(m["frame"], count))   # one moment's few frames at a time
        if not frames:
            continue
        path = os.path.join(check_dir, f"{m['key']}.jpg")
        idx = action_image(frames, window(m["frame"], count), target_for(sport, m["key"]), path)
        windows[m["key"]] = idx
        paths.append(path)
        lines.append(f"- image {len(paths)}, {m['key']}: {definitions[m['key']]}. Frames {idx[0]} to {idx[-1]}.")
    if not paths:
        return detections
    shape = ", ".join(f'"{k}": {{"frame": 0, "confidence": 0.0, "evidence": ""}}' for k in windows)
    prompt = "Moments:\n" + "\n".join(lines) + f'\n\nReturn only JSON: {{"moments": {{{shape}}}}}'
    try:
        data, model = llm.generate(config.CHECK_CHAIN, SYSTEM, [prompt] + [llm.image(p) for p in paths])
    except RuntimeError as e:
        print(f"  keeping the first answers: {str(e)[:200]}")
        return detections
    kept, removed, changes = apply_answers(moments, data.get("moments") or {}, windows, d.get("derived", {}), fps)
    result = {**detections, "moments": kept, "rejected": detections["rejected"] + removed,
              "check_model": model, "changes": changes}
    with open(os.path.join(job_dir, "detections.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    return result
