# CT-200 PDF Parsing and Traceability Approach

## Summary

This project parses the supplied CT-200 PDFs, stores each manual version as a separate tree, and generates traceable QA test ideas from saved section selections. It uses the text already embedded in these PDFs instead of running OCR on every page. The two supplied files have selectable text, and their text positions and font sizes are useful signals for finding headings.

The parser is tailored to these manuals. It does not claim to parse arbitrary PDFs. When it cannot find usable text and numbered sections, it returns an explicit error because OCR is not implemented.

## Data model

- `ManualVersion` stores a version label, title, source filename, PDF SHA-256 hash, and import time.
- `ManualSection` stores one version-specific section, its heading, numbered level, body, order, parent, and SHA-256 content hash. A logical ID based on the section number links likely corresponding sections across versions.
- `SectionSelection` stores a name and a foreign key to one manual version.
- `SelectionItem` stores the exact section text snapshot, hash, and section reference chosen for a selection.
- Generated results are stored as one JSON file per generation under `data/generated_cases/`. Each file contains a unique generation ID, selection ID, version, source snapshots, and validated test cases.

SQLite provides relational links for versions, sections, and selections. I chose one JSON file per generated result instead of adding MongoDB because the assignment only needs a small local demonstration. Separate files avoid overwriting earlier generations and are easy to inspect. This storage is not safe for multiple application processes writing to a shared directory; a production service should use a database-backed document store or shared object storage.

## PDF extraction and tree reconstruction

The parser uses `pypdf` to read text from each page and its visitor callback to capture font sizes. It normalizes the literal `\\n` sequences found in the supplied PDFs and uses font size as a heading signal:

- Main section headings use about 16.5 point text.
- Most subsection headings use about 12.9 point text.
- Body text and numbered classification list items use about 11 point text.
- The deeply numbered `2.1.1.1` heading is also about 11 point text, so the parser has a narrow fallback for section numbers with at least three dots.

The section number gives each node a stable, readable ID, such as `section-2-1-1-1`. The parser assigns a child to the closest previously seen section whose number is a prefix. This lets `2.1.1.1` attach to `2.1` even though the manual does not contain a `2.1.1` heading. Siblings stay in the order they appear in the PDF, so `3.4 Auto Shutoff` remains before `3.3 Result Display and Classification`.

Lists and tables are retained as text in the relevant section body. They are not converted into typed list items or table cells. The current extraction therefore preserves the words but does not guarantee row/column alignment for complex tables.

## Structural irregularities and handling

| Case in the supplied manual | Handling |
| --- | --- |
| Numbering skips from `2.1` to `2.1.1.1` | Keep level 4 from the number and attach to the closest existing numbered ancestor, `2.1`. |
| Section `3.4` appears before `3.3` | Preserve source order while using section numbers to find parent sections. |
| “Error Codes” appears in both `4.2` and `7.1` | Use section numbers for IDs, so repeated heading text remains two nodes under different parents. |
| Classification list starts with `1. Normal` | Use the smaller body font to keep this numbered list in the body instead of treating it as a section heading. |
| V2 adds section `5.3 Data Export` and error code E6 | Store the new numbered section in v2; keep the E6 row text in section `4.2`. |
| PDF wraps text and has inconsistent line breaks | Normalize known literal newline escapes, preserve extracted line content, and compare hashes after whitespace normalization. |
| Scanned image-only PDF has no selectable text | Return an explicit 422 error. OCR is not implemented in this version. |

## Version matching and content hashes

For this fixed manual, the matching key is the section number: `section-5-3` in one version is considered the same logical section as `section-5-3` in another. This is simple and works for the supplied v1/v2 pair. The hash covers the heading and body text after collapsing whitespace. A heading edit or body edit changes the hash.

This strategy has clear failure cases. If a section is renumbered, it appears to be a removed node plus a new node. If a number is reused for a different topic, the matcher can incorrectly treat it as the same logical node. It also does not decide whether a wording change is clinically meaningful. Those cases need human review.

Versions are immutable after import. Repeating an import with the same label and same PDF hash is idempotent; trying to reuse a label for different PDF bytes returns a conflict. The two included PDFs are imported as v1 and v2.

## Browse, selection, and generation APIs

- `GET /sections?version=latest` lists top-level sections, defaulting to the latest imported version. A version label can be supplied explicitly.
- `GET /documents/{version}/tree` returns a full saved tree.
- `GET /documents/{version}/sections/{section_id}` returns a node, descendants, full text, and content hash.
- `GET /documents/{version}/search?q=...` searches headings and body text.
- `GET /documents/changes/{section_id}?from_version=v1&to_version=v2` reports unchanged, modified, added, or removed sections and a small diff summary.
- `POST /selections` creates a named selection from section IDs in one version. Every selection item stores its exact source text and hash, so later imports do not change what the selection references.
- `POST /selections/{selection_id}/generate` generates 3–5 QA test ideas from the saved selection.
- `GET /generations/{generation_id}`, `GET /generations?selection_id=...`, and `GET /generations?node_id=...` retrieve saved output and its current staleness result.

## LLM prompt and output handling

The API calls a configurable OpenAI-compatible chat endpoint using `LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL`. The prompt includes each selected section's ID, version, content hash, and exact text. It asks for 3–5 cases with a title, preconditions, executable steps, an expected result, and source section IDs.

Pydantic validates the response as JSON, requires 3–5 complete cases, rejects unexpected fields, and verifies that each cited source ID belongs to the selection. If the response is malformed or incomplete, the API sends one repair request that includes the validation failure. If the second response is still invalid, the request returns an error and saves no partial result. Provider/network errors return an error without a retry. Structural validation cannot prove that a test is clinically complete or semantically correct; a reviewer still needs to check the generated ideas.

Each successful request creates a new generation ID and new JSON file, including when the same selection is submitted again. This keeps stochastic results and their timestamps separate rather than silently replacing earlier output.

## Staleness and its limits

On retrieval, the API compares every generation source's saved hash to the matching section in the latest imported version. It returns `current`, `stale`, or `partially_stale`, plus a per-section status. A missing section is reported as removed. Any hash change is treated as changed, including punctuation or wording changes.

This favors catching possible drift over judging meaning. It can mark a harmless typo fix stale, and it cannot distinguish a small wording edit from a changed pressure threshold. A semantic impact review could improve this, but automated semantic judgments should not replace review for safety-related requirements.

## What the first implementation missed and how it was improved

The first heading expression accepted `1. Device Overview` but incorrectly required another period after a dotted section number. As a result, numbered subsections were left inside the previous section's body. The explicit parser tests failed with missing-section lookups. I checked the extracted text and font sizes, changed the expression to accept dotted headings with or without a final period, and reran the tests. The tests now cover the deep numbering gap, repeated heading text, out-of-order siblings, numbered list items, and PDFs without usable text.

Manual inspection of the extracted section tree and comparison of the two PDFs identified the battery-life, inflation increment, E3 response time, E6, and data-export changes. Parser tests check the irregularities directly. Smoke checks also imported v1 and v2, searched and retrieved nodes, created a selection, generated output with a mocked provider, and confirmed the saved output became partially stale after v2 was imported. No live LLM request was made during validation.

## Decision log

**What part is most likely to silently give wrong results, and how would I catch it?**

Heading detection is the likeliest silent failure: a body line with a large font could look like a heading, or an unusually formatted heading could be missed. I would compare the generated tree against the PDF visually and keep explicit tests for the known numbering and list edge cases. A production-quality parser should also report uncertain headings for review.

**Where did I choose simplicity over correctness, and what would break first in production?**

I match logical sections by section number and treat every content-hash change as stale. This is easy to explain and conservative, but renumbering can break identity matching and minor text edits can create noisy stale warnings. Semantic traceability and shared, concurrent generation storage would be the first parts to replace for production use.

**Name one input I did not handle, and what does the system do with it?**

I did not implement OCR for an image-only scanned PDF. If the parser finds no usable text or numbered sections, it returns a clear unsupported-PDF error instead of saving an empty tree.

## What I would improve with more time

I would add OCR as a fallback for pages without a usable text layer, table-cell extraction, and a review output for uncertain heading decisions. I would expand the API to accept arbitrary new version files instead of the two bundled PDFs, add version-matching review for renumbered sections, and use shared database-backed storage for generated output. I would also validate generated test cases with domain review rather than relying only on structural JSON checks.
