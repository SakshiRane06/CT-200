"""Small starter API for the CT-200 manual project."""

from pathlib import Path

from fastapi import FastAPI
from fastapi import HTTPException

from app.database import create_tables
from app.ingestion import get_version_tree, ingest_manual

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
    except ValueError as error:
        # A version label cannot be reused for a different PDF.
        raise HTTPException(status_code=409, detail=str(error)) from error
