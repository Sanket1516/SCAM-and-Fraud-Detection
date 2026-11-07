<div align="center">

# SCAM and Fraud Detection

**Extracts structured data from patient-claim PDFs and scores each document for fraud / tampering risk with an explainable, rule-based engine.**

![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-000000?logo=flask&logoColor=white)
![Docling](https://img.shields.io/badge/Docling-PDF_parsing-6E40C9)
![OCR](https://img.shields.io/badge/OCR-Surya_%7C_RapidOCR-0A7EA4)
![Docker](https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white)
![pytest](https://img.shields.io/badge/tests-pytest-0A9EDC?logo=pytest&logoColor=white)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow)

<img src="docs/screenshots/03-fraud-analysis.jpg" alt="Claim Extractor Core: risk score 35/100, medium risk, five explained flags" width="880" />

</div>

## Screenshots

> Real captures of the running web UI analysing `PDF_Original/Hard/PDF_Deid_Deidentification_Hard_0.pdf` (de-identified sample) with RapidOCR.

| Upload | Processing (OCR + table extraction) |
|:---:|:---:|
| <img src="docs/screenshots/01-upload.jpg" alt="Drag and drop PDF upload" width="430" /> | <img src="docs/screenshots/02-processing.jpg" alt="Analyzing document and extracting tables" width="430" /> |
| **Extracted tables** | **Raw JSON (with `fraud_analysis`)** |
| <img src="docs/screenshots/04-tables.jpg" alt="Visit table extracted from page 2" width="430" /> | <img src="docs/screenshots/06-json.jpg" alt="Structured JSON output" width="430" /> |

<details>
<summary>Markdown view of the extracted document</summary>
<img src="docs/screenshots/05-markdown.jpg" alt="Extracted markdown content" width="700" />
</details>

## How it works

```
PDF ──► claim_parser.py ──────────────────────────► fraud_detector.py ──────────────► JSON + web UI
        Docling layout + OCR (Surya / RapidOCR)       extract key fields, run           risk_score 0–100
        → Markdown, tables, JSON                       consistency rules                 risk_level + flags
```

1. `claim_parser.py` – OCR + table extraction → Markdown, tables, JSON.
2. `fraud_detector.py` – extracts key fields and runs consistency rules, returning
   `risk_score` (0-100), `risk_level` (`low` < 20 ≤ `medium` < 50 ≤ `high`) and
   a list of explained `flags` (included in the JSON as `fraud_analysis`).
3. `app.py` – Flask web UI (`/`) and API (`POST /api/upload`, `GET /health`).

## Rules implemented

| Area | Checks |
|------|--------|
| Identity | name / DOB / age / sex differ between header and summary; OCR-level name variance (low) |
| Age & DOB | age vs DOB gap (1 yr = low, 2–9 = medium, ≥10 = high); invalid or future DOB |
| SSN & IDs | never-issued SSN ranges, placeholder SSNs, malformed SSN / hospital / doctor IDs |
| Dates | future dates, dates before birth, procedure → received → report ordering, stale reports, mixed DD/MM vs MM/DD formats |
| Visits & tests | duplicate / future / pre-birth visits, "Done" tests dated in the future, long-stale "Pending" tests |
| Vitals | implausible heart rate, respiratory rate, temperature, SpO₂, blood pressure |
| Clinical | diabetes medication without a diagnosis, duplicate medications |
| Completeness | missing core fields, no identifiers, no extractable text |

Each flag has a severity weight (high 30, medium 15, low 5; capped at 100).

## Run

Docker (needed for Surya OCR, see [`DOCKER.md`](DOCKER.md)):

```bash
docker compose build
docker compose up          # web UI on http://localhost:5000
```

Local (falls back to RapidOCR if `docling-surya` is missing):

```bash
pip install -r requirements.txt
python app.py                                   # web UI on http://localhost:5000
INPUT_PDF=PDF_Original/Easy/PDF_Deid_Deidentification_0.pdf python claim_parser.py   # CLI
```

The first run downloads the Docling layout and OCR models from Hugging Face; later runs use the local cache.

### API

```bash
curl -F "file=@PDF_Original/Hard/PDF_Deid_Deidentification_Hard_0.pdf" http://localhost:5000/api/upload
```

Returns `markdown`, `tables`, `table_count`, `fraud_analysis` (`risk_score`, `risk_level`, `flags`), `warnings` and `errors`.

## Sample data

`PDF_Original/` holds 50 de-identified claim PDFs in three difficulty levels: `Easy/` (30), `Medium/` (10) and `Hard/` (10). Example output: [`outputs/`](outputs).

## Tests

```bash
pytest tests
```

The detector is stdlib-only, so tests run without Docling or OCR models.

## Project structure

```
app.py              Flask web UI + API
claim_parser.py     Docling/OCR extraction → Markdown, tables, JSON
fraud_detector.py   rule engine → risk score, level, flags
templates/, static/ web UI
tests/              detector unit tests
PDF_Original/       de-identified sample claims
outputs/            example extraction output
Dockerfile, docker-compose.yml, DOCKER.md
```

> The detector flags documents for **human review**; it does not prove fraud.

## License

MIT, see [LICENSE](LICENSE).
