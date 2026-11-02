"""What to mark at each basketball moment, best first. Shapes are described in sports/cricket/marks.py."""

BALL = ("ring", "the basketball")
BASKET = ("arrow", "the basket")
HANDLER = ("feet", "the player with the ball")
REFEREE = ("feet", "the referee making the signal")
CONTACT = ("feet", "the two players in contact")

MARKS = {
    "gather": [BALL, HANDLER],
    "extra_step": [HANDLER],
    "dribble_ends": [BALL, HANDLER],
    "dribble_restarts": [BALL, HANDLER],
    "last_touch": [BALL, HANDLER],
    "ball_out": [BALL, HANDLER],
    "ball_in_frontcourt": [HANDLER],
    "ball_back": [BALL, HANDLER],
    "backcourt_control": [HANDLER],
    "both_hold": [BALL, ("feet", "the two players holding the ball")],
    "shot_release": [BALL, ("feet", "the player shooting")],
    "feet_set": [("feet", "the player shooting")],
    "ball_touched": [BALL, BASKET],
    "ball_through": [BASKET],
    "in_the_lane": [("feet", "the player standing in the painted lane")],
    "ball_handed": [("feet", "the player throwing the ball in")],
    "contact": [CONTACT],
    "defender_set": [("feet", "the defender")],
    "incident": [CONTACT],
    "referee_signal": [REFEREE],
    "challenge": [("feet", "the coach")],
}
