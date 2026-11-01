"""Runs all the stages for one job and saves each result in the job folder.
params: sport, decision, level, date, format, notes, match_path, innings, over_ball, start, end"""
import json, os
import sports
from pipeline import detect, normalize, plan, render, rules

STAGES = ["Normalize video", "Read event", "Explain the rule", "Find key moments", "Write captions", "Render video"]


def save(job_dir, name, data):
    with open(os.path.join(job_dir, name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def read_event(p):
    sport = p.get("sport", "cricket")
    events = sports.events(sport)
    if p.get("match_path"):
        match = events.load_match(p["match_path"])
        return events.from_source(match, p, p.get("decision") or None)
    if p.get("decision") not in sports.decisions(sport).DECISIONS:
        raise ValueError("choose a decision, or add a Cricsheet file with the innings and over.ball")
    return events.from_form(p["decision"], p.get("date", ""), p.get("format", ""), p.get("notes", ""))


def run_job(job_dir, params, progress=lambda stage: None):
    """progress(i) is called as stage i starts. Returns the path of the output video."""
    source = os.path.join(job_dir, "input.mp4")

    progress(0)
    meta = normalize.normalize(source, job_dir, params.get("start"), params.get("end"))

    progress(1)
    event = read_event(params)
    if params.get("notes"):
        event["details"]["notes"] = params["notes"]
    save(job_dir, "event.json", event)
    decision = event["subtype"]

    progress(2)
    date = params.get("date") or event["context"].get("date", "")
    sport = event["sport"]
    rule = rules.explain(decision, params.get("level", "beginner"), rules.edition_for(date, sport), sport)
    save(job_dir, "rule.json", rule)

    progress(3)
    found = detect.detect(os.path.join(job_dir, "clip.mp4"), decision, event, job_dir, meta["fps"])

    progress(4)
    replay = plan.build(decision, event, rule, found, meta["fps"])
    save(job_dir, "plan.json", replay)

    progress(5)
    return render.render(os.path.join(job_dir, "clip.mp4"), replay, meta, os.path.join(job_dir, "output.mp4"))
