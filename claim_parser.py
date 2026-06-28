"""Local Docling pipeline for extracting invoice and discharge-summary content.

This module configures Docling with Surya OCR, processes a local PDF, exports
the full document to Markdown, extracts all detected tables as JSON-safe records,
and writes a combined master dictionary to ``extracted_claim.json``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    OcrEngine,
    PdfPipelineOptions,
    RapidOcrOptions,
    TableStructureOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption

try:
    from docling_surya import SuryaOcrOptions
except ImportError:
    SuryaOcrOptions = None


def get_converter() -> tuple[DocumentConverter, list[str]]:
    """Build and return a Docling converter configured for local PDF OCR.

    Returns:
        A tuple containing the configured ``DocumentConverter`` and any setup
        warnings generated while selecting the OCR backend.
    """

    warnings: list[str] = []

    pipeline_kwargs: dict[str, Any] = {
        "do_ocr": True,
        "allow_external_plugins": True,
        "do_table_structure": True,
        "table_structure_options": TableStructureOptions(do_cell_matching=True),
    }

    if SuryaOcrOptions is not None:
        pipeline_kwargs["ocr_options"] = SuryaOcrOptions(lang=["en"])
    else:
        pipeline_kwargs["ocr_options"] = RapidOcrOptions(lang=["en"])
        warnings.append(
            "docling-surya is not installed in this environment; "
            "falling back to RapidOCR."
        )

    pipeline_options = PdfPipelineOptions(**pipeline_kwargs)

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline_options,
                ocr_options=pipeline_kwargs["ocr_options"],
            )
        }
    )
    return converter, warnings


def _table_page_number(table: Any) -> int | None:
    """Safely read the first provenance page number for a table."""

    provenance = getattr(table, "prov", None)
    if not provenance:
        return None

    first_entry = provenance[0]
    return getattr(first_entry, "page_no", None)


def _dataframe_to_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert a DataFrame to JSON-safe record dictionaries."""

    normalized = frame.copy()
    normalized = normalized.where(pd.notna(normalized), None)
    return normalized.to_dict(orient="records")


def extract_claim_data(
    pdf_path: str | Path,
    converter: DocumentConverter,
    setup_warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Parse a PDF and return Markdown plus structured table payloads.

    Args:
        pdf_path: Local path to the PDF to process.
        converter: A Docling ``DocumentConverter`` configured for PDF parsing.

    Returns:
        A master dictionary containing the document markdown, extracted tables,
        source metadata, and any recoverable processing errors.
    """

    source_path = Path(pdf_path).expanduser()
    master: dict[str, Any] = {
        "source_path": str(source_path),
        "markdown": "",
        "tables": [],
        "table_count": 0,
        "errors": [],
        "warnings": list(setup_warnings or []),
    }

    if not source_path.exists():
        master["errors"].append(f"File not found: {source_path}")
        return master

    if not source_path.is_file():
        master["errors"].append(f"Path is not a file: {source_path}")
        return master

    try:
        result = converter.convert(source_path)
    except Exception as exc:
        master["errors"].append(f"Conversion failed for {source_path.name}: {exc}")
        return master

    document = result.document
    master["markdown"] = document.export_to_markdown()

    tables: list[dict[str, Any]] = []
    for index, table in enumerate(getattr(document, "tables", []) or [], start=1):
        try:
            frame = table.export_to_dataframe(doc=document)
            tables.append(
                {
                    "table_index": index,
                    "page_no": _table_page_number(table),
                    "records": _dataframe_to_records(frame),
                }
            )
        except Exception as exc:
            master["errors"].append(
                f"Table {index} on page {_table_page_number(table)} could not be exported: {exc}"
            )

    master["tables"] = tables
    master["table_count"] = len(tables)
    return master


def main() -> None:
    """Run a sample extraction and persist the output to JSON."""

    input_pdf = Path(r"PDF_Original\Easy\PDF_Deid_Deidentification_0.pdf")
    output_dir = Path("outputs")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_name_parts = [part for part in input_pdf.with_suffix("").parts if part not in {".", ".."}]
    output_json = output_dir / f"{'_'.join(output_name_parts)}_extracted_claim.json"

    converter, setup_warnings = get_converter()
    master = extract_claim_data(input_pdf, converter, setup_warnings)

    output_json.write_text(json.dumps(master, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Input PDF: {input_pdf.resolve()}")
    print(f"Wrote {output_json.resolve()}")


if __name__ == "__main__":
    main()
