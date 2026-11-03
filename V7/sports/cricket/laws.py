"""Parses the MCC Laws files into data/laws/<edition>.json: {"36": {"title", "text", "sections": {"36.1": text}}}.
Build once with: python -m sports.cricket.laws"""
import json, os, re

LAWS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "laws")

SOURCES = {"3rd_2022": "laws_3rd_2022.docx", "4th_2026": "laws_4th_2026.pdf"}
# Body headings are upper case ("LAW 32 BOWLED"); contents lines are not ("LAW 32 Bowled 103").
LAW_RE = re.compile(r"^LAW\s+(\d{1,2})\s+([^a-z]+)$")
APPENDIX_RE = re.compile(r"^APPENDIX\s+[A-Z]\b")
SECTION_RE = re.compile(r"^(\d{1,2}\.\d{1,2})(?!\.\d)\s+\S")
JUNK_RE = re.compile(r"^(\d{1,3}(\s+\d{1,3})?|.*Laws of Cricket.*|©.*)$", re.I)


def clean(text):
    return re.sub(r"[\s\xa0]+", " ", text).strip()


def edition_for(date):
    """The 4th edition took effect on 1 October 2026. An unknown date gets the current edition."""
    return "3rd_2022" if date and date < "2026-10-01" else "4th_2026"


def read_docx(path):
    """The Word file numbers sections automatically, so the numbers are not in the text.
    Numbering level 1 marks a section, which lets us rebuild them. The index at the end repeats
    every heading in a plain style, and is where reading stops."""
    import docx
    lines, law, section, in_body = [], None, 0, False
    for p in docx.Document(path).paragraphs:
        text = clean(p.text)
        if not text:
            continue
        m = LAW_RE.match(text)
        if m:
            if p.style.name != "Heading 1":
                if in_body:
                    break
                continue
            in_body, law, section = True, m.group(1), 0
        elif APPENDIX_RE.match(text) and in_body:
            law = None
        elif in_body and law:
            pr = p._p.pPr
            num = pr.numPr if pr is not None else None
            if num is not None and num.ilvl is not None and num.ilvl.val == 1 and text[0].isupper():
                section += 1
                text = f"{law}.{section} {text}"
        lines.append(text)
    return lines


def read_pdf(path):
    from pypdf import PdfReader
    lines = []
    for page in PdfReader(path).pages:
        lines += [clean(l) for l in (page.extract_text() or "").splitlines() if l.strip()]
    return lines


def parse_lines(lines):
    """Splits lines into laws and numbered sections. Anything before the first law or
    after an appendix heading is dropped. A law can appear twice because the PDF has per-law
    contents pages, so the longest copy is the one kept."""
    laws, law, num, section = {}, None, None, None
    for line in lines:
        m = LAW_RE.match(line)
        if m:
            num, section = m.group(1), None
            law = {"title": m.group(2).strip().capitalize(), "text": "", "sections": {}}
            laws.setdefault(num, []).append(law)
            continue
        if APPENDIX_RE.match(line):
            law = None
        if law is None or JUNK_RE.match(line):
            continue
        m = SECTION_RE.match(line)
        if m and m.group(1).split(".")[0] == num:
            section = m.group(1)
            law["sections"][section] = ""
        law["text"] += line + "\n"
        if section:
            law["sections"][section] += line + "\n"
    best = {k: max(v, key=lambda x: len(x["text"])) for k, v in laws.items()}
    return {k: v for k, v in best.items() if v["sections"]}


def build_all():
    for edition, name in SOURCES.items():
        path = os.path.join(LAWS_DIR, name)
        lines = read_docx(path) if path.endswith(".docx") else read_pdf(path)
        laws = parse_lines(lines)
        with open(os.path.join(LAWS_DIR, f"{edition}.json"), "w", encoding="utf-8") as f:
            json.dump(laws, f, ensure_ascii=False, indent=1)
        print(edition, len(laws), "laws")


if __name__ == "__main__":
    build_all()
