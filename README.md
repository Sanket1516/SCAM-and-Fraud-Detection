# Claim Document Parser (SCAM & Fraud Detection)

A Flask service and CLI that turns scanned medical/insurance claim PDFs into structured data: full-document Markdown plus every detected table as JSON records, using [Docling](https://github.com/docling-project/docling) with Surya OCR.

> **Scope:** this repository implements the **document-extraction stage** that a claim fraud-detection workflow would sit on top of. It does not contain fraud-scoring or classification logic.

## Problem

Insurance and hospital claims arrive as PDFs of varying quality (clean exports, scans, noisy layouts). Fraud and anomaly checks need the text and tables in machine-readable form first. This project provides that step.

## Features

- Upload a PDF in the browser and get back JSON (Markdown + tables).
- OCR with **Surya** (via `docling-surya`); falls back to **RapidOCR** and reports a warning if Surya is not installed.
- Table structure recognition with cell matching; each table is exported with its page number as JSON-safe records (`pandas`).
- Recoverable failures (missing file, failed conversion, unexportable table) are reported in an `errors` list instead of crashing.
- Sample PDFs graded **Easy / Medium / Hard** in `PDF_Original/`.
- Dockerised, with model caches kept in named volumes.

## Tech stack

Python 3.12 · Flask · Docling · docling-surya (Surya OCR) · RapidOCR (fallback) · pandas · Docker / Docker Compose

## How it works

```
PDF upload ──► Flask /api/upload ──► Docling converter (OCR + table structure)
                                          │
                                          ├─► document Markdown
                                          └─► tables ► pandas ► JSON records
                                                         │
                                         JSON response ◄─┘  (source_path, markdown, tables, table_count, errors, warnings)
```

| File | Role |
|---|---|
| `app.py` | Flask app: `GET /` upload page, `POST /api/upload` (PDF only, 16 MB limit). |
| `claim_parser.py` | `get_converter()` builds the Docling pipeline; `extract_claim_data()` returns the result dict; `main()` runs a CLI extraction and writes JSON to `outputs/`. |
| `templates/`, `static/` | Single-page upload UI. |
| `Dockerfile`, `docker-compose.yml` | Linux x86_64 / Python 3.12 environment with Surya. |
| `DOCKER.md` | Detailed Docker notes. |

## Getting started

### Option A: Docker (recommended, required for Surya)

`docling-surya` needs Linux x86_64 and Python 3.12+. On Windows use Docker Desktop with WSL2.

```bash
docker compose build
docker compose up
```

Open <http://localhost:5000> and upload a PDF. The first run downloads OCR models into Docker volumes.

Run the CLI extractor on a sample file instead of the web app:

```bash
docker compose run --rm --entrypoint python \
  -e INPUT_PDF=/workspace/PDF_Original/Easy/PDF_Deid_Deidentification_0.pdf \
  claim-parser-surya claim_parser.py
```

The JSON is written to `outputs/` (for example `PDF_Original_Easy_PDF_Deid_Deidentification_0_extracted_claim.json`).

### Option B: local Python (RapidOCR fallback)

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

`requirements.txt` does not include `docling-surya`, so this mode uses RapidOCR.

## API

`POST /api/upload`: multipart form with a `file` field containing a `.pdf`.

```bash
curl -F "file=@PDF_Original/Easy/PDF_Deid_Deidentification_0.pdf" http://localhost:5000/api/upload
```

Response (abridged):

```json
{
  "source_path": "uploads/PDF_Deid_Deidentification_0.pdf",
  "markdown": "## Diagnostic Form ...",
  "tables": [{ "table_index": 1, "page_no": 1, "records": [ { "...": "..." } ] }],
  "table_count": 1,
  "errors": [],
  "warnings": []
}
```

Errors: `400` for a missing/non-PDF file, `500` if processing fails.

## Notes and limitations

- The sample PDFs are de-identified/synthetic documents.
- `app.py` runs Flask in debug mode for development; use a production WSGI server for deployment.
- No automated tests are included yet.

## Future improvements

- Field-level extraction (patient, diagnosis, amounts) on top of the Markdown/tables.
- Fraud and anomaly rules or models consuming the extracted data.
- Tests and a CI workflow.

## Author

Sanket Mali · [GitHub](https://github.com/Sanket1516)
