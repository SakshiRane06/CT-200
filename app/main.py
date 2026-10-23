"""Small starter API for the CT-200 manual project."""

from pathlib import Path

from fastapi import FastAPI
from fastapi import HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.browsing import (
    compare_section,
    get_section,
    latest_version_label,
    list_top_level_sections,
    search_sections,
)
from app.database import create_tables
from app.generations import find_generations, get_generation, save_generation
from app.llm import (
    InvalidLLMResponse,
    LLMConfigurationError,
    LLMRequestError,
    generate_test_cases,
)
from app.ingestion import VersionAlreadyExistsError, get_version_tree, ingest_manual
from app.parser import UnsupportedPDFError
from app.selections import create_selection, get_selection
from app.staleness import check_generation_staleness

# FastAPI uses this object to create the web application.
app = FastAPI(
    title="CT-200 Manual API",
    description="An API for parsing and browsing versions of the CT-200 manual.",
    version="0.1.0",
)

DATA_FOLDER = Path(__file__).resolve().parent.parent / "data"
MANUAL_FILES = {
    "v1": "ct200_manual.pdf",
    "v2": "ct200_manual_v2.pdf",
}


class SelectionRequest(BaseModel):
    """The version and section IDs to save as one named selection."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    version: str = Field(pattern=r"^v[0-9]+$")
    node_ids: list[str] = Field(min_length=1)


@app.on_event("startup")
def prepare_database():
    """Create empty SQLite tables when the API starts."""
    create_tables()


@app.get("/health")
def health_check():
    """Return a simple response so we can check that the API is running."""
    return {"status": "ok"}


@app.get("/documents/{version}/tree")
def get_document_tree(version: str):
    """Return a manual version that has already been imported."""
    if version not in MANUAL_FILES:
        raise HTTPException(status_code=404, detail="Unknown manual version")

    tree = get_version_tree(version)
    if tree is None:
        raise HTTPException(
            status_code=404,
            detail=f"Version {version} is not imported yet. Use POST /documents/{version}/ingest first.",
        )
    return tree


@app.post("/documents/{version}/ingest")
def import_document(version: str):
    """Parse and save one of the supplied PDF versions in SQLite."""
    file_name = MANUAL_FILES.get(version)
    if file_name is None:
        raise HTTPException(status_code=404, detail="Unknown manual version")

    pdf_path = DATA_FOLDER / file_name
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="Manual PDF was not found")

    try:
        return ingest_manual(version, pdf_path)
    except VersionAlreadyExistsError as error:
        # A version label cannot be reused for a different PDF.
        raise HTTPException(status_code=409, detail=str(error)) from error
    except UnsupportedPDFError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/sections")
def list_sections(version: str = "latest"):
    """List top-level sections, defaulting to the latest imported version."""
    selected_version = latest_version_label() if version == "latest" else version
    if selected_version is None:
        raise HTTPException(status_code=404, detail="No manual version has been imported")
    sections = list_top_level_sections(selected_version)
    if sections is None:
        raise HTTPException(status_code=404, detail="Version was not found")
    return {"version": selected_version, "sections": sections}


@app.get("/documents/{version}/sections/{section_id}")
def get_section_details(version: str, section_id: str):
    """Get a section, its children, full text, and content hash."""
    section = get_section(version, section_id)
    if section is None:
        raise HTTPException(status_code=404, detail="Version or section was not found")
    return section


@app.get("/documents/{version}/search")
def search_document(
    version: str,
    q: str = Query(min_length=1),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Search headings and section text in an imported manual version."""
    results = search_sections(version, q, limit)
    if results is None:
        raise HTTPException(status_code=404, detail="Version was not found")
    return {"version": version, "query": q, "results": results}


@app.get("/documents/changes/{section_id}")
def get_section_changes(section_id: str, from_version: str, to_version: str):
    """Tell whether a section changed and show a short word-level diff."""
    result = compare_section(section_id, from_version, to_version)
    if result is None:
        raise HTTPException(status_code=404, detail="Versions or section were not found")
    return result


@app.post("/selections", status_code=201)
def save_selection(request: SelectionRequest):
    """Save a named selection of sections from one imported version."""
    try:
        selection_id = create_selection(request.name, request.version, request.node_ids)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return get_selection(selection_id)


@app.get("/selections/{selection_id}")
def read_selection(selection_id: int):
    """Retrieve a selection and the text snapshots tied to its version."""
    selection = get_selection(selection_id)
    if selection is None:
        raise HTTPException(status_code=404, detail="Selection was not found")
    return selection


@app.post("/selections/{selection_id}/generate", status_code=201)
def generate_for_selection(selection_id: int):
    """Generate and save test cases based on a saved selection."""
    selection = get_selection(selection_id)
    if selection is None:
        raise HTTPException(status_code=404, detail="Selection was not found")

    try:
        test_cases = generate_test_cases(selection)
    except LLMConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except LLMRequestError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except InvalidLLMResponse as error:
        # Invalid or incomplete output is not saved as if it were usable.
        raise HTTPException(status_code=502, detail=str(error)) from error

    # Every successful request gets its own record, even for the same selection.
    return save_generation(selection, test_cases)


@app.get("/generations/{generation_id}")
def read_generation(generation_id: str):
    """Retrieve one saved generation by its unique ID."""
    record = get_generation(generation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Generation was not found")
    record["staleness"] = check_generation_staleness(record)
    return record


@app.get("/generations")
def list_generations(
    selection_id: int | None = None,
    node_id: str | None = Query(default=None, min_length=1),
):
    """Retrieve generations by exactly one selection ID or node ID."""
    if (selection_id is None) == (node_id is None):
        raise HTTPException(
            status_code=422,
            detail="Provide exactly one of selection_id or node_id",
        )
    records = find_generations(selection_id=selection_id, node_id=node_id)
    for record in records:
        record["staleness"] = check_generation_staleness(record)
    return records


@app.get("/generations/{generation_id}/staleness")
def read_generation_staleness(generation_id: str):
    """Return only the currentness status of one saved generation."""
    record = get_generation(generation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Generation was not found")
    return check_generation_staleness(record)
