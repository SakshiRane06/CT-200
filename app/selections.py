"""Create and retrieve version-pinned section selections."""

from sqlalchemy import select

from app.database import SessionLocal
from app.models import ManualSection, ManualVersion, SectionSelection, SelectionItem


def create_selection(name: str, version_label: str, node_ids: list[str]) -> int:
    """Save a named selection and snapshot each section's exact text."""
    if len(node_ids) != len(set(node_ids)):
        raise ValueError("A section ID can only appear once in a selection")

    with SessionLocal() as session:
        version = session.scalar(
            select(ManualVersion).where(ManualVersion.label == version_label)
        )
        if version is None:
            raise LookupError(f"Version {version_label} has not been imported")

        sections = session.scalars(
            select(ManualSection).where(
                ManualSection.version_id == version.id,
                ManualSection.logical_id.in_(node_ids),
            )
        ).all()
        sections_by_id = {section.logical_id: section for section in sections}
        missing_ids = [node_id for node_id in node_ids if node_id not in sections_by_id]
        if missing_ids:
            raise LookupError("Unknown section ID(s): " + ", ".join(missing_ids))

        selection = SectionSelection(name=name, version_id=version.id)
        session.add(selection)
        session.flush()

        for position, node_id in enumerate(node_ids):
            section = sections_by_id[node_id]
            # The saved copy means later imports cannot change this selection's text.
            text_snapshot = "\n".join(
                part for part in [section.heading, section.body_text] if part
            )
            session.add(
                SelectionItem(
                    selection_id=selection.id,
                    section_id=section.id,
                    position=position,
                    logical_id=section.logical_id,
                    section_number=section.section_number,
                    text_snapshot=text_snapshot,
                    content_hash=section.content_hash,
                )
            )

        session.commit()
        return selection.id


def get_selection(selection_id: int) -> dict | None:
    """Return a saved selection with its pinned version and text snapshots."""
    with SessionLocal() as session:
        selection = session.scalar(
            select(SectionSelection).where(SectionSelection.id == selection_id)
        )
        if selection is None:
            return None

        items = session.scalars(
            select(SelectionItem)
            .where(SelectionItem.selection_id == selection.id)
            .order_by(SelectionItem.position)
        ).all()
        return {
            "id": selection.id,
            "name": selection.name,
            "version": selection.version.label,
            "created_at": selection.created_at,
            "items": [
                {
                    "id": item.logical_id,
                    "section_number": item.section_number,
                    "version": selection.version.label,
                    "text": item.text_snapshot,
                    "content_hash": item.content_hash,
                }
                for item in items
            ],
        }
