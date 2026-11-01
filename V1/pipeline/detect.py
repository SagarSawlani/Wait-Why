"""Finds the frame of each key moment: numbered contact sheets go to Gemini, and the replies are validated.
All frames are used, including those after a camera cut. Frame numbers are 0-based."""
import json, math, os, statistics
import cv2
import numpy as np
from PIL import Image
import config
from decisions import DECISIONS, DETECT_SYSTEM, detect_prompt
from pipeline import llm

FONT = cv2.FONT_HERSHEY_SIMPLEX


def load_frames(video, width):
    cap = cv2.VideoCapture(video)
    frames = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        h, w = f.shape[:2]
        frames.append(cv2.resize(f, (width, int(h * width / w)), interpolation=cv2.INTER_AREA))
    cap.release()
    if not frames:
        raise ValueError("could not read any frames from the clip")
    return frames


def choose_step(frame_count):
    return max(config.FRAME_STEP, math.ceil(frame_count / config.MAX_CELLS))


def build_sheets(frames, step, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    idxs = list(range(0, len(frames), step))
    per_sheet = config.SHEET_COLS * config.SHEET_ROWS
    paths = []
    for s in range(0, len(idxs), per_sheet):
        chunk = idxs[s:s + per_sheet]
        cells = []
        for k in chunk:
            c = frames[k].copy()
            (tw, th), _ = cv2.getTextSize(str(k), FONT, 1.6, 3)
            cv2.rectangle(c, (0, 0), (tw + 16, th + 16), (0, 0, 0), -1)
            cv2.putText(c, str(k), (8, th + 8), FONT, 1.6, (255, 255, 255), 3, cv2.LINE_AA)
            cv2.rectangle(c, (0, 0), (c.shape[1] - 1, c.shape[0] - 1), (255, 255, 0), 1)
            cells.append(c)
        while len(cells) % config.SHEET_COLS:
            cells.append(np.zeros_like(cells[0]))
        sheet = np.vstack([np.hstack(cells[r:r + config.SHEET_COLS])
                           for r in range(0, len(cells), config.SHEET_COLS)])
        p = os.path.join(out_dir, f"sheet_{chunk[0]:05d}_{chunk[-1]:05d}.jpg")
        cv2.imwrite(p, sheet, [cv2.IMWRITE_JPEG_QUALITY, 92])
        paths.append(p)
    return idxs, paths


def read_run(data, keys, idxs):
    """One reply as {key: {frame, confidence, evidence}}. A frame not printed on a cell is dropped."""
    allowed, run = set(idxs), {}
    moments = data.get("moments") or {}
    for key in keys:
        m = moments.get(key) or {}
        frame = m.get("frame")
        if isinstance(frame, int) and not isinstance(frame, bool) and frame in allowed:
            conf = m.get("confidence")
            run[key] = {"frame": frame, "confidence": float(conf) if isinstance(conf, (int, float)) else 0.0,
                        "evidence": str(m.get("evidence") or "")}
    return run


def combine(runs, keys):
    """Median frame per moment. median_low keeps it on a real cell."""
    merged = {}
    for key in keys:
        hits = [r[key] for r in runs if key in r]
        if hits:
            frame = statistics.median_low(h["frame"] for h in hits)
            closest = min(hits, key=lambda h: abs(h["frame"] - frame))
            merged[key] = {"frame": frame, "confidence": sum(h["confidence"] for h in hits) / len(hits),
                           "evidence": closest["evidence"], "runs": [h["frame"] for h in hits]}
    return merged


def validate(decision, merged, frame_count):
    """Applies confidence and time order, adds derived moments, and returns them in order.
    Anything rejected is kept in the second value, with the reason."""
    d = DECISIONS[decision]
    kept, rejected, last = [], [], -1
    for key, label, _ in d["moments"]:
        m = merged.get(key)
        if m is None:
            continue
        if m["confidence"] < config.MIN_CONFIDENCE:
            rejected.append({"key": key, "frame": m["frame"], "reason": "low confidence"})
        elif m["frame"] < last:
            rejected.append({"key": key, "frame": m["frame"], "reason": "out of time order"})
        else:
            kept.append({"key": key, "label": label, "derived": False, **m})
            last = m["frame"]
    for key, (source, offset) in d.get("derived", {}).items():
        base = next((m for m in kept if m["key"] == source), None)
        if base and 0 <= base["frame"] + offset < frame_count:
            kept.append({"key": key, "label": key.replace("_", " ").capitalize(), "derived": True,
                         "frame": base["frame"] + offset, "confidence": base["confidence"],
                         "evidence": f"Worked out from {source}."})
    return sorted(kept, key=lambda m: m["frame"]), rejected


def detect(clip, decision, event, job_dir, fps, runs=None):
    frames = load_frames(clip, config.CELL_WIDTH)
    step = choose_step(len(frames))
    idxs, sheets = build_sheets(frames, step, os.path.join(job_dir, "sheets"))
    keys = [k for k, _, _ in DECISIONS[decision]["moments"]]
    prompt = detect_prompt(decision, event, step)
    images = [Image.open(p) for p in sheets]
    replies, models = [], []
    for _ in range(runs or config.DETECT_RUNS):
        data, model = llm.generate(config.DETECT_CHAIN, DETECT_SYSTEM, [prompt] + images)
        replies.append(read_run(data, keys, idxs))
        models.append(model)
    # models are never mixed inside one median
    used = [r for r, m in zip(replies, models) if m == models[0]]
    moments, rejected = validate(decision, combine(used, keys), len(frames))
    for m in moments:
        m["timestamp"] = round(m["frame"] / fps, 3)
    result = {"decision": decision, "frames": len(frames), "fps": fps, "step": step, "model": models[0],
              "moments": moments, "rejected": rejected}
    with open(os.path.join(job_dir, "detections.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    return result
