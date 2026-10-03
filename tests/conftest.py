"""Shared fixtures use the public bundled cohort, never fabricated clinical outcomes."""

import pytest

from hf_followup.config import ROOT
from hf_followup.data.ingest import ingest_csv


@pytest.fixture(scope="session")
def ingested():
    return ingest_csv(ROOT / "data/heart_failure_clinical_records.csv")
