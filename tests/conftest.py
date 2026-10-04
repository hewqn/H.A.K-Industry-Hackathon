"""Shared fixtures use the public bundled cohort, never fabricated clinical outcomes."""

import pytest

from hf_followup.config import ROOT
from hf_followup.data.ingest import ingest_csv


@pytest.fixture(scope="session")
def ingested():
    return ingest_csv(ROOT / "data/heart_failure_clinical_records.csv")


@pytest.fixture(autouse=True)
def _no_live_databricks(monkeypatch):
    # A developer .env must never let tests write accounts or events to the real workspace.
    for name in ("DATABRICKS_SERVER_HOSTNAME", "DATABRICKS_HTTP_PATH", "DATABRICKS_TOKEN", "HF_CATALOG"):
        monkeypatch.setenv(name, "")
