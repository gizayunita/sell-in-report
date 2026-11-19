from pathlib import Path

from google.cloud import bigquery


PROJECT_ID = "datawarehouse-490008"
LOCATION = "asia-southeast2"
SQL_DIR = Path("data_warehouse")


def main():
    # Uses Application Default Credentials from GOOGLE_APPLICATION_CREDENTIALS,
    # configured by the GitHub Actions workflow from GCP_CREDENTIALS_JSON.
    client = bigquery.Client(project=PROJECT_ID)

    print("=" * 60)
    print("SELL-IN DATA WAREHOUSE PIPELINE")
    print("=" * 60)
    print(f"Project  : {PROJECT_ID}")
    print(f"Location : {LOCATION}")
    print("=" * 60)

    print("Checking BigQuery access...")
    client.query("SELECT 1 AS auth_check", location=LOCATION).result()
    print("BigQuery authentication and job access confirmed.")

    sql_files = sorted(SQL_DIR.glob("[0-9][0-9]_*.sql"))
    if not sql_files:
        raise FileNotFoundError(
            f"No numbered SQL files found in {SQL_DIR}/"
        )

    print(f"Found {len(sql_files)} SQL models.")

    for sql_file in sql_files:
        sql = sql_file.read_text(encoding="utf-8").strip()
        if not sql:
            print(f"Skipping empty file: {sql_file}")
            continue

        print("-" * 60)
        print(f"Running: {sql_file}", flush=True)

        job = client.query(sql, location=LOCATION)
        print(f"Job ID: {job.job_id}")
        job.result()

        print(f"SUCCESS: {sql_file}", flush=True)

    print("=" * 60)
    print("ALL DATA WAREHOUSE MODELS COMPLETED SUCCESSFULLY")
    print("=" * 60)


if __name__ == "__main__":
    main()
