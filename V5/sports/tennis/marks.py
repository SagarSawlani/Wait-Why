"""What to mark at each tennis moment, best first. Shapes are described in sports/cricket/marks.py."""

BALL = ("ring", "the tennis ball")
PLAYER = ("feet", "the player hitting the ball")
SERVER = ("feet", "the player serving")
NET = ("arrow", "the net")

MARKS = {
    "serve_contact": [BALL, SERVER],
    "shot": [BALL, PLAYER],
    "ball_bounce": [BALL],
    "first_bounce": [BALL],
    "second_bounce": [BALL],
    "ball_hits_net": [BALL, NET],
    "ball_hits_body": [BALL, PLAYER],
    "net_contact": [NET],
    "feet_at_contact": [SERVER],
    "call": [("feet", "the chair umpire or line umpire making the call")],
    "incident": [("feet", "the player")],
}
