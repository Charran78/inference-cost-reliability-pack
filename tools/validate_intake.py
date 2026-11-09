import argparse
import json
import re
import sys
from pathlib import Path

TASK_TYPES = {
    "information_extraction",
    "procedure_following",
    "troubleshooting",
    "calculation",
    "structured_output",
}
SELECTION_BUCKETS = {"high_volume", "boundary_case", "current_model_failure"}
ALLOWED_FIELDS = {
    "id", "task_type", "selection_bucket", "prompt", "expected_output",
    "context", "source_ref", "tags",
}
EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])")
PHONE_RE = re.compile(
    r"(?<!\w)(?:\+\d{1,3}[ .()-]?)?(?:\(?\d{2,4}\)?[ .-]){2,4}\d{2,4}(?!\w)"
)
ISO_DATE_RE = re.compile(r"(?:19|20)\d{2}[-/.]\d{1,2}[-/.]\d{1,2}")
IBAN_RE = re.compile(r"(?<![A-Z0-9])[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30}(?![A-Z0-9])", re.I)
SSN_RE = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
DNI_NIE_RE = re.compile(r"(?<!\w)(?:\d{8}[A-HJ-NP-TV-Z]|[XYZ]\d{7}[A-HJ-NP-TV-Z])(?!\w)", re.I)
LABELED_NAME_RE = re.compile(
    r"\b(?:full\s+name|name|contact|customer|patient|employee|operator|"
    r"nombre|contacto|cliente|paciente|empleado|operario)\s*[:=]\s*"
    r"[A-ZÀ-ÖØ-Þ][\wÀ-ÖØ-öø-ÿ'-]+(?:\s+[A-ZÀ-ÖØ-Þ][\wÀ-ÖØ-öø-ÿ'-]+){1,2}",
    re.I,
)
SALUTATION_NAME_RE = re.compile(
    r"\b(?:dear|attn\.?|sr\.?|sra\.?|dr\.?|mr\.?|mrs\.?|ms\.?)\s+"
    r"[A-ZÀ-ÖØ-Þ][\wÀ-ÖØ-öø-ÿ'-]+\s+[A-ZÀ-ÖØ-Þ][\wÀ-ÖØ-öø-ÿ'-]+",
    re.I,
)


def _iban_is_valid(value):
    compact = re.sub(r"\s", "", value).upper()
    if not 15 <= len(compact) <= 34 or not compact.isalnum():
        return False
    rearranged = compact[4:] + compact[:4]
    remainder = 0
    for character in rearranged:
        digits = str(ord(character) - 55) if character.isalpha() else character
        for digit in digits:
            remainder = (remainder * 10 + int(digit)) % 97
    return remainder == 1


def _walk_strings(value, path="$ "):
    if isinstance(value, str):
        yield path.strip(), value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from _walk_strings(child, f"{path.strip()}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_strings(child, f"{path.strip()}[{index}]")


def validate_schema(records):
    """Return structural/schema errors without including record contents."""
    errors = []
    seen_ids = {}
    for line_number, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            errors.append(f"line {line_number}: record must be a JSON object")
            continue
        for field in ("id", "task_type", "selection_bucket", "prompt", "expected_output"):
            if field not in record:
                errors.append(f"line {line_number}: missing required field `{field}`")
        unknown = set(record) - ALLOWED_FIELDS
        if unknown:
            errors.append(f"line {line_number}: unsupported field(s): {', '.join(sorted(unknown))}")

        for field in ("id", "prompt"):
            if field in record and (not isinstance(record[field], str) or not record[field].strip()):
                errors.append(f"line {line_number}: `{field}` must be a non-empty string")
        task_type = record.get("task_type")
        if not isinstance(task_type, str) or task_type not in TASK_TYPES:
            errors.append(f"line {line_number}: invalid `task_type`")
        selection_bucket = record.get("selection_bucket")
        if not isinstance(selection_bucket, str) or selection_bucket not in SELECTION_BUCKETS:
            errors.append(f"line {line_number}: invalid `selection_bucket`")

        if "expected_output" in record:
            expected = record["expected_output"]
            if expected is None or expected == "" or expected == {} or expected == []:
                errors.append(f"line {line_number}: `expected_output` must not be empty")
            elif not isinstance(expected, (str, dict)):
                errors.append(f"line {line_number}: `expected_output` must be a string or JSON object")
            elif isinstance(expected, str) and not expected.strip():
                errors.append(f"line {line_number}: `expected_output` must not be blank")

        for field in ("context", "source_ref"):
            if field in record and not isinstance(record[field], str):
                errors.append(f"line {line_number}: `{field}` must be a string")
        if "source_ref" in record and isinstance(record["source_ref"], str) and not record["source_ref"].strip():
            errors.append(f"line {line_number}: `source_ref` must not be blank")
        if "tags" in record and (
            not isinstance(record["tags"], list)
            or any(not isinstance(tag, str) for tag in record["tags"])
        ):
            errors.append(f"line {line_number}: `tags` must be an array of strings")

        case_id = record.get("id")
        if isinstance(case_id, str) and case_id:
            if case_id in seen_ids:
                errors.append(f"line {line_number}: duplicate `id` (first seen on line {seen_ids[case_id]})")
            else:
                seen_ids[case_id] = line_number
    return errors


def detect_pii(records):
    """Return PII-pattern findings by line and field path; never echo matched text."""
    findings = []
    for line_number, record in enumerate(records, start=1):
        for field_path, text in _walk_strings(record):
            if EMAIL_RE.search(text):
                findings.append(f"line {line_number} {field_path}: possible PII (email)")
            if SSN_RE.search(text) or DNI_NIE_RE.search(text):
                findings.append(f"line {line_number} {field_path}: possible PII (government_id)")
            if any(_iban_is_valid(match.group(0)) for match in IBAN_RE.finditer(text)):
                findings.append(f"line {line_number} {field_path}: possible PII (iban)")
            for match in PHONE_RE.finditer(text):
                candidate = match.group(0)
                digit_count = len(re.sub(r"\D", "", candidate))
                if not ISO_DATE_RE.fullmatch(candidate) and 8 <= digit_count <= 15:
                    findings.append(f"line {line_number} {field_path}: possible PII (phone)")
                    break
            if LABELED_NAME_RE.search(text) or SALUTATION_NAME_RE.search(text):
                findings.append(f"line {line_number} {field_path}: possible PII (proper_name_heuristic)")
    return findings


def _read_jsonl(path):
    records = []
    errors = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        return [], [f"cannot read intake file: {error.strerror or error}"]
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as error:
            errors.append(f"line {line_number}: invalid JSON ({error.msg})")
    if not records and not errors:
        errors.append("intake file contains no records")
    return records, errors


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate private domain_set.jsonl before evaluation.")
    parser.add_argument("path", type=Path, help="Client-provided JSONL intake")
    args = parser.parse_args(argv)
    records, errors = _read_jsonl(args.path)
    errors.extend(validate_schema(records))
    errors.extend(detect_pii(records))
    if errors:
        print(f"Rejected: {len(errors)} validation issue(s).", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Accepted: schema checks passed; no configured PII patterns detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())