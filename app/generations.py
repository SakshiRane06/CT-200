"""Save and retrieve generated test cases as one JSON file per generation."""

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path


STORE_FOLDER = Path(__file__).resolve().parent.parent / "data" / "generated_cases"


def save_generation(selection: dict, test_cases: list[dict]) -> dict:
    """Write one immutable generation record with its exact source snapshots."""
    STORE_FOLDER.mkdir(parents=True, exist_ok=True)
    generation_id = str(uuid.uuid4())
    record = {
        "id": generation_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "selection_id": selection["id"],
        "selection_name": selection["name"],
        "version": selection["version"],
        "sources": selection["items"],
        "test_cases": test_cases,
    }

    # Write to a temporary file first so an interrupted save leaves no half file.
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=STORE_FOLDER, delete=False
        ) as temporary_file:
            json.dump(record, temporary_file, ensure_ascii=False, indent=2)
            temporary_path = Path(temporary_file.name)
        temporary_path.replace(STORE_FOLDER / f"{generation_id}.json")
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()

    return record


def get_generation(generation_id: str) -> dict | None:
    """Load one saved generation, rejecting non-UUID IDs for safe paths."""
    try:
        safe_id = str(uuid.UUID(generation_id))
    except ValueError:
        return None

    record_path = STORE_FOLDER / f"{safe_id}.json"
    if not record_path.exists():
        return None
    return json.loads(record_path.read_text(encoding="utf-8"))


def find_generations(selection_id: int | None = None, node_id: str | None = None) -> list[dict]:
    """Find saved outputs by their selection ID or any selected node ID."""
    if not STORE_FOLDER.exists():
        return []

    matches = []
    for record_path in STORE_FOLDER.glob("*.json"):
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # Ignore a damaged file and keep other generations retrievable.
            continue

        matches_selection = selection_id is not None and record.get("selection_id") == selection_id
        matches_node = node_id is not None and any(
            item.get("id") == node_id for item in record.get("sources", [])
        )
        if matches_selection or matches_node:
            matches.append(record)

    return sorted(matches, key=lambda item: item["created_at"], reverse=True)
