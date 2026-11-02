"""Markers: choosing what Jev found, and drawing it. No API calls."""
import json, os, sys
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline import render, spotlight
import sports

BOX = {"top": 0.4, "bottom": 0.42, "left": 0.5, "right": 0.52}
PERSON = {"top": 0.2, "bottom": 0.6, "left": 0.4, "right": 0.5}
NO_MARKER = {"cricket": {"umpires_confer", "players_leave", "review_called", "review_graphic", "final_decision"},
             "football": {"final_decision"}, "basketball": {"clock_zero"}, "tennis": {"review_graphic", "clock_zero"}}


@pytest.mark.parametrize("sport", ["cricket", "football", "basketball", "tennis"])
def test_every_moment_has_a_marker_or_is_listed(sport):
    marks, keys = sports.marks(sport).MARKS, set()
    for d in sports.decisions(sport).DECISIONS.values():
        keys |= {m[0] for m in d["moments"]} | set(d.get("derived", {}))
    assert keys - set(marks) == NO_MARKER[sport]
    assert all(option[0] in ("ring", "arrow", "feet") for options in marks.values() for option in options)


def test_first_sure_option_wins(monkeypatch):
    replies = {"ball": (BOX, 0.2), "bowler": (PERSON, 0.9)}
    monkeypatch.setattr(spotlight, "ask", lambda frame, target: replies[target])
    chosen, tries = spotlight.choose(None, [("ring", "ball"), ("feet", "bowler")])
    assert chosen["target"] == "bowler" and len(tries) == 2


def test_an_option_can_need_a_higher_score(monkeypatch):
    monkeypatch.setattr(spotlight, "ask", lambda frame, target: (BOX if target == "card" else PERSON, 0.6))
    chosen, _ = spotlight.choose(None, [("ring", "card", 0.7), ("feet", "referee")])
    assert chosen["target"] == "referee"


def test_nothing_sure_means_no_marker(monkeypatch):
    monkeypatch.setattr(spotlight, "ask", lambda frame, target: (BOX, 0.1))
    assert spotlight.choose(None, [("ring", "ball")])[0] is None


def test_ring_refuses_a_big_box_and_jev_failure():
    assert not spotlight.usable(PERSON, 0.9, "ring")
    assert spotlight.usable(PERSON, 0.9, "feet")
    assert not spotlight.usable(None, 0.0, "feet")
    assert not spotlight.usable({**BOX, "left": 0.9}, 0.9, "ring")


def test_no_key_means_no_call(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert spotlight.ask(None, "ball") == (None, 0.0)


def test_mark_fills_steps_and_logs(tmp_path, monkeypatch):
    monkeypatch.setattr(spotlight, "read_frames", lambda clip, wanted: {f: None for f in wanted})
    monkeypatch.setattr(spotlight, "ask", lambda frame, target: (PERSON, 0.9))
    plan = {"steps": [{"moment": "umpire_signal", "frame": 5, "highlight": None},
                      {"moment": "review_graphic", "frame": 6, "highlight": None}]}
    spotlight.mark("clip", plan, "cricket", str(tmp_path))
    assert plan["steps"][0]["highlight"]["shape"] == "feet" and plan["steps"][1]["highlight"] is None
    assert "umpire_signal" in json.load(open(tmp_path / "markers.json", encoding="utf-8"))


def test_a_box_wider_than_a_person_gets_no_feet_marker():
    empty_grass = {"top": 0.48, "bottom": 0.62, "left": 0.48, "right": 0.64}
    assert not spotlight.usable(empty_grass, 0.9, "feet")
    assert spotlight.usable(empty_grass, 0.9, "arrow")


def test_a_target_can_quote_the_moments_evidence(monkeypatch):
    asked = []
    monkeypatch.setattr(spotlight, "ask", lambda frame, target: (asked.append(target), (PERSON, 0.9))[1])
    spotlight.choose(None, [("feet", "the player described here: {evidence}")], "claret shirt, far right")
    assert asked == ["the player described here: claret shirt, far right"]


@pytest.mark.parametrize("shape,box", [("ring", BOX), ("feet", PERSON), ("arrow", PERSON), ("arrow", {**PERSON, "top": 0.02}),
                                       ("feet", {**PERSON, "bottom": 0.99}), ("feet", {**PERSON, "top": 0.05, "bottom": 0.9, "left": 0.9, "right": 1.0})])
def test_each_shape_draws_without_changing_the_source(shape, box):
    frame = np.zeros((360, 640, 3), np.uint8)
    drawn = render.marker(frame, {"shape": shape, "box": box})
    assert frame.sum() == 0 and drawn.sum() > 0
