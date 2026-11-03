"""Parses the Official NBA Playing Rules into data/laws/<edition>.json, in the same shape as cricket:
{"10": {"title", "text", "sections": {"10.13": text}}}. Section ids are arabic, so Section XIII is 10.13.
Rule 12 has two parts that each restart at Section I: Part A keeps 12.1 and Part B starts at 12.21.
Build once with: python -m sports.basketball.laws"""
import json, os, re

LAWS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "laws")
SOURCES = {"nba_2026_27": "rules_2026_27.pdf"}
PART_B = 20
RULE_RE = re.compile(r"^RULE NO\. (\d{1,2})[^\w\s](.+)$")
SECTION_RE = re.compile(r"^Section ([IVX]+)\s*[^\w\s().]\s*(\S.*)$")   # not "Section XIV)." or "Section II(N)."
PAGE_RE = re.compile(r"^(- \d+ -|Official Rules)$")
END = "COMMENTS ON THE RULES"
ROMAN = {"I": 1, "V": 5, "X": 10}
SPLIT_WORDS = {"PLA YERS": "PLAYERS", "PENAL TIES": "PENALTIES", "VIOLA TIONS": "VIOLATIONS",
               "INST ANT REPLA Y": "INSTANT REPLAY", "GOAL TENDING": "GOALTENDING"}


def edition_for(date):
    """Only one edition is stored so far, so every date uses it."""
    return "nba_2026_27"


def clean(text):
    return re.sub(r"[\s\xa0]+", " ", text).strip()


def title(text):
    """The PDF splits words in headings after a T, A or L: "T raveling", "PLA YERS", "PENAL TIES"."""
    text = re.sub(r"(?:(?<=\s)|^)([TA]) (?=[a-z])", r"\1", clean(text))
    for broken, whole in SPLIT_WORDS.items():
        text = text.replace(broken, whole)
    return text


def arabic(roman):
    values = [ROMAN[c] for c in roman]
    return sum(-v if v < n else v for v, n in zip(values, values[1:] + [0]))


def read_pages(path):
    from pypdf import PdfReader
    return [[clean(l) for l in (p.extract_text() or "").splitlines() if l.strip()] for p in PdfReader(path).pages]


def parse_pages(pages):
    laws, law, number, section, offset, last = {}, None, None, None, 0, 0
    for lines in pages:
        for line in lines:
            if PAGE_RE.match(line):
                continue
            if line.startswith(END) and laws:
                return laws
            rule = RULE_RE.match(line)
            if rule and rule.group(1) not in laws:
                number = rule.group(1)
                law = laws[number] = {"title": title(rule.group(2)), "text": "", "sections": {}}
                section, offset, last = None, 0, 0
                continue
            head = SECTION_RE.match(line) if law else None
            if head:
                n = arabic(head.group(1))
                if n <= last:   # numbering restarted, so this is Part B of the rule
                    offset = PART_B
                last = n
                section = f"{number}.{n + offset}"
                line = f"{section} {title(head.group(2))}"
                law["sections"][section] = ""
            if law:
                law["text"] += line + "\n"
                if section:
                    law["sections"][section] += line + "\n"
    return laws


def build_all():
    for edition, name in SOURCES.items():
        laws = parse_pages(read_pages(os.path.join(LAWS_DIR, name)))
        with open(os.path.join(LAWS_DIR, f"{edition}.json"), "w", encoding="utf-8") as f:
            json.dump(laws, f, ensure_ascii=False, indent=1)
        print(edition, len(laws), "rules")


if __name__ == "__main__":
    build_all()
