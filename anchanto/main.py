import csv
import logging
import os
import sys

from google.api_core.exceptions import GoogleAPIError
from google.cloud import storage

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "dwh-learning-project")
BUCKET_NAME = "bucket_som"
PREFIX = "sales_parquet/raw/online/anchanto/scrwms/"

REQUIRED_COLUMNS = [
    "Marketplace",
    "Order Date",
    "Order Number",
    "Item Upc",
    "Item Name",
    "Ordered Quantity",
    "Order Status",
    "Customer Name",
    "Shipping City",
    "Shipping Postcode",
    "Order Packing Date",
    "Delivery Date (DD/MM/YYYY)",
    "Dispatch Scheduled Date",
    "Unit Price",
    "Dispatch Date",
    "Discount Value",
]


def read_csv_header(blob):
    """Read only the first CSV row from GCS; do not download the full file."""
    with blob.open("r", encoding="utf-8-sig", newline="") as file_obj:
        reader = csv.reader(file_obj)
        try:
            return next(reader)
        except StopIteration:
            return []


def validate_file(blob):
    """Validate one CSV file and return its validation details."""
    try:
        actual_columns = [column.strip() for column in read_csv_header(blob)]

        if not actual_columns:
            return {
                "status": "EMPTY",
                "missing": REQUIRED_COLUMNS.copy(),
                "unexpected": [],
                "actual_count": 0,
            }

        missing = [col for col in REQUIRED_COLUMNS if col not in actual_columns]
        unexpected = [col for col in actual_columns if col not in REQUIRED_COLUMNS]

        return {
            "status": "PASS" if not missing else "FAIL",
            "missing": missing,
            "unexpected": unexpected,
            "actual_count": len(actual_columns),
        }
    except (UnicodeDecodeError, csv.Error, GoogleAPIError, OSError) as exc:
        logging.exception("Could not read header for %s", blob.name)
        return {
            "status": "ERROR",
            "missing": [],
            "unexpected": [],
            "actual_count": 0,
            "error": str(exc),
        }


def main() -> int:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials_path:
        logging.error("GOOGLE_APPLICATION_CREDENTIALS is not set.")
        return 1

    if not os.path.isfile(credentials_path):
        logging.error("ADC credentials file was not found at the configured path.")
        return 1

    try:
        client = storage.Client(project=PROJECT_ID)
        logging.info("Validating CSV headers in gs://%s/%s", BUCKET_NAME, PREFIX)

        csv_blobs = (
            blob
            for blob in client.list_blobs(BUCKET_NAME, prefix=PREFIX)
            if not blob.name.endswith("/") and blob.name.lower().endswith(".csv")
        )

        total = passed = failed = empty = errors = 0

        for blob in csv_blobs:
            total += 1
            result = validate_file(blob)

            logging.info(
                "[%s] %s | header columns: %s",
                result["status"],
                blob.name,
                result["actual_count"],
            )

            if result["status"] == "PASS":
                passed += 1
            elif result["status"] == "EMPTY":
                empty += 1
                logging.warning("  File has no header row.")
            elif result["status"] == "ERROR":
                errors += 1
                logging.error("  Read error: %s", result.get("error", "Unknown error"))
            else:
                failed += 1
                logging.error("  Missing columns (%s): %s", len(result["missing"]), result["missing"])

            if result["unexpected"]:
                logging.warning("  Unexpected columns: %s", result["unexpected"])

        logging.info(
            "VALIDATION SUMMARY | total: %s | passed: %s | failed: %s | empty: %s | errors: %s",
            total,
            passed,
            failed,
            empty,
            errors,
        )

        if total == 0:
            logging.warning("No CSV files found under the configured GCS prefix.")
            return 1

        return 1 if failed or empty or errors else 0

    except GoogleAPIError:
        logging.exception("Google Cloud Storage request failed.")
        return 1
    except Exception:
        logging.exception("Unexpected error during header validation.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
