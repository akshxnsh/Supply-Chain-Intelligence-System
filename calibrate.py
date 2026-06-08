"""Run nightly to update calibration outcomes for alerts that are 30+ days old."""
from src.ingestion.bq_client import update_calibration_outcomes

if __name__ == "__main__":
    print("Running calibration outcome update...")
    update_calibration_outcomes()
    print("Done.")
