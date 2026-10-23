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

## API overview

- The parser uses the manuals' embedded text and printed font sizes. OCR can be added as a fallback for pages without usable text.
- Each PDF version is saved separately. A section number is the current cross-version matching key; each saved section has a content hash.
- Browse a saved section with `GET /documents/v1/sections/section-3-2`.
- Search a saved version with `GET /documents/v1/search?q=battery`.
- Compare a section across versions with `GET /documents/changes/section-2-1-1-1?from_version=v1&to_version=v2`.
- Save a version-pinned selection with `POST /selections`, then retrieve its exact text snapshots with `GET /selections/{selection_id}`.
- Generate QA test cases for a saved selection with `POST /selections/{selection_id}/generate`.
- Retrieve saved generations by ID, selection ID, or source node ID.
- Generation retrieval includes a staleness status, and `GET /generations/{generation_id}/staleness` returns the status by itself.

Generated results are stored as separate JSON files under `data/generated_cases/`. This keeps each generation independent and makes its exact source snapshots easy to inspect. This local JSON store is suitable for the assignment demo; a multi-process production service would need a database-backed document store or shared storage.

Generation uses an OpenAI-compatible chat endpoint. Set these values in the same PowerShell window before starting the API; keep the API key private:

```powershell
$env:LLM_API_KEY = "your-provider-key"
$env:LLM_BASE_URL = "https://your-provider.example/v1"
$env:LLM_MODEL = "your-provider-model"
```

The API validates the JSON structure and checks that each case cites a section in the selection. It retries once when the response is malformed or incomplete. If the retry is still invalid, it returns an error and saves no generation. Each successful request creates a separate generation record, including when the same selection is submitted twice. Retrieval compares each saved source hash with the latest imported manual; any text change marks that source as changed, even if the edit is only a wording change.

## Demonstrate the v1 to v2 traceability flow

Start the server and configure the LLM settings above. Then run these commands in PowerShell. The first generation uses v1 text; importing v2 afterwards lets retrieval report which source sections changed.

```powershell
$baseUrl = "http://127.0.0.1:8000"

# Import version 1 and create a selection from its changed battery-life section.
Invoke-RestMethod -Method Post -Uri "$baseUrl/documents/v1/ingest"

$body = @{
    name = "Battery life"
    version = "v1"
    node_ids = @("section-2-1-1-1")
} | ConvertTo-Json

$selection = Invoke-RestMethod -Method Post -Uri "$baseUrl/selections" -ContentType "application/json" -Body $body
$generation = Invoke-RestMethod -Method Post -Uri "$baseUrl/selections/$($selection.id)/generate"

# Import version 2 only after the generation has been saved.
Invoke-RestMethod -Method Post -Uri "$baseUrl/documents/v2/ingest"

# The response includes the original source text and its current staleness status.
$result = Invoke-RestMethod -Method Get -Uri "$baseUrl/generations/$($generation.id)"
$result.staleness.status
$result.staleness.sources
```

The top-level section list defaults to the latest imported version. To browse a specific imported version, pass its label:

```powershell
Invoke-RestMethod -Method Get -Uri "$baseUrl/sections"
Invoke-RestMethod -Method Get -Uri "$baseUrl/sections?version=v1"
```
