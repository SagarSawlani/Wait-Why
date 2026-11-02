"""Every tennis decision the system knows. Same entry format as sports/cricket/decisions.py.
To add a decision, add one entry to DECISIONS. Prompts come from sports/shared.py.
Many tennis calls are spoken or electronic, so a visible call is often missing from a clip."""
from sports import shared

RULEBOOK = "Rules of Tennis 2026"

SERVE = ("serve_contact", "Ball is struck", "the frame in which the server's racket hits the ball, at full stretch with the ball above her or his head. Once the ball has left the racket and is travelling down the court, you are already too late")
BOUNCE = ("ball_bounce", "Ball lands", "the first frame in which the ball touches the court. Follow the ball frame by frame from the racket: a serve must cross the net before it can land, then lands in well under a second, and you see it change from a fast streak to a slower dot as it bounces. A ball on the server's side of the net has not landed. A ball rolling slowly, or already behind the far baseline, has landed long before, so go back to the first touch. Answer only if this is visible")
CALL = ("call", "The call", "the first frame in which a line umpire, the chair umpire or an on-screen graphic is clearly shown giving the call. A call that can only be heard does not count, so set this to null if it is not shown")
SHOT = ("shot", "The shot", "the frame in which the player's racket hits the ball")
LINE_LIMIT = "Tennis balls are small and fast, so do not claim the exact gap from the line unless an electronic review graphic shows it."

DECISIONS = {
    # ---------- serving ----------
    "service_fault": {
        "label": "Service fault", "group": "serve", "signal": "a line umpire or the chair umpire calls fault, or a line umpire points out",
        "laws": [("19", None), ("17", None), ("16", None)],
        "moments": [SERVE, BOUNCE, CALL],
        "watch": "Leave ball_bounce as null if the landing point cannot be seen. Evidence says only that the ball hits the court, never whether it was in or out.",
        "limits": LINE_LIMIT + " The official called a fault, so never say or suggest the serve landed in. Do not say which box or line it hit; say the official judged the serve a fault.",
    },
    "foot_fault": {
        "label": "Foot fault", "group": "serve", "signal": "a line umpire calls foot fault",
        "laws": [("18", None)],
        "moments": [("feet_at_contact", "Feet at the serve", "the frame showing the server's feet near the baseline as the racket meets the ball"), SERVE, CALL],
        "watch": "Replays count here, because the feet are often only clear in one.",
        "limits": "Do not claim the foot touched the line unless the frame clearly shows it.",
    },
    "double_fault": {
        "label": "Double fault", "group": "serve", "signal": "the second serve is called a fault and the point goes to the receiver",
        "laws": [("20", None), ("24", None)],
        "moments": [SERVE, BOUNCE, CALL],
        "watch": "Use the second serve. If the clip shows both serves, serve_contact is the later one.",
        "limits": LINE_LIMIT,
    },
    "service_let": {
        "label": "Service let", "group": "serve", "signal": "the chair umpire calls let and the serve is played again",
        "laws": [("22", None)],
        "moments": [SERVE, ("ball_hits_net", "Ball clips the net", "the frame in which the ball touches the net, strap or band"), BOUNCE, CALL],
        "limits": "A net touch is often only heard. Do not claim it unless the frame shows it.",
    },
    # ---------- line calls ----------
    "ball_out": {
        "label": "Ball out", "group": "lines", "signal": "a line umpire calls out and points out with an arm",
        "laws": [("12", None), ("24", None)],
        "moments": [("shot", "The last shot", "the frame in which a player's racket hits the final shot of the point, the one the opponent never returns. Never a serve or earlier stroke that was played back"),
                    ("ball_bounce", "Ball lands", "the first frame in which that final shot touches the ground, only if this is visible. It comes after the shot, usually within a second or two"),
                    CALL],
        "watch": "The clip may show a whole rally. Work backwards from the end: find where the players stop playing the ball, then the last racket contact before that. Every earlier shot was returned, so it did not go out. Replays and review graphics count here. Leave ball_bounce as null if the landing point cannot be seen.",
        "limits": LINE_LIMIT,
    },
    "ball_in": {
        "label": "Ball in (touches the line)", "group": "lines", "signal": "a line umpire shows flat hands, palms down, or makes no call",
        "laws": [("12", None), ("25", None)],
        "moments": [SHOT, BOUNCE, CALL],
        "watch": "Replays and review graphics count here. Leave ball_bounce as null if the landing point cannot be seen.",
        "limits": LINE_LIMIT,
    },
    "electronic_review": {
        "label": "Electronic line review", "group": "lines", "signal": "the player challenges, or the chair umpire reviews, and a graphic shows the result",
        "laws": [("33", None)],
        "moments": [BOUNCE, ("review_graphic", "Review graphic", "the first frame in which the electronic review graphic shows where the ball landed")],
        "watch": "Replays and graphics count here. The graphic is the best evidence.",
    },
    # ---------- losing the point ----------
    "net_touch": {
        "label": "Player touches the net", "group": "point", "signal": "the chair umpire calls the point against the player",
        "laws": [("24", None)],
        "moments": [("net_contact", "Player touches the net", "the frame in which the player, their racket or their clothing touches the net"), CALL],
        "watch": "Replays count here.",
    },
    "double_bounce": {
        "label": "Double bounce (not up)", "group": "point", "signal": "the chair umpire calls not up",
        "laws": [("24", None)],
        "moments": [("first_bounce", "First bounce", "the frame in which the ball first lands on the player's side, if visible"),
                    ("second_bounce", "Second bounce", "the frame in which the ball lands a second time before the player hits it, if visible"), CALL],
        "watch": "Replays count here, because they are often the only clear view.",
    },
    "double_hit": {
        "label": "Double hit or carry", "group": "point", "signal": "the chair umpire calls the point against the player",
        "laws": [("24", None)],
        "moments": [SHOT, CALL],
        "watch": "Replays count here.",
        "limits": "Whether the player made one deliberate swing is the umpire's judgement.",
    },
    "ball_hits_player": {
        "label": "Ball hits a player", "group": "point", "signal": "the chair umpire calls the point against the player who was hit",
        "laws": [("24", None)],
        "moments": [SHOT, ("ball_hits_body", "Ball hits the player", "the frame in which the ball touches the player or their clothing"), CALL],
        "limits": "Do not claim the ball touched the player unless the frame shows it.",
    },
    "hindrance": {
        "label": "Hindrance", "group": "point", "signal": "the chair umpire calls hindrance",
        "laws": [("26", None), ("23", None)],
        "moments": [("incident", "The incident", "the frame showing what interrupted the player, if visible"), CALL],
        "limits": "Whether the hindrance was deliberate is the umpire's judgement.",
    },
    # ---------- conduct ----------
    "time_violation": {
        "label": "Time violation", "group": "conduct", "signal": "the chair umpire announces a time violation, often with a graphic",
        "laws": [("32", "Time violations"), ("21", None), ("29", None)],
        "moments": [("clock_zero", "Serve clock runs out", "the first frame in which an on-court or on-screen clock shows 0, if shown"), CALL],
        "limits": "The penalty depends on the competition, so do not state it unless the clip shows it.",
    },
    "code_violation": {
        "label": "Code violation", "group": "conduct", "signal": "the chair umpire announces a code violation, often with a graphic",
        "laws": [("32", "Violations of the Code of Conduct"), ("32", "The Point Penalty Schedule")],
        "moments": [("incident", "The incident", "the frame showing the action that led to the call, if visible"), CALL],
        "limits": "The reason may not be visible. Do not name an offence unless the clip shows it.",
    },
}

GROUP_LABELS = {"serve": "Serving", "lines": "Line calls", "point": "Losing the point", "conduct": "Conduct"}

# What Jev should box for a moment. A moment left out gets no box: the ball is too small to box.
BOX_TARGETS = {"call": "the chair umpire", "serve_contact": "the player serving", "shot": "the player hitting the ball",
               "feet_at_contact": "the player serving", "net_contact": "the net", "ball_hits_net": "the net",
               "incident": "the player"}


def cite(section):
    """Rule 24 is stored as 24.1, and the two added parts are 32 and 33 (see sports/tennis/laws.py)."""
    rule, number = str(section).split(".")
    if rule == "32":
        return f"Code of Conduct {number}"
    return "Electronic Line Calling" if rule == "33" else f"Rule {rule}"


DETECT_SYSTEM, LEVELS, RULE_SYSTEM, PLAN_SYSTEM, detect_prompt, rule_prompt, plan_prompt = shared.prompts(DECISIONS, "tennis", "a tennis official")
