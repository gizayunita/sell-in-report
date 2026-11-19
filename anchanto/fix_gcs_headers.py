import csv
import logging
import os
import sys
from pathlib import PurePosixPath

from google.api_core.exceptions import GoogleAPIError
from google.cloud import storage

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "dwh-learning-project")
BUCKET_NAME = "bucket_som"
PREFIX = "sales_parquet/raw/online/anchanto/scrwms/"
BACKUP_PREFIX = PREFIX + "_backup_before_header_fix/"
TEMP_PREFIX = PREFIX + "_tmp_header_fix/"

OLD_HEADER = "Estimated Delivery Date (DD/MM/YYYY)"
NEW_HEADER = "Delivery Date (DD/MM/YYYY)"

TARGET_FILES = [
    "Anchanto 26 10 Oct - Order Report-3.csv",
    "Anchanto 26 11 Nov - Order Report-1.csv",
    "Anchanto 26 11 Nov - Order Report-2.csv",
]


def fix_one_file(bucket, filename):
    source_name = PREFIX + filename
    backup_name = BACKUP_PREFIX + filename
    temp_name = TEMP_PREFIX + filename + ".tmp"

    source = bucket.blob(source_name)
    backup = bucket.blob(backup_name)
    temp = bucket.blob(temp_name)

    if not source.exists():
        raise RuntimeError(f"Source object not found: gs://{BUCKET_NAME}/{source_name}")
    if backup.exists():
        raise RuntimeError(
            f"Backup already exists; refusing to overwrite it: gs://{BUCKET_NAME}/{backup_name}"
        )

    # Confirm the exact expected header before creating any backup or changing data.
    with source.open("r", encoding="utf-8-sig", newline="") as src:
        reader = csv.reader(src)
        try:
            original_header = next(reader)
        except StopIteration:
            raise RuntimeError(f"CSV is empty: {source_name}")

    if OLD_HEADER not in original_header:
        raise RuntimeError(
            f"Expected alias '{OLD_HEADER}' not found in {source_name}; "
            "file left unchanged."
        )
    if NEW_HEADER in original_header:
        raise RuntimeError(
            f"Canonical header already exists in {source_name}; file left unchanged."
        )
    if len(original_header) != 16:
        raise RuntimeError(
            f"Expected 16 columns in {source_name}, found {len(original_header)}; "
            "file left unchanged."
        )

    # Preserve an untouched copy before preparing the replacement.
    bucket.copy_blob(source, bucket, new_name=backup_name)
    logging.info("BACKUP CREATED: gs://%s/%s", BUCKET_NAME, backup_name)

    # Stream the CSV row by row; no full-file download or in-memory load.
    rows_written = 0
    with source.open("r", encoding="utf-8-sig", newline="") as src, \
         temp.open("w", encoding="utf-8", newline="") as dst:
        reader = csv.reader(src)
        writer = csv.writer(dst)
        header = next(reader)
        header = [NEW_HEADER if value == OLD_HEADER else value for value in header]
        writer.writerow(header)

        for row in reader:
            writer.writerow(row)
            rows_written += 1

    # Verify the staged object before replacing the original object.
    temp.reload()
    with temp.open("r", encoding="utf-8-sig", newline="") as staged:
        staged_header = next(csv.reader(staged), [])

    if NEW_HEADER not in staged_header or OLD_HEADER in staged_header:
        temp.delete()
        raise RuntimeError(f"Staged header verification failed for {source_name}")

    # Replace original only after backup and staged-file verification succeed.
    bucket.copy_blob(temp, bucket, new_name=source_name)
    temp.delete()

    logging.info(
        "UPDATED: gs://%s/%s | data rows streamed: %s",
        BUCKET_NAME,
        source_name,
        rows_written,
    )


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials_path or not os.path.isfile(credentials_path):
        logging.error("Valid GOOGLE_APPLICATION_CREDENTIALS file is required.")
        return 1

    try:
        client = storage.Client(project=PROJECT_ID)
        bucket = client.bucket(BUCKET_NAME)

        for filename in TARGET_FILES:
            fix_one_file(bucket, filename)

        logging.info("SUCCESS: all three GCS CSV headers were updated.")
        logging.info(
            "Original files are backed up under gs://%s/%s",
            BUCKET_NAME,
            BACKUP_PREFIX,
        )
        return 0

    except (GoogleAPIError, OSError, RuntimeError, StopIteration) as exc:
        logging.exception("GCS header update stopped: %s", exc)
        return 1
    except Exception:
        logging.exception("Unexpected failure during GCS header update.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
