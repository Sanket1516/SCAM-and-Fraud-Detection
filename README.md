# SCAM and Fraud Detection

Extracts structured data from patient-claim PDFs (Docling + Surya/RapidOCR) and
scores each document for **fraud / tampering risk** with a rule-based engine.

## Pipeline

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

Docker (needed for Surya OCR, see `DOCKER.md`):

```bash
docker compose build
docker compose up          # web UI on http://localhost:5000
```

Local (falls back to RapidOCR if `docling-surya` is missing):

```bash
pip install -r requirements.txt
python app.py                                   # web UI
INPUT_PDF=PDF_Original/Easy/PDF_Deid_Deidentification_0.pdf python claim_parser.py   # CLI
```

## Tests

```bash
pytest tests
```

The detector is stdlib-only, so tests run without Docling or OCR models.

> The detector flags documents for **human review**; it does not prove fraud.
