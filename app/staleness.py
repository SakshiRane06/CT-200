"""Compare generated source snapshots with the latest imported manual."""

from sqlalchemy import select

from app.database import SessionLocal
from app.models import ManualSection, ManualVersion


def classify_sources(
    sources: list[dict], current_version: str, current_hashes: dict[str, str]
) -> dict:
    """Classify each source snapshot using its stable section ID and hash."""
    source_status = []
    for source in sources:
        node_id = source["id"]
        current_hash = current_hashes.get(node_id)

        if current_hash is None:
            status = "removed"
        elif current_hash == source["content_hash"]:
            status = "current"
        else:
            status = "changed"

        source_status.append(
            {
                "id": node_id,
                "source_version": source["version"],
                "checked_against_version": current_version,
                "status": status,
                "source_hash": source["content_hash"],
                "current_hash": current_hash,
            }
        )

    changed_count = sum(item["status"] != "current" for item in source_status)
    current_count = len(source_status) - changed_count
    if not source_status:
        overall_status = "unknown"
    elif changed_count == 0:
        overall_status = "current"
    elif current_count == 0:
        overall_status = "stale"
    else:
        overall_status = "partially_stale"

    return {
        "status": overall_status,
        "checked_against_version": current_version,
        "sources": source_status,
    }


def check_generation_staleness(generation: dict) -> dict:
    """Check a saved generation against the newest imported version."""
    with SessionLocal() as session:
        latest = session.scalar(
            select(ManualVersion).order_by(ManualVersion.id.desc()).limit(1)
        )
        if latest is None:
            return {
                "status": "unknown",
                "checked_against_version": None,
                "sources": [],
            }

        node_ids = [source["id"] for source in generation.get("sources", [])]
        rows = session.scalars(
            select(ManualSection).where(
                ManualSection.version_id == latest.id,
                ManualSection.logical_id.in_(node_ids),
            )
        ).all()
        latest_hashes = {row.logical_id: row.content_hash for row in rows}

        return classify_sources(generation.get("sources", []), latest.label, latest_hashes)
