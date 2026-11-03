import os
import time
import app as web
import config

PASSWORD = "a-long-test-password"


def online(monkeypatch, tmp_path, probe=None):
    monkeypatch.setattr(config, "PUBLIC", True)
    monkeypatch.setattr(config, "APP_PASSWORD", PASSWORD)
    monkeypatch.setattr(config, "VIDEOS_DIR", str(tmp_path))
    monkeypatch.setattr(config, "JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setattr(config, "DAILY_JOBS", 3)
    monkeypatch.setattr(config, "VISITOR_DAILY_JOBS", 2)
    monkeypatch.setattr(web, "run_job", lambda *args: None)
    monkeypatch.setattr(web, "jobs", {})
    monkeypatch.setattr(web, "failed_logins", {})
    monkeypatch.setattr(web, "usage", {"day": None, "total": 0, "visitors": {}})
    monkeypatch.setattr(web, "LIBRARY", [{"youtube": "abc", "start": 0, "end": None, "sport": "tennis",
                                          "decision": "ball_out", "description": "A serve", "file": "a.mp4"}])
    monkeypatch.setattr(web.normalize, "probe", probe or (lambda path: {
        "avg_frame_rate": "25/1", "nb_read_packets": 125, "width": 1920, "height": 1080}))
    (tmp_path / "a.mp4").write_bytes(b"clip bytes")
    os.makedirs(config.JOBS_DIR, exist_ok=True)
    return web.app.test_client()


def login_token(client):
    page = client.get("/login").get_data(as_text=True)
    return page.split('name="csrf" value="')[1].split('"')[0]


def log_in(client):
    res = client.post("/login", data={"password": PASSWORD, "csrf": login_token(client)})
    assert res.status_code == 302
    page = client.get("/").get_data(as_text=True)
    return page.split('<meta name="csrf" content="')[1].split('"')[0]


def run(client, token):
    return client.post("/run", data={"library": "1", "sport": "tennis", "decision": "ball_out", "level": "beginner"},
                       headers={"X-CSRF-Token": token})


def test_every_page_needs_the_password(monkeypatch, tmp_path):
    client = online(monkeypatch, tmp_path)
    assert client.get("/").status_code == 302
    assert client.get("/library/1").status_code == 401
    assert client.post("/run", data={}).status_code == 401
    assert client.get("/healthz").status_code == 200


def test_wrong_passwords_lock_the_address(monkeypatch, tmp_path):
    client = online(monkeypatch, tmp_path)
    token = login_token(client)
    for _ in range(config.LOGIN_TRIES):
        assert client.post("/login", data={"password": "wrong", "csrf": token}).status_code == 401
    res = client.post("/login", data={"password": PASSWORD, "csrf": token})
    assert res.status_code == 401 and "Too many" in res.get_data(as_text=True)


def test_a_post_without_the_page_token_is_refused(monkeypatch, tmp_path):
    client = online(monkeypatch, tmp_path)
    log_in(client)
    assert run(client, "forged").status_code == 403


def test_jobs_are_capped_per_visitor_and_per_day(monkeypatch, tmp_path):
    first, second = online(monkeypatch, tmp_path), web.app.test_client()
    a, b = log_in(first), log_in(second)
    assert run(first, a).status_code == 200
    for job in web.jobs.values():
        job["state"] = "done"   # so the waiting limit does not get in the way
    assert run(first, a).status_code == 200
    res = run(first, a)
    assert res.status_code == 429 and "your 2 clips" in res.get_json()["error"]
    for job in web.jobs.values():
        job["state"] = "done"
    assert run(second, b).status_code == 200
    for job in web.jobs.values():
        job["state"] = "done"
    res = run(second, b)
    assert res.status_code == 429 and "today's limit" in res.get_json()["error"]


def test_only_the_visitor_who_started_a_job_can_see_it(monkeypatch, tmp_path):
    first, second = online(monkeypatch, tmp_path), web.app.test_client()
    a = log_in(first)
    log_in(second)
    job = run(first, a).get_json()["job"]
    web.jobs[job]["state"] = "running"   # the fake run writes no plan
    assert first.get(f"/status/{job}").status_code == 200
    assert second.get(f"/status/{job}").status_code == 404
    assert second.get(f"/video/{job}").status_code == 404


def test_a_clip_too_long_is_refused_and_not_counted(monkeypatch, tmp_path):
    client = online(monkeypatch, tmp_path, probe=lambda path: {
        "avg_frame_rate": "30/1", "nb_read_packets": 30 * 121, "width": 1920, "height": 1080})
    token = log_in(client)
    res = run(client, token)
    assert res.status_code == 400 and "121 s long" in res.get_json()["error"]
    assert web.usage["total"] == 0 and os.listdir(config.JOBS_DIR) == []


def test_a_file_that_is_not_a_video_is_refused(monkeypatch, tmp_path):
    def broken(path):
        raise ValueError("not a readable video")
    client = online(monkeypatch, tmp_path, probe=broken)
    token = log_in(client)
    res = run(client, token)
    assert res.status_code == 400 and "not a readable video" in res.get_json()["error"]


def test_bigger_than_1080p_is_refused():
    def probe(path):
        return {"avg_frame_rate": "25/1", "nb_read_packets": 50, "width": 3840, "height": 2160}
    original, web.normalize.probe = web.normalize.probe, probe
    try:
        assert "1080p" in web.check_clip("x.mp4")
    finally:
        web.normalize.probe = original


def test_a_failed_run_hides_the_details_online(monkeypatch, tmp_path):
    online(monkeypatch, tmp_path)

    def crash(*args):
        raise RuntimeError("secret detail from the server")
    monkeypatch.setattr(web, "run_job", crash)
    web.jobs["abcdefabcdef"] = {"state": "queued", "stage": 0, "error": "", "owner": "x"}
    web.worker("abcdefabcdef", str(tmp_path), {})
    assert "secret" not in web.jobs["abcdefabcdef"]["error"]


def test_pages_send_the_security_headers(monkeypatch, tmp_path):
    client = online(monkeypatch, tmp_path)
    res = client.get("/login")
    assert "frame-ancestors" in res.headers["Content-Security-Policy"]
    assert res.headers["X-Content-Type-Options"] == "nosniff"


def temp_files(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "TEMP_FILES", True)
    monkeypatch.setattr(config, "SELECTED_DIR", str(tmp_path / "selected"))


def finished_job(owner, minutes_ago=0, state="done"):
    job_id = os.urandom(6).hex()
    os.makedirs(os.path.join(config.JOBS_DIR, job_id))
    open(os.path.join(config.JOBS_DIR, job_id, "output.mp4"), "wb").close()
    web.jobs[job_id] = {"state": state, "stage": 0, "error": "", "owner": owner,
                        **({"done_at": time.time() - minutes_ago * 60} if state in ("done", "failed") else {})}
    return job_id


def exists(job_id):
    return os.path.isdir(os.path.join(config.JOBS_DIR, job_id))


def test_jobs_are_deleted_30_minutes_after_the_output(monkeypatch, tmp_path):
    online(monkeypatch, tmp_path)
    temp_files(monkeypatch, tmp_path)
    fresh, old, failed, running = (finished_job("v", 5), finished_job("v", 31), finished_job("v", 31, "failed"),
                                   finished_job("v", state="running"))
    orphan = os.path.join(config.JOBS_DIR, "aaaaaaaaaaaa")   # left by a crash: no job owns it
    os.makedirs(orphan)
    os.utime(orphan, (0, 0))
    web.clean_old_files()
    assert exists(fresh) and exists(running)
    assert not exists(old) and not exists(failed) and not os.path.exists(orphan)
    assert old not in web.jobs and fresh in web.jobs


def test_leaving_the_page_deletes_only_that_visitors_files(monkeypatch, tmp_path):
    client = online(monkeypatch, tmp_path)
    temp_files(monkeypatch, tmp_path)
    token = log_in(client)
    with client.session_transaction() as s:
        me = s["visitor"]
    mine, theirs = finished_job(me), finished_job("someone-else")
    os.makedirs(config.SELECTED_DIR)
    picked, other = (os.path.join(config.SELECTED_DIR, f"{who}_1.mp4") for who in (me, "someone-else"))
    for path in (picked, other):
        open(path, "wb").close()
    assert client.post("/forget", data={"csrf": "forged"}).status_code == 403
    assert exists(mine)
    assert client.post("/forget", data={"csrf": token}).status_code == 204
    assert not exists(mine) and not os.path.exists(picked)
    assert exists(theirs) and os.path.exists(other)


def test_a_job_still_running_is_deleted_when_it_ends(monkeypatch, tmp_path):
    online(monkeypatch, tmp_path)
    temp_files(monkeypatch, tmp_path)
    job_id = finished_job("v", state="running")
    web.forget_visitor("v")
    assert exists(job_id) and web.jobs[job_id]["forget"]
    web.worker(job_id, os.path.join(config.JOBS_DIR, job_id), {})
    assert not exists(job_id) and job_id not in web.jobs


def test_a_finished_job_gets_its_output_time(monkeypatch, tmp_path):
    online(monkeypatch, tmp_path)
    temp_files(monkeypatch, tmp_path)
    job_id = finished_job("v", state="running")
    web.worker(job_id, os.path.join(config.JOBS_DIR, job_id), {})
    assert web.jobs[job_id]["state"] == "done" and time.time() - web.jobs[job_id]["done_at"] < 5


def test_stopping_or_starting_the_server_wipes_everything(monkeypatch, tmp_path):
    online(monkeypatch, tmp_path)
    temp_files(monkeypatch, tmp_path)
    job_id = finished_job("v")
    os.makedirs(config.SELECTED_DIR)
    open(os.path.join(config.SELECTED_DIR, "v_1.mp4"), "wb").close()
    web.wipe_all()
    assert not exists(job_id) and os.listdir(config.SELECTED_DIR) == [] and web.jobs == {}


def test_a_library_clip_is_downloaded_for_this_visitor_only(monkeypatch, tmp_path):
    client = online(monkeypatch, tmp_path)
    temp_files(monkeypatch, tmp_path)
    monkeypatch.setattr(web, "LIBRARY", web.LIBRARY + [
        {"youtube": "abcdefghijk", "start": 0, "end": 5, "sport": "tennis", "decision": "ball_out", "description": "x"},
        {"youtube": "bcdefghijkl", "start": 0, "end": 5, "sport": "tennis", "decision": "ball_out", "description": "y"}])
    fetched = []

    def fetch(clip, path=None):
        fetched.append(path)
        open(path, "wb").close()
        return path
    monkeypatch.setattr(web, "fetch_clip", fetch)
    log_in(client)
    assert client.get("/library/1").status_code == 200          # packed with the app: used as it is
    assert fetched == [os.path.join(config.VIDEOS_DIR, "a.mp4")]
    assert client.get("/library/2").status_code == 200
    assert client.get("/library/3").status_code == 200
    assert [os.path.basename(p).split("_")[1] for p in os.listdir(config.SELECTED_DIR)] == ["3.mp4"]   # one at a time
    assert os.path.isfile(os.path.join(config.VIDEOS_DIR, "a.mp4"))


def test_locally_there_is_no_password_and_no_limit(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "VIDEOS_DIR", str(tmp_path))
    monkeypatch.setattr(config, "JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setattr(web, "run_job", lambda *args: None)
    monkeypatch.setattr(web, "LIBRARY", [{"youtube": "abc", "start": 0, "end": None, "sport": "tennis",
                                          "decision": "ball_out", "description": "A serve", "file": "a.mp4"}])
    (tmp_path / "a.mp4").write_bytes(b"clip bytes")
    os.makedirs(config.JOBS_DIR)
    client = web.app.test_client()
    for _ in range(config.VISITOR_DAILY_JOBS + 1):
        res = client.post("/run", data={"library": "1", "sport": "tennis", "decision": "ball_out", "level": "beginner"})
        assert res.status_code == 200


def test_a_login_without_the_page_token_is_refused(monkeypatch, tmp_path):
    client = online(monkeypatch, tmp_path)
    login_token(client)
    res = client.post("/login", data={"password": PASSWORD, "csrf": "forged"})
    assert res.status_code == 401 and "expired" in res.get_data(as_text=True)
    assert client.get("/").status_code == 302


def test_scripts_need_the_nonce_of_their_own_response(monkeypatch, tmp_path):
    client = online(monkeypatch, tmp_path)
    log_in(client)
    pages = [client.get("/"), client.get("/")]
    nonces = []
    for res in pages:
        csp = res.headers["Content-Security-Policy"]
        assert "unsafe-inline" not in csp
        nonce = csp.split("script-src 'nonce-")[1].split("'")[0]
        assert f'<script nonce="{nonce}">' in res.get_data(as_text=True)
        nonces.append(nonce)
    assert nonces[0] != nonces[1]


def test_bad_start_and_end_are_refused_and_not_counted(monkeypatch, tmp_path):
    client = online(monkeypatch, tmp_path)
    token = log_in(client)
    for start, end in (("nan", ""), ("-1", ""), ("", "inf"), ("1e9", ""), ("5", "2"), ("abc", "")):
        res = client.post("/run", data={"library": "1", "sport": "tennis", "decision": "ball_out", "level": "beginner",
                                        "start": start, "end": end}, headers={"X-CSRF-Token": token})
        assert res.status_code == 400, (start, end)
    assert web.usage["total"] == 0 and os.listdir(config.JOBS_DIR) == []
