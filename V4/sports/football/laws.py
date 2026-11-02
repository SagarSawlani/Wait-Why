"""Parses the IFAB Laws of the Game into data/laws/<edition>.json, in the same shape as cricket:
{"11": {"title", "text", "sections": {"11.1": text}}}. The VAR protocol is stored as "18".
Build once with: python -m sports.football.laws"""
import json, os, re

LAWS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "laws")
SOURCES = {"2026_27": "laws_2026_27_double.pdf"}
VAR = "18"
HEADER_RE = re.compile(r"^Laws of the Game \d{4}/\d{2}\s*\|\s*Law (\d{1,2})\s*\|\s*(.+)$")
SECTION_RE = re.compile(r"^(\d{1,2})\.\s+(\S.*)$")
JUNK_RE = re.compile(r"^(\d{1,6}|Law|Laws of the Game.*)$")
END_RE = re.compile(r"^FIFA Quality", re.I)   # the section straight after the VAR protocol


def edition_for(date):
    """Only one edition is stored so far, so every date uses it."""
    return "2026_27"


def clean(text):
    return re.sub(r"[\s\xa0]+", " ", text).strip()


def read_pages(path):
    from pypdf import PdfReader
    return [[clean(l) for l in (p.extract_text() or "").splitlines() if l.strip()] for p in PdfReader(path).pages]


def parse_pages(pages):
    """A running header switches law. A section must be the next number, which skips numbered lists.
    Reading starts at Law 1, moves to the VAR protocol, and stops where that protocol ends."""
    laws, law, next_section, section = {}, None, 1, None
    for lines in pages:
        if lines[:3] and any(l == "protocol" for l in lines[:5]) and law:
            law = laws[VAR] = {"title": "Video assistant referee (VAR) protocol", "text": "", "sections": {}}
            next_section, section = 1, None
        # a law's opening page ends with a side marker: "Law", its number, its title
        for i, line in enumerate(lines[:-2]):
            if line == "Law" and lines[i + 1].isdigit() and lines[i + 1] not in laws:
                header = next((HEADER_RE.match(l) for l in lines if HEADER_RE.match(l)), None)
                title = header.group(2).strip() if header else lines[i + 2]
                law = laws[lines[i + 1]] = {"title": title, "text": "", "sections": {}}
                next_section, section = 1, None
        marker = {lines[i + 2] for i in range(len(lines) - 2) if lines[i] == "Law" and lines[i + 1].isdigit()}
        for line in lines:
            if line in marker:
                continue
            m = HEADER_RE.match(line)
            if m:
                number = m.group(1)
                if number not in laws:
                    law = laws[number] = {"title": m.group(2).strip(), "text": "", "sections": {}}
                    next_section, section = 1, None
                continue
            if law is None or JUNK_RE.match(line):
                continue
            if END_RE.match(line) and VAR in laws:
                return {k: v for k, v in laws.items() if v["sections"]}
            m = SECTION_RE.match(line)
            if m and int(m.group(1)) == next_section:
                number = next(k for k, v in laws.items() if v is law)
                section = f"{number}.{next_section}"
                law["sections"][section] = ""
                line = f"{section} {m.group(2)}"
                next_section += 1
            law["text"] += line + "\n"
            if section:
                law["sections"][section] += line + "\n"
    return {k: v for k, v in laws.items() if v["sections"]}


def build_all():
    for edition, name in SOURCES.items():
        laws = parse_pages(read_pages(os.path.join(LAWS_DIR, name)))
        with open(os.path.join(LAWS_DIR, f"{edition}.json"), "w", encoding="utf-8") as f:
            json.dump(laws, f, ensure_ascii=False, indent=1)
        print(edition, len(laws), "laws")


if __name__ == "__main__":
    build_all()
