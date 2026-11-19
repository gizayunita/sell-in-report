import argparse
import csv
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from google.cloud import storage

PROJECT_ID = "datawarehouse-490008"
DEFAULT_SOURCE = "gs://bucket_som/sales_parquet/raw/online/anchanto/scrwms/"
DEFAULT_BACKUP = "gs://bucket_som/sales_parquet/raw/online/anchanto/_backup_before_header_fix/"
SCHEMA_FILE = Path(__file__).with_name("anchanto_validation.csv")
DELIVERY_FORMATS = ("%d/%m/%Y, %H:%M:%S", "%d/%m/%Y")
CANONICAL_FIELDS = [
    "marketplace", "order_date", "order_number", "item_upc", "item_name",
    "ordered_quantity", "order_status", "customer_name", "shipping_city",
    "shipping_postcode", "order_packing_date", "delivery_date",
    "dispatch_scheduled_date", "unit_price", "dispatch_date", "discount_value",
]


def normalize_header(value):
    value = (value or "").replace("\ufeff", "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", value).strip("_")


def header_to_field(value):
    key = normalize_header(value)
    aliases = {
        "marketplace": "marketplace",
        "order_date": "order_date",
        "order_number": "order_number",
        "item_upc": "item_upc",
        "item_name": "item_name",
        "ordered_quantity": "ordered_quantity",
        "order_status": "order_status",
        "customer_name": "customer_name",
        "shipping_city": "shipping_city",
        "shipping_postcode": "shipping_postcode",
        "order_packing_date": "order_packing_date",
        "delivery_date": "delivery_date",
        "delivery_date_dd_mm_yyyy": "delivery_date",
        "estimated_delivery_date_dd_mm_yyyy": "delivery_date",
        "estimated_delivery_date": "delivery_date",
        "dispatch_scheduled_date": "dispatch_scheduled_date",
        "unit_price": "unit_price",
        "dispatch_date": "dispatch_date",
        "discount_value": "discount_value",
    }
    if key.startswith("delivery_date") or key.startswith("estimated_delivery_date"):
        return "delivery_date"
    return aliases.get(key)


def parse_gcs_uri(uri):
    if not uri.startswith("gs://"):
        raise ValueError(f"Invalid GCS URI: {uri}")
    bucket, _, prefix = uri[5:].partition("/")
    if not bucket:
        raise ValueError(f"Missing bucket in GCS URI: {uri}")
    return bucket, prefix


def normalize_delivery_date(value, file_name, row_number):
    value = (value or "").strip()
    if not value:
        return ""
    for fmt in DELIVERY_FORMATS:
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed.strftime("%d/%m/%Y, %H:%M:%S")
        except ValueError:
            pass
    raise ValueError(
        f"{file_name}, row {row_number}: unsupported Delivery Date value {value!r}; "
        "expected DD/MM/YYYY or DD/MM/YYYY, HH:MM:SS"
    )


def normalize_file(source_blob, backup_bucket, backup_prefix):
    print("\n" + "=" * 88)
    print(f"SOURCE: gs://{source_blob.bucket.name}/{source_blob.name}", flush=True)

    backup_name = backup_prefix.rstrip("/") + "/" + Path(source_blob.name).name
    backup_blob = backup_bucket.blob(backup_name)
    if not backup_blob.exists():
        backup_bucket.copy_blob(source_blob, backup_bucket, backup_name)
        print(f"BACKUP CREATED: gs://{backup_bucket.name}/{backup_name}")
    else:
        print(f"BACKUP EXISTS, preserving: gs://{backup_bucket.name}/{backup_name}")

    # Write to a temporary object, then replace the source only after validation succeeds.
    output_name = source_blob.name + ".normalizing.tmp"
    output_blob = backup_bucket.blob(output_name)

    rows_written = 0
    date_only_count = 0
    timestamp_count = 0
    blank_count = 0

    try:
        with source_blob.open("rt", encoding="utf-8-sig", newline="") as source:
            reader = csv.reader(source)
            try:
                source_headers = next(reader)
            except StopIteration:
                raise ValueError("CSV is empty")

            source_to_canonical = {}
            for index, header in enumerate(source_headers):
                canonical = header_to_field(header)
                if canonical is None:
                    print(f"WARNING: ignoring unrecognized source column: {header!r}")
                    continue
                if canonical in source_to_canonical:
                    raise ValueError(
                        f"Multiple source headers map to {canonical!r}: "
                        f"{source_headers[source_to_canonical[canonical]]!r} and {header!r}"
                    )
                source_to_canonical[canonical] = index

            missing = [field for field in CANONICAL_FIELDS if field not in source_to_canonical]
            if missing:
                raise ValueError(
                    f"Missing required columns: {missing}. Source headers: {source_headers}"
                )

            delivery_source_header = source_headers[source_to_canonical["delivery_date"]]
            print(f"Delivery Date source header: {delivery_source_header}")
            print(f"Source column count: {len(source_headers)}")
            print(f"Canonical column count: {len(CANONICAL_FIELDS)}")

            with output_blob.open("wt", encoding="utf-8", newline="", ignore_flush=True) as target:
                writer = csv.writer(target)
                output_headers = [
                    "Delivery Date (DD/MM/YYYY)" if field == "delivery_date" else field
                    for field in CANONICAL_FIELDS
                ]
                writer.writerow(output_headers)

                for row_number, row in enumerate(reader, start=2):
                    if not row or all(not (cell or "").strip() for cell in row):
                        continue
                    if len(row) != len(source_headers):
                        raise ValueError(
                            f"Row {row_number}: expected {len(source_headers)} columns, got {len(row)}"
                        )

                    output_row = [
                        (row[source_to_canonical[field]] or "").strip()
                        for field in CANONICAL_FIELDS
                    ]

                    raw_delivery = output_row[CANONICAL_FIELDS.index("delivery_date")]
                    normalized_delivery = normalize_delivery_date(
                        raw_delivery, source_blob.name, row_number
                    )
                    if not raw_delivery:
                        blank_count += 1
                    elif raw_delivery.count(",") == 0:
                        date_only_count += 1
                    else:
                        timestamp_count += 1

                    output_row[CANONICAL_FIELDS.index("delivery_date")] = normalized_delivery
                    writer.writerow(output_row)
                    rows_written += 1

        print(f"ROWS NORMALIZED: {rows_written:,}")
        print(f"Delivery Date timestamp values: {timestamp_count:,}")
        print(f"Delivery Date date-only values converted to midnight: {date_only_count:,}")
        print(f"Delivery Date blank values retained: {blank_count:,}")
        backup_bucket.copy_blob(output_blob, source_blob.bucket, source_blob.name)
        output_blob.delete()
        print(f"NORMALIZED IN PLACE: gs://{source_blob.bucket.name}/{source_blob.name}", flush=True)
        return source_blob.name, rows_written
    except Exception:
        # Never leave a partial normalized CSV that the external table could read.
        try:
            output_blob.delete()
        except Exception:
            pass
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Normalize Anchanto CSV headers and Delivery Date values for BigQuery external tables."
    )
    parser.add_argument("--source-uri", default=DEFAULT_SOURCE)
    parser.add_argument("--backup-uri", default=DEFAULT_BACKUP)
    args = parser.parse_args()

    source_bucket_name, source_prefix = parse_gcs_uri(args.source_uri)
    backup_bucket_name, backup_prefix = parse_gcs_uri(args.backup_uri)
    if source_bucket_name != backup_bucket_name:
        raise ValueError("Source and backup must be in the same GCS bucket for this workflow.")

    client = storage.Client(project=PROJECT_ID)
    source_bucket = client.bucket(source_bucket_name)
    backup_bucket = client.bucket(backup_bucket_name)

    source_blobs = [
        blob for blob in client.list_blobs(source_bucket_name, prefix=source_prefix)
        if blob.name.lower().endswith(".csv")
    ]
    source_blobs.sort(key=lambda blob: blob.name)

    if not source_blobs:
        raise RuntimeError(f"No source CSV files found at {args.source_uri}")

    print("=" * 88)
    print("ANCHANTO CSV NORMALIZATION")
    print(f"Source: {args.source_uri}")
    print(f"Backup: {args.backup_uri}")
    print(f"Files found: {len(source_blobs)}")
    print("Original CSVs will be copied to backup before each file is normalized in place.")
    print("=" * 88)

    total_rows = 0
    for blob in source_blobs:
        _, rows = normalize_file(blob, backup_bucket, backup_prefix)
        total_rows += rows

    print("\n" + "=" * 88)
    print(f"FILES NORMALIZED: {len(source_blobs)}")
    print(f"TOTAL ROWS NORMALIZED: {total_rows:,}")
    print("DELIVERY DATE: canonical DATETIME text format (DD/MM/YYYY, HH:MM:SS)")
    print("DATE-ONLY VALUES: converted to 00:00:00")
    print("NORMALIZATION COMPLETE: normalized CSVs remain in scrwms/")
    print("=" * 88)


if __name__ == "__main__":
    main()
