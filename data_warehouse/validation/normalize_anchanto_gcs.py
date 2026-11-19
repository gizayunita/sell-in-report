import argparse
import csv
import io
from pathlib import Path

from google.cloud import storage

PROJECT_ID = "datawarehouse-490008"
DEFAULT_SOURCE = "gs://bucket_som/sales_parquet/raw/online/anchanto/scrwms/"
DEFAULT_BACKUP = "gs://bucket_som/sales_parquet/raw/online/anchanto/_backup_before_header_fix/"


def parse_gcs_uri(uri):
    if not uri.startswith("gs://"):
        raise ValueError(f"Invalid GCS URI: {uri}")
    bucket, _, prefix = uri[5:].partition("/")
    if not bucket:
        raise ValueError(f"Missing bucket in GCS URI: {uri}")
    return bucket, prefix


def ensure_backup_and_restore(source_blob, backup_bucket, backup_prefix):
    backup_name = backup_prefix.rstrip("/") + "/" + Path(source_blob.name).name
    backup_blob = backup_bucket.blob(backup_name)

    if not backup_blob.exists():
        backup_bucket.copy_blob(source_blob, backup_bucket, backup_name)
        print(f"BACKUP CREATED: gs://{backup_bucket.name}/{backup_name}")
    else:
        print(f"BACKUP EXISTS: gs://{backup_bucket.name}/{backup_name}")

    # Restore the untouched original before applying the one-header correction.
    backup_bucket.copy_blob(backup_blob, source_blob.bucket, source_blob.name)
    print(f"ORIGINAL RESTORED: gs://{source_blob.bucket.name}/{source_blob.name}")


def rename_estimated_delivery_header(source_blob, backup_bucket):
    temp_blob = backup_bucket.blob(source_blob.name + ".header_fix.tmp")
    changed = False

    try:
        with source_blob.open("rt", encoding="utf-8-sig", newline="") as source:
            first_line = source.readline()
            if not first_line:
                raise ValueError(f"CSV is empty: {source_blob.name}")

            headers = next(csv.reader([first_line]))
            updated_headers = []
            for header in headers:
                normalized = " ".join((header or "").replace("\ufeff", "").strip().lower().split())
                if normalized.startswith("estimated delivery date"):
                    updated_headers.append("Delivery Date (DD/MM/YYYY)")
                    changed = True
                else:
                    updated_headers.append(header)

            if not any(
                " ".join((h or "").strip().lower().split()).startswith("delivery date")
                for h in headers
            ) and not changed:
                raise ValueError(f"No Delivery Date header found in {source_blob.name}: {headers}")

            header_buffer = io.StringIO(newline="")
            csv.writer(header_buffer, lineterminator="\n").writerow(updated_headers)
            with temp_blob.open("wt", encoding="utf-8", newline="", ignore_flush=True) as target:
                target.write(header_buffer.getvalue())
                while True:
                    chunk = source.read(8 * 1024 * 1024)
                    if not chunk:
                        break
                    target.write(chunk)

        backup_bucket.copy_blob(temp_blob, source_blob.bucket, source_blob.name)
        temp_blob.delete()
        print(f"HEADER {'RENAMED' if changed else 'ALREADY STANDARD'}: {source_blob.name}")
        print(f"HEADERS: {updated_headers}")
    except Exception:
        try:
            temp_blob.delete()
        except Exception:
            pass
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Restore original Anchanto CSVs, then rename only Estimated Delivery Date header."
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
    print("PHASE 1: back up and restore ALL original CSV files before changing any header.")
    for blob in blobs:
        ensure_backup_and_restore(blob, backup_bucket, backup_prefix)

    print("\nPHASE 2: rename ONLY Estimated Delivery Date header.")
    for blob in blobs:
        current_blob = source_bucket.blob(blob.name)
        rename_estimated_delivery_header(current_blob, backup_bucket)

    print("\nHEADER FIX COMPLETE")
    print("All original files were restored first; only Estimated Delivery Date headers were changed.")
    print("All other headers, column order, and data rows were preserved.")


if __name__ == "__main__":
    main()
