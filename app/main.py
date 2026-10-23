"""Small starter API for the CT-200 manual project."""

from fastapi import FastAPI

# FastAPI uses this object to create the web application.
app = FastAPI(
    title="CT-200 Manual API",
    description="An API for parsing and browsing versions of the CT-200 manual.",
    version="0.1.0",
)


@app.get("/health")
def health_check():
    """Return a simple response so we can check that the API is running."""
    return {"status": "ok"}
