"""Prompts and form events shared by sports that have no match data file yet (basketball, tennis).
Each sport keeps only its own decisions, and gets the rest from these two functions."""
import re


def event_context(event):
    actors = ", ".join(f"{a['role']}: {a['name']}" for a in event.get("actors", []) if a.get("name"))
    c = event.get("context", {})
    parts = [actors, c.get("format", ""), c.get("competition", ""), event.get("details", {}).get("notes", "")]
    return "; ".join(p for p in parts if p)


def prompts(decisions, sport, official):
    """Returns the prompts a sport's decisions.py must expose, in the order it unpacks them."""
    detect_system = f"""You are a {sport} video analyst. You receive contact sheets made from one broadcast clip
about a single decision by {official}. Find the frame numbers of key moments, for a replay that explains the
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
- Use the cell closest to the moment.
- Moments must be in the order listed.
- The clip may cut to other camera angles. Later live shots still count.
- Ignore graphics and crowd shots, and use the live view rather than a replay, unless the request says otherwise.
- evidence is one short literal sentence about what you see in that cell.
- confidence is a number from 0 to 1.

Always return only JSON in the requested shape."""

    def detect_prompt(decision, event, step):
        d = decisions[decision]
        lines = [f"Cells are {step} frame(s) apart.",
                 f"The decision is: {d['label']}. Its signal is: {d['signal']}."]
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

    levels = {"beginner": f"someone watching {sport} for the first time; no jargon, explain any {sport} word you use",
              "standard": "a regular fan who knows the basics",
              "expert": "a keen follower who wants the precise wording and conditions"}

    rule_system = """You turn an official rule into a short explanation for fans during a live match.
Use only the rule text you are given. Do not add anything from memory.
Keep every condition that decides the outcome. Do not quote more than a few words.
Conditions are things that must all be true. When the text gives alternatives joined by "or",
write them as one condition containing the word "or", never as separate conditions.
Leave out clauses that only apply in unusual cases.
Return only JSON in the requested shape."""

    def rule_prompt(decision, level, sections):
        d = decisions[decision]
        text = "\n\n".join(f"[{s['id']}]\n{s['text']}" for s in sections)
        return f"""Decision: {d['label']}
Reader: {levels[level]}

Official text:
{text}

Return only JSON:
{{"title": "short title",
 "summary": "at most 2 sentences a fan can read in 6 seconds",
 "conditions": ["each condition that must be true, at most 5, each under 12 words"],
 "citations": ["the section ids you used, exactly as written in square brackets"]}}"""

    plan_system = f"""You write the captions for a slow-motion replay that explains a decision by {official} to a fan.
Each step belongs to one moment found in the video. You write words only; you never choose frames.
Only state what the evidence or the match data supports. Never invent names, distances or speeds.
Captions are read during a 3 second pause, so keep each under 16 words.
Return only JSON in the requested shape."""

    def plan_prompt(decision, event, rule, moments):
        d = decisions[decision]
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

    return detect_system, levels, rule_system, plan_system, detect_prompt, rule_prompt, plan_prompt


def form_event(sport, decisions, decision, date="", fmt="", notes=""):
    """The event for a decision chosen on the page. A match data adapter would write this same shape."""
    if decision not in decisions:
        raise ValueError(f"unknown decision: {decision}")
    if date and not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise ValueError(f"date must be YYYY-MM-DD, got {date!r}")
    return {"event_id": f"manual-{decision}", "sport": sport, "event_type": decisions[decision]["group"],
            "subtype": decision, "outcome": decisions[decision]["label"], "status": "final", "actors": [],
            "context": {"format": fmt, "date": date, "competition": ""}, "details": {"notes": notes}, "source": "manual"}
