"""Store parsed manual versions in SQLite."""

import hashlib
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal, create_tables
from app.models import ManualSection, ManualVersion
from app.parser import parse_pdf


def _sha256(value: bytes) -> str:
    """Return a short, standard SHA-256 fingerprint."""
    return hashlib.sha256(value).hexdigest()


def _section_hash(heading: str, body_text: str) -> str:
    """Hash the heading and body so either kind of edit is detectable."""
    clean_text = " ".join((heading + " " + body_text).split())
    return _sha256(clean_text.encode("utf-8"))


def _store_section(
    session: Session,
    version_id: int,
    section_data: dict,
    order_counter: list[int],
    parent_id: int | None = None,
) -> None:
    """Save a section first, then save its children underneath it."""
    order_counter[0] += 1
    body_text = section_data["body_text"]
    section = ManualSection(
        version_id=version_id,
        section_number=section_data["section_number"],
        # The section number is our simple cross-version matching key.
        logical_id="section-" + section_data["section_number"].replace(".", "-"),
        heading=section_data["heading"],
        level=section_data["level"],
        body_text=body_text,
        content_hash=_section_hash(section_data["heading"], body_text),
        order_index=order_counter[0],
        parent_id=parent_id,
    )
    session.add(section)
    session.flush()  # Assign an ID before the child rows refer to this section.

    for child_data in section_data["children"]:
        _store_section(session, version_id, child_data, order_counter, section.id)


def ingest_manual(version_label: str, pdf_path: str | Path) -> dict:
    """Parse and save a manual, preserving any versions already imported."""
    create_tables()
    pdf_path = Path(pdf_path)
    pdf_bytes = pdf_path.read_bytes()
    pdf_hash = _sha256(pdf_bytes)
    tree = parse_pdf(pdf_path)

    with SessionLocal() as session:
        existing = session.scalar(
            select(ManualVersion).where(ManualVersion.label == version_label)
        )
        if existing:
            # Do not silently replace a version: saved selections may refer to it.
            if existing.pdf_hash == pdf_hash:
                return {"version": version_label, "sections": len(existing.sections), "already_imported": True}
            raise ValueError(f"Version {version_label} already exists with different PDF content")

        version = ManualVersion(
            label=version_label,
            title=tree["title"],
            source_file=pdf_path.name,
            pdf_hash=pdf_hash,
        )
        session.add(version)
        session.flush()

        order_counter = [0]
        for section_data in tree["sections"]:
            _store_section(session, version.id, section_data, order_counter)

        session.commit()
        return {
            "version": version_label,
            "sections": order_counter[0],
            "already_imported": False,
        }


def get_version_tree(version_label: str) -> dict | None:
    """Load an imported version and return it as a nested JSON structure."""
    create_tables()
    with SessionLocal() as session:
        version = session.scalar(
            select(ManualVersion).where(ManualVersion.label == version_label)
        )
        if version is None:
            return None

        # Load every section once, then connect parents and children in memory.
        rows = session.scalars(
            select(ManualSection)
            .where(ManualSection.version_id == version.id)
            .order_by(ManualSection.order_index)
        ).all()
        by_id = {row.id: row for row in rows}
        children_by_parent: dict[int | None, list[ManualSection]] = {}
        for row in rows:
            children_by_parent.setdefault(row.parent_id, []).append(row)

        def to_dict(row: ManualSection) -> dict:
            return {
                "id": row.logical_id,
                "section_number": row.section_number,
                "heading": row.heading,
                "level": row.level,
                "parent_id": by_id[row.parent_id].logical_id if row.parent_id else None,
                "body_text": row.body_text,
                "content_hash": row.content_hash,
                "children": [to_dict(child) for child in children_by_parent.get(row.id, [])],
            }

        return {
            "version": version.label,
            "title": version.title,
            "source_file": version.source_file,
            "pdf_hash": version.pdf_hash,
            "sections": [to_dict(row) for row in children_by_parent.get(None, [])],
        }
