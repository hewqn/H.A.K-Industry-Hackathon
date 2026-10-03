"""Databricks SQL wiring point. Intentionally incomplete: backend owner connects it.

Install the optional databricks extra only when the workspace permits external SQL.
Use native parameters for values and an approved identifier allowlist for tables.
Do not expose this connection, raw outcomes, SQL, or credentials to the frontend.
"""

import os
import re

from hf_followup.domain.errors import DomainError


class DatabricksRepository:
    def __init__(self):
        self.hostname = os.getenv("DATABRICKS_SERVER_HOSTNAME", "")
        self.http_path = os.getenv("DATABRICKS_HTTP_PATH", "")
        self.token = os.getenv("DATABRICKS_TOKEN", "")
        self.catalog = os.getenv("HF_CATALOG", "")
        self.schema = os.getenv("HF_SCHEMA", "hf_hackathon")

    def connect(self):
        if not all((self.hostname, self.http_path, self.token, self.catalog)):
            raise DomainError(
                "databricks_unconfigured", "Databricks workspace connection is not configured.", 503
            )
        if not all(
            re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", part) for part in (self.catalog, self.schema)
        ):
            raise DomainError("invalid_namespace", "Review the approved catalog/schema names.")
        from databricks import sql

        return sql.connect(
            server_hostname=self.hostname, http_path=self.http_path, access_token=self.token
        )

    # TODO(BACKEND, DB-02): implement every method of repositories/base.py.Repository.
    # Native binding example (only after choosing approved table identifiers):
    # with self.connect() as connection, connection.cursor() as cursor:
    #     cursor.execute("SELECT features_json FROM approved.patient_features WHERE patient_id=?", [patient_id])
    #     rows = cursor.fetchall()
    # See docs/databricks.md for event/outbox and restricted export/import requirements.
