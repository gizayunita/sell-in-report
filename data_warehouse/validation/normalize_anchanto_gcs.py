import argparse
import csv
import re
from pathlib import Path

from google.cloud import storage

PROJECT_ID = "datawarehouse-490008"
DEFAULT_SOURCE = "gs://bucket_som/sales_parquet/raw/online/anchanto/scrwms/"
DEFAULT_BACKUP = "gs://bucket_som/sales_parquet/raw/online/anchanto/_backup_before_header_fix/"

# BigQuery external table reads CSV fields by position. Every source export
# must therefore be written in this one canonical order.
CANONICAL_FIELDS = [
    "marketplace", "order_date", "order_number", "item_upc", "item_name",
    "ordered_quantity", "order_status", "customer_name", "shipping_city",
    "shipping_postcode", "order_packing_date", "delivery_date",
    "dispatch_scheduled_date", "unit_price", "dispatch_date", "discount_value",
]
DELIVERY_HEADER = "Delivery Date (DD/MM/YYYY)"


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
        "estimated_delivery_date": "delivery_date",
        "estimated_delivery_date_dd_mm_yyyy": "delivery_date",
        "dispatch_scheduled_date": "dispatch_scheduled_date",
        "unit_price": "unit_price",
        "dispatch_date": "dispatch_date",
        "discount_value": "discount_value",
    }
    return aliases.get(key)


def parse_gcs_uri(uri):
    if not uri.startswith("gs://"):
        raise ValueError(f"Invalid GCS URI: {uri}")
    bucket, _, prefix = uri[5:].partition("/")
    if not bucket:
        raise ValueError(f"Missing bucket in GCS URI: {uri}")
    return bucket, prefix


def backup_and_restore_all(blobs, backup_bucket, backup_prefix):
    print("\nPHASE 1: create/preserve backups and restore ALL originals.")
    for blob in blobs:
        backup_name = backup_prefix.rstrip("/") + "/" + Path(blob.name).name
        backup_blob = backup_bucket.blob(backup_name)
        if not backup_blob.exists():
            backup_bucket.copy_blob(blob, backup_bucket, backup_name)
            print(f"BACKUP CREATED: gs://{backup_bucket.name}/{backup_name}")
        else:
            print(f"BACKUP EXISTS: gs://{backup_bucket.name}/{backup_name}")
            backup_bucket.copy_blob(backup_blob, blob.bucket, blob.name)
            print(f"ORIGINAL RESTORED: gs://{blob.bucket.name}/{blob.name}")


def normalize_one_file(source_blob, backup_bucket, backup_prefix):
    # Read the immutable backup, not a previously normalized source object.
    backup_name = backup_prefix.rstrip("/") + "/" + Path(source_blob.name).name
    backup_blob = backup_bucket.blob(backup_name)
    if not backup_blob.exists():
        raise RuntimeError(f"Missing original backup: gs://{backup_bucket.name}/{backup_name}")

    temp_name = backup_prefix.rstrip("/") + "/_tmp/" + Path(source_blob.name).name + ".tmp"
    temp_blob = backup_bucket.blob(temp_name)
    row_count = 0

    try:
        with backup_blob.open("rt", encoding="utf-8-sig", newline="") as source:
            reader = csv.reader(source)
            try:
                source_headers = next(reader)
            except StopIteration:
                raise ValueError(f"CSV is empty: {source_blob.name}")

            field_indexes = {}
            original_headers = {}
            for index, header in enumerate(source_headers):
                field = header_to_field(header)
                if field is None:
                    raise ValueError(
                        f"Unrecognized header {header!r} in {source_blob.name}. "
                        "Refusing to drop or misplace a column."
                    )
                if field in field_indexes:
                    raise ValueError(
                        f"Duplicate mapping for {field!r} in {source_blob.name}"
                    )
                field_indexes[field] = index
                original_headers[field] = header

            missing = [field for field in CANONICAL_FIELDS if field not in field_indexes]
            extra = [field for field in field_indexes if field not in CANONICAL_FIELDS]
            if missing or extra or len(source_headers) != len(CANONICAL_FIELDS):
                raise ValueError(
                    f"Schema mismatch in {source_blob.name}; missing={missing}, extra={extra}, "
                    f"source_headers={source_headers}"
                )

            output_headers = [
                DELIVERY_HEADER if field == "delivery_date" else original_headers[field]
                for field in CANONICAL_FIELDS
            ]

            with temp_blob.open("wt", encoding="utf-8", newline="", ignore_flush=True) as target:
                writer = csv.writer(target)
                writer.writerow(output_headers)

                for row_number, row in enumerate(reader, start=2):
                    if not row or all(not (cell or "").strip() for cell in row):
                        continue
                    if len(row) != len(source_headers):
                        raise ValueError(
                            f"{source_blob.name}, row {row_number}: expected "
                            f"{len(source_headers)} columns, got {len(row)}"
                        )
                    writer.writerow([row[field_indexes[field]] for field in CANONICAL_FIELDS])
                    row_count += 1

        # Replace scrwms object only after the complete temp CSV was written.
        backup_bucket.copy_blob(temp_blob, source_blob.bucket, source_blob.name)
        temp_blob.delete()

        source_order = [header_to_field(h) for h in source_headers]
        print(f"FILE: {source_blob.name}")
        print(f"SOURCE ORDER: {source_order}")
        print(f"OUTPUT ORDER: {CANONICAL_FIELDS}")
        print(f"ROWS REORDERED: {row_count:,}")
        print(f"OUTPUT HEADER: {output_headers}")
    except Exception:
        try:
            temp_blob.delete()
        except Exception:
            pass
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Restore Anchanto originals, then reorder CSV columns to the BigQuery canonical order."
    )
    parser.add_argument("--source-uri", default=DEFAULT_SOURCE)
    parser.add_argument("--backup-uri", default=DEFAULT_BACKUP)
    args = parser.parse_args()

    source_bucket_name, source_prefix = parse_gcs_uri(args.source_uri)
    backup_bucket_name, backup_prefix = parse_gcs_uri(args.backup_uri)
    if source_bucket_name != backup_bucket_name:
        raise ValueError("Source and backup must be in the same GCS bucket.")

    client = storage.Client(project=PROJECT_ID)
    source_bucket = client.bucket(source_bucket_name)
    backup_bucket = client.bucket(backup_bucket_name)
    blobs = [
        blob for blob in client.list_blobs(source_bucket_name, prefix=source_prefix)
        if blob.name.lower().endswith(".csv")
    ]
    blobs.sort(key=lambda blob: blob.name)
    if not blobs:
        raise RuntimeError(f"No CSV files found at {args.source_uri}")

    print(f"CSV files found: {len(blobs)}")
    backup_and_restore_all(blobs, backup_bucket, backup_prefix)

    print("\nPHASE 2: map by header and reorder every file to canonical column order.")
    for blob in blobs:
        normalize_one_file(source_bucket.blob(blob.name), backup_bucket, backup_prefix)

    print("\nNORMALIZATION COMPLETE")
    print("All CSVs now use the canonical 16-column order expected by the BigQuery external table.")
    print("Only the Delivery Date header is standardized; other header labels are retained.")
    print("All data values are preserved; blank values remain blank.")


if __name__ == "__main__":
    main()
