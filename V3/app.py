"""Local web page: upload an MP4, choose the inputs, get the explained video back.
Run: python app.py, then open http://127.0.0.1:5000"""
import json, os, re, threading, traceback, uuid
from flask import Flask, abort, jsonify, render_template, request, send_from_directory
import config
import sports
from sports.cricket.events import OVER_BALL_RE
from pipeline.run import STAGES, run_job

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1024 ** 3   # 1 GB
JOB_ID_RE = re.compile(r"^[0-9a-f]{12}$")
jobs = {}
SPORTS = ["cricket", "football"]
one_at_a_time = threading.Lock()   # jobs share the daily Gemini limit


def number(text):
    text = (text or "").strip()
    return float(text) if text else None


def read_form(form, files, job_dir):
    sport = form.get("sport", "cricket")
    if sport not in SPORTS:
        raise ValueError("unknown sport")
    catalog = sports.decisions(sport)
    p = {"sport": sport, "decision": form.get("decision", ""), "level": form.get("level", "beginner"),
         "date": form.get("date", "").strip(), "format": form.get("format", "").strip(),
         "notes": form.get("notes", "").strip(), "start": number(form.get("start")), "end": number(form.get("end"))}
    if p["level"] not in catalog.LEVELS:
        raise ValueError("unknown explanation level")
    match = files.get("statsbomb" if sport == "football" else "cricsheet")
    if match and match.filename and sport == "football":
        try:
            p["period"], p["minute"], p["second"] = (int(form.get(k) or 0) for k in ("period", "minute", "second"))
        except ValueError:
            raise ValueError("period, minute and second must be whole numbers")
        if not p["period"]:
            raise ValueError("with a StatsBomb file, enter the period")
        p["match_path"] = os.path.join(job_dir, "match.json")
        match.save(p["match_path"])
    elif match and match.filename:
        over_ball = form.get("over_ball", "").strip()
        if not OVER_BALL_RE.match(over_ball):
            raise ValueError("with a Cricsheet file, enter the over.ball, like 12.3")
        p["match_path"] = os.path.join(job_dir, "match.json")
        match.save(p["match_path"])
        p["innings"], p["over_ball"] = int(form.get("innings") or 1), over_ball
    elif p["decision"] not in catalog.DECISIONS:
        raise ValueError("choose a decision, or add a match data file")
    return p


def worker(job_id, job_dir, params):
    job = jobs[job_id]
    with one_at_a_time:
        try:
            run_job(job_dir, params, lambda stage: job.update(stage=stage, state="running"))
            job.update(state="done", stage=len(STAGES))
        except Exception as e:
            traceback.print_exc()
            job.update(state="failed", error=str(e))


@app.get("/")
def index():
    groups = {}
    for sport in SPORTS:
        catalog = sports.decisions(sport)
        groups[sport] = {}
        for key, d in catalog.DECISIONS.items():
            groups[sport].setdefault(catalog.GROUP_LABELS[d["group"]], []).append((key, d["label"]))
    return render_template("index.html", groups=groups, levels=["beginner", "standard", "expert"], stages=STAGES)


@app.post("/run")
def start():
    video = request.files.get("video")
    if not video or not video.filename.lower().endswith(".mp4"):
        return jsonify(error="upload an MP4 file"), 400
    job_id = uuid.uuid4().hex[:12]
    job_dir = os.path.join(config.JOBS_DIR, job_id)
    os.makedirs(job_dir)
    try:
        params = read_form(request.form, request.files, job_dir)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    video.save(os.path.join(job_dir, "input.mp4"))
    jobs[job_id] = {"state": "queued", "stage": 0, "error": ""}
    threading.Thread(target=worker, args=(job_id, job_dir, params), daemon=True).start()
    return jsonify(job=job_id)


@app.get("/status/<job_id>")
def status(job_id):
    if job_id not in jobs:
        abort(404)
    result = dict(jobs[job_id])
    if result["state"] == "done":
        path = os.path.join(config.JOBS_DIR, job_id, "plan.json")
        with open(path, encoding="utf-8") as f:
            result["plan"] = json.load(f)
    return jsonify(result)


@app.get("/video/<job_id>")
def video(job_id):
    if not JOB_ID_RE.match(job_id):
        abort(404)
    return send_from_directory(os.path.join(config.JOBS_DIR, job_id), "output.mp4", conditional=True)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, threaded=True)
