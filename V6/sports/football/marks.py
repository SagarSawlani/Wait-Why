"""What to mark at each football moment, best first. Shapes are described in sports/cricket/marks.py."""

BALL = ("ring", "the football")
GOAL = ("arrow", "the goal")
REFEREE = ("feet", "the referee")
PLAYER = ("feet", "the player closest to the ball")
CONTACT = ("feet", "the two players in contact")

MARKS = {
    "kick": [BALL, PLAYER],
    "ball_crosses_line": [BALL, GOAL],
    "ball_in_net": [BALL, GOAL],
    "pass_played": [BALL, PLAYER],
    "attacker_involved": [("feet", "the player described here: {evidence}")],   # filled from the moment's evidence
    "flag_raised": [("feet", "the assistant referee raising a flag")],
    "contact": [CONTACT],
    "incident": [CONTACT],
    "ball_hits_arm": [BALL, PLAYER],
    "card_shown": [("ring", "the card held up by the referee", 0.7), REFEREE],   # a weak guess lands on a player
    "yellow_shown": [("ring", "the yellow card held up by the referee", 0.7), REFEREE],
    "red_shown": [("ring", "the red card held up by the referee", 0.7), REFEREE],
    "referee_signal": [REFEREE],
    "last_touch": [BALL, PLAYER],
    "ball_out": [BALL],
    "review_signal": [REFEREE],
    "at_monitor": [REFEREE],
}
