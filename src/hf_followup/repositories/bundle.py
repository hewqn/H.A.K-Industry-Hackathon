"""Shared checksum utility for backend-owned notebook export/import transport.

Checksums detect corruption, not authenticity. Never load arbitrary untrusted bundles.
TODO(DB-02): define/validate versioned feature/prediction/report and command envelopes
against the allowlist and cohort/model versions before using them in the application.
"""

import hashlib
import json


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()
