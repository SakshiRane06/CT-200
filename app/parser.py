"""Read the CT-200 PDF text and rebuild its numbered section tree."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from pypdf import PdfReader


# A section heading starts with a number such as "2." or "2.1".
SECTION_HEADING = re.compile(r"^(\d+(?:\.\d+)*)(?:\.)?\s+(.+?)\s*$")


@dataclass
class Section:
    """One section in the manual and its position in the section tree."""

    section_number: str
    heading: str
    level: int
    parent_id: str | None
    body_parts: list[str] = field(default_factory=list)
    children: list["Section"] = field(default_factory=list)

    @property
    def node_id(self) -> str:
        """Use the manual's section number as a readable, stable ID."""
        return "section-" + self.section_number.replace(".", "-")

    def to_dict(self) -> dict:
        """Return a JSON-friendly version of this section and its children."""
        result = asdict(self)
        result["id"] = self.node_id
        result["body_text"] = "\n".join(self.body_parts).strip()
        result.pop("body_parts")
        result["children"] = [child.to_dict() for child in self.children]
        return result


def _clean_text(text: str) -> str:
    """Fix common PDF text quirks while keeping useful line breaks."""
    # Some manual versions contain the two characters backslash and n
    # where an actual line break should be.
    text = text.replace("\\n", "\n")
    return "\n".join(line.strip() for line in text.splitlines()).strip()


def _make_tree(text_parts: list[tuple[str, float]]) -> tuple[str, list[Section]]:
    """Build sections from text snippets and their printed font sizes."""
    title_parts: list[str] = []
    sections: list[Section] = []
    by_number: dict[str, Section] = {}
    current_section: Section | None = None

    for raw_text, font_size in text_parts:
        text = _clean_text(raw_text)
        if not text:
            continue

        # Each extracted snippet can contain more than one line.
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue

            match = SECTION_HEADING.match(line)

            # Most headings use a larger font than body text. The manual has
            # one exception: 2.1.1.1 is printed in body-sized text. We accept
            # that deeply numbered form as a heading even without the font cue.
            looks_like_heading = bool(
                match
                and (
                    font_size >= 12
                    or match.group(1).count(".") >= 3
                )
            )

            if looks_like_heading and match:
                number, heading = match.groups()
                section = Section(
                    section_number=number,
                    heading=heading,
                    level=number.count(".") + 1,
                    parent_id=None,
                )

                # Find the closest earlier section whose number is a prefix.
                # This handles numbering gaps, such as 2.1.1.1 with no 2.1.1.
                parent_number = number.rpartition(".")[0]
                while parent_number and parent_number not in by_number:
                    parent_number = parent_number.rpartition(".")[0]
                if parent_number:
                    parent = by_number[parent_number]
                    section.parent_id = parent.node_id
                    parent.children.append(section)
                else:
                    sections.append(section)

                by_number[number] = section
                current_section = section
                continue

            # Keep title text outside the section tree, then attach the rest
            # of the text to the most recent heading.
            if current_section is None:
                title_parts.append(line)
            else:
                current_section.body_parts.append(line)

    return " ".join(title_parts), sections


def parse_pdf(pdf_path: str | Path) -> dict:
    """Extract text from the supplied PDF and return a nested section tree.

    The CT-200 PDFs already contain selectable text, so we use that text and
    its font sizes instead of running OCR on clean text. OCR can be added as a
    fallback if a future input page has no usable text layer.
    """
    reader = PdfReader(str(pdf_path))
    text_parts: list[tuple[str, float]] = []

    for page in reader.pages:
        # pypdf calls this function for each piece of positioned PDF text.
        def collect_text(text, _cm, _tm, _font, font_size):
            if text and text.strip():
                text_parts.append((text, float(font_size or 0)))

        page.extract_text(visitor_text=collect_text)

    title, sections = _make_tree(text_parts)
    return {
        "title": title,
        "sections": [section.to_dict() for section in sections],
    }
