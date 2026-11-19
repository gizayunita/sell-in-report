import argparse
import csv
import re
import sys
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from google.cloud import storage


SCHEMA_FILE = Path(__file__).with_name("anchanto_validation.csv")
MAX_EXAMPLES = 5


def load_schema():
    with SCHEMA_FILE.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))

    if not rows:
        raise RuntimeError(f"Validation schema is empty: {SCHEMA_FILE}")

    for row in rows:
        row["field_name"] = row["field_name"].strip()
        row["data_type"] = row["data_type"].strip().upper()
        row["nullable"] = row["nullable"].strip().lower() == "true"
        row["date_format"] = (row.get("date_format") or "").strip()

    return rows


def validate_value(value, field):
    value = (value or "").strip()

    if not value:
        return None if field["nullable"] else "required value is blank"

    data_type = field["data_type"]

    if data_type == "STRING":
        # IDs remain strings. Scientific notation is suspicious for identifier fields.
        if field["field_name"] in ("order_number", "item_upc"):
            if re.fullmatch(r"[+-]?\d+(?:\.\d+)?[eE][+-]?\d+", value):
                return "identifier appears to be in scientific notation"
        return None

    if data_type == "DATETIME":
        try:
            datetime.strptime(value, field["date_format"])
            return None
        except ValueError:
            return f"expected datetime format {field['date_format']}"

    if data_type == "INT64":
        if not re.fullmatch(r"[+-]?\d+", value):
            return "expected whole number (INT64)"
        try:
            number = int(value)
            if number < -(2**63) or number > 2**63 - 1:
                return "value is outside INT64 range"
        except ValueError:
            return "invalid INT64"
        return None

    if data_type == "FLOAT64":
        try:
            number = Decimal(value)
            if not number.is_finite():
                return "numeric value must be finite"
        except (InvalidOperation, ValueError):
            return "expected numeric value (FLOAT64)"
        return None

    return f"unsupported schema type: {data_type}"


def validate_blob(blob, schema):
    expected_headers = [field["field_name"] for field in schema]
    expected_lookup = {name.lower(): field for name, field in zip(expected_headers, schema)}
    counts = Counter()
    examples = {}
    errors = []

    print(f"\nFILE: gs://{blob.bucket.name}/{blob.name}", flush=True)

    with blob.open("rt", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)

        try:
            actual_headers = next(reader)
        except StopIteration:
            return 0, ["CSV is empty"], counts, examples

        normalized_headers = [header.strip().lower() for header in actual_headers]

        if normalized_headers != [name.lower() for name in expected_headers]:
            errors.append(
                "Header mismatch. "
                f"Expected {expected_headers}; received {actual_headers}"
            )

        duplicate_headers = [
            name for name, count in Counter(normalized_headers).items() if count > 1
        ]
        if duplicate_headers:
            errors.append(f"Duplicate headers: {duplicate_headers}")

        row_count = 0
        for row_number, values in enumerate(reader, start=2):
            row_count += 1
            counts["rows"] += 1

            if not values or all(not str(value).strip() for value in values):
                counts["blank_rows"] += 1
                continue

            if len(values) != len(expected_headers):
                counts["wrong_column_count"] += 1
                examples.setdefault("wrong_column_count", [])
                if len(examples["wrong_column_count"]) < MAX_EXAMPLES:
                    examples["wrong_column_count"].append(
                        f"row {row_number}: expected {len(expected_headers)} fields, got {len(values)}"
                    )
                continue

            # Repeated header inside data rows.
            if [str(v).strip().lower() for v in values] == [h.lower() for h in expected_headers]:
                counts["repeated_header_rows"] += 1
                examples.setdefault("repeated_header_rows", [])
                if len(examples["repeated_header_rows"]) < MAX_EXAMPLES:
                    examples["repeated_header_rows"].append(f"row {row_number}")
                continue

            for column_index, field in enumerate(schema):
                value = values[column_index]
                issue = validate_value(value, field)
                if issue:
                    key = f"{field['field_name']} - {issue}"
                    counts[key] += 1
                    examples.setdefault(key, [])
                    if len(examples[key]) < MAX_EXAMPLES:
                        examples[key].append(
                            f"row {row_number}: {value[:100]!r}"
                        )

    for key, count in counts.items():
        if key in ("rows", "blank_rows"):
            continue
        errors.append(f"{key}: {count} occurrence(s)")

    print(f"Rows checked: {row_count:,}")
    print(f"Blank rows: {counts['blank_rows']:,}")
    print(f"Wrong column count: {counts['wrong_column_count']:,}")
    print(f"Repeated header rows: {counts['repeated_header_rows']:,}")

    for key, values in examples.items():
        print(f"  {key}:")
        for value in values:
            print(f"    - {value}")

    for error in errors:
        print(f"  ERROR: {error}")

    return row_count, errors, counts, examples


def parse_gcs_uri(uri):
    if not uri.startswith("gs://"):
        raise ValueError("GCS URI must start with gs://")
    path = uri[5:]
    bucket_name, separator, prefix = path.partition("/")
    if not bucket_name:
        raise ValueError("GCS URI is missing bucket name")
    return bucket_name, prefix if separator else ""


def main():
    parser = argparse.ArgumentParser(
        description="Validate Anchanto CSV data in GCS against the reference schema."
    )
    parser.add_argument(
        "--gcs-uri",
        required=True,
        help="GCS object or prefix, e.g. gs://bucket-name/path/to/anchanto/",
    )
    args = parser.parse_args()

    schema = load_schema()
    bucket_name, prefix = parse_gcs_uri(args.gcs_uri)

    print("=" * 72)
    print("ANCHANTO GCS CSV VALIDATION")
    print("=" * 72)
    print(f"Reference schema: {SCHEMA_FILE}")
    print(f"GCS source: gs://{bucket_name}/{prefix}")
    print("ID columns order_number and item_upc are validated as STRING.")

    client = storage.Client()
    bucket = client.bucket(bucket_name)

    if prefix.lower().endswith(".csv"):
        blobs = [bucket.get_blob(prefix)]
        blobs = [blob for blob in blobs if blob is not None]
    else:
        blobs = [
            blob for blob in client.list_blobs(bucket_name, prefix=prefix)
            if blob.name.lower().endswith(".csv")
        ]

    if not blobs:
        raise RuntimeError(f"No CSV files found at {args.gcs_uri}")

    total_rows = 0
    failed_files = []

    for blob in sorted(blobs, key=lambda item: item.name):
        try:
            row_count, errors, _, _ = validate_blob(blob, schema)
            total_rows += row_count
            if errors:
                failed_files.append(blob.name)
        except Exception as exc:
            failed_files.append(blob.name)
            print(f"ERROR reading {blob.name}: {exc}")

    print("\n" + "=" * 72)
    print(f"Files checked: {len(blobs)}")
    print(f"Total rows checked: {total_rows:,}")
    print(f"Files with validation errors: {len(failed_files)}")
    if failed_files:
        print("FAILED FILES:")
        for name in failed_files:
            print(f"  - gs://{bucket_name}/{name}")
        print("VALIDATION FAILED. Stop before loading to BigQuery.")
        sys.exit(1)

    print("VALIDATION PASSED. All checked CSV files match the reference schema.")
    print("=" * 72)


if __name__ == "__main__":
    main()
