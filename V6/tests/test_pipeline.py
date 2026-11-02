"""Unit tests. No real clips and no API calls: the LLM is stubbed, and the render test draws its own frames.
Run from V1: python -m pytest tests -q"""
import json, os, sys
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from sports.cricket import events, laws
from sports.cricket.decisions import DECISIONS, detect_prompt, plan_prompt, rule_prompt
from pipeline import detect, llm, normalize, plan, render, rules


def ball(delivery="12.3", **extra):
    return {"actual_delivery": delivery, "batter": "A", "bowler": "B", "non_striker": "C",
            "runs": {"batter": 0, "extras": 0, "total": 0}, **extra}


def match(deliveries):
    return {"info": {"match_type": "Test", "dates": ["2024-01-02"], "event": {"name": "Cup"}, "teams": ["X", "Y"]},
            "innings": [{"team": "X", "overs": [{"over": 12, "deliveries": deliveries}]}]}


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr(llm, "RETRY_WAIT", 0)


# ---------- decisions ----------
@pytest.mark.parametrize("edition", ["3rd_2022", "4th_2026"])
@pytest.mark.parametrize("key", list(DECISIONS))
def test_every_decision_finds_law_text(key, edition):
    sections = rules.retrieve(key, edition)
    assert sections and all(s["text"] for s in sections)


@pytest.mark.parametrize("edition", ["3rd_2022", "4th_2026"])
@pytest.mark.parametrize("key", list(DECISIONS))
def test_every_named_section_exists(key, edition):
    """A title that matches nothing would silently lose rule text, unless the edition dropped it."""
    book = rules.load_laws(edition)
    for number, title in DECISIONS[key]["laws"]:
        if title is None or title == "Ball bouncing over head height":
            continue
        heads = [rules.heading(t) for t in book[number]["sections"].values()]
        assert any(h.startswith(title.lower()) for h in heads), (number, title)


@pytest.mark.parametrize("key", list(DECISIONS))
def test_decision_is_complete_and_prompts_build(key):
    d = DECISIONS[key]
    assert d["label"] and d["signal"] and d["moments"]
    keys = [m[0] for m in d["moments"]]
    assert len(keys) == len(set(keys))
    event = events.from_form(key)
    prompt = detect_prompt(key, event, 2)
    assert all(k in prompt for k in keys)
    assert d["label"] in rule_prompt(key, "beginner", [{"id": "1.1", "text": "x"}])
    moments = [{"key": keys[0], "label": "L", "evidence": "e"}]
    assert keys[0] in plan_prompt(key, event, {"summary": "s", "conditions": []}, moments)


def test_rule_prompt_keeps_alternatives_together():
    from sports.cricket.decisions import RULE_SYSTEM
    assert 'joined by "or"' in RULE_SYSTEM


def test_wide_variety_of_decisions():
    assert len(DECISIONS) >= 20
    assert {"bowled", "lbw", "caught", "run_out", "stumped", "four", "six", "wide", "no_ball_front_foot"} <= set(DECISIONS)


# ---------- laws ----------
def test_parse_lines_keeps_longest_copy_and_stops_at_appendix():
    lines = ["LAW 32 BOWLED", "32.1 Out Bowled 103", "LAW 32 Bowled 103", "LAW 32 BOWLED", "32.1 Out Bowled",
             "The striker is out.", "32.1.1 Sub clause", "12", "APPENDIX A", "33.1 Not a law"]
    parsed = laws.parse_lines(lines)
    assert parsed["32"]["title"] == "Bowled"
    assert "The striker is out." in parsed["32"]["sections"]["32.1"]
    assert "32.2" not in parsed["32"]["sections"] and "Not a law" not in parsed["32"]["text"]


def test_lbw_text_is_real():
    for edition in ("3rd_2022", "4th_2026"):
        assert "would have hit the wicket" in rules.load_laws(edition)["36"]["text"]


# ---------- normalize ----------
GOOD = {"codec_name": "h264", "pix_fmt": "yuv420p", "r_frame_rate": "25/1", "avg_frame_rate": "25/1",
        "width": 1920, "height": 1080}


def test_compliant_clip_has_no_problems():
    assert normalize.problems(GOOD) == []


@pytest.mark.parametrize("change,word", [({"codec_name": "hevc"}, "codec"), ({"pix_fmt": "yuv420p10le"}, "pixel"),
                                         ({"r_frame_rate": "30/1"}, "variable"), ({"width": 1921}, "odd")])
def test_problem_detection(change, word):
    assert word in normalize.problems({**GOOD, **change})[0]


def test_encode_fixes_everything_in_one_command():
    cmd = " ".join(normalize.encode_command("a.mp4", "b.mp4", {"avg_frame_rate": "30000/1001"}, 1.0, 4.0))
    assert all(x in cmd for x in ("libx264", "yuv420p", "fps=30000/1001", "-ss 1.0", "-t 3.0"))


def test_ntsc_rate_is_read():
    assert normalize.rate("30000/1001") == pytest.approx(29.97, abs=0.01)
    assert normalize.rate("0/0") == 0.0


# ---------- events ----------
@pytest.mark.parametrize("delivery,key", [
    (ball(wickets=[{"kind": "lbw", "player_out": "A"}]), "lbw"),
    (ball(wickets=[{"kind": "caught and bowled", "player_out": "A"}]), "caught_and_bowled"),
    (ball(extras={"wides": 1}), "wide"), (ball(extras={"noballs": 1}), "no_ball_other"),
    (ball(runs={"batter": 6, "extras": 0, "total": 6}), "six"),
    (ball(runs={"batter": 4, "extras": 0, "total": 4}), "four"),
    (ball(runs={"batter": 4, "extras": 0, "total": 4, "non_boundary": True}), None),
    (ball(extras={"legbyes": 1}), "leg_bye"), (ball(extras={"byes": 4}), "bye"),
    (ball(review={"by": "X", "decision": "upheld"}), "drs_review"), (ball(), None)])
def test_classify(delivery, key):
    assert events.classify(delivery) == key


def test_event_from_cricsheet():
    m = match([ball(wickets=[{"kind": "caught", "player_out": "A", "fielders": [{"name": "F"}]}])])
    e = events.from_cricsheet(m, 1, "12.3")
    assert e["subtype"] == "caught" and e["context"]["date"] == "2024-01-02" and e["context"]["format"] == "Test"
    assert {"role": "fielder", "name": "F"} in e["actors"]


def test_wide_and_rebowled_ball_share_a_number():
    m = match([ball(extras={"wides": 1}), ball(wickets=[{"kind": "bowled", "player_out": "A"}])])
    assert len(events.find_balls(m, 1, "12.3")) == 2
    assert events.from_cricsheet(m, 1, "12.3", "wide")["subtype"] == "wide"
    assert events.from_cricsheet(m, 1, "12.3")["subtype"] == "bowled"


def test_wrong_ball_stops_the_run():
    m = match([ball(runs={"batter": 4, "extras": 0, "total": 4})])
    with pytest.raises(ValueError, match="expected bowled"):
        events.from_cricsheet(m, 1, "12.3", "bowled")


@pytest.mark.parametrize("innings,over_ball", [(2, "12.3"), (1, "13.1"), (1, "abc")])
def test_bad_ball_reference(innings, over_ball):
    with pytest.raises(ValueError):
        events.from_cricsheet(match([ball()]), innings, over_ball)


def test_ball_with_no_decision_needs_a_choice():
    with pytest.raises(ValueError, match="no umpire decision"):
        events.from_cricsheet(match([ball()]), 1, "12.3")
    assert events.from_cricsheet(match([ball()]), 1, "12.3", "not_out_appeal")["subtype"] == "not_out_appeal"


def test_front_foot_choice_matches_a_scored_no_ball():
    m = match([ball(extras={"noballs": 1})])
    assert events.from_cricsheet(m, 1, "12.3", "no_ball_front_foot")["subtype"] == "no_ball_front_foot"


def test_real_format_sample_keys():
    with pytest.raises(ValueError):
        events.validate({"subtype": "bowled"})
    with pytest.raises(ValueError, match="unknown decision"):
        events.from_form("nonsense")
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        events.from_form("bowled", date="02/01/2024")


# ---------- llm chain ----------
CHAIN = [("gemini-3.8-flash", 2), ("gemini-3.6-flash", 1), ("gemini-3.5-flash-lite", 1)]


def test_detection_uses_the_planned_chain():
    assert config.DETECT_CHAIN[0] == ("gemini-3.8-flash", 1)


def test_chain_order_matches_the_plan(monkeypatch):
    calls = []
    def fail(model, system, contents):
        calls.append(model)
        raise RuntimeError("no")
    monkeypatch.setattr(llm, "_call", fail)
    with pytest.raises(RuntimeError, match="all models failed"):
        llm.generate(CHAIN, "s", ["c"])
    assert calls == ["gemini-3.8-flash", "gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"]


def test_chain_stops_at_first_success(monkeypatch):
    calls = []
    def reply(model, system, contents):
        calls.append(model)
        if len(calls) < 3:
            raise RuntimeError("no")
        return '```json\n{"ok": 1}\n```'
    monkeypatch.setattr(llm, "_call", reply)
    assert llm.generate(CHAIN, "s", ["c"]) == ({"ok": 1}, "gemini-3.6-flash")


def test_hung_call_times_out_retries_then_falls_back(monkeypatch):
    import threading
    monkeypatch.setattr(config, "CALL_TIMEOUT", 0.05)
    release, calls = threading.Event(), []
    def reply(model, system, contents):
        calls.append(model)
        if model == "gemini-3.8-flash":
            release.wait(5)   # hangs, like a request that never returns
        return '{"ok": 1}'
    monkeypatch.setattr(llm, "_call", reply)
    data, model = llm.generate(CHAIN, "s", ["c"])
    release.set()
    assert calls == ["gemini-3.8-flash", "gemini-3.8-flash", "gemini-3.6-flash"]
    assert (data, model) == ({"ok": 1}, "gemini-3.6-flash")


def test_real_client_accepts_the_timeout(monkeypatch):
    """Builds the real client and stops before anything is sent."""
    from google import genai
    monkeypatch.setenv("GEMINI_API_KEY", "not-a-real-key")
    from google.genai import types
    client = genai.Client(http_options=types.HttpOptions(timeout=config.CALL_TIMEOUT * 1000))
    assert client is not None


def test_bad_reply_counts_as_a_failure(monkeypatch):
    replies = iter(["not json", '{"good": 1}'])
    monkeypatch.setattr(llm, "_call", lambda *a: next(replies))
    assert llm.generate([("m", 2)], "s", ["c"])[0] == {"good": 1}


# ---------- rules ----------
def test_edition_follows_the_date():
    assert rules.edition_for("2025-06-01") == "3rd_2022"
    assert rules.edition_for("2026-10-01") == "4th_2026"
    assert rules.edition_for("") == "4th_2026"


SECTIONS = [{"id": "36.1", "text": "x"}]


def test_citation_must_be_retrieved():
    good = {"title": "t", "summary": "s", "conditions": [], "citations": ["36.1.2"]}
    rules.check_reply(good, SECTIONS)
    with pytest.raises(ValueError, match="not in the retrieved"):
        rules.check_reply({**good, "citations": ["21.5"]}, SECTIONS)
    with pytest.raises(ValueError):
        rules.check_reply({**good, "citations": []}, SECTIONS)


@pytest.mark.parametrize("written", ["[36.1]", "Law 36.1", "[36.1.2]", "36.1"])
def test_citation_formats_from_real_replies(written):
    reply = {"title": "t", "summary": "s", "conditions": [], "citations": [written]}
    rules.check_reply(reply, SECTIONS)
    assert reply["citations"] == ["36.1"]


def test_explain_caches_and_only_calls_once(monkeypatch, tmp_path):
    monkeypatch.setattr(rules, "CACHE_DIR", str(tmp_path))
    calls = []
    def reply(model, system, contents):
        calls.append(model)
        return json.dumps({"title": "t", "summary": "s", "conditions": ["c"], "citations": ["32.1"]})
    monkeypatch.setattr(llm, "_call", reply)
    first = rules.explain("bowled", "beginner", "4th_2026")
    assert rules.explain("bowled", "beginner", "4th_2026") == first and len(calls) == 1


def test_failed_explanation_shows_official_text_and_is_not_cached(monkeypatch, tmp_path):
    monkeypatch.setattr(rules, "CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(llm, "_call", lambda *a: '{"title": "t", "summary": "s", "conditions": [], "citations": ["99.9"]}')
    out = rules.explain("bowled", "beginner", "4th_2026")
    assert out["source"] == "official text" and "Bowled" in out["summary"]
    assert not list(tmp_path.rglob("*.json"))


# ---------- detection ----------
def test_step_grows_for_long_clips():
    assert detect.choose_step(50) == 2 and detect.choose_step(600) == 5


def test_sheets_cover_all_frames(tmp_path):
    frames = [np.zeros((270, 480, 3), np.uint8) for _ in range(30)]
    idxs, paths = detect.build_sheets(frames, 2, str(tmp_path))
    assert idxs == list(range(0, 30, 2)) and len(paths) == 2


def test_frames_not_on_a_cell_are_dropped():
    data = {"moments": {"release": {"frame": 5, "confidence": 0.9}, "stumps_hit": {"frame": 16, "confidence": 0.9},
                        "bails_off": {"frame": None}}}
    assert list(detect.read_run(data, ["release", "stumps_hit", "bails_off"], [0, 2, 16])) == ["stumps_hit"]


def test_median_uses_a_real_answer():
    runs = [{"stumps_hit": {"frame": f, "confidence": 0.8, "evidence": str(f)}} for f in (16, 18, 28)]
    merged = detect.combine(runs, ["stumps_hit"])
    assert merged["stumps_hit"]["frame"] == 18 and merged["stumps_hit"]["evidence"] == "18"


def test_validation_applies_confidence_order_and_derived():
    merged = {"release": {"frame": 20, "confidence": 0.9, "evidence": ""},
              "stumps_hit": {"frame": 16, "confidence": 0.9, "evidence": ""},
              "bails_off": {"frame": 22, "confidence": 0.1, "evidence": ""}}
    kept, rejected = detect.validate("bowled", merged, 50)
    assert [m["key"] for m in kept] == ["release"]
    assert {r["reason"] for r in rejected} == {"out of time order", "low confidence"}
    merged["release"]["frame"] = 6
    kept, _ = detect.validate("bowled", merged, 50)
    assert [(m["key"], m["frame"]) for m in kept] == [("release", 6), ("bat_miss", 15), ("stumps_hit", 16)]


# ---------- plan ----------
MOMENTS = [{"key": "release", "label": "Ball released", "frame": 6, "timestamp": 0.24, "evidence": "seen"},
           {"key": "stumps_hit", "label": "Ball hits the stumps", "frame": 16, "timestamp": 0.64, "evidence": ""}]
RULE = {"title": "Bowled", "summary": "s", "conditions": ["c"], "citations": ["32.1"]}


def test_llm_can_never_set_a_frame_or_add_a_step(monkeypatch):
    reply = {"headline": "Out", "steps": [{"moment": "release", "title": "T", "caption": "C", "frame": 99},
                                          {"moment": "invented", "title": "X", "caption": "Y", "frame": 1}]}
    monkeypatch.setattr(llm, "_call", lambda *a: json.dumps(reply))
    p = plan.build("bowled", events.from_form("bowled"), RULE, {"moments": MOMENTS}, 25)
    assert [(s["moment"], s["frame"]) for s in p["steps"]] == [("release", 6), ("stumps_hit", 16)]
    assert p["steps"][0]["caption"] == "C" and p["steps"][1]["title"] == "Ball hits the stumps"
    assert all(s["highlight"] is None for s in p["steps"])


@pytest.mark.parametrize("decision,key,word", [("four", "ball_reaches_boundary", "hits or crosses"),
                                               ("six", "ball_clears_boundary", "crosses")])
def test_boundary_caption_is_fixed_wording(monkeypatch, decision, key, word):
    reply = {"steps": [{"moment": key, "title": "T", "caption": "The ball hits the ground before the rope."}]}
    monkeypatch.setattr(llm, "_call", lambda *a: json.dumps(reply))
    moments = [{"key": key, "label": "L", "frame": 10, "timestamp": 0.4, "evidence": ""}]
    caption = plan.build(decision, events.from_form(decision), RULE, {"moments": moments}, 25)["steps"][0]["caption"]
    assert word in caption and "ground" not in caption


def test_plan_survives_llm_failure(monkeypatch):
    def fail(*a):
        raise RuntimeError("no")
    monkeypatch.setattr(llm, "_call", fail)
    p = plan.build("bowled", events.from_form("bowled"), RULE, {"moments": MOMENTS}, 25)
    assert p["caption_source"] == "plain labels" and len(p["steps"]) == 2


def test_no_moments_needs_no_llm_call(monkeypatch):
    def fail(*a):
        raise AssertionError("should not be called")
    monkeypatch.setattr(llm, "_call", fail)
    assert plan.build("bowled", events.from_form("bowled"), RULE, {"moments": []}, 25)["steps"] == []


# ---------- render ----------
def test_cards_and_overlay_keep_the_frame_size():
    long_text = "word " * 120
    assert render.card(640, 360, "Title", long_text, ["a", "b"], "foot").shape == (360, 640, 3)
    frame = np.zeros((360, 640, 3), np.uint8)
    step = {"title": "T", "caption": long_text, "position": 0.5}
    assert render.overlay(frame, step, 0.5, [step]).shape == (360, 640, 3)
    assert render.overlay(frame, None, 0.0, []).shape == (360, 640, 3)


def test_replay_keeps_a_short_lead_in_and_tail():
    plan = {"steps": [{"frame": 200}, {"frame": 300}]}
    assert render.replay_window(plan, 25, 700) == (125, 350)
    assert render.replay_window({"steps": [{"frame": 10}, {"frame": 690}]}, 25, 700) == (0, 699)
    assert render.replay_window({"steps": []}, 25, 700) == (0, 699)


def test_timeline_positions_follow_the_replay_not_the_clip():
    steps = render.timeline({"steps": [{"frame": 125}, {"frame": 350}]}, 125, 350)
    assert [s["position"] for s in steps] == [0, 1]


def test_caption_moves_to_the_top_only_for_a_low_marker():
    low = {"title": "T", "caption": "C", "highlight": {"box": {"bottom": 0.9}}}
    high = {"title": "T", "caption": "C", "highlight": {"box": {"bottom": 0.5}}}
    assert render.under_caption(low) and not render.under_caption(high)
    assert not render.under_caption({"title": "T", "caption": "C", "highlight": None}) and not render.under_caption(None)
    frame = np.zeros((360, 640, 3), np.uint8)
    drawn = render.overlay(frame, low, 0.5, [])
    assert drawn[10, 320].sum() > 0 and drawn[300, 320].sum() == 0


def test_llm_instructions_never_reach_the_screen(tmp_path, monkeypatch):
    import cv2
    src = str(tmp_path / "drawn.avi")
    writer = cv2.VideoWriter(src, cv2.VideoWriter_fourcc(*"MJPG"), 10, (320, 180))
    for _ in range(3):
        writer.write(np.zeros((180, 320, 3), np.uint8))
    writer.release()
    seen, real = [], render.card
    def spy(width, height, title, body, bullets=(), footer=""):
        seen.append(" ".join([title, body, *bullets, footer]))
        return real(width, height, title, body, bullets, footer)
    monkeypatch.setattr(render, "card", spy)
    p = {"label": "Four", "headline": "Out", "steps": [], "rule": {**RULE, "limits": "SECRET INSTRUCTION"}}
    render.render(src, p, {"width": 320, "height": 180, "fps": 10, "fps_rational": "10/1", "frames": 3},
                  str(tmp_path / "out.mp4"))
    assert seen and not any("SECRET" in s for s in seen)


def test_render_makes_a_playable_clip_with_pauses(tmp_path):
    """Uses a short clip of drawn frames made here, so no real video is involved."""
    import cv2
    src = str(tmp_path / "drawn.avi")
    writer = cv2.VideoWriter(src, cv2.VideoWriter_fourcc(*"MJPG"), 10, (320, 180))
    for i in range(10):
        writer.write(np.full((180, 320, 3), i * 20, np.uint8))
    writer.release()
    p = {"label": "Bowled", "headline": "Out", "rule": {**RULE, "limits": ""},
         "steps": [{"moment": "release", "frame": 3, "title": "T", "caption": "C"}]}
    out = str(tmp_path / "output.mp4")
    render.render(src, p, {"width": 320, "height": 180, "fps": 10, "fps_rational": "10/1", "frames": 10}, out)
    info = normalize.probe(out)
    assert normalize.problems(info) == []
    expected = 60 + 30 + 10 * config.SLOWDOWN + 50   # intro + pause + slowed clip + end card
    assert int(info["nb_read_packets"]) == expected


def test_normalize_keeps_a_compliant_file_and_fixes_a_bad_one(tmp_path):
    import cv2
    src = str(tmp_path / "input.avi")
    writer = cv2.VideoWriter(src, cv2.VideoWriter_fourcc(*"MJPG"), 10, (321, 181))
    for i in range(12):
        writer.write(np.full((181, 321, 3), i * 10, np.uint8))
    writer.release()
    meta = normalize.normalize(src, str(tmp_path))
    assert meta["encoded"] and meta["width"] == 320 and meta["height"] == 180 and meta["frames"] == 12
    second = tmp_path / "again"
    second.mkdir()
    meta2 = normalize.normalize(str(tmp_path / "clip.mp4"), str(second))
    assert not meta2["encoded"] and meta2["frames"] == 12


# ---------- web page ----------
@pytest.fixture
def web(monkeypatch, tmp_path):
    import app as server
    monkeypatch.setattr(server.config, "JOBS_DIR", str(tmp_path))
    return server, server.app.test_client()


def test_page_lists_every_decision(web):
    html = web[1].get("/").get_data(as_text=True)
    assert all(f'value="{k}"' in html for k in DECISIONS)


def test_page_offers_football(web):
    from sports.football.decisions import DECISIONS as FOOTBALL
    html = web[1].get("/").get_data(as_text=True)
    assert all(f'value="{k}"' in html for k in FOOTBALL)


def test_football_job_passes_sport_and_time(web, monkeypatch):
    import io, time
    server, client = web
    seen = {}
    def fake(job_dir, params, progress):
        seen.update(params)
        with open(os.path.join(job_dir, "plan.json"), "w") as f:
            json.dump({"steps": []}, f)
    monkeypatch.setattr(server, "run_job", fake)
    client.post("/run", data={"video": (io.BytesIO(b"x"), "a.mp4"), "sport": "football", "period": "2", "minute": "61",
                              "second": "5", "statsbomb": (io.BytesIO(b"[]"), "m.json")})
    for _ in range(50):
        if seen:
            break
        time.sleep(0.02)
    assert (seen["sport"], seen["period"], seen["minute"], seen["second"]) == ("football", 2, 61, 5)


def test_unknown_sport_is_refused(web):
    import io
    r = web[1].post("/run", data={"video": (io.BytesIO(b"x"), "a.mp4"), "sport": "golf", "decision": "six"})
    assert r.status_code == 400


def test_upload_needs_mp4_and_a_decision(web):
    import io
    client = web[1]
    bad = client.post("/run", data={"video": (io.BytesIO(b"x"), "a.mov"), "decision": "bowled"})
    assert bad.status_code == 400
    none = client.post("/run", data={"video": (io.BytesIO(b"x"), "a.mp4")})
    assert none.status_code == 400 and "decision" in none.get_json()["error"]
    no_ball = client.post("/run", data={"video": (io.BytesIO(b"x"), "a.mp4"), "over_ball": "x",
                                        "cricsheet": (io.BytesIO(b"{}"), "m.json")})
    assert no_ball.status_code == 400 and "over.ball" in no_ball.get_json()["error"]


def test_job_runs_and_reports(web, monkeypatch):
    import io, time
    server, client = web
    def fake(job_dir, params, progress):
        progress(2)
        with open(os.path.join(job_dir, "plan.json"), "w") as f:
            json.dump({"steps": []}, f)
    monkeypatch.setattr(server, "run_job", fake)
    job = client.post("/run", data={"video": (io.BytesIO(b"x"), "a.mp4"), "decision": "six"}).get_json()["job"]
    for _ in range(50):
        status = client.get(f"/status/{job}").get_json()
        if status["state"] == "done":
            break
        time.sleep(0.02)
    assert status["state"] == "done" and status["plan"] == {"steps": []}


def test_failed_job_shows_its_error(web, monkeypatch):
    import io, time
    server, client = web
    def fake(job_dir, params, progress):
        raise ValueError("bad clip")
    monkeypatch.setattr(server, "run_job", fake)
    job = client.post("/run", data={"video": (io.BytesIO(b"x"), "a.mp4"), "decision": "six"}).get_json()["job"]
    for _ in range(50):
        status = client.get(f"/status/{job}").get_json()
        if status["state"] == "failed":
            break
        time.sleep(0.02)
    assert status["error"] == "bad clip"


def test_paths_cannot_escape_the_jobs_folder(web):
    assert web[1].get("/video/..%2F..%2Fconfig").status_code == 404
    assert web[1].get("/status/nope").status_code == 404
