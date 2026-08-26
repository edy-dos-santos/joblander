"""Deterministic .docx generation for the job-application-assistant backend.

This module is intentionally the ONLY place that builds documents. The
agent (see agent_client.py / main.py) never writes document code - it
returns structured JSON (section text / paragraphs), and this module turns
that into a real .docx with python-docx. That split is deliberate: a fixed
renderer fed structured content is predictable, unit-testable, and produces
identical formatting every run, unlike asking a model to regenerate docx
markup (or LaTeX) from scratch on every request.

Two render paths:

  - Templated  (render_templated): the user supplies a .docx whose regions
    are marked with <<KEY>> placeholders (real glyphs are the guillemets
    U+00AB/U+00BB, e.g. the shipped `TEMPLATE_DOUBLE_COLUMN_MARKED.docx`
    uses <<NAME>>, <<CONTACT>>, <<SUMMARY>>, <<WORKHISTORY>>, ...). Each
    marker paragraph's run(s) are replaced in place, so the template's own
    styling (font, size, bold, color) survives untouched.
  - Plain (render_resume_plain / render_cover_letter_plain): no template
    available - build a clean document from the section/paragraph
    structure directly.

Both paths are exercised by this file's own __main__ self-test block and
by an external test fixture (test_docx_render.py) kept outside this repo.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Iterator

from docx import Document
from docx.enum.text import WD_BREAK
from docx.text.paragraph import Paragraph
from docx.text.run import Run

# The template's markers are guillemets, not straight angle brackets or
# quotes - easy to mistype. Spelled out explicitly so a future edit can't
# silently drift onto the wrong character.
_LEFT_GUILLEMET = "\u00ab"   # «
_RIGHT_GUILLEMET = "\u00bb"  # »

MARKER_RE = re.compile(
    rf"^\ufeff?\s*{_LEFT_GUILLEMET}\s*([A-Za-z]+)\s*{_RIGHT_GUILLEMET}\s*$"
)

# The eleven region keys produced by the frontend's MAP_CV_TASK / the
# tailor endpoint's structured JSON. Marker names in the template are the
# same keys upper-cased with no separators (workHistory -> WORKHISTORY).
SECTION_KEYS = [
    "name", "contact", "websites", "availability", "residency",
    "skills", "summary", "workHistory", "education", "certifications",
    "projects",
]

SECTION_LABELS = {
    "name": "Name",
    "contact": "Contact",
    "websites": "Websites / Portfolios / Profiles",
    "availability": "Availability",
    "residency": "Residency",
    "skills": "Skills",
    "summary": "Summary",
    "workHistory": "Work History",
    "education": "Education",
    "certifications": "Certifications",
    "projects": "Projects",
}

_BULLET_PREFIXES = ("- ", "* ", "\u2022 ", "\u2022")

# The prompts ask the model for plain text, but it still sometimes falls back
# to Markdown habits (picked up from the Markdown-heavy skill docs it reads
# for tailoring guidance) - '##'/'###' headers and '**bold**' spans. Neither
# was previously parsed, so the literal '#'/'*' characters leaked straight
# into the .docx. Parsed here rather than relying solely on prompt wording,
# since instruction-following isn't guaranteed.
_HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")

_UNSAFE_FILENAME_CHARS = re.compile(r'[^A-Za-z0-9 ._-]+')


def safe_filename(text: str | None, fallback: str = "file") -> str:
    """Sanitize free text (company/role names) into a filesystem-safe
    fragment for building output filenames. Never returns an empty string."""
    text = (text or "").strip()
    text = _UNSAFE_FILENAME_CHARS.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or fallback


# --------------------------------------------------------------------------
# Templated path
# --------------------------------------------------------------------------

def _iter_block_paragraphs(parent) -> Iterator[Paragraph]:
    """Yield every paragraph under `parent` (a Document or a table _Cell),
    recursing into any nested tables so a marker inside a nested table
    cell is still found."""
    for p in parent.paragraphs:
        yield p
    for table in parent.tables:
        for row in table.rows:
            for cell in row.cells:
                yield from _iter_block_paragraphs(cell)


def find_markers(path: str | Path) -> list[str]:
    """Return the marker names (upper-cased) present in a .docx, or [].
    Used both by tests and by the caller deciding templated-vs-plain."""
    doc = Document(str(path))
    found = []
    for para in _iter_block_paragraphs(doc):
        m = MARKER_RE.match(para.text)
        if m:
            found.append(m.group(1).upper())
    return found


def find_marked_template(templates_dir: str | Path) -> Path | None:
    """Look for a .docx in `templates_dir` that contains at least one
    <<MARKER>> paragraph. Returns the first match, or None. There is
    currently no endpoint that uploads a template into an instance's
    templates/ dir (see 04-implement-server.md) - this only fires when a
    template has been placed there some other way."""
    templates_dir = Path(templates_dir)
    if not templates_dir.is_dir():
        return None
    for candidate in sorted(templates_dir.glob("*.docx")):
        try:
            if find_markers(candidate):
                return candidate
        except Exception:
            continue
    return None


def _copy_font(src: Run, dst: Run) -> None:
    """Copy the visible font properties from one run to another, so text
    inserted next to a marker's original run matches its styling exactly."""
    dst.bold = src.bold
    dst.italic = src.italic
    dst.underline = src.underline
    try:
        dst.font.all_caps = src.font.all_caps
    except Exception:
        pass
    dst.font.name = src.font.name
    dst.font.size = src.font.size
    dst.font.strike = src.font.strike
    color = src.font.color
    try:
        if color is not None and color.type is not None and color.rgb is not None:
            dst.font.color.rgb = color.rgb
    except Exception:
        pass


def _fill_paragraph(para: Paragraph, value: str) -> None:
    """Replace a single-marker paragraph's content with `value`, splitting
    embedded newlines into additional runs joined by line breaks (not new
    paragraphs), so table-cell/paragraph structure is never disturbed."""
    runs = para.runs
    if runs:
        base = runs[0]
        for extra in runs[1:]:
            extra.text = ""
    else:
        base = para.add_run()

    lines = (value or "").split("\n")
    base.text = lines[0]
    for line in lines[1:]:
        br_run = para.add_run()
        _copy_font(base, br_run)
        br_run.add_break(WD_BREAK.LINE)
        text_run = para.add_run(line)
        _copy_font(base, text_run)


def render_templated(
    template_path: str | Path,
    output_path: str | Path,
    values: dict[str, str],
) -> list[str]:
    """Load `template_path`, replace every <<KEY>> marker paragraph whose
    key (case-insensitive) is present in `values`, and save to
    `output_path`. Markers with no matching key are left untouched.
    Returns the list of keys actually replaced (empty list => the
    template had no markers matching any provided key - almost certainly
    a caller bug, worth checking in tests/logs)."""
    template_path = Path(template_path)
    if not template_path.is_file():
        raise FileNotFoundError(f"Template not found: {template_path}")

    doc = Document(str(template_path))
    key_by_upper = {k.upper(): k for k in values}
    replaced: list[str] = []

    for para in _iter_block_paragraphs(doc):
        m = MARKER_RE.match(para.text)
        if not m:
            continue
        marker = m.group(1).upper()
        key = key_by_upper.get(marker)
        if key is None:
            continue
        _fill_paragraph(para, values.get(key) or "")
        replaced.append(key)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))
    return replaced


# --------------------------------------------------------------------------
# Plain path - resume
# --------------------------------------------------------------------------

_RESUME_SECTION_ORDER = [
    ("summary", "Summary"),
    ("skills", "Skills"),
    ("workHistory", "Work History"),
    ("education", "Education"),
    ("certifications", "Certifications"),
    ("projects", "Projects"),
    ("availability", "Availability"),
    ("residency", "Residency"),
]


def _add_bold_runs(paragraph: Paragraph, text: str) -> None:
    """Add `text` to `paragraph` as one or more runs, turning **bold** spans
    into real bold runs and stripping the asterisks, instead of leaving the
    literal markers in the document."""
    pos = 0
    matched = False
    for m in _BOLD_RE.finditer(text):
        matched = True
        if m.start() > pos:
            paragraph.add_run(text[pos:m.start()])
        paragraph.add_run(m.group(1)).bold = True
        pos = m.end()
    if pos < len(text) or not matched:
        paragraph.add_run(text[pos:])


def _add_body_lines(doc: Document, value: str) -> None:
    for raw_line in (value or "").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        heading_m = _HEADING_RE.match(line)
        if heading_m:
            p = doc.add_paragraph()
            _add_bold_runs(p, heading_m.group(1).strip())
            for run in p.runs:
                run.bold = True
            continue
        if line.startswith(_BULLET_PREFIXES):
            text = line.lstrip("-*\u2022").strip()
            p = doc.add_paragraph(style="List Bullet")
            _add_bold_runs(p, text)
        else:
            p = doc.add_paragraph()
            _add_bold_runs(p, line)


def render_resume_plain(
    output_path: str | Path,
    sections: dict[str, str],
) -> None:
    """Build a clean resume .docx from the eleven-region section
    structure, for when no marked template is available."""
    doc = Document()

    name = (sections.get("name") or "").strip()
    if name:
        doc.add_heading(name, level=1)

    contact_parts = [
        (sections.get("contact") or "").strip(),
        (sections.get("websites") or "").strip(),
    ]
    contact_line = " | ".join(p for p in contact_parts if p)
    if contact_line:
        doc.add_paragraph(contact_line)

    for key, label in _RESUME_SECTION_ORDER:
        value = (sections.get(key) or "").strip()
        if not value:
            continue
        doc.add_heading(label, level=2)
        _add_body_lines(doc, value)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))


# --------------------------------------------------------------------------
# Plain path - cover letter
# --------------------------------------------------------------------------

def render_cover_letter_plain(
    output_path: str | Path,
    *,
    greeting: str,
    paragraphs: Iterable[str],
    closing: str,
    signature_name: str,
) -> None:
    """Build a clean cover-letter .docx from greeting/paragraphs/closing
    /signature, for when no marked template is available."""
    doc = Document()

    if greeting and greeting.strip():
        doc.add_paragraph(greeting.strip())

    for para_text in paragraphs:
        _add_body_lines(doc, para_text)
        doc.add_paragraph("")

    if closing and closing.strip():
        doc.add_paragraph(closing.strip())
    if signature_name and signature_name.strip():
        doc.add_paragraph(signature_name.strip())

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(output_path))


# --------------------------------------------------------------------------
# Self-test (run this file directly for a quick smoke check; the real
# test suite is Lab/runs/tests/test_docx_render.py)
# --------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        out = tmp / "plain-resume.docx"
        render_resume_plain(out, {
            "name": "Jane Doe",
            "contact": "jane@example.com",
            "summary": "Data analyst.",
            "skills": "- SQL\n- Power BI",
            "workHistory": "Analyst at Acme (2020-2024)\n- Did things",
        })
        print("plain resume ->", out, out.exists())

        out2 = tmp / "plain-cover.docx"
        render_cover_letter_plain(
            out2,
            greeting="Dear Hiring Manager,",
            paragraphs=["Opening paragraph.", "Body paragraph with detail."],
            closing="Kind regards,",
            signature_name="Jane Doe",
        )
        print("plain cover letter ->", out2, out2.exists())

    print("OK" if len(sys.argv) < 2 else "OK (no template arg check here)")
