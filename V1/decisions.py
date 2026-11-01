"""Every umpire decision the system knows, and every prompt it sends.

To add a decision, add one entry to DECISIONS. Nothing else needs to change.
  label    shown to the fan
  group    dismissal, not_out, runs, extras, stoppage or review
  signal   what the umpire does to show the decision
  laws     (law number, section title) pairs; a title of None means the whole law.
           Titles are used because section numbers differ between editions.
  moments  (key, label, definition) in time order; the detector finds these
  derived  optional {moment: (other moment, frame offset)}, worked out instead of detected
  watch    extra guidance for the detector
  limits   what the video cannot prove, so captions never claim it
  captions optional {moment: text}, fixed wording that replaces the LLM's caption
  note     optional context for the rule explanation
"""

RELEASE = ("release", "Ball released", "the first frame in which the ball has left the bowler's hand")
SIGNAL = ("umpire_signal", "Umpire's signal", "the first frame in which the umpire is visible and clearly making the signal. Players raising their arms are not the umpire, and if the umpire is not shown making it, set this to null")
PAD = ("ball_hits_pad", "Ball hits the batter", "the first frame in which the ball strikes the batter's pad or body")
APPEAL = ("appeal", "The appeal", "the first frame in which the fielders are clearly appealing to the umpire")
CONTACT = ("bat_contact", "Bat meets ball", "the frame in which the bat hits the ball")

DECISIONS = {
    # ---------- dismissals ----------
    "bowled": {
        "label": "Bowled", "group": "dismissal", "signal": "raised index finger, often not needed",
        "laws": [("32", None)],
        "moments": [RELEASE,
                    ("stumps_hit", "Ball hits the stumps", "the first frame in which the ball reaches or touches the stumps at the batter's end"),
                    ("bails_off", "Bails fly", "the first frame in which the stumps are visibly disturbed or a bail is in the air")],
        "derived": {"bat_miss": ("stumps_hit", -1)},
        "watch": "The batter may hide the stumps at impact. Use the first frame with the ball at the stumps, not the frame where the bail is first seen.",
        "limits": "The ball may have touched the bat or body first, so describe bat_miss as the ball passing the bat, never as a clean miss.",
    },
    "caught": {
        "label": "Caught", "group": "dismissal", "signal": "raised index finger",
        "laws": [("33", None)],
        "moments": [RELEASE, CONTACT,
                    ("catch_taken", "Catch completed", "the first frame in which a fielder has the ball in hand before it touches the ground"),
                    SIGNAL],
        "watch": "The catch may follow a camera cut to a fielder. That shot still counts as live footage.",
        "limits": "A faint edge may not be visible, so never claim the ball touched the bat unless it is clear.",
    },
    "caught_and_bowled": {
        "label": "Caught and bowled", "group": "dismissal", "signal": "raised index finger",
        "laws": [("33", None)],
        "moments": [RELEASE, CONTACT,
                    ("catch_taken", "Bowler takes the catch", "the first frame in which the bowler has the ball in hand before it touches the ground")],
        "watch": "The bowler is also the catcher.",
        "limits": "",
    },
    "lbw": {
        "label": "Leg before wicket", "group": "dismissal", "signal": "raised index finger after an appeal",
        "laws": [("36", None)],
        "moments": [RELEASE,
                    ("ball_pitches", "Ball lands", "the first frame in which the ball touches the pitch, only if this is visible"),
                    PAD, APPEAL, SIGNAL],
        "watch": "Leave ball_pitches as null if the landing point cannot be seen.",
        "limits": "A broadcast clip cannot prove where the ball landed, the exact impact point, or that it would have hit the wicket, unless a tracking graphic shows it. Present these as what the umpire had to judge.",
    },
    "run_out": {
        "label": "Run out", "group": "dismissal", "signal": "raised index finger, or the third umpire's decision on screen",
        "laws": [("38", None), ("30", None)],
        "moments": [("batters_running", "Batters run", "the first frame in which the batters are clearly running"),
                    ("wicket_broken", "Wicket broken", "the first frame in which the ball or the hand holding it breaks the wicket"),
                    ("batter_at_crease", "Batter's position", "the frame that best shows where the batter is at the moment the wicket is broken")],
        "watch": "Replays of the same moment do not count unless the clip only shows it in a replay.",
        "limits": "Whether the batter was short of the crease may need a side-on replay, so do not claim it unless visible.",
    },
    "stumped": {
        "label": "Stumped", "group": "dismissal", "signal": "raised index finger, or the third umpire's decision on screen",
        "laws": [("39", None), ("30", None)],
        "moments": [RELEASE,
                    ("batter_leaves_crease", "Batter leaves the crease", "the first frame in which the batter is clearly out of the ground"),
                    ("ball_past_bat", "Ball beats the bat", "the frame in which the ball passes the bat"),
                    ("stumps_broken", "Keeper breaks the wicket", "the first frame in which the wicket-keeper breaks the wicket")],
        "limits": "Whether any part of the batter was behind the line may need a side-on replay.",
    },
    "hit_wicket": {
        "label": "Hit wicket", "group": "dismissal", "signal": "raised index finger",
        "laws": [("35", None)],
        "moments": [RELEASE,
                    ("wicket_broken", "Batter breaks the wicket", "the first frame in which the batter's bat or body breaks the wicket")],
        "limits": "",
    },
    "hit_ball_twice": {
        "label": "Hit the ball twice", "group": "dismissal", "signal": "raised index finger after an appeal",
        "laws": [("34", None)],
        "moments": [RELEASE, ("first_strike", "First strike", "the first time the ball hits the bat or the striker"),
                    ("second_strike", "Second strike", "the frame in which the striker deliberately hits the ball again"),
                    APPEAL],
        "limits": "Whether the second strike was only to protect the wicket is the umpire's judgement.",
    },
    "obstructing_the_field": {
        "label": "Obstructing the field", "group": "dismissal", "signal": "raised index finger after an appeal",
        "laws": [("37", None)],
        "moments": [("obstruction", "The obstruction", "the frame in which the batter blocks a fielder, the ball or a throw"), APPEAL, SIGNAL],
        "limits": "Whether the act was wilful is the umpire's judgement and cannot be proved from video.",
    },
    "timed_out": {
        "label": "Timed out", "group": "dismissal", "signal": "raised index finger after an appeal",
        "laws": [("40", None)],
        "moments": [("batter_arrives", "Incoming batter", "the frame in which the incoming batter is seen, or is seen to be missing"), APPEAL, SIGNAL],
        "limits": "The time limit depends on the competition, and the clip may not show the full wait.",
    },
    # ---------- not out ----------
    "not_out_appeal": {
        "label": "Not out", "group": "not_out", "signal": "the umpire shakes their head or says not out",
        "laws": [("31", "Answering appeals"), ("31", "Umpire not to give batter out")],
        "moments": [RELEASE, APPEAL,
                    ("umpire_response", "Umpire says not out", "the first frame in which the umpire clearly refuses the appeal")],
        "limits": "The clip may not show why the umpire refused, so describe the appeal and the response only.",
    },
    # ---------- runs ----------
    "four": {
        "label": "Four", "group": "runs", "signal": "arm waved from side to side across the chest",
        "laws": [("19", "Ball grounded beyond"), ("19", "Runs scored from boundaries"), ("19", "Determining the boundary")],
        "moments": [RELEASE, CONTACT,
                    ("ball_reaches_boundary", "Ball reaches the boundary", "the first frame in which the ball touches or crosses the boundary"),
                    SIGNAL],
        "watch": "The ball reaching the boundary usually comes after a camera cut.",
        "captions": {"ball_reaches_boundary": "The ball hits or crosses the boundary."},
        "limits": "Never say where the ball landed or whether it touched the ground.",
    },
    "six": {
        "label": "Six", "group": "runs", "signal": "both arms raised above the head",
        "laws": [("19", "Ball grounded beyond"), ("19", "Runs scored from boundaries"), ("19", "Fielder grounded beyond")],
        "moments": [RELEASE, CONTACT,
                    ("ball_clears_boundary", "Ball clears the boundary", "the first frame in which the ball is seen landing beyond the boundary, or clearly going over it"),
                    SIGNAL],
        "watch": "The landing usually comes after a camera cut.",
        "captions": {"ball_clears_boundary": "The ball crosses the boundary."},
        "limits": "Never say where the ball landed or whether it touched the ground.",
    },
    "short_run": {
        "label": "Short run", "group": "runs", "signal": "arm bent upwards to touch the nearer shoulder",
        "laws": [("18", "Short runs"), ("18", "Unintentional short runs"), ("18", "Deliberate short runs")],
        "moments": [("turn_for_next_run", "Batter turns", "the frame in which the batter turns for another run"), SIGNAL],
        "limits": "Whether the bat was grounded behind the crease may not be visible.",
    },
    "bye": {
        "label": "Bye", "group": "runs", "signal": "open hand raised above the head",
        "laws": [("23", "Byes")],
        "moments": [RELEASE, ("ball_past_batter", "Ball misses everything", "the frame in which the ball passes the batter without touching bat or body"),
                    ("batters_running", "Batters run", "the first frame in which the batters are clearly running"), SIGNAL],
        "limits": "",
    },
    "leg_bye": {
        "label": "Leg bye", "group": "runs", "signal": "raised knee touched with a hand",
        "laws": [("23", "Leg byes")],
        "moments": [RELEASE, PAD,
                    ("batters_running", "Batters run", "the first frame in which the batters are clearly running"), SIGNAL],
        "limits": "Whether the batter tried to play the ball or avoid it is the umpire's judgement.",
    },
    # ---------- extras ----------
    "wide": {
        "label": "Wide", "group": "extras", "signal": "both arms stretched out horizontally",
        "laws": [("22", "Judging a Wide"), ("22", "Delivery not a Wide"), ("22", "Penalty for a Wide")],
        "moments": [RELEASE,
                    ("ball_past_batter", "Ball passes the batter", "the frame in which the ball passes the batter"),
                    SIGNAL],
        "limits": "The wide line may not be visible from this camera. Limited-overs competitions can apply stricter wide rules than the Laws.",
    },
    "no_ball_front_foot": {
        "label": "No ball (front foot)", "group": "extras", "signal": "one arm stretched out horizontally",
        "laws": [("21", "Fair delivery – the feet"), ("21", "Penalty for a No ball")],
        "moments": [("front_foot_landing", "Front foot lands", "the first frame in which the bowler's front foot is on the ground in the delivery stride"),
                    RELEASE, SIGNAL],
        "watch": "A close-up replay of the foot counts if it is the only view of it.",
        "limits": "From behind the bowler the line is usually hidden, so do not claim the foot's position unless visible.",
    },
    "no_ball_height": {
        "label": "No ball (height)", "group": "extras", "signal": "one arm stretched out horizontally",
        "laws": [("41", "Bowling of dangerous and unfair non-"), ("41", "Bowling of dangerous and unfair short"),
                 ("21", "Ball bouncing over head height"), ("21", "Penalty for a No ball")],
        "moments": [RELEASE, ("ball_at_batter", "Ball reaches the batter", "the frame in which the ball reaches the batter on the full or at its highest point"), SIGNAL],
        "limits": "Exact ball height cannot be measured from video. Competitions can also set their own limits on short balls.",
    },
    "no_ball_other": {
        "label": "No ball", "group": "extras", "signal": "one arm stretched out horizontally",
        "laws": [("21", None)],
        "moments": [RELEASE, SIGNAL],
        "watch": "Say in the evidence what the reason appears to be, if it can be seen.",
        "limits": "The clip may not show the reason for the call.",
    },
    # ---------- stoppages and penalties ----------
    "dead_ball": {
        "label": "Dead ball", "group": "stoppage", "signal": "crossing and re-crossing the wrists below the waist",
        "laws": [("20", "Ball is dead"), ("20", "Umpire calling and signalling")],
        "moments": [("incident", "What stopped play", "the frame that shows why the ball became dead"), SIGNAL],
        "limits": "The cause may be off camera.",
    },
    "penalty_runs": {
        "label": "Penalty runs", "group": "stoppage", "signal": "one hand on the opposite shoulder for the side receiving them",
        "laws": [("41", "Penalty runs"), ("18", "Runs awarded for penalties")],
        "moments": [("incident", "The offence", "the frame that shows the action being penalised"), SIGNAL],
        "limits": "The reason may not be visible in the clip.",
    },
    "fitness_for_play": {
        "label": "Play suspended (light, rain or ground)", "group": "stoppage", "signal": "the umpires confer and remove the bails",
        "laws": [("2", "Fitness for play"), ("2", "Suspension of play in dangerous")],
        "moments": [("umpires_confer", "Umpires confer", "the first frame in which the umpires are clearly discussing the conditions"),
                    ("players_leave", "Play stops", "the first frame in which the players start to leave or the covers appear")],
        "limits": "Light readings and competition rules are not visible in the clip.",
    },
    # ---------- review ----------
    "drs_review": {
        "label": "Review (DRS)", "group": "review", "signal": "the umpire makes a T with the arms, and later changes or confirms the decision",
        "laws": [("31", "Umpire not to give batter out"), ("31", "Consultation by umpires"), ("2", "Umpire’s decision")],
        "moments": [("review_called", "Review requested", "the first frame in which a player or umpire makes the T signal"),
                    ("review_graphic", "Evidence on screen", "the first frame showing ball tracking, a replay or the third umpire's graphic"),
                    ("final_decision", "Final decision", "the first frame showing the final decision")],
        "watch": "Reviews contain replays and graphics, and in this case they do count as evidence.",
        "note": "The review system comes from the competition's playing conditions, not the Laws. Say so. The Laws only cover appeals, consultation and umpires changing a decision.",
        "limits": "Only state numbers or results shown on screen.",
    },
}

GROUP_LABELS = {"dismissal": "Dismissals", "not_out": "Not out", "runs": "Runs", "extras": "Extras",
                "stoppage": "Stoppages and penalties", "review": "Reviews"}

# ---------------- moment detection ----------------
DETECT_SYSTEM = """You are a cricket video analyst. You receive contact sheets made from one broadcast clip
about a single umpire decision. Find the frame numbers of key moments, for a replay that explains the
decision to fans.

How to read the input:
- The sheets are in time order. Inside a sheet, cells go left to right, then top to bottom.
- Each cell is one video frame. Its frame number is printed in white on a black box at the top-left.
- Cells are a fixed number of frames apart (stated in the request). Frames between cells are not shown.
- Always answer with a frame number printed on a cell. Never invent or interpolate numbers.

Rules:
- Judge each moment by what is visible, not by what usually happens. The decision and match context
  tell you what happened, but not that the clip shows it.
- If a moment does not happen, or is not visible in any cell, set its frame to null. Do not guess.
- Use the cell closest to the moment. If it falls between two cells, pick the earlier one
  unless the later one is clearly closer.
- Moments must be in the order listed.
- The clip may cut to other camera angles. Later live shots still count.
- Ignore graphics and crowd shots. Moments of the delivery itself must come from live footage,
  unless the request says otherwise.
- evidence is one short literal sentence about what you see in that cell.
- confidence is a number from 0 to 1.

Always return only JSON in the requested shape."""


def detect_prompt(decision, event, step):
    d = DECISIONS[decision]
    lines = [f"Cells are {step} frame(s) apart.",
             f"The umpire's decision is: {d['label']}. Its signal is: {d['signal']}."]
    context = event_context(event)
    if context:
        lines.append(f"Match context: {context}")
    lines.append("\nMoments to find:")
    lines += [f"- {key}: {definition}." for key, _, definition in d["moments"]]
    if d.get("watch"):
        lines.append(f"\nFor this decision: {d['watch']}")
    moments = ",\n".join(f'  "{key}": {{"frame": 0, "confidence": 0.0, "evidence": ""}}'
                         for key, _, _ in d["moments"])
    lines.append(f'\nReturn only JSON:\n{{"moments": {{\n{moments}\n }},\n "camera_cuts": []}}')
    return "\n".join(lines)


def event_context(event):
    actors = ", ".join(f"{a['role']}: {a['name']}" for a in event.get("actors", []) if a.get("name"))
    c = event.get("context", {})
    parts = [actors, c.get("format", ""), c.get("competition", ""), event.get("details", {}).get("notes", "")]
    return "; ".join(p for p in parts if p)


# ---------------- rule explanation ----------------
LEVELS = {"beginner": "someone watching cricket for the first time; no jargon, explain any cricket word you use",
          "standard": "a regular fan who knows the basics",
          "expert": "a keen follower who wants the precise wording and conditions"}

RULE_SYSTEM = """You turn an official rule into a short explanation for fans during a live match.
Use only the rule text you are given. Do not add anything from memory.
Keep every condition that decides the outcome. Do not quote more than a few words.
Conditions are things that must all be true. When the text gives alternatives joined by "or",
write them as one condition containing the word "or", never as separate conditions.
Leave out clauses that only apply in unusual cases.
Return only JSON in the requested shape."""


def rule_prompt(decision, level, sections):
    d = DECISIONS[decision]
    text = "\n\n".join(f"[{s['id']}]\n{s['text']}" for s in sections)
    note = f"\nAlso note: {d['note']}" if d.get("note") else ""
    return f"""Decision: {d['label']}
Reader: {LEVELS[level]}{note}

Official text:
{text}

Return only JSON:
{{"title": "short title",
 "summary": "at most 2 sentences a fan can read in 6 seconds",
 "conditions": ["each condition that must be true, at most 5, each under 12 words"],
 "citations": ["the section ids you used, exactly as written in square brackets"]}}"""


# ---------------- replay plan ----------------
PLAN_SYSTEM = """You write the captions for a slow-motion replay that explains an umpire's decision to a fan.
Each step belongs to one moment found in the video. You write words only; you never choose frames.
Only state what the evidence or the match data supports. Never invent names, distances or speeds.
Captions are read during a 3 second pause, so keep each under 16 words.
Return only JSON in the requested shape."""


def plan_prompt(decision, event, rule, moments):
    d = DECISIONS[decision]
    found = "\n".join(f"- {m['key']} ({m['label']}): {m.get('evidence') or 'no description'}" for m in moments)
    context = event_context(event) or "none"
    limits = f"\nDo not claim: {d['limits']}" if d.get("limits") else ""
    return f"""Decision: {d['label']}
Match context: {context}
Rule: {rule['summary']}
Conditions: {'; '.join(rule.get('conditions', []))}{limits}

Moments found, in order:
{found}

Write one step per moment. Link each caption to the rule where you can.
Return only JSON:
{{"headline": "the decision in under 8 words",
 "steps": [{{"moment": "moment key", "title": "2 to 4 words", "caption": "under 16 words"}}]}}"""
