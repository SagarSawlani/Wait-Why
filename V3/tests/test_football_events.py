"""StatsBomb adapter. Fixtures copy the real file's shape. No API calls."""
import json, os, sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline.run import read_event
from sports.football import events


def ev(name, minute, second=0, period=1, **extra):
    return {"index": minute * 100 + second, "period": period, "minute": minute, "second": second,
            "type": {"name": name}, "team": {"name": "X"}, "player": {"name": "P"}, **extra}


GOAL = ev("Shot", 22, 24, shot={"outcome": {"name": "Goal"}})
PEN = ev("Foul Committed", 21, 0, foul_committed={"penalty": True})
YELLOW = ev("Bad Behaviour", 94, 35, 2, bad_behaviour={"card": {"name": "Yellow Card"}})
MATCH = [ev("Half Start", 0), PEN, GOAL, YELLOW, ev("Offside", 29, 6),
         ev("Pass", 30, **{"pass": {"type": {"name": "Corner"}}}),
         ev("Pass", 31, **{"pass": {"outcome": {"name": "Pass Offside"}}}), ev("Pass", 32, **{"pass": {}})]


@pytest.mark.parametrize("e,key", [
    (GOAL, "goal"), (PEN, "penalty"), (YELLOW, "yellow_card"), (ev("Offside", 1), "offside"),
    (ev("Foul Committed", 1), "foul_free_kick"), (ev("Foul Committed", 1, foul_committed={"advantage": True}), "advantage"),
    (ev("Foul Committed", 1, foul_committed={"type": {"name": "Handball"}}), "handball"),
    (ev("Foul Committed", 1, foul_committed={"card": {"name": "Red Card"}}), "red_card"),
    (ev("Bad Behaviour", 1, bad_behaviour={"card": {"name": "Second Yellow"}}), "second_yellow"),
    (ev("Pass", 1, **{"pass": {"type": {"name": "Throw-in"}}}), "throw_in"),
    (ev("Shot", 1, shot={"outcome": {"name": "Saved"}}), None), (ev("Carry", 1), None)])
def test_classify(e, key):
    assert events.classify(e) == key


def test_finds_nearest_within_window():
    e = events.from_statsbomb(MATCH, 1, 22, 21)
    assert e["subtype"] == "goal" and e["sport"] == "football" and e["actors"][0]["name"] == "P"


def test_period_matters():
    with pytest.raises(ValueError, match="no referee decision"):
        events.from_statsbomb(MATCH, 1, 94, 35)
    assert events.from_statsbomb(MATCH, 2, 94, 35)["subtype"] == "yellow_card"


def test_wrong_decision_stops_the_run():
    with pytest.raises(ValueError, match="expected penalty"):
        events.from_statsbomb(MATCH, 1, 22, 24, "penalty")


def test_uncheckable_decision_is_accepted():
    assert events.from_statsbomb(MATCH, 1, 22, 24, "goal_disallowed")["subtype"] == "goal_disallowed"
    assert events.from_statsbomb(MATCH, 1, 50, 0, "var_check")["subtype"] == "var_check"


def test_plan_uses_football_rulebook_names(monkeypatch):
    from pipeline import llm, plan
    monkeypatch.setattr(llm, "_call", lambda *a: "{}")
    rule = {"title": "t", "summary": "s", "citations": ["18.1", "18.2", "5.4"]}
    p = plan.build("var_check", events.from_form("var_check"), rule, {"moments": []}, 25)
    assert p["rulebook"] == "Laws of the Game" and p["rule"]["citations"] == ["VAR protocol", "5.4"]


def test_rejects_other_files(tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"innings": []}))
    with pytest.raises(ValueError, match="not a StatsBomb"):
        events.load_match(str(p))


def test_run_reads_football(tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps(MATCH))
    params = {"sport": "football", "match_path": str(p), "period": 1, "minute": 22, "second": 24}
    assert read_event(params)["subtype"] == "goal"
    assert read_event({"sport": "football", "decision": "offside"})["source"] == "manual"
