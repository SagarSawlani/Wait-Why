"""Web page: upload an MP4, choose the inputs, get the explained video back.
Run locally: python app.py, then open http://127.0.0.1:5001
Online (PUBLIC=1) every page needs APP_PASSWORD, and jobs are capped per day and per visitor."""
import datetime, hmac, json, os, re, secrets, shutil, subprocess, threading, time, traceback, uuid
from flask import (Flask, abort, jsonify, redirect, render_template, request, send_from_directory, session,
                   url_for)
from werkzeug.middleware.proxy_fix import ProxyFix
import config
import sports
from sports.cricket.events import OVER_BALL_RE
from pipeline import normalize
from pipeline.run import STAGES, run_job

if config.PUBLIC and len(config.APP_PASSWORD) < 12:
    raise SystemExit("PUBLIC=1 needs APP_PASSWORD with at least 12 characters")

app = Flask(__name__)
app.secret_key = config.SECRET_KEY or secrets.token_hex(32)
app.config.update(MAX_CONTENT_LENGTH=(config.MAX_UPLOAD_MB + 10) * 1024 ** 2,   # room for the match JSON
                  SESSION_COOKIE_HTTPONLY=True, PERMANENT_SESSION_LIFETIME=datetime.timedelta(hours=12))
if config.PUBLIC:
    # Hugging Face shows the app inside an iframe on its own site, so the cookie must work cross-site.
    # Posts still need the page's CSRF token.
    app.config.update(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_SAMESITE="None", SESSION_COOKIE_PARTITIONED=True)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
JOB_ID_RE = re.compile(r"^[0-9a-f]{12}$")
jobs = {}
SPORTS = ["cricket", "football", "basketball", "tennis"]
one_at_a_time = threading.Lock()   # jobs share the daily Gemini limit
fetching = threading.Lock()        # the preview and a run can ask for the same clip
counting = threading.Lock()        # guards jobs, usage and failed_logins
usage = {"day": None, "total": 0, "visitors": {}}
failed_logins = {}
with open(config.LIBRARY_PATH, encoding="utf-8") as f:
    LIBRARY = json.load(f)

CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src https://fonts.gstatic.com; img-src 'self' data:; media-src 'self' blob:; "
       "frame-src https://www.youtube-nocookie.com; connect-src 'self'; form-action 'self'; base-uri 'none'; "
       "object-src 'none'; frame-ancestors 'self' https://huggingface.co")


def number(text):
    text = (text or "").strip()
    return float(text) if text else None


def library_file(clip):
    return clip.get("file") or f"library/{clip['youtube']}_{clip['start']}_{clip['end']}.mp4"


def library_rows():
    rows = []
    for number, clip in enumerate(LIBRARY, 1):
        label = sports.decisions(clip["sport"]).DECISIONS[clip["decision"]]["label"]
        rows.append(dict(clip, number=number, label=label))
    return rows


def library_clip(number):
    """The library clip for a 1-based Sr. No. from the page, or None."""
    number = str(number)
    if not number.isdigit() or not 1 <= int(number) <= len(LIBRARY):
        return None
    return LIBRARY[int(number) - 1]


def fetch_clip(clip):
    """Cut the clip from YouTube the first time it is used; after that the saved MP4 stays frozen."""
    path = os.path.join(config.VIDEOS_DIR, library_file(clip))
    with fetching:
        if os.path.isfile(path):
            return path
        if not config.ALLOW_FETCH:
            raise RuntimeError("this clip is not on the server, so choose another or upload an MP4")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        cmd = ["yt-dlp", "--no-playlist", "--no-warnings", "-f", "bv*[ext=mp4][height<=1080]+ba[ext=m4a]/b[ext=mp4]",
               "--merge-output-format", "mp4", "--download-sections", f"*{clip['start']}-{clip['end'] or 'inf'}",
               "--force-keyframes-at-cuts", "-o", path, "--", f"https://youtu.be/{clip['youtube']}"]
        try:
            done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  timeout=config.FETCH_TIMEOUT)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise RuntimeError(f"could not get this clip from YouTube: {e}")
        if done.returncode or not os.path.isfile(path):
            raise RuntimeError(f"could not get this clip from YouTube: {done.stderr.strip()[-300:]}")
    return path


def check_clip(path, start=None, end=None):
    """Refuses a file that is not a video, or one too big to hold in memory. Returns the error, or ''."""
    try:
        info = normalize.probe(path)
    except ValueError:
        return "this file is not a readable video"
    fps = normalize.rate(info.get("avg_frame_rate", 0))
    frames = int(info.get("nb_read_packets") or 0)
    if fps <= 0 or frames <= 0:
        return "could not read the frame rate of this video"
    if start is not None or end is not None:
        frames = min(frames, int(((end or frames / fps) - (start or 0)) * fps) + 1)
    pixels = int(info.get("width") or 0) * int(info.get("height") or 0)
    if pixels <= 0:
        return "could not read the size of this video"
    if pixels > config.MAX_PIXELS:
        return "the video is bigger than 1080p, so send a 1080p or smaller copy"
    limit = int(config.MAX_FRAME_GB * 1024 ** 3 / (pixels * 3))
    if frames > limit:
        return (f"the clip has {frames} frames and the limit at this size is {limit} "
                f"(about {limit / fps:.0f} s), so send a shorter clip")
    return ""


if config.PUBLIC and not config.ALLOW_FETCH:
    # only clips packed by pack_clips.py are listed online
    LIBRARY = [c for c in LIBRARY if os.path.isfile(os.path.join(config.VIDEOS_DIR, library_file(c)))]


def visitor():
    if "visitor" not in session:
        session["visitor"] = secrets.token_hex(8)
        session["csrf"] = secrets.token_urlsafe(24)
    return session["visitor"]


def logged_in():
    return not config.APP_PASSWORD or session.get("in") is True


def reserve_job():
    """Counts one job against today's limits. Returns the error, or ''. Locally there are no limits."""
    if not config.PUBLIC:
        return ""
    today = datetime.date.today()
    with counting:
        if usage["day"] != today:
            usage.update(day=today, total=0, visitors={})
        if sum(j["state"] in ("queued", "running") for j in jobs.values()) >= config.MAX_WAITING:
            return "the server is busy with other clips, so try again in a few minutes"
        if usage["total"] >= config.DAILY_JOBS:
            return "today's limit of clips is used up, so try again tomorrow"
        if usage["visitors"].get(visitor(), 0) >= config.VISITOR_DAILY_JOBS:
            return f"you have used your {config.VISITOR_DAILY_JOBS} clips for today"
        usage["total"] += 1
        usage["visitors"][visitor()] = usage["visitors"].get(visitor(), 0) + 1
    return ""


def release_job():
    """Gives back a job that was refused after it was counted."""
    if not config.PUBLIC:
        return
    with counting:
        usage["total"] -= 1
        usage["visitors"][visitor()] -= 1


def clean_old_jobs():
    cutoff = time.time() - config.JOB_HOURS * 3600
    if not os.path.isdir(config.JOBS_DIR):
        return
    for name in os.listdir(config.JOBS_DIR):
        path = os.path.join(config.JOBS_DIR, name)
        with counting:
            busy = jobs.get(name, {}).get("state") in ("queued", "running")
        if not busy and os.path.isdir(path) and os.path.getmtime(path) < cutoff:
            shutil.rmtree(path, ignore_errors=True)
            with counting:
                jobs.pop(name, None)


def keep_cleaning():
    while True:
        try:
            clean_old_jobs()
        except OSError:
            traceback.print_exc()
        time.sleep(3600)


def read_form(form, files, job_dir):
    sport = form.get("sport", "cricket")
    if sport not in SPORTS:
        raise ValueError("unknown sport")
    catalog = sports.decisions(sport)
    p = {"sport": sport, "decision": form.get("decision", ""), "level": form.get("level", "beginner"),
         "date": form.get("date", "").strip()[:40], "format": form.get("format", "").strip()[:40],
         "notes": form.get("notes", "").strip()[:500], "start": number(form.get("start")), "end": number(form.get("end"))}
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
            # online, the details stay in the server log
            job.update(state="failed", error="The run failed. Try again later, or try another clip."
                       if config.PUBLIC else str(e))


@app.before_request
def guard():
    if request.endpoint in ("login", "healthz"):
        return None
    if not logged_in():
        if request.method == "GET" and request.endpoint == "index":
            return redirect(url_for("login"))
        return jsonify(error="log in first"), 401
    if request.method == "POST" and config.APP_PASSWORD:
        sent = request.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(sent, session.get("csrf", "")):
            return jsonify(error="this page has expired, so reload it"), 403
    return None


@app.after_request
def headers(res):
    res.headers["X-Content-Type-Options"] = "nosniff"
    res.headers["Referrer-Policy"] = "same-origin"
    res.headers["Content-Security-Policy"] = CSP
    res.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if config.PUBLIC:
        res.headers["Strict-Transport-Security"] = "max-age=31536000"
    if request.endpoint in ("login", "index", "status"):
        res.headers["Cache-Control"] = "no-store"
    return res


@app.errorhandler(413)
def too_big(_):
    return jsonify(error=f"the upload is over {config.MAX_UPLOAD_MB} MB"), 413


@app.get("/healthz")
def healthz():
    return "ok"


@app.route("/login", methods=["GET", "POST"])
def login():
    if not config.APP_PASSWORD:
        return redirect(url_for("index"))
    error = ""
    if request.method == "POST":
        address, now = request.remote_addr or "?", time.time()
        with counting:
            tries = [t for t in failed_logins.get(address, []) if now - t < 900]
            failed_logins[address] = tries
        if len(tries) >= config.LOGIN_TRIES:
            error = "Too many wrong passwords. Wait 15 minutes."
        elif hmac.compare_digest(request.form.get("password", "").encode(), config.APP_PASSWORD.encode()):
            session.clear()
            session.permanent = True
            session["in"] = True
            visitor()
            return redirect(url_for("index"))
        else:
            with counting:
                failed_logins[address].append(now)
            error = "Wrong password."
    return render_template("login.html", error=error), 401 if error else 200


@app.post("/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/")
def index():
    visitor()
    groups = {}
    for sport in SPORTS:
        catalog = sports.decisions(sport)
        groups[sport] = {}
        for key, d in catalog.DECISIONS.items():
            groups[sport].setdefault(catalog.GROUP_LABELS[d["group"]], []).append((key, d["label"]))
    return render_template("index.html", groups=groups, levels=["beginner", "standard", "expert"], stages=STAGES,
                           library=library_rows(), csrf=session["csrf"], public=config.PUBLIC,
                           max_mb=config.MAX_UPLOAD_MB, locked=bool(config.APP_PASSWORD))


@app.get("/library/<int:number>")
def library_video(number):
    clip = library_clip(number)
    if not clip:
        abort(404)
    try:
        fetch_clip(clip)
    except RuntimeError as e:
        return jsonify(error=str(e)), 502
    return send_from_directory(config.VIDEOS_DIR, library_file(clip), conditional=True)


@app.post("/run")
def start():
    chosen = request.form.get("library")
    picked = library_clip(chosen) if chosen else None
    video = request.files.get("video")
    if chosen and not picked:
        return jsonify(error="that clip is not in the list, so choose another"), 400
    if not picked and (not video or not video.filename.lower().endswith(".mp4")):
        return jsonify(error="upload an MP4 file"), 400
    try:
        picked_path = fetch_clip(picked) if picked else None
    except RuntimeError as e:
        return jsonify(error=str(e)), 400
    refused = reserve_job()
    if refused:
        return jsonify(error=refused), 429
    if config.PUBLIC:
        clean_old_jobs()
    job_id = uuid.uuid4().hex[:12]
    job_dir = os.path.join(config.JOBS_DIR, job_id)
    os.makedirs(job_dir)
    try:
        params = read_form(request.form, request.files, job_dir)
        source = os.path.join(job_dir, "input.mp4")
        if picked:
            shutil.copyfile(picked_path, source)
        else:
            video.save(source)
        problem = check_clip(source, params["start"], params["end"]) if config.PUBLIC else ""
        if problem:
            raise ValueError(problem)
    except Exception as e:
        shutil.rmtree(job_dir, ignore_errors=True)
        release_job()
        if not isinstance(e, ValueError):
            raise
        return jsonify(error=str(e)), 400
    with counting:
        jobs[job_id] = {"state": "queued", "stage": 0, "error": "", "owner": visitor()}
    threading.Thread(target=worker, args=(job_id, job_dir, params), daemon=True).start()
    return jsonify(job=job_id)


def own_job(job_id):
    """The job, if it exists and this visitor started it."""
    job = jobs.get(job_id) if JOB_ID_RE.match(job_id) else None
    if not job or not hmac.compare_digest(job["owner"], session.get("visitor", "")):
        abort(404)
    return job


@app.get("/status/<job_id>")
def status(job_id):
    result = {k: v for k, v in own_job(job_id).items() if k != "owner"}
    if result["state"] == "done":
        path = os.path.join(config.JOBS_DIR, job_id, "plan.json")
        with open(path, encoding="utf-8") as f:
            result["plan"] = json.load(f)
    return jsonify(result)


@app.get("/video/<job_id>")
def video(job_id):
    own_job(job_id)
    return send_from_directory(os.path.join(config.JOBS_DIR, job_id), "output.mp4", conditional=True)


if config.PUBLIC:   # locally, old jobs are kept
    threading.Thread(target=keep_cleaning, daemon=True).start()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, threaded=True)
