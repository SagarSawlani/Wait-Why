import os
import subprocess
import app as web
import config
import sports


def fake_library(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "VIDEOS_DIR", str(tmp_path))
    monkeypatch.setattr(config, "JOBS_DIR", str(tmp_path / "jobs"))
    monkeypatch.setattr(web, "run_job", lambda *args: None)
    monkeypatch.setattr(web, "LIBRARY", [{"youtube": "abc", "start": 0, "end": None, "sport": "tennis",
                                          "decision": "ball_out", "description": "A serve", "file": "a.mp4"},
                                         {"youtube": "def", "start": 5, "end": 9, "sport": "tennis",
                                          "decision": "ball_out", "description": "New"}])
    (tmp_path / "a.mp4").write_bytes(b"clip bytes")
    return web.app.test_client()


def fake_yt_dlp(monkeypatch, returncode=0):
    calls = []

    def run(cmd, **kwargs):
        calls.append(cmd)
        if not returncode:
            with open(cmd[cmd.index("-o") + 1], "wb") as f:
                f.write(b"cut bytes")
        return subprocess.CompletedProcess(cmd, returncode, "", "video unavailable")
    monkeypatch.setattr(web.subprocess, "run", run)
    return calls


def test_every_library_entry_names_a_real_decision():
    for clip in web.LIBRARY:
        assert clip["decision"] in sports.decisions(clip["sport"]).DECISIONS
        assert clip["youtube"] and clip["description"]
        assert clip.get("file") or clip["end"]


def test_library_has_several_different_decisions_per_sport():
    for sport in web.SPORTS:
        assert len({c["decision"] for c in web.LIBRARY if c["sport"] == sport}) >= 3


def test_page_embeds_the_section_data_without_showing_times(monkeypatch, tmp_path):
    client = fake_library(monkeypatch, tmp_path)
    page = client.get("/").get_data(as_text=True)
    assert "youtu.be/abc" in page and "Select from here" in page
    assert 'data-start="5" data-end="9"' in page


def test_saved_clip_is_served_without_yt_dlp(monkeypatch, tmp_path):
    client = fake_library(monkeypatch, tmp_path)
    calls = fake_yt_dlp(monkeypatch)
    assert client.get("/library/1").data == b"clip bytes"
    assert client.get("/library/3").status_code == 404
    assert calls == []


def test_new_clip_is_cut_once_with_its_section(monkeypatch, tmp_path):
    client = fake_library(monkeypatch, tmp_path)
    calls = fake_yt_dlp(monkeypatch)
    assert client.get("/library/2").data == b"cut bytes"
    assert client.get("/library/2").data == b"cut bytes"
    assert len(calls) == 1
    assert "*5-9" in calls[0] and calls[0][-1] == "https://youtu.be/def"


def test_failed_cut_is_reported(monkeypatch, tmp_path):
    client = fake_library(monkeypatch, tmp_path)
    fake_yt_dlp(monkeypatch, returncode=1)
    assert client.get("/library/2").status_code == 502
    res = client.post("/run", data={"library": "2", "sport": "tennis", "decision": "ball_out"})
    assert res.status_code == 400 and "video unavailable" in res.get_json()["error"]


def test_run_copies_the_library_clip_without_an_upload(monkeypatch, tmp_path):
    client = fake_library(monkeypatch, tmp_path)
    os.makedirs(config.JOBS_DIR)
    res = client.post("/run", data={"library": "1", "sport": "tennis", "decision": "ball_out", "level": "beginner"})
    assert res.status_code == 200
    with open(os.path.join(config.JOBS_DIR, res.get_json()["job"], "input.mp4"), "rb") as f:
        assert f.read() == b"clip bytes"


def test_run_refuses_an_unknown_library_clip(monkeypatch, tmp_path):
    client = fake_library(monkeypatch, tmp_path)
    res = client.post("/run", data={"library": "9", "sport": "tennis", "decision": "ball_out"})
    assert res.status_code == 400 and "not in the list" in res.get_json()["error"]


def test_run_still_needs_a_clip(monkeypatch, tmp_path):
    client = fake_library(monkeypatch, tmp_path)
    res = client.post("/run", data={"sport": "tennis", "decision": "ball_out"})
    assert res.status_code == 400 and res.get_json()["error"] == "upload an MP4 file"
