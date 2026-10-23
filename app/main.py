"""Small starter API for the CT-200 manual project."""

from pathlib import Path

from fastapi import FastAPI
from fastapi import HTTPException

from app.parser import parse_pdf

# FastAPI uses this object to create the web application.
app = FastAPI(
    title="CT-200 Manual API",
    description="An API for parsing and browsing versions of the CT-200 manual.",
    version="0.1.0",
)

DATA_FOLDER = Path(__file__).resolve().parent.parent / "data"


@app.get("/health")
def health_check():
    """Return a simple response so we can check that the API is running."""
    return {"status": "ok"}


@app.get("/documents/{version}/tree")
def get_document_tree(version: str):
    """Parse and return one of the two supplied manual versions."""
    # Only allow the two expected file names; never accept a path from a caller.
    file_names = {
        "v1": "ct200_manual.pdf",
        "v2": "ct200_manual_v2.pdf",
    }
    file_name = file_names.get(version)
    if file_name is None:
        raise HTTPException(status_code=404, detail="Unknown manual version")

    pdf_path = DATA_FOLDER / file_name
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="Manual PDF was not found")

    return parse_pdf(pdf_path)
