"""Asks Jev where the action is at each key moment and fills each step's highlight for the renderer.
sports/<sport>/marks.py lists what to look for, best first, with an optional higher score to require. Jev always returns a box, so its presence score
decides whether to trust it. If nothing passes, or Jev fails, that step has no marker."""
import base64, json, os, uuid
from concurrent.futures import ThreadPoolExecutor
import cv2
import requests
import config
import sports
from pipeline import verify


def ask(frame, target):
    """Returns ({top, bottom, left, right} as fractions, presence score), or (None, 0.0) if Jev fails."""
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key:
        return None, 0.0
    asset = uuid.uuid4().hex[:8] + "-frame"
    body = {"model": "jev-1.14.0", "state": {"photo": asset},
            "assets": {asset: {"type": "image", "format": "jpg",
                               "data_base64": base64.b64encode(verify.to_jpg(frame)).decode()}},
            "questions": {"box": {"type": "box", "instructions": f"{target} in `photo`"},
                          "seen": {"type": "noul", "instructions": f"Is {target} clearly visible in `photo`?"}}}
    head = {"Authorization": f"Bearer {key}", "TypeSafe-Danger-Zone-Images": "true", "Content-Type": "application/json"}
    try:
        answers = requests.post(verify.JEV_URL, headers=head, json=body, timeout=config.CALL_TIMEOUT).json()["answers"]
        b = answers["box"]["box"]
        return {k: float(b[k]) for k in ("top", "bottom", "left", "right")}, float(answers["seen"]["noul"])
    except Exception as e:
        print(f"  Jev failed: {str(e)[:100]}")
        return None, 0.0


def usable(box, score, shape, needed=None):
    if box is None or score < (needed or config.MARK_MIN_SCORE):
        return False
    if not (0 <= box["left"] < box["right"] <= 1 and 0 <= box["top"] < box["bottom"] <= 1):
        return False
    area = (box["right"] - box["left"]) * (box["bottom"] - box["top"])
    return shape != "ring" or area <= config.RING_MAX_AREA   # a ring is for small things only


def choose(frame, options):
    """The first option Jev is sure of, and every try for the job folder."""
    tries = []
    for shape, target, *needed in options:
        box, score = ask(frame, target)
        tries.append({"shape": shape, "target": target, "score": score, "box": box})
        if usable(box, score, shape, *needed):
            return {"shape": shape, "target": target, "score": score, "box": box}, tries
    return None, tries


def read_frames(clip, wanted):
    cap = cv2.VideoCapture(clip)
    frames, index = {}, 0
    while len(frames) < len(wanted):
        ok, f = cap.read()
        if not ok:
            break
        if index in wanted:
            frames[index] = f
        index += 1
    cap.release()
    return frames


def mark(clip, plan, sport, job_dir):
    """Fills each step's highlight in place and saves every try in markers.json."""
    options = sports.marks(sport).MARKS
    steps = [s for s in plan["steps"] if options.get(s["moment"])]
    frames = read_frames(clip, {s["frame"] for s in steps})
    steps = [s for s in steps if s["frame"] in frames]
    if not steps:
        return plan
    with ThreadPoolExecutor(len(steps)) as pool:
        found = list(pool.map(lambda s: choose(frames[s["frame"]], options[s["moment"]]), steps))
    log = {}
    for step, (highlight, tries) in zip(steps, found):
        step["highlight"] = highlight
        log[step["moment"]] = tries
    with open(os.path.join(job_dir, "markers.json"), "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=1)
    return plan
