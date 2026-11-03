"""Every football decision the system knows, and every prompt it sends.
Same entry format as sports/cricket/decisions.py. To add a decision, add one entry to DECISIONS."""

KICK = ("kick", "The kick", "the frame in which the player's foot strikes the ball")
PASS = ("pass_played", "Ball played", "the first frame in which a team-mate plays or touches the ball towards the attacker")
FOUL = ("contact", "The contact", "the frame showing the challenge or contact that led to the decision")
WHISTLE = ("referee_signal", "Referee's signal", "the first frame in which the referee clearly signals the decision")
CARD = ("card_shown", "Card shown", "the first frame in which the referee holds the card up")
OUT = ("ball_out", "Ball goes out", "the first frame in which the ball is seen crossing the touchline or goal line")

CARD_LAWS = [("12", "Disciplinary action")]
VAR_LAWS = [("18", "Principles"), ("5", "Video assistant referee")]

DECISIONS = {
    # ---------- goals ----------
    "goal": {
        "label": "Goal", "group": "goals", "signal": "the referee points to the centre circle",
        "laws": [("10", "Goal scored"), ("9", "Ball out of play")],
        "moments": [KICK, ("ball_crosses_line", "Ball crosses the line", "the first frame in which the ball is past the goal line"), WHISTLE],
        "captions": {"ball_crosses_line": "The ball crosses the goal line."},
        "limits": "Do not claim the whole ball crossed the line unless the frame or a goal-line graphic clearly shows it.",
    },
    "goal_disallowed": {
        "label": "Goal disallowed", "group": "goals", "signal": "the referee waves the goal away or signals a free kick",
        "laws": [("10", "Goal scored"), ("11", "Offside offence"), ("12", "Direct free kick")],
        "moments": [("incident", "The incident", "the frame showing the offence that cancels the goal, if visible"),
                    ("ball_in_net", "Ball in the net", "the first frame in which the ball is in the goal"), WHISTLE],
        "watch": "Replays count here, because they often show the offence.",
        "limits": "The reason may not be visible. Do not name an offence unless the clip shows it.",
    },
    # ---------- offside ----------
    "offside": {
        "label": "Offside", "group": "offside", "signal": "the assistant referee raises the flag",
        "laws": [("11", "Offside position"), ("11", "Offside offence"), ("11", "No offence")],
        "moments": [("pass_played", "Ball played", "the final pass or shot by the attacking team before play stops for offside, including a shot saved by the keeper. If the attacking team passes several times, use the last one; never a touch by a defender. The evidence must give the passer's shirt colour"),
                    ("attacker_involved", "Attacker goes for the ball", "the first frame in which the team-mate that final pass reaches touches the ball or challenges an opponent. He wears the passer's shirt colour, and the ball must have had time to travel, so this is normally many frames after the pass. A player the ball only flies past does not count. If nobody reaches the ball, use the frame where the team-mate nearest its path is clearly running onto it. The evidence must give his shirt colour and where he is in the frame"),
                    ("flag_raised", "Flag raised", "the first frame in which you can actually see the assistant referee's flag held up. It is often shown only after the live play, in a close-up, so look through every cell to the end of the clip")],
        "watch": "Work in this order. First decide which team is attacking: it is moving towards the goal that the other team is defending, so use the goal, the goalkeeper and where most defenders stand, not the score or the kit. Then follow the ball through every cell of the live play, and note each pass by the attacking team until play stops. Only then choose the frames. The pass and the attacker must be from the live play, not a replay. The flag may appear after the live play. If you cannot see one of the moments, answer null for it.",
        "captions": {"pass_played": "A team-mate plays the ball. Offside is judged at this instant, not when the attacker receives it.",
                     "attacker_involved": "This attacker goes for the pass. Getting involved is what can make it an offence.",
                     "flag_raised": "The flag is the officials' call on where the attacker was at the pass. This view cannot prove it."},
        "limits": "The camera angle usually cannot prove the attacker's position. Unless a line graphic shows it, present position as what the officials judged.",
    },
    # ---------- fouls ----------
    "foul_free_kick": {
        "label": "Foul (free kick)", "group": "fouls", "signal": "the referee blows and points the direction of the free kick",
        "laws": [("12", "Direct free kick"), ("13", "Types of free kick")],
        "moments": [FOUL, WHISTLE],
        "watch": "Replays count here.",
        "limits": "Careless, reckless and excessive force are the referee's judgement.",
    },
    "penalty": {
        "label": "Penalty", "group": "fouls", "signal": "the referee points to the penalty mark",
        "laws": [("12", "Direct free kick"), ("14", "Procedure")],
        "moments": [FOUL, WHISTLE],
        "watch": "Replays count here.",
        "limits": "Do not claim the exact location of the contact unless a line is clearly visible.",
    },
    "handball": {
        "label": "Handball", "group": "fouls", "signal": "the referee blows and may point to the arm",
        "laws": [("12", "Direct free kick")],
        "moments": [("ball_hits_arm", "Ball hits the arm", "the frame in which the ball touches the hand or arm"), WHISTLE],
        "watch": "Replays count here, because they are often the only clear view.",
        "limits": "Whether the arm was deliberate or unnaturally positioned is the referee's judgement.",
    },
    "advantage": {
        "label": "Advantage played", "group": "fouls", "signal": "both arms swept forward",
        "laws": [("5", "Powers and duties")],
        "moments": [FOUL, ("referee_signal", "Advantage signal", "the first frame in which the referee sweeps both arms forward")],
        "limits": "",
    },
    # ---------- cards ----------
    "yellow_card": {
        "label": "Yellow card", "group": "cards", "signal": "the referee holds up a yellow card",
        "laws": CARD_LAWS, "moments": [FOUL, CARD],
        "limits": "The clip may not show why the card was given.",
    },
    "red_card": {
        "label": "Red card", "group": "cards", "signal": "the referee holds up a red card",
        "laws": CARD_LAWS, "moments": [FOUL, CARD],
        "limits": "The clip may not show why the card was given.",
    },
    "second_yellow": {
        "label": "Second yellow card", "group": "cards", "signal": "the referee shows a yellow card, then a red card",
        "laws": CARD_LAWS,
        "moments": [FOUL, ("yellow_shown", "Yellow card", "the first frame showing the yellow card"),
                    ("red_shown", "Red card", "the first frame showing the red card")],
        "limits": "The first caution may not be in the clip.",
    },
    # ---------- restarts ----------
    "corner": {
        "label": "Corner kick", "group": "restarts", "signal": "the referee points to the corner arc",
        "laws": [("17", "Procedure")], "moments": [("last_touch", "Last touch", "the frame in which a defender last touches the ball"), OUT, WHISTLE],
        "limits": "A faint touch may not be visible.",
    },
    "goal_kick": {
        "label": "Goal kick", "group": "restarts", "signal": "the referee points to the goal area",
        "laws": [("16", "Procedure")], "moments": [("last_touch", "Last touch", "the frame in which an attacker last touches the ball"), OUT, WHISTLE],
        "limits": "A faint touch may not be visible.",
    },
    "throw_in": {
        "label": "Throw-in", "group": "restarts", "signal": "the assistant referee flags the direction",
        "laws": [("15", "Procedure"), ("9", "Ball out of play")], "moments": [OUT, WHISTLE],
        "limits": "",
    },
    "ball_out": {
        "label": "Ball out of play", "group": "restarts", "signal": "the referee or assistant referee stops play",
        "laws": [("9", "Ball out of play"), ("9", "Ball in play")], "moments": [OUT, WHISTLE],
        "captions": {"ball_out": "The ball crosses the line."},
        "limits": "Do not claim the whole ball was over the line unless clearly shown.",
    },
    # ---------- review ----------
    "var_check": {
        "label": "VAR check", "group": "review", "signal": "the referee touches the earpiece or holds a finger up",
        "laws": VAR_LAWS,
        "moments": [("incident", "Incident checked", "the frame showing the incident under review"),
                    ("final_decision", "Final decision", "the first frame showing the final decision")],
        "watch": "Replays and graphics count as evidence here.",
        "limits": "Only state results shown on screen.",
    },
    "on_field_review": {
        "label": "On-field review", "group": "review", "signal": "the referee draws a TV screen shape in the air",
        "laws": VAR_LAWS,
        "moments": [("review_signal", "Review signal", "the first frame of the referee drawing the screen shape"),
                    ("at_monitor", "Referee at the monitor", "the first frame of the referee at the pitchside monitor"),
                    ("final_decision", "Final decision", "the first frame showing the final decision")],
        "watch": "Replays and graphics count as evidence here.",
        "limits": "Only state results shown on screen.",
    },
}

RULEBOOK = "Laws of the Game"


def cite(section):
    """The VAR protocol is stored as Law 18, which is only our label."""
    return "VAR protocol" if str(section).startswith("18.") else section


GROUP_LABELS = {"goals": "Goals", "offside": "Offside", "fouls": "Fouls", "cards": "Cards",
                "restarts": "Restarts", "review": "Reviews"}

DETECT_SYSTEM = """You are a football video analyst. You receive contact sheets made from one broadcast clip
about a single referee decision. Find the frame numbers of key moments, for a replay that explains the
decision to fans.

How to read the input:
- The sheets are in time order. Inside a sheet, cells go left to right, then top to bottom.
- Each cell is one video frame. Its frame number is printed in white on a black box at the top-left.
- Cells are a fixed number of frames apart (stated in the request). Frames between cells are not shown.
- Always answer with a frame number printed on a cell. Never invent or interpolate numbers.

Rules:
- Judge each moment by what is visible, not by what usually happens.
- If a moment does not happen, or is not visible in any cell, set its frame to null. Do not guess.
- Use the cell closest to the moment.
- Moments must be in the order listed.
- The clip may cut to other camera angles. Later live shots still count.
- Ignore graphics and crowd shots, and use the live view rather than a replay, unless the request says otherwise.
- evidence is one short literal sentence about what you see in that cell.
- confidence is a number from 0 to 1.

Always return only JSON in the requested shape."""


def event_context(event):
    actors = ", ".join(f"{a['role']}: {a['name']}" for a in event.get("actors", []) if a.get("name"))
    c = event.get("context", {})
    parts = [actors, c.get("format", ""), c.get("competition", ""), event.get("details", {}).get("notes", "")]
    return "; ".join(p for p in parts if p)


def detect_prompt(decision, event, step):
    d = DECISIONS[decision]
    lines = [f"Cells are {step} frame(s) apart.",
             f"The referee's decision is: {d['label']}. Its signal is: {d['signal']}."]
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


LEVELS = {"beginner": "a complete beginner watching football for the first time. Explain it the way you would to a 12-year-old friend sitting next to you: short everyday words and one idea at a time. Clarity matters more than covering every case, so keep only what the viewer would need to understand this call. Never mention rule numbers, and replace formal words with plain ones. The summary is one sentence under 15 words. Give at most 3 conditions, each under 8 words, and never end one with 'or'. Explain any football word you have to use",
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
    return f"""Decision: {d['label']}
Reader: {LEVELS[level]}

Official text:
{text}

Return only JSON:
{{"title": "short title",
 "summary": "at most 2 sentences a fan can read in 6 seconds",
 "conditions": ["each condition that must be true, at most 5, each under 12 words"],
 "exceptions": ["what the text says does not count, at most 2, each under 12 words"],
 "citations": ["the section ids you used, exactly as written in square brackets"]}}"""


PLAN_SYSTEM = """You write the captions for a slow-motion replay that explains a referee's decision to a fan.
Each step belongs to one moment found in the video. You write words only; you never choose frames.
Only state what the evidence or the match data supports. Never invent names, distances or speeds.
A title and the headline name what happens in that moment, in plain words. They never judge it, so avoid words like
confirmed, proven, correct, penalized or gains advantage.
Captions are read during a 3 second pause, so keep each under 16 words.
Return only JSON in the requested shape."""


def plan_prompt(decision, event, rule, moments):
    d = DECISIONS[decision]
    found = "\n".join(f"- {m['key']} ({m['label']}): {m.get('evidence') or 'no description'}" for m in moments)
    limits = f"\nDo not claim: {d['limits']}" if d.get("limits") else ""
    return f"""Decision: {d['label']}
Match context: {event_context(event) or 'none'}
Rule: {rule['summary']}
Conditions: {'; '.join(rule.get('conditions', []))}{limits}

Moments found, in order:
{found}

Write one step per moment. Link each caption to the rule where you can.
Return only JSON:
{{"headline": "the decision in under 8 words",
 "steps": [{{"moment": "moment key", "title": "2 to 4 words", "caption": "under 16 words"}}]}}"""
