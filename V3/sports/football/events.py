"""Builds the event JSON, from one moment of a StatsBomb match file or from the form.
StatsBomb is the prototype's source; a live feed would replace it by writing this same event."""
import json, re
from sports.football.decisions import DECISIONS

WINDOW = 5   # seconds either side of the time given, because broadcast clocks and event data differ
CARDS = {"Yellow Card": "yellow_card", "Second Yellow": "second_yellow", "Red Card": "red_card"}
PASS_RESTARTS = {"Corner": "corner", "Goal Kick": "goal_kick", "Throw-in": "throw_in"}
# StatsBomb records these outcomes, but not these calls, so an event cannot confirm or deny them.
NOT_IN_STATSBOMB = {"goal_disallowed", "var_check", "on_field_review", "ball_out"}


def classify(e):
    """Returns the decision key for one StatsBomb event, or None if it is not a referee decision."""
    kind = e.get("type", {}).get("name")
    if kind == "Shot" and e.get("shot", {}).get("outcome", {}).get("name") == "Goal":
        return "goal"
    if kind == "Offside" or e.get("pass", {}).get("outcome", {}).get("name") == "Pass Offside":
        return "offside"
    if kind == "Bad Behaviour":
        return CARDS.get(e.get("bad_behaviour", {}).get("card", {}).get("name"))
    if kind == "Foul Committed":
        foul = e.get("foul_committed", {})
        card = CARDS.get(foul.get("card", {}).get("name"))
        if card:
            return card
        if foul.get("penalty"):
            return "penalty"
        if foul.get("type", {}).get("name") == "Handball":
            return "handball"
        return "advantage" if foul.get("advantage") else "foul_free_kick"
    if kind == "Pass":
        return PASS_RESTARTS.get(e.get("pass", {}).get("type", {}).get("name"))
    return None


def find_events(match, period, minute, second):
    """Decision events near the time, nearest first."""
    target = minute * 60 + second
    near = [(abs(e["minute"] * 60 + e["second"] - target), e) for e in match
            if e.get("period") == period and "minute" in e and classify(e)]
    return [e for gap, e in sorted(near, key=lambda x: (x[0], x[1].get("index", 0))) if gap <= WINDOW]


def choose_event(found, expected):
    if expected in NOT_IN_STATSBOMB:
        return (found[0] if found else {}), expected
    if not found:
        raise ValueError(f"no referee decision within {WINDOW} seconds of that time")
    if expected:
        for e in found:
            if classify(e) == expected:
                return e, expected
        got = ", ".join(classify(e) for e in found)
        raise ValueError(f"expected {expected}, but StatsBomb shows: {got}. Check the period and time")
    return found[0], classify(found[0])


def from_statsbomb(match, period, minute, second, expected=None, date="", competition=""):
    e, key = choose_event(find_events(match, period, minute, second), expected)
    actors = [{"role": "player", "name": e["player"]["name"]}] if e.get("player") else []
    return make_event(key, actors, "statsbomb", {"format": "", "date": date, "competition": competition},
                      {"period": period, "minute": minute, "second": second,
                       "team": e.get("team", {}).get("name", "")})


def from_source(match, p, expected=None):
    return from_statsbomb(match, p["period"], p["minute"], p["second"], expected, p.get("date", ""))


def from_form(decision, date="", fmt="", notes=""):
    return make_event(decision, [], "manual", {"format": fmt, "date": date, "competition": ""}, {"notes": notes})


def make_event(key, actors, source, context, details):
    event = {"event_id": f"{source}-{key}-{details.get('minute', 'manual')}", "sport": "football",
             "event_type": DECISIONS.get(key, {}).get("group", ""), "subtype": key,
             "outcome": DECISIONS.get(key, {}).get("label", ""), "status": "final",
             "actors": actors, "context": context, "details": details, "source": source}
    validate(event)
    return event


def validate(event):
    if event["subtype"] not in DECISIONS:
        raise ValueError(f"unknown decision: {event['subtype']}")
    date = event["context"].get("date", "")
    if date and not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise ValueError(f"date must be YYYY-MM-DD, got {date!r}")


def load_match(path):
    with open(path, encoding="utf-8") as f:
        match = json.load(f)
    if not isinstance(match, list) or not match or "type" not in match[0]:
        raise ValueError("this is not a StatsBomb events JSON file")
    return match
