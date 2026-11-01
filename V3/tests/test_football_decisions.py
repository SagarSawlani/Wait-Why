"""Every football decision must resolve to Law text and build its prompts. No API calls."""
import os, sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline import rules
from sports.football.decisions import DECISIONS, detect_prompt, plan_prompt, rule_prompt

EVENT = {"sport": "football", "actors": [], "context": {}, "details": {}}


@pytest.mark.parametrize("key", list(DECISIONS))
def test_every_title_finds_a_section(key):
    book = rules.load_laws("2026_27", "football")
    for number, title in DECISIONS[key]["laws"]:
        heads = [rules.heading(t) for t in book[number]["sections"].values()]
        assert any(h.startswith(title.lower()) for h in heads), (number, title)


@pytest.mark.parametrize("key", list(DECISIONS))
def test_prompts_build(key):
    d = DECISIONS[key]
    keys = [m[0] for m in d["moments"]]
    assert len(keys) == len(set(keys)) and d["label"] and d["signal"]
    assert all(k in detect_prompt(key, EVENT, 2) for k in keys)
    assert d["label"] in rule_prompt(key, "beginner", [{"id": "1.1", "text": "x"}])
    assert keys[0] in plan_prompt(key, EVENT, {"summary": "s"}, [{"key": keys[0], "label": "L"}])
