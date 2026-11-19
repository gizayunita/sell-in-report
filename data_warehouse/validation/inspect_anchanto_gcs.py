import argparse
import csv
import re
from collections import Counter
from datetime import datetime
from google.cloud import storage

DEFAULT_PREFIX = "sales_parquet/raw/online/anchanto/scrwms/"
SENSITIVE_COLUMNS = {"customer_name", "phone", "email", "address"}
DATETIME_FORMAT = "%d/%m/%Y, %H:%M:%S"
MAX_SAMPLE_ROWS = 3
MAX_INSPECT_ROWS = 5000


def safe_sample(headers, row):
    output = {}
    for index, header in enumerate(headers):
        value = row[index] if index < len(row) else ""
        if header.strip().lower() in SENSITIVE_COLUMNS and value:
            output[header] = "[REDACTED]"
        else:
            output[header] = value[:100]
    return output


def inspect_file(blob):
    print("\n" + "=" * 90)
    print(f"FILE: gs://{blob.bucket.name}/{blob.name}")
    print(f"SIZE: {blob.size:,} bytes")
    print(f"UPDATED: {blob.updated}")

    counts = Counter()
    samples = []
    date_examples = {}
    header = None
    row_count = 0
    width_counts = Counter()

    with blob.open("rt", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        try:
            header = next(reader)
        except StopIteration:
            print("STATUS: EMPTY CSV")
            return

        clean_headers = [str(value).strip() for value in header]
        print(f"COLUMN COUNT: {len(clean_headers)}")
        print("HEADERS:")
        for position, name in enumerate(clean_headers, start=1):
            print(f"  {position:02d}. {name}")

        duplicates = [name for name, count in Counter(x.lower() for x in clean_headers).items() if count > 1]
        print(f"DUPLICATE HEADERS: {duplicates if duplicates else 'None'}")

        for row_number, row in enumerate(reader, start=2):
            row_count += 1
            width_counts[len(row)] += 1
            if not row or all(not str(value).strip() for value in row):
                counts["blank_rows"] += 1
                continue

            if len(samples) < MAX_SAMPLE_ROWS:
                samples.append((row_number, safe_sample(clean_headers, row)))

            if len(row) != len(clean_headers):
                counts["wrong_column_count"] += 1
                continue

            for index, name in enumerate(clean_headers):
                value = (row[index] or "").strip()
                if not value:
                    counts[f"blank::{name}"] += 1
                    continue

                lower_name = name.lower()
                if "date" in lower_name or lower_name.endswith("_on"):
                    date_examples.setdefault(name, {"valid": 0, "invalid": 0, "examples": []})
                    try:
                        datetime.strptime(value, DATETIME_FORMAT)
                        date_examples[name]["valid"] += 1
                    except ValueError:
                        date_examples[name]["invalid"] += 1
                        if len(date_examples[name]["examples"]) < 3:
                            date_examples[name]["examples"].append(value[:100])

            if row_count >= MAX_INSPECT_ROWS:
                break

    print(f"ROWS INSPECTED: {row_count:,}" + (" (inspection limit reached)" if row_count >= MAX_INSPECT_ROWS else ""))
    print(f"ROW WIDTH DISTRIBUTION: {dict(sorted(width_counts.items()))}")
    print(f"BLANK ROWS: {counts['blank_rows']:,}")
    print(f"ROWS WITH WRONG COLUMN COUNT: {counts['wrong_column_count']:,}")

    print("SAMPLE ROWS (customer name / phone / email / address are redacted):")
    for row_number, sample in samples:
        print(f"  Row {row_number}: {sample}")

    if date_examples:
        print("DATETIME FIELD CHECK (expected format: %d/%m/%Y, %H:%M:%S):")
        for name, result in date_examples.items():
            print(
                f"  {name}: valid={result['valid']:,}, invalid={result['invalid']:,}, "
                f"invalid_examples={result['examples']}"
            )

    print("BLANK COUNTS BY COLUMN:")
    for key, value in sorted(counts.items()):
        if key.startswith("blank::"):
            print(f"  {key.split('::', 1)[1]}: {value:,}")


def main():
    parser = argparse.ArgumentParser(description="Inspect Anchanto CSV files in GCS without loading BigQuery.")
    parser.add_argument("--gcs-uri", default=f"gs://bucket_som/{DEFAULT_PREFIX}")
    args = parser.parse_args()

    if not args.gcs_uri.startswith("gs://"):
        raise ValueError("--gcs-uri must start with gs://")

    bucket_and_prefix = args.gcs_uri[5:]
    bucket_name, separator, object_name = bucket_and_prefix.partition("/")
    if not bucket_name:
        raise ValueError("Missing GCS bucket name")

    # Explicit project is required because the GitHub secret uses end-user ADC credentials.
    client = storage.Client(project="datawarehouse-490008")
    bucket = client.bucket(bucket_name)

    if object_name.lower().endswith(".csv"):
        blobs = [bucket.get_blob(object_name)]
        blobs = [blob for blob in blobs if blob is not None]
    else:
        blobs = [
            blob for blob in client.list_blobs(bucket_name, prefix=object_name)
            if blob.name.lower().endswith(".csv")
        ]

    if not blobs:
        raise RuntimeError(f"No CSV files found at {args.gcs_uri}")

    print("=" * 90)
    print("ANCHANTO CSV INSPECTION - READ ONLY")
    print(f"GCS LOCATION: {args.gcs_uri}")
    print(f"CSV FILES FOUND: {len(blobs)}")
    print("No BigQuery SQL or table writes will be executed.")
    print(f"Maximum rows inspected per file: {MAX_INSPECT_ROWS:,}")

    for blob in sorted(blobs, key=lambda item: item.name):
        inspect_file(blob)

    print("\nINSPECTION COMPLETE")


if __name__ == "__main__":
    main()
