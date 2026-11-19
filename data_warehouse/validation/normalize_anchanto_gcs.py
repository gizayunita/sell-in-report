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


def normalize_file(source_blob, backup_bucket, backup_prefix):
    backup_name = backup_prefix.rstrip("/") + "/" + Path(source_blob.name).name
    backup_blob = backup_bucket.blob(backup_name)

    # Always use the untouched backup as the source on reruns. This also
    # restores files changed by the previously stopped broad normalizer.
    if not backup_blob.exists():
        backup_bucket.copy_blob(source_blob, backup_bucket, backup_name)
        print(f"BACKUP CREATED: gs://{backup_bucket.name}/{backup_name}")
    else:
        print(f"BACKUP EXISTS: using original copy gs://{backup_bucket.name}/{backup_name}")

    temp_name = source_blob.name + ".header_fix.tmp"
    temp_blob = backup_bucket.blob(temp_name)
    changed = False

    try:
        with backup_blob.open("rt", encoding="utf-8-sig", newline="") as source:
            first_line = source.readline()
            if not first_line:
                raise ValueError(f"CSV is empty: {source_blob.name}")

            try:
                headers = next(csv.reader([first_line]))
            except (csv.Error, StopIteration) as exc:
                raise ValueError(f"Cannot parse CSV header in {source_blob.name}: {exc}")

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
                raise ValueError(
                    f"No Delivery Date or Estimated Delivery Date header found in {source_blob.name}: {headers}"
                )

            header_buffer = io.StringIO(newline="")
            csv.writer(header_buffer, lineterminator="\n").writerow(updated_headers)
            with temp_blob.open("wt", encoding="utf-8", newline="", ignore_flush=True) as target:
                target.write(header_buffer.getvalue())
                # Preserve every data row exactly as it exists in the original backup.
                while True:
                    chunk = source.read(8 * 1024 * 1024)
                    if not chunk:
                        break
                    target.write(chunk)

        backup_bucket.copy_blob(temp_blob, source_blob.bucket, source_blob.name)
        temp_blob.delete()
        print(
            f"HEADER {'UPDATED' if changed else 'UNCHANGED'}: "
            f"gs://{source_blob.bucket.name}/{source_blob.name}"
        )
        print(f"HEADERS: {updated_headers}")
    except Exception:
        try:
            temp_blob.delete()
        except Exception:
            pass
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Change only Estimated Delivery Date header to Delivery Date; preserve all other headers and data."
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
    print("Only Estimated Delivery Date header will be renamed.")
    print("All other headers, column order, and data rows will be preserved.")
    for blob in blobs:
        print(f"\nSOURCE: gs://{source_bucket.name}/{blob.name}")
        normalize_file(blob, backup_bucket, backup_prefix)

    print("\nHEADER FIX COMPLETE")


if __name__ == "__main__":
    main()
