# Docker + Surya Setup

This project can run `docling-surya` only in a Linux x86_64 environment with Python 3.12+.

## Prerequisites

- Docker Desktop installed on Windows
- WSL2 backend enabled in Docker Desktop

## Build

```powershell
docker compose build
```

## Run the default Hard sample

```powershell
docker compose run --rm claim-parser-surya
```

This uses:

- `INPUT_PDF=/workspace/PDF_Original/Hard/PDF_Deid_Deidentification_Hard_0.pdf`
- `OUTPUT_DIR=/workspace/outputs`

The JSON will be written into the repo's `outputs/` folder on Windows.

## Run a different PDF

```powershell
docker compose run --rm `
  -e INPUT_PDF=/workspace/PDF_Original/Easy/PDF_Deid_Deidentification_0.pdf `
  claim-parser-surya
```

## Output naming

The parser writes path-aware filenames such as:

```text
outputs/PDF_Original_Hard_PDF_Deid_Deidentification_Hard_0_extracted_claim.json
```

## Notes

- The first run will download model weights into the Docker volume `huggingface-cache`.
- The parser script accepts `INPUT_PDF` and `OUTPUT_DIR` via environment variables.
- If you want to change the default sample path, update `default_pdf` in `claim_parser.py`.
