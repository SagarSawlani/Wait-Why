"""Reads SoccerNet Labels-caption comments as football events. No API calls."""
import json, os, sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sports.football import events

MATCH = {"referee": "Martin Atkinson", "gameDate": "21/02/2015 - 18:00", "gameHomeTeam": "Chelsea", "gameAwayTeam": "Burnley",
         "annotations": [
             {"gameTime": "2 - 25:18", "label": "y-card", "description": "Branislav Ivanovic (Chelsea) gets a yellow."},
             {"gameTime": "2 - 24:33", "label": "r-card", "description": "Nemanja Matic (Chelsea) receives a red card."},
             {"gameTime": "2 - 24:20", "label": "", "description": "No label here."},
             {"gameTime": "1 - 24:33", "label": "corner", "description": "Corner kick."}]}


def source(period=2, minute=24, second=33):
    return {"period": period, "minute": minute, "second": second}


def test_nearest_comment_in_the_half_is_used():
    e = events.from_source(MATCH, source())
    assert (e["subtype"], e["source"], e["context"]["date"]) == ("red_card", "soccernet", "2015-02-21")
    assert e["actors"] == [{"role": "player", "name": "Nemanja Matic"}, {"role": "referee", "name": "Martin Atkinson"}]
    assert e["details"]["notes"] == "Nemanja Matic (Chelsea) receives a red card."


def test_referee_list_in_real_files_is_read():
    e = events.from_source({**MATCH, "referee": ["Atkinson M."]}, source())
    assert e["actors"][1] == {"role": "referee", "name": "Atkinson M."}


def test_half_is_respected():
    assert events.from_source(MATCH, source(period=1))["subtype"] == "corner"


def test_expected_decision_picks_the_matching_comment():
    assert events.from_source(MATCH, source(second=50), "yellow_card")["subtype"] == "yellow_card"
    with pytest.raises(ValueError, match="expected goal"):
        events.from_source(MATCH, source(), "goal")


def test_nothing_nearby_stops_the_run():
    with pytest.raises(ValueError, match="no labelled comment"):
        events.from_source(MATCH, source(minute=5))


def test_load_match_accepts_both_formats(tmp_path):
    p = tmp_path / "labels.json"
    p.write_text(json.dumps(MATCH), encoding="utf-8")
    assert events.load_match(str(p))["referee"] == "Martin Atkinson"
