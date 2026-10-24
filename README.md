# CT-200 Manual Parser and QA Traceability API

This project reads the supplied CT-200 manual PDFs and provides an API for browsing sections, comparing manual versions, and generating QA test ideas linked to their source text.

## What it does

- Imports the supplied v1 and v2 manuals and saves their sections as a tree.
- Lets you list, browse, and search sections.
- Compares the same section across manual versions.
- Saves a selection of manual sections with their original text.
- Uses an OpenAI-compatible language model API to generate structured QA test ideas for a selection.
- Tracks whether a generated result refers to text that has changed in the latest imported manual.

## Requirements

- Windows with PowerShell, Python 3.10 or newer, and Git.
- A provider API key to test QA generation. Groq is the configured example provider; see [LLM setup](#set-up-llm-generation). Other OpenAI-compatible providers can be used by changing the settings in `.env`.

## Clone and install

Run these commands in PowerShell:

```powershell
git clone https://github.com/SakshiRane06/CT-200.git
cd CT-200
py -m venv .venv
\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

You do not need to activate the virtual environment. Running Python through `.venv\Scripts\python.exe` also works when PowerShell blocks activation scripts.

## Set up LLM generation

Importing and browsing the manuals does not need an LLM key. Generating QA cases does.

1. Copy the example settings file and open the local copy:

   ```powershell
   Copy-Item .env.example .env
   notepad .env
   ```

2. Create an API key with your chosen provider. For Groq, use the [Groq API keys page](https://console.groq.com/keys).
3. Put the key between the quotes for `LLM_API_KEY` in `.env`. Keep the key private. `.env` is ignored by Git and should never be committed.
4. Save and close the file.

The example `.env` settings use Groq's OpenAI-compatible endpoint and the `openai/gpt-oss-120b` model. Provider availability, model names, and usage limits can change. Check your provider's current documentation if a request is rejected.

## Start the API

From the project folder, run:

```powershell
\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Keep this PowerShell window open while testing. Open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) in a browser to use the interactive API page. For each request, expand the endpoint, click **Try it out**, enter the values, then click **Execute**.

Check that the server is running with `GET /health`. A successful response is:

```json
{"status":"ok"}
```

## Try the main workflow in the browser

### 1. Import both manuals

Use `POST /documents/{version}/ingest` twice: once with `version` set to `v1`, then with `version` set to `v2`. The PDFs are included in the `data` folder. A repeat import of the same PDF version may report that it was already imported.

### 2. Browse or search the manual

- Use `GET /documents/{version}/tree` to view the full tree for `v1` or `v2`.
- Use `GET /sections` with `version` set to `v1` or `v2` to list top-level sections.
- Use `GET /documents/{version}/sections/{section_id}` to inspect a section. For example, use `v1` and `section-2-1-1-1` for the battery-life section.
- Use `GET /documents/{version}/search` with `version` set to `v1` and `q` set to `battery`.
- Use `GET /documents/changes/{section_id}` with `section_id` `section-2-1-1-1`, `from_version` `v1`, and `to_version` `v2` to compare battery-life text.

### 3. Save a section selection

Use `POST /selections` with this request body:

```json
{
  "name": "Battery life test",
  "version": "v1",
  "node_ids": ["section-2-1-1-1"]
}
```

Note the `id` returned in the response. Use it as `selection_id` in the next requests.

### 4. Generate QA test ideas

Use `POST /selections/{selection_id}/generate`, entering the selection ID from step 3. A successful response includes a generation ID and structured test cases. Each case should cite a section from the selection.

Generated cases are AI suggestions. Review their steps and expected results against the manual before using or presenting them. The API checks the output structure and source IDs; it cannot guarantee the cases are clinically complete or correct.

### 5. Check saved output and staleness

- Use `GET /generations/{generation_id}` to retrieve a saved generation.
- Use `GET /generations/{generation_id}/staleness` to see whether its source text changed in the latest imported manual.
- Use `GET /generations` with either `selection_id` or `node_id` to list matching generations. Supply exactly one of those filters.

Because both manuals are imported before generating the v1 selection, a battery-life generation is expected to be reported as stale against v2 if that section's text differs.

## Run the automated checks

In a second PowerShell window from the project folder, run:

```powershell
\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The tests cover known PDF structure edge cases, generated-response validation, and staleness classification. They use a mocked LLM response and do not require a provider key.

## Files and local data

- `app/` contains the API, parser, storage, and generation code.
- `data/ct200_manual.pdf` and `data/ct200_manual_v2.pdf` are the supplied input manuals.
- `ct200.db` is created locally to store imported versions, sections, and selections.
- Generated QA responses are saved under `data/generated_cases/`.
- `APPROACH.md` describes the parsing and traceability decisions in more detail.

## Known limitations

- The parser is designed for the two supplied manuals, not arbitrary PDFs.
- OCR is not implemented, so image-only scanned PDFs are unsupported.
- Section numbers are used to match sections across versions. A renumbered section may appear as removed and added.
- Any source text change marks a generation stale, even if the change is minor.
- Generated QA cases need human review before use.
