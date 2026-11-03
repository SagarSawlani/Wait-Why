"""Every basketball decision the system knows. Same entry format as sports/cricket/decisions.py.
To add a decision, add one entry to DECISIONS. Prompts come from sports/shared.py."""
from sports import shared

RULEBOOK = "NBA Official Playing Rules 2026-27"
ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII"]

SHOT = ("shot_release", "Shot released", "the first frame in which the ball has left the shooter's hand")
SIGNAL = ("referee_signal", "Referee's signal", "the first frame in which a referee is visible and clearly making the signal. Players raising their arms are not the referee, and if a referee is not shown making it, set this to null")
CONTACT = ("contact", "The contact", "the frame showing the contact that led to the call")
GATHER = ("gather", "Player gathers the ball", "the first frame in which the player has control of the ball with both hands or stops dribbling")
TOUCH = ("ball_touched", "Ball touched", "the frame in which a defender or attacker touches the ball near the basket")

DECISIONS = {
    # ---------- ball handling ----------
    "traveling": {
        "label": "Traveling", "group": "ball_handling", "signal": "the referee rolls the fists around each other",
        "laws": [("10", "Traveling"), ("4", "Traveling"), ("4", "The Gather")],
        "moments": [GATHER, ("extra_step", "The extra step", "the first frame in which the player has clearly taken a step beyond what the rule allows"), SIGNAL],
        "watch": "Replays count here, because they often show the feet better.",
        "limits": "Do not count steps or name the pivot foot unless the feet are clearly visible.",
    },
    "double_dribble": {
        "label": "Double dribble", "group": "ball_handling", "signal": "the referee moves both hands up and down, palms down",
        "laws": [("10", "Dribble"), ("4", "Dribble")],
        "moments": [("dribble_ends", "Dribble ends", "the first frame in which the player holds the ball in one or both hands"),
                    ("dribble_restarts", "Dribble restarts", "the first frame in which the player dribbles the ball again"), SIGNAL],
    },
    "out_of_bounds": {
        "label": "Out of bounds", "group": "ball_handling", "signal": "the referee points in the direction of the team that gets the ball",
        "laws": [("10", "Out-of-Bounds"), ("8", "Player"), ("8", "Ball")],
        "moments": [("last_touch", "Last touch", "the frame in which a player last touches the ball before it goes out"),
                    ("ball_out", "Ball goes out", "the first frame in which the ball or the player holding it is on or over the boundary line"), SIGNAL],
        "watch": "Replays count here.",
        "limits": "Do not claim who touched the ball last unless the frame clearly shows it.",
    },
    "backcourt": {
        "label": "Backcourt violation", "group": "ball_handling", "signal": "the referee points to the frontcourt, then waves the ball the other way",
        "laws": [("10", "Ball in Backcourt"), ("4", "Frontcourt/Backcourt")],
        "moments": [("ball_in_frontcourt", "Ball in the frontcourt", "the first frame in which the ball and the player with it are clearly past the midcourt line"),
                    ("ball_back", "Ball goes back", "the first frame in which the offensive team touches the ball in the backcourt"), SIGNAL],
        "limits": "Do not say which player touched it last unless the frame clearly shows it.",
    },
    "held_ball": {
        "label": "Held ball (jump ball)", "group": "ball_handling", "signal": "the referee raises both thumbs",
        "laws": [("4", "Held Ball"), ("6", "Other Jump Balls")],
        "moments": [("both_hold", "Both players hold the ball", "the first frame in which players from both teams have their hands firmly on the ball"), SIGNAL],
    },
    # ---------- clock ----------
    "shot_clock": {
        "label": "Shot clock violation", "group": "clock", "signal": "the referee taps the head, with a raised hand",
        "laws": [("7", "Definition"), ("7", "Starting and Stopping"), ("7", "Putting Ball In Play After Violation")],
        "moments": [("clock_zero", "Clock reaches zero", "the first frame in which the on-screen shot clock shows 0"),
                    SHOT, SIGNAL],
        "watch": "Use the on-screen shot clock graphic if it is shown. shot_release may come before or after the clock reaches zero, so it may be left out if it is not clear.",
        "limits": "Do not claim the ball was or was not released in time unless the clock and the ball are both visible.",
    },
    "eight_second": {
        "label": "Eight-second violation", "group": "clock", "signal": "the referee shows eight fingers",
        "laws": [("10", "Eight-Second Rule")],
        "moments": [("backcourt_control", "Team gets the ball", "the first frame in which the offensive team has control of the ball in the backcourt"), SIGNAL],
    },
    "offensive_three_seconds": {
        "label": "Three seconds (offense)", "group": "clock", "signal": "the referee holds up three fingers",
        "laws": [("10", "Offensive Three-Second Rule")],
        "moments": [("in_the_lane", "Player in the lane", "the first frame in which the offensive player is clearly standing in the painted lane"), SIGNAL],
        "limits": "The count is the referee's. Do not state exact time in the lane.",
    },
    "defensive_three_seconds": {
        "label": "Three seconds (defense)", "group": "clock", "signal": "the referee holds up three fingers",
        "laws": [("10", "Defensive Three-Second Rule")],
        "moments": [("in_the_lane", "Player in the lane", "the first frame in which the defensive player is clearly standing in the painted lane"), SIGNAL],
        "limits": "The count and whether the defender was actively guarding are the referee's judgement.",
    },
    "five_second_inbound": {
        "label": "Five seconds to inbound", "group": "clock", "signal": "the referee shows five fingers",
        "laws": [("10", "Thrower-in")],
        "moments": [("ball_handed", "Thrower has the ball", "the first frame in which the player out of bounds has the ball"), SIGNAL],
    },
    # ---------- basket ----------
    "goaltending": {
        "label": "Goaltending", "group": "basket", "signal": "the referee points to the basket and counts the shot",
        "laws": [("11", None)],
        "moments": [SHOT, TOUCH, SIGNAL],
        "watch": "Replays count here, because they are often the only clear view.",
        "limits": "Whether the ball was on its way down, or above the rim, is what the referee had to judge unless a replay clearly shows it.",
    },
    "basket_interference": {
        "label": "Basket interference", "group": "basket", "signal": "the referee points to the basket, then signals the result",
        "laws": [("11", None)],
        "moments": [SHOT, ("ball_touched", "Ball, rim or net touched", "the frame in which a player touches the ball, rim or net while the ball is on or in the basket"), SIGNAL],
        "watch": "Replays count here, because they are often the only clear view.",
    },
    "three_pointer": {
        "label": "Three-point basket", "group": "basket", "signal": "the referee raises both arms",
        "laws": [("5", "Scoring")],
        "moments": [("feet_set", "Feet at the line", "the last frame before the shooter leaves the floor, showing the feet near the three-point line"),
                    SHOT, ("ball_through", "Ball goes through", "the first frame in which the ball is through the net"), SIGNAL],
        "limits": "Do not claim the feet were behind the line unless the frame clearly shows it.",
    },
    # ---------- fouls ----------
    "blocking_foul": {
        "label": "Blocking foul", "group": "fouls", "signal": "the referee puts both hands on the hips",
        "laws": [("12", "Types"), ("4", "Fouls")],
        "moments": [CONTACT, SIGNAL],
        "watch": "Replays count here.",
        "limits": "Whether the defender had a legal position is the referee's judgement.",
    },
    "charging": {
        "label": "Charging (offensive foul)", "group": "fouls", "signal": "the referee puts one hand behind the head and points the other way",
        "laws": [("12", "Offensive Fouls"), ("12", "Types")],
        "moments": [("defender_set", "Defender in position", "the last frame before the contact, showing where the defender stands"), CONTACT, SIGNAL],
        "watch": "Replays count here.",
        "limits": "Whether the defender was set in time is the referee's judgement.",
    },
    "shooting_foul": {
        "label": "Shooting foul", "group": "fouls", "signal": "the referee strikes the wrist, then shows the free throws with raised fingers",
        "laws": [("12", "Types"), ("12", "Free Throw Penalty Situations")],
        "moments": [CONTACT, SHOT, SIGNAL],
        "watch": "contact and shot_release may come in either order. Report each frame, and leave one null if it is not clear.",
        "limits": "Do not claim the number of free throws unless the signal or a graphic shows it.",
    },
    "loose_ball_foul": {
        "label": "Loose ball foul", "group": "fouls", "signal": "the referee raises a fist, then points the direction",
        "laws": [("12", "Loose Ball Fouls")],
        "moments": [CONTACT, SIGNAL],
    },
    "flagrant_foul": {
        "label": "Flagrant foul", "group": "fouls", "signal": "the referee crosses the arms above the head or holds a wrist above the head",
        "laws": [("12", "Flagrant Foul")],
        "moments": [CONTACT, SIGNAL],
        "watch": "Replays count here, because the call usually follows a review.",
        "limits": "Whether the contact was unnecessary or excessive is the referee's judgement.",
    },
    "technical_foul": {
        "label": "Technical foul", "group": "fouls", "signal": "the referee makes a T with both hands",
        "laws": [("12", "Conduct")],
        "moments": [("incident", "The incident", "the frame showing the action that led to the call, if visible"), SIGNAL],
        "limits": "The reason may not be visible. Do not name an offence unless the clip shows it.",
    },
    # ---------- reviews ----------
    "instant_replay": {
        "label": "Instant replay review", "group": "review", "signal": "the referee draws a rectangle in the air, then gives the final call",
        "laws": [("13", "Instant Replay Review"), ("13", "Replay Review Process")],
        "moments": [("incident", "The incident", "the frame showing the play being reviewed"), SIGNAL],
        "watch": "Replays and graphics count here.",
    },
    "coachs_challenge": {
        "label": "Coach's challenge", "group": "review", "signal": "the coach twirls a finger, then the referee gives the result",
        "laws": [("14", "Overview"), ("14", "Reviewable Matters")],
        "moments": [("incident", "The incident", "the frame showing the play being challenged"),
                    ("challenge", "Challenge made", "the first frame in which the coach is shown signalling the challenge"), SIGNAL],
        "watch": "Replays and graphics count here.",
        "limits": "Do not state the result unless the clip or the match context shows it.",
    },
}

GROUP_LABELS = {"ball_handling": "Ball handling", "clock": "Clock violations", "basket": "At the basket",
                "fouls": "Fouls", "review": "Reviews"}

# What Jev should box for a moment. A moment left out gets no box: the ball is too small to box.
BOX_TARGETS = {"referee_signal": "the referee", "contact": "the two players in contact", "gather": "the player with the ball",
               "extra_step": "the player with the ball", "dribble_ends": "the player with the ball",
               "dribble_restarts": "the player with the ball", "shot_release": "the player shooting",
               "feet_set": "the player shooting", "defender_set": "the defender", "ball_touched": "the basket",
               "ball_through": "the basket", "both_hold": "the two players holding the ball"}


def cite(section):
    """Section ids are arabic, and Part B of Rule 12 starts at 12.21 (see sports/basketball/laws.py)."""
    rule, number = str(section).split(".")
    n = int(number)
    if rule != "12":
        return f"Rule {rule}, Section {ROMAN[n]}"
    return f"Rule 12B, Section {ROMAN[n - 20]}" if n > 20 else f"Rule 12A, Section {ROMAN[n]}"


DETECT_SYSTEM, LEVELS, RULE_SYSTEM, PLAN_SYSTEM, detect_prompt, rule_prompt, plan_prompt = shared.prompts(DECISIONS, "basketball", "a referee")
