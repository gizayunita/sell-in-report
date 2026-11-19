import json
import os
import sys
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.api_core.exceptions import Forbidden, GoogleAPICallError, NotFound
from google.auth.transport.requests import Request
from google.cloud import bigquery
from google.oauth2.credentials import Credentials


PROJECT_ID = os.getenv("GCP_PROJECT_ID", "datawarehouse-490008")
LOCATION = os.getenv("BIGQUERY_LOCATION", "asia-southeast2")
SQL_DIR = Path("data_warehouse")


def load_credentials():
    raw = os.environ.get("GCP_CREDENTIALS_JSON")
    if not raw:
        raise RuntimeError(
            "GitHub Secret GCP_CREDENTIALS_JSON is missing or empty."
        )

    try:
        info = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "GCP_CREDENTIALS_JSON is not valid JSON. Check the GitHub Secret."
        ) from exc

    if info.get("type") != "authorized_user":
        raise RuntimeError(
            "GCP_CREDENTIALS_JSON must contain OAuth authorized_user credentials. "
            "This workflow does not accept service-account JSON in this secret."
        )

    required = ("client_id", "client_secret", "refresh_token")
    missing = [key for key in required if not info.get(key)]
    if missing:
        raise RuntimeError(
            "OAuth credentials are missing required fields: "
            + ", ".join(missing)
        )

    credentials = Credentials(
        token=None,
        refresh_token=info["refresh_token"],
        token_uri=info.get(
            "token_uri", "https://oauth2.googleapis.com/token"
        ),
        client_id=info["client_id"],
        client_secret=info["client_secret"],
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )

    try:
        credentials.refresh(Request())
    except RefreshError as exc:
        raise RuntimeError(
            "OAuth token refresh failed. The refresh token may be expired, "
            "revoked, or not authorized for the required Google API scopes."
        ) from exc

    return credentials


def main():
    credentials = load_credentials()
    client = bigquery.Client(
        project=PROJECT_ID,
        credentials=credentials,
        location=LOCATION,
    )

    print(f"Authenticated with OAuth user credentials. Project: {PROJECT_ID}")
    print(f"Checking BigQuery job access in location {LOCATION}...")

    try:
        client.query("SELECT 1 AS auth_check", location=LOCATION).result()
    except Forbidden as exc:
        raise RuntimeError(
            "Google authentication succeeded, but this account is not allowed "
            "to create BigQuery jobs in the selected project. Ask the GCP "
            "administrator to grant BigQuery Job User on the project."
        ) from exc
    except NotFound as exc:
        raise RuntimeError(
            "BigQuery could not find the project or location. Verify the "
            "project ID and BigQuery location."
        ) from exc

    sql_files = sorted(SQL_DIR.glob("[0-9][0-9]_*.sql"))
    if not sql_files:
        raise RuntimeError(f"No numbered SQL files found in {SQL_DIR}/")

    print(f"Found {len(sql_files)} SQL models. Starting sequential execution.")

    for sql_file in sql_files:
        sql = sql_file.read_text(encoding="utf-8").strip()
        if not sql:
            print(f"Skipping empty file: {sql_file}")
            continue

        print(f"START: {sql_file}", flush=True)
        try:
            job = client.query(sql, location=LOCATION)
            job.result()
        except Forbidden as exc:
            raise RuntimeError(
                f"Permission denied while running {sql_file}. The account "
                "may have BigQuery Job User but lack write permissions on "
                "the target dataset/table. Ask the dataset/project admin "
                "to grant the required BigQuery data permissions."
            ) from exc
        except GoogleAPICallError as exc:
            raise RuntimeError(f"BigQuery failed while running {sql_file}: {exc}") from exc

        print(f"SUCCESS: {sql_file} (job_id={job.job_id})", flush=True)

    print(f"All {len(sql_files)} SQL models completed successfully.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
