"""Finds the frame of each key moment: numbered contact sheets go to Gemini, and the replies are validated.
All frames are used, including those after a camera cut. Frame numbers are 0-based."""
import json, math, os, statistics
import cv2
import numpy as np
import config
import sports
from pipeline import llm
from pipeline.frames import Clip, frames_at

FONT = cv2.FONT_HERSHEY_SIMPLEX


def choose_step(frame_count):
    return max(config.FRAME_STEP, math.ceil(frame_count / config.MAX_CELLS))


def build_sheets(frames, step, out_dir, first=0, last=None):
    """frames is a frames.Clip (read as needed) or a list. Each sheet is drawn in place and written before the
    next is started, so only one sheet and one frame are in memory at a time."""
    os.makedirs(out_dir, exist_ok=True)
    idxs = list(range(first, len(frames) if last is None else last + 1, step))
    per_sheet = config.SHEET_COLS * config.SHEET_ROWS
    paths, chunk, sheet = [], [], None

    def write():
        p = os.path.join(out_dir, f"sheet_{chunk[0]:05d}_{chunk[-1]:05d}.jpg")
        rows = -(-len(chunk) // config.SHEET_COLS)
        cv2.imwrite(p, sheet[:rows * cell_h], [cv2.IMWRITE_JPEG_QUALITY, 92])
        paths.append(p)

    for k, frame in frames_at(frames, idxs):
        c = frame.copy()
        (tw, th), _ = cv2.getTextSize(str(k), FONT, 1.6, 3)
        cv2.rectangle(c, (0, 0), (tw + 16, th + 16), (0, 0, 0), -1)
        cv2.putText(c, str(k), (8, th + 8), FONT, 1.6, (255, 255, 255), 3, cv2.LINE_AA)
        cv2.rectangle(c, (0, 0), (c.shape[1] - 1, c.shape[0] - 1), (255, 255, 0), 1)
        if sheet is None:
            cell_h, cell_w = c.shape[:2]
            sheet = np.zeros((config.SHEET_ROWS * cell_h, config.SHEET_COLS * cell_w, 3), np.uint8)
        if not chunk:
            sheet[:] = 0   # empty cells on the last sheet stay black, as before
        row, col = divmod(len(chunk), config.SHEET_COLS)
        sheet[row * cell_h:(row + 1) * cell_h, col * cell_w:(col + 1) * cell_w] = c
        chunk.append(k)
        if len(chunk) == per_sheet:
            write()
            chunk = []
    if chunk:
        write()
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


def validate(decision, merged, frame_count, sport="cricket"):
    """Applies confidence and time order, adds derived moments, and returns them in order.
    Anything rejected is kept in the second value, with the reason."""
    d = sports.decisions(sport).DECISIONS[decision]
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


def ask(frames, step, sheet_dir, decision, event, runs=None, first=0, last=None):
    """One pass over frames first to last. Returns the validated moments, the rejected ones and the model."""
    idxs, sheets = build_sheets(frames, step, sheet_dir, first, last)
    sport = event["sport"]
    prompts = sports.decisions(sport)
    keys = [k for k, _, _ in prompts.DECISIONS[decision]["moments"]]
    prompt = prompts.detect_prompt(decision, event, step)
    images = [llm.image(p) for p in sheets]   # the JPEG bytes as they are; no decoded copy in memory
    replies, models = [], []
    for _ in range(runs or config.DETECT_RUNS):
        data, model = llm.generate(config.DETECT_CHAIN, prompts.DETECT_SYSTEM, [prompt] + images)
        replies.append(read_run(data, keys, idxs))
        models.append(model)
    # models are never mixed inside one median
    used = [r for r, m in zip(replies, models) if m == models[0]]
    moments, rejected = validate(decision, combine(used, keys), len(frames), sport)
    return moments, rejected, models[0], step


def refine_window(moments, step, frame_count):
    """The stretch a second, finer pass should read, or None if the first pass was already fine."""
    if step <= config.FRAME_STEP or not moments:
        return None
    first = max(min(m["frame"] for m in moments) - config.REFINE_MARGIN * step, 0)
    last = min(max(m["frame"] for m in moments) + config.REFINE_MARGIN * step, frame_count - 1)
    return first, last


def detect(clip, decision, event, job_dir, fps, runs=None):
    frames = Clip(clip, config.CELL_WIDTH)
    step = choose_step(len(frames))
    sheet_dir = os.path.join(job_dir, "sheets")
    moments, rejected, model, step = ask(frames, step, sheet_dir, decision, event, runs)
    window = refine_window(moments, step, len(frames))
    if window:
        fine = max(config.FRAME_STEP, math.ceil((window[1] - window[0] + 1) / config.MAX_CELLS))
        if fine < step:
            try:
                better, dropped, model2, step2 = ask(frames, fine, os.path.join(job_dir, "sheets_fine"), decision, event, runs, *window)
                if len(better) >= len(moments):   # a fine pass that loses moments is a worse answer
                    moments, rejected, model, step = better, dropped, model2, step2
            except RuntimeError as e:
                print(f"  keeping the first pass: {str(e)[:160]}")
    models = [model]
    for m in moments:
        m["timestamp"] = round(m["frame"] / fps, 3)
    result = {"decision": decision, "frames": len(frames), "fps": fps, "step": step, "model": models[0],
              "moments": moments, "rejected": rejected}
    with open(os.path.join(job_dir, "detections.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    return result
