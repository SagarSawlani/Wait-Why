"""Builds the event JSON, either from one ball of a Cricsheet match file or from the form.
Cricsheet is the prototype's source; a live feed would replace it by writing this same event."""
import json, re
from decisions import DECISIONS

WICKET_KINDS = {"bowled": "bowled", "caught": "caught", "caught and bowled": "caught_and_bowled", "lbw": "lbw",
                "run out": "run_out", "stumped": "stumped", "hit wicket": "hit_wicket",
                "hit the ball twice": "hit_ball_twice", "obstructing the field": "obstructing_the_field",
                "handled the ball": "obstructing_the_field", "timed out": "timed_out"}
# Cricsheet records the score, not these calls, so such a ball cannot confirm or deny them.
NOT_IN_CRICSHEET = {"not_out_appeal", "short_run", "dead_ball", "fitness_for_play"}
OVER_BALL_RE = re.compile(r"^\d{1,3}\.\d{1,2}$")


def classify(ball):
    """Returns the decision key for one Cricsheet delivery, or None if the umpire made no decision."""
    wickets = ball.get("wickets") or []
    if wickets:
        return WICKET_KINDS.get(wickets[0].get("kind"))
    extras, runs = ball.get("extras") or {}, ball.get("runs") or {}
    if "wides" in extras:
        return "wide"
    if "noballs" in extras:
        return "no_ball_other"
    if "penalty" in extras:
        return "penalty_runs"
    if not runs.get("non_boundary"):
        if runs.get("batter") == 6:
            return "six"
        if runs.get("batter") == 4:
            return "four"
    if "byes" in extras:
        return "bye"
    if "legbyes" in extras:
        return "leg_bye"
    return "drs_review" if ball.get("review") else None


def find_balls(match, innings, over_ball):
    """over_ball is the scorecard value, like 12.3. A wide or no-ball shares its value with the
    ball bowled again, so this returns a list."""
    if not OVER_BALL_RE.match(str(over_ball)):
        raise ValueError(f"over.ball must look like 12.3, got {over_ball!r}")
    all_innings = match.get("innings", [])
    if not 1 <= innings <= len(all_innings):
        raise ValueError(f"this match has {len(all_innings)} innings, not {innings}")
    over_num = int(str(over_ball).split(".")[0])
    for over in all_innings[innings - 1]["overs"]:
        if over["over"] == over_num:
            found = [b for b in over["deliveries"] if b.get("actual_delivery") == str(over_ball)]
            if found:
                return found
    raise ValueError(f"ball {over_ball} not found in innings {innings}")


def choose_ball(balls, expected):
    """With an expected decision, the ball must match it, so a wrong over number stops the run."""
    keyed = [(b, classify(b)) for b in balls]
    if expected in NOT_IN_CRICSHEET:
        return balls[-1], expected
    if expected == "drs_review":
        for ball in balls:
            if ball.get("review"):
                return ball, expected
    if expected:
        for ball, key in keyed:
            if key == expected or (expected.startswith("no_ball") and key == "no_ball_other"):
                return ball, expected
        got = ", ".join(str(k) for _, k in keyed)
        raise ValueError(f"expected {expected}, but Cricsheet shows: {got}. Check the innings and over.ball")
    decided = [(b, k) for b, k in keyed if k]
    if not decided:
        raise ValueError("this ball has no umpire decision in Cricsheet")
    return decided[-1]


def from_cricsheet(match, innings, over_ball, expected=None):
    ball, key = choose_ball(find_balls(match, innings, over_ball), expected)
    info = match.get("info", {})
    wickets = ball.get("wickets") or []
    actors = [{"role": "batter", "name": ball.get("batter")}, {"role": "bowler", "name": ball.get("bowler")}]
    if wickets:
        actors.append({"role": "dismissed", "name": wickets[0].get("player_out")})
        actors += [{"role": "fielder", "name": f["name"]} for f in wickets[0].get("fielders", []) if f.get("name")]
    dates = info.get("dates") or [""]
    return make_event(key, actors, status="final", source="cricsheet",
                      context={"format": info.get("match_type", ""), "date": dates[0],
                               "competition": (info.get("event") or {}).get("name", "")},
                      details={"innings": innings, "over_ball": str(over_ball), "runs": ball.get("runs", {}),
                               "extras": ball.get("extras", {}), "review": ball.get("review", {}),
                               "teams": info.get("teams", [])})


def from_form(decision, date="", fmt="", notes=""):
    return make_event(decision, [], status="final", source="manual",
                      context={"format": fmt, "date": date, "competition": ""}, details={"notes": notes})


def make_event(key, actors, status, source, context, details):
    event = {"event_id": f"{source}-{key}-{details.get('over_ball', 'manual')}", "sport": "cricket",
             "event_type": DECISIONS.get(key, {}).get("group", ""), "subtype": key,
             "outcome": DECISIONS.get(key, {}).get("label", ""), "status": status,
             "actors": actors, "context": context, "details": details, "source": source}
    validate(event)
    return event


def validate(event):
    missing = [k for k in ("event_id", "sport", "event_type", "subtype", "outcome", "status",
                           "actors", "context", "details", "source") if k not in event]
    if missing:
        raise ValueError(f"event is missing {missing}")
    if event["subtype"] not in DECISIONS:
        raise ValueError(f"unknown decision: {event['subtype']}")
    date = event["context"].get("date", "")
    if date and not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise ValueError(f"date must be YYYY-MM-DD, got {date!r}")


def load_match(path):
    with open(path, encoding="utf-8") as f:
        match = json.load(f)
    if "innings" not in match or "info" not in match:
        raise ValueError("this is not a Cricsheet match JSON file")
    return match
