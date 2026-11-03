"""Web page: upload an MP4, choose the inputs, get the explained video back.
Run locally: python app.py, then open http://127.0.0.1:5002
Online (PUBLIC=1) every page needs APP_PASSWORD, and jobs are capped per day and per visitor."""
import atexit, datetime, glob, hmac, json, math, os, re, secrets, shutil, subprocess, tempfile, threading, time, traceback, uuid
from flask import (Flask, abort, g, jsonify, redirect, render_template, request, send_from_directory, session,
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
YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_cookies_path = None
jobs = {}
SPORTS = ["cricket", "football", "basketball", "tennis"]
one_at_a_time = threading.Lock()   # jobs share the daily Gemini limit
fetching = threading.Lock()        # the preview and a run can ask for the same clip
counting = threading.Lock()        # guards jobs, usage and failed_logins
usage = {"day": None, "total": 0, "visitors": {}}
failed_logins = {}
with open(config.LIBRARY_PATH, encoding="utf-8") as f:
    LIBRARY = json.load(f)

# The page's one <script> and <style> carry a fresh nonce per response, so no other script can run.
CSP = ("default-src 'self'; script-src 'nonce-{n}'; style-src 'nonce-{n}' https://fonts.googleapis.com; "
       "font-src https://fonts.gstatic.com; img-src 'self' data:; media-src 'self' blob:; "
       "frame-src https://www.youtube-nocookie.com; connect-src 'self'; form-action 'self'; base-uri 'none'; "
       "object-src 'none'; frame-ancestors 'self' https://huggingface.co")
MAX_SECONDS = 6 * 3600   # a start or end later than this is a typing mistake


def number(text):
    """A start or end time in seconds, or None. Refuses negatives, NaN and infinity."""
    text = (text or "").strip()[:20]
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        raise ValueError("start and end must be numbers of seconds")
    if not math.isfinite(value) or not 0 <= value <= MAX_SECONDS:
        raise ValueError("start and end must be between 0 and 21600 seconds")
    return value


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


def cookies_file():
    """Writes the YT_COOKIES secret to a private file once and returns its path, or None.
    yt-dlp rewrites the file it is given, so the secret itself is never touched."""
    global _cookies_path
    if not config.YT_COOKIES:
        return None
    if _cookies_path is None:
        fd, path = tempfile.mkstemp(prefix="yt-cookies-", suffix=".txt")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(config.YT_COOKIES.replace("\\n", "\n"))   # also accepts a one-line paste with \n
        os.chmod(path, 0o600)
        _cookies_path = path
    return _cookies_path


def fetch_clip(clip, path=None):
    """Cut the clip from YouTube into path, unless it is already there; then the saved MP4 stays frozen.
    Only clips listed in library.json are ever fetched, never a link typed by a visitor."""
    path = path or os.path.join(config.VIDEOS_DIR, library_file(clip))
    with fetching:
        if os.path.isfile(path):
            return path
        if not config.ALLOW_FETCH:
            raise RuntimeError("this clip is not on the server, so choose another or upload an MP4")
        if not YOUTUBE_ID_RE.match(str(clip.get("youtube", ""))):
            raise RuntimeError("this clip has no valid YouTube ID")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        cmd = ["yt-dlp", "--no-playlist", "--no-warnings", "-f", "bv*[ext=mp4][height<=1080]+ba[ext=m4a]/b[ext=mp4]",
               "--merge-output-format", "mp4", "--download-sections", f"*{clip['start']}-{clip['end'] or 'inf'}",
               "--force-keyframes-at-cuts", "--max-filesize", f"{config.MAX_UPLOAD_MB}M", "--no-exec", "-o", path]
        if cookies_file():
            cmd += ["--cookies", cookies_file()]
        cmd += ["--", f"https://youtu.be/{clip['youtube']}"]
        try:
            done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  timeout=config.FETCH_TIMEOUT)
            detail = done.stderr.strip()[-300:] if done.returncode or not os.path.isfile(path) else ""
        except (OSError, subprocess.TimeoutExpired) as e:
            detail = str(e)[-300:]
        if detail:
            for leftover in glob.glob(glob.escape(path) + "*"):   # partial downloads would look like a frozen clip
                os.remove(leftover)
            print(f"  YouTube fetch failed for {clip['youtube']}: {detail}")
            if config.PUBLIC:   # details stay in the server log
                raise RuntimeError("YouTube did not send this clip right now, so try again later, "
                                   "choose another, or upload an MP4")
            raise RuntimeError(f"could not get this clip from YouTube: {detail}")
    return path


def clip_path(number, clip):
    """The file a library clip is read from. A clip packed with the app (or in the local videos folder) is used as
    it is. With TEMP_FILES, any other clip is downloaded for this visitor only, and deleted with their files."""
    saved = os.path.join(config.VIDEOS_DIR, library_file(clip))
    if os.path.isfile(saved) or not config.TEMP_FILES:
        return fetch_clip(clip, saved)
    os.makedirs(config.SELECTED_DIR, exist_ok=True)
    target = os.path.join(config.SELECTED_DIR, f"{visitor()}_{int(number)}.mp4")
    for old in glob.glob(os.path.join(config.SELECTED_DIR, f"{visitor()}_*")):
        if old != target:   # one selected clip per visitor
            remove(old)
    return fetch_clip(clip, target)


def remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def check_clip(path, start=None, end=None):
    """Refuses a file that is not a video, bigger than 1080p, or too long. Returns the error, or ''."""
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
    if frames / fps > config.MAX_CLIP_SECONDS:
        return (f"the clip is {frames / fps:.0f} s long and the limit is {config.MAX_CLIP_SECONDS} s, "
                f"so send a shorter clip or set the start and end")
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


def delete_job(job_id):
    """Deletes a job's folder (input, output and every file made on the way) and forgets the job."""
    shutil.rmtree(os.path.join(config.JOBS_DIR, job_id), ignore_errors=True)
    with counting:
        jobs.pop(job_id, None)


def forget_visitor(owner):
    """The visitor refreshed or left the page: deletes their selected clip and their finished jobs.
    A job still running is deleted as soon as it ends, since nobody is left to see it."""
    if not config.TEMP_FILES or not owner:
        return
    for path in glob.glob(os.path.join(config.SELECTED_DIR, f"{owner}_*")):
        remove(path)
    finished = []
    with counting:
        for job_id, job in jobs.items():
            if job["owner"] != owner:
                continue
            if job["state"] in ("queued", "running"):
                job["forget"] = True
            else:
                finished.append(job_id)
    for job_id in finished:
        delete_job(job_id)


def clean_old_files(now=None):
    """Deletes jobs TEMP_MINUTES after their output was made, plus selected clips and job folders that old
    which no job owns (left by a crash). A queued or running job is never touched."""
    if not config.TEMP_FILES:
        return
    now, limit = now or time.time(), config.TEMP_MINUTES * 60
    with counting:
        expired = [i for i, j in jobs.items() if j.get("done_at") and now - j["done_at"] >= limit]
        known = set(jobs)
    for job_id in expired:
        delete_job(job_id)
    for folder, is_job in ((config.JOBS_DIR, True), (config.SELECTED_DIR, False)):
        if not os.path.isdir(folder):
            continue
        for name in os.listdir(folder):
            path = os.path.join(folder, name)
            try:
                old = now - os.path.getmtime(path) >= limit
            except OSError:
                continue
            if is_job and name not in known and old:
                shutil.rmtree(path, ignore_errors=True)
            elif not is_job and old:
                remove(path)


def wipe_all():
    """Deletes every job and selected clip. Runs when the server starts and when it stops, so nothing a visitor
    sent survives a restart, even one after a crash."""
    for folder in (config.JOBS_DIR, config.SELECTED_DIR):
        if os.path.isdir(folder):
            for name in os.listdir(folder):
                path = os.path.join(folder, name)
                shutil.rmtree(path, ignore_errors=True) if os.path.isdir(path) else remove(path)
    with counting:
        jobs.clear()


def keep_cleaning():
    while True:
        try:
            clean_old_files()
        except OSError:
            traceback.print_exc()
        time.sleep(60)


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
    if p["start"] is not None and p["end"] is not None and p["end"] <= p["start"]:
        raise ValueError("the end must be after the start")
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
            end = {"state": "done", "stage": len(STAGES)}
        except Exception as e:
            traceback.print_exc()
            # online, the details stay in the server log
            end = {"state": "failed", "error": "The run failed. Try again later, or try another clip."
                   if config.PUBLIC else str(e)}
        with counting:   # the 30 minutes start now; forget_visitor checks the state under the same lock
            job.update(end, done_at=time.time())
            gone = job.get("forget")
        if gone and config.TEMP_FILES:
            delete_job(job_id)


@app.context_processor
def nonce():
    return {"nonce": g.get("nonce", "")}


@app.before_request
def guard():
    g.nonce = secrets.token_urlsafe(16)
    if request.endpoint in ("login", "healthz", "static"):
        return None
    if not logged_in():
        if request.method == "GET" and request.endpoint == "index":
            return redirect(url_for("login"))
        return jsonify(error="log in first"), 401
    if request.method == "POST" and config.APP_PASSWORD:
        # sendBeacon (used when the page is left) cannot set headers, so it sends the token as a form field
        sent = request.headers.get("X-CSRF-Token") or request.form.get("csrf", "")
        if not hmac.compare_digest(sent, session.get("csrf", "")):
            return jsonify(error="this page has expired, so reload it"), 403
    return None


@app.after_request
def headers(res):
    res.headers["X-Content-Type-Options"] = "nosniff"
    res.headers["Referrer-Policy"] = "same-origin"
    res.headers["Content-Security-Policy"] = CSP.format(n=g.get("nonce") or secrets.token_urlsafe(16))
    res.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    res.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    if request.endpoint not in ("login", "index"):   # the pages themselves load inside Hugging Face's iframe
        res.headers["Cross-Origin-Resource-Policy"] = "same-origin"
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


def note_failed_login(address, now):
    """Records a wrong password, and forgets addresses with no recent tries so the table stays small."""
    with counting:
        failed_logins.setdefault(address, []).append(now)
        if len(failed_logins) > 10000:
            for key in [k for k, v in failed_logins.items() if not v or now - v[-1] >= 900]:
                failed_logins.pop(key, None)


@app.route("/login", methods=["GET", "POST"])
def login():
    if not config.APP_PASSWORD:
        return redirect(url_for("index"))
    if "login_csrf" not in session:
        session["login_csrf"] = secrets.token_urlsafe(24)
    error = ""
    if request.method == "POST":
        address, now = request.remote_addr or "?", time.time()
        with counting:
            tries = [t for t in failed_logins.get(address, []) if now - t < 900]
            failed_logins[address] = tries
            locked = len(tries) >= config.LOGIN_TRIES
        if locked:
            error = "Too many wrong passwords. Wait 15 minutes."
        elif not hmac.compare_digest(request.form.get("csrf", ""), session.get("login_csrf", "")):
            error = "This page has expired. Try again."
        elif hmac.compare_digest(request.form.get("password", "").encode(), config.APP_PASSWORD.encode()):
            session.clear()   # a fresh session, so a cookie set before login is never reused
            session.permanent = True
            session["in"] = True
            visitor()
            return redirect(url_for("index"))
        else:
            note_failed_login(address, now)
            error = "Wrong password."
    return render_template("login.html", error=error, csrf=session["login_csrf"]), 401 if error else 200


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
                           max_mb=config.MAX_UPLOAD_MB, locked=bool(config.APP_PASSWORD),
                           temp_minutes=config.TEMP_MINUTES if config.TEMP_FILES else 0)


@app.get("/library/<int:number>")
def library_video(number):
    clip = library_clip(number)
    if not clip:
        abort(404)
    try:
        path = clip_path(number, clip)
    except RuntimeError as e:
        return jsonify(error=str(e)), 502
    return send_from_directory(os.path.dirname(path), os.path.basename(path), conditional=True)


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
        picked_path = clip_path(chosen, picked) if picked else None
    except RuntimeError as e:
        return jsonify(error=str(e)), 400
    refused = reserve_job()
    if refused:
        return jsonify(error=refused), 429
    clean_old_files()
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


@app.post("/forget")
def forget():
    """Sent by the page as it unloads (refresh, close, leaving the site)."""
    forget_visitor(session.get("visitor", ""))
    return "", 204


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


if config.TEMP_FILES:   # locally (TEMP_FILES=0 by default) jobs are kept as a record
    wipe_all()   # anything left by a crash or a hard stop
    atexit.register(wipe_all)
    threading.Thread(target=keep_cleaning, daemon=True).start()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5002, threaded=True)   # V7 keeps 5001
