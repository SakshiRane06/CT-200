# CT-200 Manual Parser

A small backend API that will parse the CT-200 manual into a structured, versioned tree and help keep generated QA test ideas traceable to their source text.

## Current checkpoint

The API has a health endpoint at `GET /health`. Import either manual with `POST /documents/v1/ingest` or `POST /documents/v2/ingest`, then browse the saved tree at `GET /documents/v1/tree` or `GET /documents/v2/tree`. Imported sections and hashes are stored in `ct200.db`.

## Set up locally

1. Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install the project packages:

   ```powershell
   pip install -r requirements.txt
   ```

3. Start the API:

   ```powershell
   uvicorn app.main:app --reload
   ```

4. Open `http://127.0.0.1:8000/health` to check that it is running. The interactive API page is at `http://127.0.0.1:8000/docs`.

## Current behavior and planned work

- The parser uses the manuals' embedded text and printed font sizes. OCR can be added as a fallback for pages without usable text.
- Each PDF version is saved separately. A section number is the current cross-version matching key; each saved section has a content hash.
- Browse a saved section with `GET /documents/v1/sections/section-3-2`.
- Search a saved version with `GET /documents/v1/search?q=battery`.
- Compare a section across versions with `GET /documents/changes/section-2-1-1-1?from_version=v1&to_version=v2`.
- Save a version-pinned selection with `POST /selections`, then retrieve its exact text snapshots with `GET /selections/{selection_id}`.
- Add QA test-case generation and staleness reporting.

To try the current versioned browse flow after starting the server, import both versions:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/documents/v1/ingest
Invoke-RestMethod -Method Post http://127.0.0.1:8000/documents/v2/ingest
```

Next, add validated QA test-case generation, staleness reporting, and the decision-focused approach document.
