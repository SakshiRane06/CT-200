"""Read stored manual sections for the browse and search endpoints."""

from difflib import SequenceMatcher

from sqlalchemy import or_, select

from app.database import SessionLocal
from app.models import ManualSection, ManualVersion


def _section_dict(section: ManualSection, include_children: bool = True) -> dict:
    """Turn one database row into a JSON-friendly section."""
    children = []
    if include_children:
        children = [_section_dict(child) for child in section.children]

    own_text = "\n".join(part for part in [section.heading, section.body_text] if part)
    full_text_parts = [own_text]
    full_text_parts.extend(child["full_text"] for child in children)

    return {
        "id": section.logical_id,
        "section_number": section.section_number,
        "heading": section.heading,
        "level": section.level,
        "parent_id": section.parent.logical_id if section.parent else None,
        "body_text": section.body_text,
        "full_text": "\n".join(part for part in full_text_parts if part),
        "content_hash": section.content_hash,
        "children": children,
    }


def get_section(version_label: str, section_id: str) -> dict | None:
    """Find a section by its stable logical ID in one manual version."""
    with SessionLocal() as session:
        version = session.scalar(
            select(ManualVersion).where(ManualVersion.label == version_label)
        )
        if version is None:
            return None
        section = session.scalar(
            select(ManualSection).where(
                ManualSection.version_id == version.id,
                ManualSection.logical_id == section_id,
            )
        )
        return _section_dict(section) if section else None


def search_sections(version_label: str, query: str, limit: int = 20) -> list[dict] | None:
    """Search section headings and body text in one imported version."""
    with SessionLocal() as session:
        version = session.scalar(
            select(ManualVersion).where(ManualVersion.label == version_label)
        )
        if version is None:
            return None

        words = f"%{query}%"
        rows = session.scalars(
            select(ManualSection)
            .where(
                ManualSection.version_id == version.id,
                or_(ManualSection.heading.ilike(words), ManualSection.body_text.ilike(words)),
            )
            .order_by(ManualSection.order_index)
            .limit(limit)
        ).all()

        return [
            {
                "id": row.logical_id,
                "section_number": row.section_number,
                "heading": row.heading,
                "parent_id": row.parent.logical_id if row.parent else None,
                "content_hash": row.content_hash,
                "snippet": row.body_text[:240],
            }
            for row in rows
        ]


def _text_changes(old_text: str, new_text: str) -> dict:
    """Return a small word-level summary instead of a full diff."""
    old_words = old_text.split()
    new_words = new_text.split()
    matcher = SequenceMatcher(a=old_words, b=new_words)
    changes = []

    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        changes.append(
            {
                "type": tag,
                "old_text": " ".join(old_words[old_start:old_end])[:160],
                "new_text": " ".join(new_words[new_start:new_end])[:160],
            }
        )

    return {"changes": changes[:5], "more_changes": len(changes) > 5}


def compare_section(section_id: str, from_label: str, to_label: str) -> dict | None:
    """Compare one stable section ID between two saved manual versions."""
    with SessionLocal() as session:
        versions = {
            version.label: version
            for version in session.scalars(
                select(ManualVersion).where(ManualVersion.label.in_([from_label, to_label]))
            ).all()
        }
        if from_label not in versions or to_label not in versions:
            return None

        source = session.scalar(
            select(ManualSection).where(
                ManualSection.version_id == versions[from_label].id,
                ManualSection.logical_id == section_id,
            )
        )
        target = session.scalar(
            select(ManualSection).where(
                ManualSection.version_id == versions[to_label].id,
                ManualSection.logical_id == section_id,
            )
        )

        if source is None and target is None:
            return None
        if source is None:
            return {
                "id": section_id,
                "from_version": from_label,
                "to_version": to_label,
                "changed": True,
                "change_type": "added",
                "old_hash": None,
                "new_hash": target.content_hash,
            }
        if target is None:
            return {
                "id": section_id,
                "from_version": from_label,
                "to_version": to_label,
                "changed": True,
                "change_type": "removed",
                "old_hash": source.content_hash,
                "new_hash": None,
            }

        changed = source.content_hash != target.content_hash
        old_text = "\n".join([source.heading, source.body_text])
        new_text = "\n".join([target.heading, target.body_text])
        result = {
            "id": section_id,
            "from_version": from_label,
            "to_version": to_label,
            "changed": changed,
            "change_type": "modified" if changed else "unchanged",
            "old_hash": source.content_hash,
            "new_hash": target.content_hash,
        }
        if changed:
            result["diff"] = _text_changes(old_text, new_text)
        return result
