"""Backend/database owner implements this transport-independent persistence boundary.

SQLite may be a local cache/outbox; Databricks is the primary backend in the PRD.
Do not enable workflow APIs until revision checks, immutable events, replay, and
idempotency are implemented and tested. No implementation silently pretends to commit.
"""

from typing import Protocol


class Repository(Protocol):
    def load_cohort(self, cohort_id: str) -> dict:
        """Return manifest + allowlisted features; never raw outcomes."""
        ...

    def load_predictions(self, cohort_id: str, model_version: str) -> dict:
        """Return complete frozen predictions with model/explanation/provenance metadata."""
        ...

    def load_reports(self, cohort_id: str) -> dict:
        """Return aggregate descriptive/CV/test reports with their population labels."""
        ...

    def read_session_events(self, session_id: str) -> list[dict]:
        """Read ordered immutable commands; deduplicate command IDs and detect conflicts."""
        ...

    def append_command(self, command: dict) -> dict:
        """Check command ID + expected revision, append one full event, confirm receipt.

        One API writer per session. On ambiguous timeout query command ID before retry.
        Return committed only after confirmation; offline cache returns pending_sync.
        """
        ...

    def read_summary(self, cache_key: str) -> dict | None:
        """Cache key includes patient/evidence digest + prompt/generator versions."""
        ...

    def write_summary(self, cache_key: str, summary: dict) -> None:
        """Store validated text and evidence references; reconstructable after event commit."""
        ...
