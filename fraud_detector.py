"""Rule-based fraud / anomaly detection for extracted patient-claim documents.

The detector works on the output of :func:`claim_parser.extract_claim_data`
(Markdown text plus table records).  It pulls out the key claim fields, runs a
set of consistency / plausibility rules and returns a risk assessment::

    {
      "risk_score": 0-100,
      "risk_level": "low" | "medium" | "high",
      "flags": [{"rule", "severity", "message", "evidence"}, ...],
      "fields": {...extracted fields...},
    }

It is deliberately dependency-free (stdlib only) so it can be unit tested
without Docling / OCR models installed.
"""

from __future__ import annotations

import html
import re
from collections import Counter
from datetime import date, datetime
from difflib import SequenceMatcher
from typing import Any

SEVERITY_WEIGHTS = {"high": 30, "medium": 15, "low": 5}
DATE_RE = r"\d{1,2}/\d{1,2}/\d{4}"
_WORD = r"[A-Za-z][A-Za-z'.\-]*"
# a name word that is not itself a "Label:"
_NAME_WORD = rf"{_WORD}(?![A-Za-z'.\-]|\s*:)"


# --------------------------------------------------------------------------- #
# Text helpers
# --------------------------------------------------------------------------- #
def normalize_text(text: str) -> str:
    """Strip Markdown / HTML noise left behind by OCR and table export."""
    text = html.unescape(text or "")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</?[a-zA-Z][^>]*>", "", text)
    text = re.sub(r"<!--.*?-->", "", text)
    text = re.sub(r"^#+\s*", "", text, flags=re.M)
    text = text.replace("|", " ")
    return text


def parse_date(value: str) -> list[date]:
    """Return candidate dates for ``dd/mm/yyyy`` or ``mm/dd/yyyy`` strings.

    Both interpretations are returned when the string is ambiguous.
    """
    match = re.fullmatch(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*", value or "")
    if not match:
        return []
    a, b, year = (int(g) for g in match.groups())
    candidates: list[date] = []
    for day, month in ((a, b), (b, a)):  # dd/mm first, then mm/dd
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def _first_date(value: str | None) -> date | None:
    candidates = parse_date(value or "")
    return candidates[0] if candidates else None


def _same_date(a: str | None, b: str | None) -> bool:
    return bool(set(parse_date(a or "")) & set(parse_date(b or "")))


def _age_on(dob: date, when: date) -> int:
    return when.year - dob.year - ((when.month, when.day) < (dob.month, dob.day))


def _clean_name(name: str | None) -> str | None:
    if not name:
        return None
    return re.sub(r"\s+", " ", name).strip(" .,-") or None


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


# --------------------------------------------------------------------------- #
# Field extraction
# --------------------------------------------------------------------------- #
def _search(pattern: str, text: str, flags: int = re.I) -> re.Match | None:
    return re.search(pattern, text, flags)


def extract_fields(markdown: str, tables: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Extract the claim fields used by the rules from raw document text."""
    text = normalize_text(markdown)
    fields: dict[str, Any] = {}

    # Structured demographics ------------------------------------------------
    m = _search(rf"(?:patient\s+)?name:\s*((?:{_NAME_WORD}\s*){{1,4}})", text)
    fields["name"] = _clean_name(m.group(1)) if m else None

    m = _search(rf"DOB:?\s*({DATE_RE})", text)
    fields["dob"] = m.group(1) if m else None

    m = _search(r"\bAge:\s*(\d{1,3})", text) or _search(rf"DOB:?\s*{DATE_RE}\s+(\d{{1,3}})\s*Y\b", text)
    fields["age"] = int(m.group(1)) if m else None

    m = _search(r"\bSex:\s*(male|female|other)", text) or _search(
        rf"DOB:?\s*{DATE_RE}(?:\s+\d{{1,3}}\s*Y)?\s+(male|female)\b", text
    )
    fields["sex"] = m.group(1).lower() if m else None

    m = _search(r"\bSSN:?\s*([\d\-Xx*]{9,11})", text)
    fields["ssn"] = m.group(1) if m else None

    m = _search(r"Hospital\s*ID:?\s*([A-Z0-9\-]+)", text)
    fields["hospital_id"] = m.group(1) if m else None
    m = _search(r"Doctor\s*Unique\s*ID:?\s*([A-Z0-9\-]+)", text)
    fields["doctor_id"] = m.group(1) if m else None
    m = _search(r"\bMRN:?\s*(\d+)", text)
    fields["mrn"] = m.group(1) if m else None
    m = _search(r"BILLING\s*NO:?\s*(\d+)", text)
    fields["billing_no"] = m.group(1) if m else None

    # Narrative summary ("X, born on D, is a 46-year-old Female ...") -------
    narrative: dict[str, Any] = {}
    m = re.search(
        rf"(?:^|[.\n])\s*({_WORD}(?: {_WORD}){{1,3}}),?\s+(?:was\s+)?born\s+on\s+({DATE_RE})",
        text,
        re.M,
    )
    if m:
        narrative["name"] = _clean_name(m.group(1))
        narrative["dob"] = m.group(2)
        window = text[m.end() : m.end() + 160]
        a = re.search(r"aged?\s+(\d{1,3})|(\d{1,3})[-\s]year[-\s]old", window, re.I)
        if a:
            narrative["age"] = int(a.group(1) or a.group(2))
        s = re.search(r"\b(female|male)\b", window, re.I)
        if s:
            narrative["sex"] = s.group(1).lower()
    fields["narrative"] = narrative

    # Vitals -----------------------------------------------------------------
    vitals: dict[str, Any] = {}
    for key, pattern in {
        "heart_rate": r"Heart\s*Rate:?\s*(\d+(?:\.\d+)?)",
        "respiratory_rate": r"Respiratory\s*Rate:?\s*(\d+(?:\.\d+)?)",
        "temperature_c": r"(?:emperature|Temperature)\s*Celsius:?\s*(\d+(?:\.\d+)?)",
        "oxygen_saturation": r"Oxygen\s*Saturation(?:\s*Percent)?:?\s*(\d+(?:\.\d+)?)",
    }.items():
        m = _search(pattern, text)
        if m:
            vitals[key] = float(m.group(1))
    m = _search(r"Blood\s*Pressure:?\s*(\d{2,3})\s*/\s*(\d{2,3})", text)
    if m:
        vitals["systolic"], vitals["diastolic"] = int(m.group(1)), int(m.group(2))
    fields["vitals"] = vitals

    # Document dates -----------------------------------------------------------
    dates: dict[str, str] = {}
    for key, label in {
        "recorded": r"Recorded\s*Date",
        "procedure": r"PROCEDURE\s*DATE",
        "received": r"RECEIVED\s*DATE",
        "report": r"REPORT\s*DATE",
    }.items():
        m = _search(rf"{label}:?\s*({DATE_RE})", text)
        if m:
            dates[key] = m.group(1)
    fields["dates"] = dates

    # Free-text doctor notes ---------------------------------------------------
    fields["has_diabetes"] = bool(_search(r"diabet", text))
    fields["medications"] = []

    # Tables -------------------------------------------------------------------
    visits: list[dict[str, str]] = []
    tests: list[dict[str, str]] = []
    for table in tables or []:
        for record in table.get("records") or []:
            norm = {normalize_text(str(k)).strip().lower(): (v if v is None else normalize_text(str(v)).strip()) for k, v in record.items()}
            if "reason" in norm and "date" in norm:
                visits.append({"date": norm["date"] or "", "reason": norm["reason"] or ""})
            elif "status" in norm:
                name_key = next((k for k in norm if k not in {"status", "on/last"}), None)
                tests.append(
                    {
                        "name": (norm.get(name_key) or "") if name_key else "",
                        "status": (norm["status"] or "").lower(),
                        "date": norm.get("on/last") or "",
                    }
                )
            elif "dosage" in norm:
                med_key = next((k for k in norm if k not in {"dosage", "frequency"}), None)
                if med_key and norm.get(med_key):
                    fields["medications"].append(norm[med_key])

    # Fall back to Markdown/text table rows when Docling returned no tables.
    if not visits:
        visits = [
            {"date": d, "reason": r.strip()}
            for d, r in re.findall(rf"^\s*({DATE_RE})\s{{2,}}(\S.*)$", text, re.M)
            if not re.search(r"done|pending", r, re.I)
        ]
    fields["visits"] = visits
    fields["tests"] = tests
    return fields


# --------------------------------------------------------------------------- #
# Rules
# --------------------------------------------------------------------------- #
class _Flags:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def add(self, rule: str, severity: str, message: str, evidence: Any = None) -> None:
        self.items.append(
            {"rule": rule, "severity": severity, "message": message, "evidence": evidence}
        )


def _check_identity(f: dict[str, Any], flags: _Flags, today: date) -> None:
    n = f["narrative"]

    if f["name"] and n.get("name") and f["name"].lower() != n["name"].lower():
        ratio = _similarity(f["name"], n["name"])
        if ratio >= 0.8:
            flags.add("name_ocr_variance", "low",
                      "Patient name differs slightly between sections (likely OCR damage).",
                      {"header": f["name"], "summary": n["name"]})
        else:
            flags.add("name_mismatch", "high",
                      "Patient name differs between the header and the summary.",
                      {"header": f["name"], "summary": n["name"]})

    if f["dob"] and n.get("dob") and not _same_date(f["dob"], n["dob"]):
        flags.add("dob_mismatch", "high", "Date of birth differs between sections.",
                  {"header": f["dob"], "summary": n["dob"]})

    if f["age"] is not None and n.get("age") is not None and f["age"] != n["age"]:
        flags.add("age_mismatch", "medium", "Stated age differs between sections.",
                  {"header": f["age"], "summary": n["age"]})

    if f["sex"] and n.get("sex") and f["sex"] != n["sex"]:
        flags.add("sex_mismatch", "medium", "Sex differs between sections.",
                  {"header": f["sex"], "summary": n["sex"]})

    dob_str = f["dob"] or n.get("dob")
    age = f["age"] if f["age"] is not None else n.get("age")
    dob_candidates = parse_date(dob_str or "")
    if dob_str and not dob_candidates:
        flags.add("invalid_dob", "high", "Date of birth is not a valid calendar date.", dob_str)
    if dob_candidates:
        if all(c > today for c in dob_candidates):
            flags.add("future_dob", "high", "Date of birth is in the future.", dob_str)
        elif age is not None:
            ref = _first_date(f["dates"].get("report") or f["dates"].get("recorded")) or today
            # Use the best-fitting interpretation of an ambiguous date.
            best = min(abs(_age_on(c, ref) - age) for c in dob_candidates if c <= ref) if any(c <= ref for c in dob_candidates) else None
            if best is not None and best >= 2:
                flags.add("age_dob_inconsistent", "high" if best >= 10 else "medium",
                          "Stated age does not match the date of birth.",
                          {"dob": dob_str, "stated_age": age, "difference_years": best})
            elif best == 1:
                flags.add("age_dob_off_by_one", "low",
                          "Stated age is one year off the date of birth.",
                          {"dob": dob_str, "stated_age": age})

    ssn = f["ssn"]
    if not ssn:
        flags.add("missing_ssn", "low", "No SSN found in the document.")
    elif re.fullmatch(r"\d{3}-?\d{2}-?\d{4}", ssn):
        digits = ssn.replace("-", "")
        area, group, serial = digits[:3], digits[3:5], digits[5:]
        if area in {"000", "666"} or area.startswith("9") or group == "00" or serial == "0000":
            flags.add("invalid_ssn", "high", "SSN uses a range that is never issued.", ssn)
        elif len(set(digits)) == 1 or digits in {"123456789", "987654321"}:
            flags.add("fake_ssn_pattern", "high", "SSN looks like a placeholder.", ssn)
    else:
        flags.add("malformed_ssn", "medium", "SSN is not in NNN-NN-NNNN form.", ssn)

    for key, label, pattern in (
        ("hospital_id", "Hospital ID", r"HOSP\d{8}"),
        ("doctor_id", "Doctor ID", r"DR\d{5}[A-Z]"),
    ):
        value = f[key]
        if value and not re.fullmatch(pattern, value):
            flags.add(f"malformed_{key}", "low", f"{label} does not follow the usual format.", value)


def _check_dates(f: dict[str, Any], flags: _Flags, today: date) -> None:
    d = f["dates"]
    parsed = {k: _first_date(v) for k, v in d.items()}
    dob_cands = parse_date(f["dob"] or f["narrative"].get("dob") or "")
    dob = dob_cands[0] if dob_cands else None

    for key, value in d.items():
        if not parse_date(value):
            flags.add("invalid_date", "medium", f"{key.title()} date is not a valid calendar date.", value)
        elif all(c > today for c in parse_date(value)):
            flags.add("future_date", "high", f"{key.title()} date is in the future.", value)
        elif dob and all(c < dob for c in parse_date(value)):
            flags.add("date_before_birth", "high", f"{key.title()} date is before the patient's birth.", value)

    # Procedure -> received -> report must be chronological.  Because the
    # format can be dd/mm or mm/dd, pick the interpretation that works if any.
    chain = [k for k in ("procedure", "received", "report") if k in d and parse_date(d[k])]
    for earlier, later in zip(chain, chain[1:]):
        if all(a > b for a in parse_date(d[earlier]) for b in parse_date(d[later])):
            flags.add("date_order", "high",
                      f"{later.title()} date is before the {earlier} date.",
                      {earlier: d[earlier], later: d[later]})

    if "procedure" in d and "report" in d and parsed.get("procedure") and parsed.get("report"):
        gap = (parsed["report"] - parsed["procedure"]).days
        if gap > 180:
            flags.add("stale_report", "medium", "Report was issued long after the procedure.",
                      {"days": gap})

    # Mixed date formats inside one document.
    formats = set()
    for value in list(d.values()) + [f["dob"] or ""] + [v["date"] for v in f["visits"]]:
        m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/\d{4}", value or "")
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a > 12:
                formats.add("DD/MM")
            elif b > 12:
                formats.add("MM/DD")
    if len(formats) > 1:
        flags.add("mixed_date_formats", "medium",
                  "Document mixes DD/MM/YYYY and MM/DD/YYYY dates, which can hide tampering.")
    narrative_dob, header_dob = f["narrative"].get("dob"), f["dob"]
    if narrative_dob and header_dob and narrative_dob != header_dob and _same_date(narrative_dob, header_dob):
        flags.add("dob_format_differs", "low",
                  "Date of birth is written in different formats in different sections.",
                  {"header": header_dob, "summary": narrative_dob})

    # Visits / tests -----------------------------------------------------------
    visit_dates = [v["date"] for v in f["visits"] if v["date"]]
    for v in visit_dates:
        cands = parse_date(v)
        if not cands:
            flags.add("invalid_date", "medium", "A past-visit date is not valid.", v)
        elif all(c > today for c in cands):
            flags.add("future_visit", "high", "A past hospital visit is dated in the future.", v)
        elif dob and all(c < dob for c in cands):
            flags.add("visit_before_birth", "high", "A hospital visit predates the patient's birth.", v)
    dupes = [v for v, c in Counter(visit_dates).items() if c > 1]
    if dupes:
        flags.add("duplicate_visits", "medium", "The same visit date appears more than once.", dupes)
    reasons = Counter(v["reason"].lower() for v in f["visits"] if v["reason"])
    repeated = [r for r, c in reasons.items() if c >= 3]
    if repeated:
        flags.add("repeated_visit_reason", "low", "The same visit reason is repeated 3+ times.", repeated)

    ref_report = parsed.get("report") or parsed.get("recorded")
    for t in f["tests"]:
        cands = parse_date(t["date"])
        if not cands:
            continue
        if t["status"] == "done" and all(c > today for c in cands):
            flags.add("done_test_in_future", "high", "A test marked 'Done' has a future date.", t)
        elif t["status"] == "pending" and ref_report and all(c < ref_report for c in cands):
            # A test still "pending" long before the report was issued.
            if (ref_report - max(cands)).days > 30:
                flags.add("stale_pending_test", "low",
                          "A test is still pending although its date is long past.", t)


def _check_vitals(f: dict[str, Any], flags: _Flags) -> None:
    v = f["vitals"]
    limits = {
        "heart_rate": (30, 220, "Heart rate"),
        "respiratory_rate": (5, 60, "Respiratory rate"),
        "temperature_c": (32.0, 43.0, "Temperature"),
        "oxygen_saturation": (50, 100, "Oxygen saturation"),
    }
    for key, (lo, hi, label) in limits.items():
        if key in v and not lo <= v[key] <= hi:
            flags.add("implausible_vital", "high", f"{label} is outside the survivable range.",
                      {key: v[key]})
    if "systolic" in v:
        s, d = v["systolic"], v["diastolic"]
        if s <= d:
            flags.add("implausible_bp", "high", "Systolic pressure is not above diastolic.", f"{s}/{d}")
        elif not (60 <= s <= 260 and 30 <= d <= 160):
            flags.add("implausible_bp", "high", "Blood pressure is outside the plausible range.", f"{s}/{d}")
    if not v:
        flags.add("missing_vitals", "low", "No vitals found in the document.")


def _check_clinical(f: dict[str, Any], flags: _Flags) -> None:
    diabetes_meds = {"metformin", "insulin", "glipizide", "glimepiride", "sitagliptin"}
    meds = {m.lower().split()[0] for m in f["medications"] if m}
    if meds & diabetes_meds and not f["has_diabetes"]:
        flags.add("medication_without_diagnosis", "medium",
                  "Diabetes medication is listed but no diabetes diagnosis appears.",
                  sorted(meds & diabetes_meds))
    dup_meds = [m for m, c in Counter(x.lower() for x in f["medications"]).items() if c > 1]
    if dup_meds:
        flags.add("duplicate_medications", "low", "A medication is listed more than once.", dup_meds)


def _check_completeness(f: dict[str, Any], flags: _Flags) -> None:
    missing = [k for k in ("name", "dob") if not f[k] and not f["narrative"].get(k)]
    if missing:
        flags.add("missing_core_fields", "high",
                  "Core identity fields could not be found.", missing)
    if not f["doctor_id"] and not f["hospital_id"] and not f["mrn"] and not f["billing_no"]:
        flags.add("missing_identifiers", "medium",
                  "No hospital, doctor, MRN or billing identifiers found.")


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def risk_level(score: int) -> str:
    return "high" if score >= 50 else "medium" if score >= 20 else "low"


def analyze_claim(
    master: dict[str, Any] | None = None,
    *,
    markdown: str | None = None,
    tables: list[dict[str, Any]] | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Run all fraud rules over an extraction result and score it.

    Pass either the ``master`` dict from ``extract_claim_data`` or raw
    ``markdown`` / ``tables``.  ``today`` is injectable for deterministic tests.
    """
    if master is not None:
        markdown = master.get("markdown", "")
        tables = master.get("tables", [])
    today = today or datetime.now().date()

    fields = extract_fields(markdown or "", tables)
    flags = _Flags()
    if not (markdown or "").strip():
        flags.add("no_content", "high", "No text could be extracted from the document.")
    else:
        _check_completeness(fields, flags)
        _check_identity(fields, flags, today)
        _check_dates(fields, flags, today)
        _check_vitals(fields, flags)
        _check_clinical(fields, flags)

    order = {"high": 0, "medium": 1, "low": 2}
    items = sorted(flags.items, key=lambda x: order[x["severity"]])
    score = min(100, sum(SEVERITY_WEIGHTS[x["severity"]] for x in items))
    if any(x["rule"] == "no_content" for x in items):
        score = max(score, 50)  # an unreadable document can never be "low/medium"
    return {
        "risk_score": score,
        "risk_level": risk_level(score),
        "flag_count": len(items),
        "flags": items,
        "fields": fields,
    }
