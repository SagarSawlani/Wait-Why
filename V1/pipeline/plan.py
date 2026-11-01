"""Builds the replay plan. The LLM writes the words; frames only ever come from the detections."""
from config import TEXT_CHAIN
from decisions import DECISIONS, PLAN_SYSTEM, plan_prompt
from pipeline import llm


def check_reply(data):
    if not isinstance(data.get("steps"), list):
        raise ValueError("reply has no steps")


def merge_steps(data, moments, fixed=None):
    """One step per detected moment, in time order. A moment the LLM skipped keeps its plain label,
    and anything it added is ignored, along with any frame it wrote. fixed wording always wins."""
    written = {s.get("moment"): s for s in data.get("steps", []) if isinstance(s, dict)}
    fixed = fixed or {}
    steps = []
    for m in moments:
        s = written.get(m["key"], {})
        steps.append({"moment": m["key"], "frame": m["frame"], "timestamp": m.get("timestamp"),
                      "title": str(s.get("title") or m["label"]),
                      "caption": fixed.get(m["key"]) or str(s.get("caption") or m.get("evidence") or m["label"]),
                      "highlight": None})   # filled later by the spotlight step
    return steps


def build(decision, event, rule, detections, fps):
    d, moments = DECISIONS[decision], detections["moments"]
    data, source = {}, "plain labels"
    if moments:
        try:
            data, source = llm.generate(TEXT_CHAIN, PLAN_SYSTEM, [plan_prompt(decision, event, rule, moments)],
                                        check=check_reply)
        except RuntimeError as e:
            print(f"  using plain labels: {e}")
    return {"decision": decision, "label": d["label"], "headline": str(data.get("headline") or d["label"]),
            "fps": fps, "rule": {"title": rule["title"], "summary": rule["summary"],
                                 "conditions": rule.get("conditions", []), "citations": rule.get("citations", []),
                                 "limits": d.get("limits", "")},
            "steps": merge_steps(data, moments, d.get("captions")), "caption_source": source}
