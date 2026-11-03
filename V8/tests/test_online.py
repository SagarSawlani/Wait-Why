import os
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


def log_in(client):
    res = client.post("/login", data={"password": PASSWORD})
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
    for _ in range(config.LOGIN_TRIES):
        assert client.post("/login", data={"password": "wrong"}).status_code == 401
    res = client.post("/login", data={"password": PASSWORD})
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


def test_a_clip_too_big_for_memory_is_refused_and_not_counted(monkeypatch, tmp_path):
    client = online(monkeypatch, tmp_path, probe=lambda path: {
        "avg_frame_rate": "30/1", "nb_read_packets": 3000, "width": 1920, "height": 1080})
    token = log_in(client)
    res = run(client, token)
    assert res.status_code == 400 and "frames" in res.get_json()["error"]
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


def test_old_jobs_are_deleted(monkeypatch, tmp_path):
    online(monkeypatch, tmp_path)
    old = os.path.join(config.JOBS_DIR, "aaaaaaaaaaaa")
    os.makedirs(old)
    os.utime(old, (0, 0))
    web.clean_old_jobs()
    assert not os.path.exists(old)


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
