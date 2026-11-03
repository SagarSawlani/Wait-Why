"""What to mark at each cricket moment, best first. ring: thin circle round something small. arrow: points at a
fixed thing like the stumps, without covering it. feet: flat ellipse on the ground under a person, so their
body stays in view. A moment left out gets no marker."""

BALL = ("ring", "the small cricket ball")
BATTER = ("feet", "the batter")
BOWLER = ("feet", "the bowler")
STUMPS = ("arrow", "the three wooden stumps at the batter's end")
UMPIRE = ("feet", "the umpire")
FIELDER = ("feet", "the fielder nearest the ball")

MARKS = {
    "release": [("ring", "the small cricket ball just released from the bowler's hand"), BOWLER],
    "ball_pitches": [BALL, BATTER],
    "ball_hits_pad": [BALL, BATTER],
    "ball_at_batter": [BALL, BATTER],
    "ball_past_bat": [BALL, STUMPS],
    "ball_past_batter": [BALL, BATTER],
    "bat_miss": [BALL, BATTER],
    "bat_contact": [("ring", "the cricket bat"), BATTER],
    "first_strike": [("ring", "the cricket bat"), BATTER],
    "second_strike": [("ring", "the cricket bat"), BATTER],
    "stumps_hit": [STUMPS],
    "bails_off": [STUMPS],
    "stumps_broken": [STUMPS],
    "wicket_broken": [STUMPS],
    "catch_taken": [("feet", "the fielder catching the ball")],
    "appeal": [("feet", "the player appealing with arms raised")],
    "umpire_signal": [UMPIRE],
    "umpire_response": [UMPIRE],
    "batters_running": [BATTER],
    "batter_at_crease": [BATTER],
    "batter_leaves_crease": [BATTER],
    "batter_arrives": [BATTER],
    "turn_for_next_run": [BATTER],
    "obstruction": [BATTER],
    "front_foot_landing": [BOWLER],
    "ball_reaches_boundary": [BALL, FIELDER],
    "ball_clears_boundary": [BALL],
    "incident": [("feet", "the player involved in the incident")],
}
