"""Parses the Rules of Tennis from Tennis Canada's Rules of the Court into data/laws/<edition>.json, in the
same shape as cricket. Rule 24 is stored as 24.1. Two parts are added for calls the 31 Rules do not cover:
the Code of Conduct as "32" (sections 32.1 to 32.4) and Electronic Line Calling as "33".
The ITF's own PDF sits behind a bot wall, and this book reprints the same 31 Rules with Tennis Canada's notes.
Build once with: python -m sports.tennis.laws"""
import json, os, re

LAWS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "laws")
SOURCES = {"rules_2026": "rules_of_the_court_2026.pdf"}
HEAD_RE = re.compile(r"^(\d{1,2})\.\s+([A-Z][A-Z &]{3,})$")
PAGE_RE = re.compile(r"^(\d{1,3}|Rules of Tennis|Tournament Regulations|Code of Conduct)$")
CONDUCT, ELC = "32", "33"
RULES_END = "AMENDMENT TO THE RULES OF TENNIS"
ELC_START, CONDUCT_START = "26. ELECTRONIC LINE CALLING", "THE CODE OF CONDUCT"
CONDUCT_SECTIONS = 4


def edition_for(date):
    """Only one edition is stored so far, so every date uses it."""
    return "rules_2026"


def clean(text):
    return re.sub(r"[\s\xa0]+", " ", text).strip()


def read_pages(path):
    from pypdf import PdfReader
    return [[clean(l) for l in (p.extract_text() or "").splitlines() if l.strip()] for p in PdfReader(path).pages]


def parse_rules(lines):
    laws, law, sid = {}, None, None
    for line in lines:
        if line.startswith(RULES_END) and laws:   # the contents page lists it first
            break
        m = HEAD_RE.match(line)
        if m and int(m.group(1)) == len(laws) + 1:
            sid = f"{m.group(1)}.1"
            law = laws[m.group(1)] = {"title": m.group(2).title(), "text": "", "sections": {sid: f"{sid} {m.group(2)}\n"}}
        elif law:
            law["sections"][sid] += line + "\n"
    for law in laws.values():
        law["text"] = "".join(law["sections"].values())
    return laws


def parse_elc(lines):
    start = lines.index(ELC_START)
    end = lines.index(CONDUCT_START, start)
    text = f"{ELC}.1 ELECTRONIC LINE CALLING\n" + "\n".join(lines[start + 1:end]) + "\n"
    return {"title": "Electronic Line Calling", "text": text, "sections": {f"{ELC}.1": text}}


def parse_conduct(lines):
    sections, sid = {}, None
    for line in lines[lines.index(CONDUCT_START, lines.index(ELC_START)) + 1:]:
        m = HEAD_RE.match(line)
        if m and int(m.group(1)) == len(sections) + 1:
            if len(sections) == CONDUCT_SECTIONS:
                break
            sid = f"{CONDUCT}.{m.group(1)}"
            sections[sid] = f"{sid} {m.group(2)}\n"
        elif sid:
            sections[sid] += line + "\n"
    return {"title": "Code of Conduct", "text": "".join(sections.values()), "sections": sections}


def parse_pages(pages):
    lines = [line for page in pages for line in page if not PAGE_RE.match(line)]
    return {**parse_rules(lines), CONDUCT: parse_conduct(lines), ELC: parse_elc(lines)}


def build_all():
    for edition, name in SOURCES.items():
        laws = parse_pages(read_pages(os.path.join(LAWS_DIR, name)))
        with open(os.path.join(LAWS_DIR, f"{edition}.json"), "w", encoding="utf-8") as f:
            json.dump(laws, f, ensure_ascii=False, indent=1)
        print(edition, len(laws), "rules")


if __name__ == "__main__":
    build_all()
