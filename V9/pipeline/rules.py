"""Finds the Laws for a decision by exact lookup, has the LLM simplify them, then validates and caches."""
import importlib, json, os, re
import sports
from config import CACHE_DIR, ROOT, TEXT_CHAIN
from pipeline import llm

MAX_CHARS = 9000
_laws = {}


def edition_for(date, sport="cricket"):
    return importlib.import_module(f"sports.{sport}.laws").edition_for(date)


def load_laws(edition, sport="cricket"):
    if (sport, edition) not in _laws:
        path = os.path.join(ROOT, "sports", sport, "data", "laws", f"{edition}.json")
        with open(path, encoding="utf-8") as f:
            _laws[sport, edition] = json.load(f)
    return _laws[sport, edition]


def heading(text):
    """A section's text from its title on. The PDF wraps long titles and splits "Umpire’s" in two."""
    return " ".join(text.split()).split(" ", 1)[-1].lower().replace("’ s", "’s")


def retrieve(decision, edition, sport="cricket"):
    laws, found = load_laws(edition, sport), []
    for number, title in sports.decisions(sport).DECISIONS[decision]["laws"]:
        for sid, text in laws[number]["sections"].items():
            if title is None or heading(text).startswith(title.lower()):
                found.append({"id": sid, "text": text.strip()})
    used, sections = 0, []
    for s in found:
        used += len(s["text"])
        if sections and used > MAX_CHARS:
            break
        sections.append(s)
    return sections


def check_reply(data, sections):
    ids = {s["id"] for s in sections}
    if not str(data.get("summary", "")).strip() or not str(data.get("title", "")).strip():
        raise ValueError("reply has no title or summary")
    if not isinstance(data.get("conditions"), list):
        raise ValueError("conditions must be a list")
    cites = data.get("citations")
    if not cites or not isinstance(cites, list):
        raise ValueError("reply has no citations")
    for c in cites:
        # models may write [32.1], Law 32.1 or the sub-clause 32.1.1, which all mean section 32.1
        found = re.search(r"\d{1,2}\.\d{1,2}", str(c))
        if not found or found.group() not in ids:
            raise ValueError(f"citation {c} is not in the retrieved text")
    data["citations"] = sorted({re.search(r"\d{1,2}\.\d{1,2}", str(c)).group() for c in cites})


def official_fallback(decision, sections, sport="cricket"):
    text = re.sub(r"\s+", " ", sections[0]["text"])
    return {"title": sports.decisions(sport).DECISIONS[decision]["label"], "summary": text[:280], "conditions": [],
            "citations": [sections[0]["id"]], "source": "official text"}


def explain(decision, level, edition, sport="cricket"):
    """One LLM call ever per (decision, edition, level). A failed call is never cached."""
    key = f"{sport}_{decision}_{edition}_{level}"
    path = os.path.join(CACHE_DIR, "rules", key + ".json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    prompts = sports.decisions(sport)
    sections = retrieve(decision, edition, sport)
    if not sections:
        raise ValueError(f"no Law text found for {decision} in {edition}")
    try:
        data, model = llm.generate(TEXT_CHAIN, prompts.RULE_SYSTEM, [prompts.rule_prompt(decision, level, sections)],
                                   check=lambda d: check_reply(d, sections))
    except RuntimeError as e:
        print(f"  using the official text: {e}")
        return official_fallback(decision, sections, sport)
    data.update(source=model, edition=edition, level=level)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return data
