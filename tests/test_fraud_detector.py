import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fraud_detector import analyze_claim, parse_date, extract_fields  # noqa: E402

TODAY = date(2025, 6, 1)

CLEAN = """
Patient Summary
Anna Kimberly Delacruz, born on 18/06/1968, is a 57-year-old female. History of Type 2 Diabetes Mellitus.

Name: Anna Kimberly Delacruz
DOB: 18/06/1968
Age: 57
Sex: Female
SSN: 190-52-9537
Hospital ID: HOSP26508961
Doctor Unique ID: DR14144B
Heart Rate: 72
Respiratory Rate: 16
Temperature Celsius: 36.7
Oxygen Saturation Percent: 98
Blood Pressure: 130/85 mmHg
Recorded Date: 15/11/2024
"""


def rules(result):
    return {f["rule"] for f in result["flags"]}


def test_parse_date_ambiguity():
    assert len(parse_date("07/06/1949")) == 2
    assert parse_date("15/07/2005") == [date(2005, 7, 15)]
    assert parse_date("31/02/2005") == []


def test_clean_document_is_low_risk():
    r = analyze_claim(markdown=CLEAN, today=TODAY)
    assert r["risk_level"] == "low", r["flags"]
    assert r["fields"]["name"] == "Anna Kimberly Delacruz"
    assert r["fields"]["ssn"] == "190-52-9537"


def test_age_dob_mismatch_flagged():
    r = analyze_claim(markdown=CLEAN.replace("Age: 57", "Age: 38").replace("57-year", "38-year"), today=TODAY)
    assert "age_dob_inconsistent" in rules(r)


def test_header_vs_summary_mismatches():
    text = CLEAN.replace("born on 18/06/1968", "born on 02/02/1970").replace("Anna Kimberly Delacruz, ", "Bob Stone, ")
    r = analyze_claim(markdown=text, today=TODAY)
    assert {"dob_mismatch", "name_mismatch"} <= rules(r)
    assert r["risk_level"] == "high"


def test_invalid_ssn_and_vitals():
    text = CLEAN.replace("190-52-9537", "666-00-0000").replace("Heart Rate: 72", "Heart Rate: 400").replace("130/85", "80/120")
    r = analyze_claim(markdown=text, today=TODAY)
    assert {"invalid_ssn", "implausible_vital", "implausible_bp"} <= rules(r)


def test_date_order_and_future_dates():
    text = CLEAN + "\nPROCEDURE DATE: 28/04/2025\nRECEIVED DATE: 26/04/2025\nREPORT DATE: 25/04/2025\n"
    assert "date_order" in rules(analyze_claim(markdown=text, today=TODAY))
    text = CLEAN + "\nREPORT DATE: 28/04/2027\n"
    assert "future_date" in rules(analyze_claim(markdown=text, today=TODAY))


def test_table_rules():
    tables = [
        {"records": [{"Date": "15/10/2024", "Reason": "Check-up"}, {"Date": "15/10/2024", "Reason": "Flu"},
                     {"Date": "01/01/1960", "Reason": "Exam"}]},
        {"records": [{"Medication Test": "ECG", "Status": "Done", "On/Last": "01/01/2030"}]},
    ]
    r = analyze_claim(markdown=CLEAN, tables=tables, today=TODAY)
    assert {"duplicate_visits", "visit_before_birth", "done_test_in_future"} <= rules(r)


def test_empty_document_is_high_risk():
    r = analyze_claim({"markdown": "", "tables": []}, today=TODAY)
    assert r["risk_level"] == "high" and "no_content" in rules(r)


def test_score_is_capped():
    text = CLEAN.replace("190-52-9537", "000-00-0000").replace("Heart Rate: 72", "Heart Rate: 1") + "\nREPORT DATE: 01/01/2099\n"
    assert analyze_claim(markdown=text, today=TODAY)["risk_score"] <= 100


def test_repo_hard_sample_output():
    """Real Docling output shipped in the repo: mixed date formats + OCR-damaged name."""
    path = next((ROOT / "outputs").glob("*Hard_0*.json"))
    master = json.loads(path.read_text(encoding="utf-8"))
    r = analyze_claim(master, today=TODAY)
    assert r["fields"]["dob"] == "07/15/2005"
    assert "name_ocr_variance" in rules(r)
    assert "mixed_date_formats" in rules(r)
    assert len(r["fields"]["visits"]) == 6


@pytest.mark.parametrize("idx", range(30))
def test_repo_easy_pdfs_extract_core_fields(idx):
    pdf = ROOT / "PDF_Original" / "Easy" / f"PDF_Deid_Deidentification_{idx}.pdf"
    text = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True).stdout
    if not text.strip():
        pytest.skip("pdftotext unavailable or scanned PDF")
    f = extract_fields(text)
    assert f["name"] and f["dob"] and f["ssn"], f
    analyze_claim(markdown=text, today=date(2025, 6, 1))  # must not raise
