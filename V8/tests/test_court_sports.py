"""Every basketball and tennis decision must resolve to rule text and build its prompts. No API calls."""
import io, os, sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app as web_app
from pipeline import rules, verify
import sports

CASES = [("basketball", key) for key in sports.decisions("basketball").DECISIONS]
CASES += [("tennis", key) for key in sports.decisions("tennis").DECISIONS]


def event(sport):
    return {"sport": sport, "actors": [], "context": {}, "details": {}}


@pytest.mark.parametrize("sport,key", CASES)
def test_every_decision_finds_rule_text(sport, key):
    d = sports.decisions(sport).DECISIONS[key]
    book = rules.load_laws(rules.edition_for("", sport), sport)
    for number, title in d["laws"]:
        heads = [rules.heading(t) for t in book[number]["sections"].values()]
        assert title is None or any(h.startswith(title.lower()) for h in heads), (number, title)
    sections = rules.retrieve(key, rules.edition_for("", sport), sport)
    assert sections and all(len(s["text"]) > 80 for s in sections)


@pytest.mark.parametrize("sport,key", CASES)
def test_prompts_build(sport, key):
    catalog = sports.decisions(sport)
    d = catalog.DECISIONS[key]
    keys = [m[0] for m in d["moments"]]
    assert len(keys) == len(set(keys)) and d["label"] and d["signal"] and d["group"] in catalog.GROUP_LABELS
    assert all(k in catalog.detect_prompt(key, event(sport), 2) for k in keys)
    assert d["label"] in catalog.rule_prompt(key, "beginner", [{"id": "1.1", "text": "x"}])
    assert keys[0] in catalog.plan_prompt(key, event(sport), {"summary": "s"}, [{"key": keys[0], "label": "L"}])


@pytest.mark.parametrize("sport", ["basketball", "tennis"])
def test_every_section_id_can_be_cited_and_checked(sport):
    catalog = sports.decisions(sport)
    book = rules.load_laws(rules.edition_for("", sport), sport)
    for rule in book.values():
        for sid in rule["sections"]:
            assert catalog.cite(sid)
            data = {"title": "t", "summary": "s", "conditions": [], "citations": [f"[{sid}]"]}
            rules.check_reply(data, [{"id": sid}])
            assert data["citations"] == [sid]


def test_nba_book_keeps_both_parts_of_rule_12():
    book = rules.load_laws("nba_2026_27", "basketball")
    assert len(book) == 14
    assert list(book["2"]["sections"]) == [f"2.{n}" for n in range(1, 9)]   # a cross-reference is not a heading
    assert not [s for n, rule in book.items() if n != "12" for s in rule["sections"] if int(s.split(".")[1]) > 20]
    assert rules.heading(book["12"]["sections"]["12.5"]).startswith("conduct")
    assert rules.heading(book["12"]["sections"]["12.24"]).startswith("flagrant foul")
    assert "Traveling" in book["10"]["sections"]["10.13"]


def test_nba_citations_use_the_book_numbering():
    cite = sports.decisions("basketball").cite
    assert cite("10.13") == "Rule 10, Section XIII"
    assert cite("12.5") == "Rule 12A, Section V"
    assert cite("12.24") == "Rule 12B, Section IV"


def test_tennis_book_has_all_rules_and_added_parts():
    book = rules.load_laws("rules_2026", "tennis")
    assert list(book)[:31] == [str(n) for n in range(1, 32)]
    assert book["18"]["title"] == "Foot Fault" and "foot" in book["18"]["sections"]["18.1"].lower()
    assert list(book["32"]["sections"]) == ["32.1", "32.2", "32.3", "32.4"]
    assert "Tournament Regulations" not in book["24"]["sections"]["24.1"]


def test_tennis_citations_name_each_source():
    cite = sports.decisions("tennis").cite
    assert (cite("24.1"), cite("32.3"), cite("33.1")) == ("Rule 24", "Code of Conduct 3", "Electronic Line Calling")


def test_box_targets_come_from_the_sport():
    assert verify.target_for("basketball", "referee_signal") == "the referee"
    assert verify.target_for("tennis", "call") == "the chair umpire"
    assert verify.target_for("tennis", "ball_bounce") is None
    assert verify.target_for("cricket", "release") == "the bowler"


@pytest.mark.parametrize("sport", ["basketball", "tennis"])
def test_form_event_needs_a_known_decision(sport):
    events = sports.events(sport)
    key = next(iter(sports.decisions(sport).DECISIONS))
    assert events.from_form(key, "2026-10-06")["sport"] == sport
    with pytest.raises(ValueError):
        events.from_form("no_such_decision")
    with pytest.raises(ValueError):
        events.from_form(key, "yesterday")


def test_page_offers_the_new_sports():
    page = web_app.app.test_client().get("/").get_data(as_text=True)
    assert 'value="basketball"' in page and 'value="tennis"' in page
    assert "Goaltending" in page and "Foot fault" in page and "Choose a decision" in page


def test_tennis_job_starts_from_the_form(monkeypatch):
    seen = {}
    monkeypatch.setattr(web_app, "worker", lambda job_id, job_dir, params: seen.update(params))
    reply = web_app.app.test_client().post("/run", data={"video": (io.BytesIO(b"x"), "a.mp4"), "sport": "tennis",
                                                         "decision": "foot_fault"}, content_type="multipart/form-data")
    assert reply.status_code < 400
    web_app.threading.Event().wait(0.2)
    assert (seen["sport"], seen["decision"]) == ("tennis", "foot_fault")


def test_basketball_job_needs_a_decision():
    reply = web_app.app.test_client().post("/run", data={"video": (io.BytesIO(b"x"), "a.mp4"), "sport": "basketball"},
                                           content_type="multipart/form-data")
    assert reply.status_code == 400
