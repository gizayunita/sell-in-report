import os
import sys
import logging
from google.cloud import storage
from google.api_core.exceptions import GoogleAPIError

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "dwh-learning-project")
BUCKET_NAME = "bucket_som"
PREFIX = "sales_parquet/raw/online/anchanto/scrwms/"


def main() -> int:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not credentials_path:
        logging.error(
            "GOOGLE_APPLICATION_CREDENTIALS is not set. "
            "Configure ADC in the GitHub Actions workflow before running this script."
        )
        return 1

    if not os.path.isfile(credentials_path):
        logging.error("ADC credentials file was not found at the configured path.")
        return 1

    try:
        client = storage.Client(project=PROJECT_ID)
        blobs = client.list_blobs(BUCKET_NAME, prefix=PREFIX)

        logging.info("Checking GCS location: gs://%s/%s", BUCKET_NAME, PREFIX)

        file_count = 0
        total_bytes = 0

        for blob in blobs:
            # Ignore folder-marker objects, if present.
            if blob.name.endswith("/"):
                continue

            file_count += 1
            total_bytes += blob.size or 0
            logging.info("Found: %s | %s bytes", blob.name, blob.size or 0)

        if file_count == 0:
            logging.warning("No files found under the configured GCS prefix.")
        else:
            logging.info(
                "GCS check successful: %s file(s), %.2f MB total.",
                file_count,
                total_bytes / (1024 * 1024),
            )

        return 0

    except GoogleAPIError:
        logging.exception("Google Cloud Storage request failed.")
        return 1
    except Exception:
        logging.exception("Unexpected error while checking GCS.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
