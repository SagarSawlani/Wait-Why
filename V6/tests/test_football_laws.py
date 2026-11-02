"""Checks the parsed IFAB Laws. No API calls."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline import rules
from sports.football import laws

BOOK = rules.load_laws("2026_27", "football")


def test_all_laws_and_var_present():
    assert sorted(map(int, BOOK)) == list(range(1, 19))


def test_key_sections_are_real_text():
    assert "Offside offence" in BOOK["11"]["sections"]["11.2"]
    assert "Goal scored" in BOOK["10"]["sections"]["10.1"]
    assert "The Players" == BOOK["3"]["title"]
    assert "Number of players" in BOOK["3"]["sections"]["3.1"]
    assert "ball" in BOOK["2"]["text"].lower() and "substitution" not in BOOK["2"]["text"].lower()


def test_var_protocol_stops_at_its_end():
    assert "FIFA Quality" not in BOOK["18"]["text"] and "Law changes" not in BOOK["18"]["text"]
    assert "review" in BOOK["18"]["text"]


def test_edition_routing():
    assert rules.edition_for("2026-08-01", "football") == "2026_27"


def test_side_marker_starts_a_law():
    pages = [["Laws of the Game 2026/27 | Law 1 | One", "1. First", "text", "Law", "1", "One"],
             ["1. Second", "more", "Law", "2", "Two"]]
    parsed = laws.parse_pages(pages)
    assert parsed["2"]["title"] == "Two" and "2.1" in parsed["2"]["sections"]
