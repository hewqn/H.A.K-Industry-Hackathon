"""Validate source CSV, assigning identity before any exclusions (PRD §5–6)."""

import csv
import hashlib
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from hf_followup.domain.constants import (
    BINARY_FIELDS,
    COHORT_ID,
    EVALUATION_FIELDS,
    FEATURES,
    SCHEMA_VERSION,
    SOURCE_HASH,
)
from hf_followup.domain.errors import DomainError


@dataclass(frozen=True)
class Cohort:
    features: dict[str, dict]
    manifest: dict


@dataclass(frozen=True)
class Ingestion:
    cohort: Cohort
    outcomes: dict[str, dict]  # Restricted. Never pass into ApplicationService.


def ingest_csv(path: Path, *, verify_bundled: bool = True) -> Ingestion:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    normalized_digest = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
    if verify_bundled and normalized_digest != SOURCE_HASH:
        raise DomainError(
            "source_hash_mismatch", "Bundled dataset checksum does not match the PRD."
        )
    features, outcomes, excluded, warnings = {}, {}, [], []
    missing_rows = missing_cells = source_count = 0
    required = (*FEATURES, *EVALUATION_FIELDS)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []
        if absent := sorted(set(required) - set(header)):
            raise DomainError("missing_columns", f"Required columns missing: {', '.join(absent)}")
        if len(header) != len(set(header)):
            raise DomainError("duplicate_columns", "CSV header contains duplicate names.")
        if unknown := sorted(set(header) - set(required)):
            warnings.append({"code": "unknown_columns", "fields": unknown})
        for row_number, row in enumerate(reader, 1):
            source_count += 1
            patient_id = f"HF-{row_number:04d}"
            empty = [
                field
                for field in required
                if row.get(field) is None
                or str(row[field]).strip().lower() in {"", "na", "nan", "null"}
            ]
            if empty:
                missing_rows += 1
                missing_cells += len(empty)
                excluded.append(
                    {
                        "patient_id": patient_id,
                        "source_row": row_number,
                        "reason": "missing_values",
                        "fields": empty,
                    }
                )
                continue
            errors, values = [], {}
            if None in row:
                errors.append("unexpected_extra_cells")
            for field in required:
                try:
                    value = float(row[field])
                    if not math.isfinite(value):
                        raise ValueError("non-finite")
                    values[field] = value
                    if field in BINARY_FIELDS | {"DEATH_EVENT"} and value not in (0, 1):
                        errors.append(f"{field}:binary_encoding")
                    if field == "ejection_fraction" and not 0 <= value <= 100:
                        errors.append(f"{field}:out_of_range")
                    if field in {"age", "serum_creatinine", "serum_sodium"} and value <= 0:
                        errors.append(f"{field}:nonpositive")
                    if field in {"platelets", "creatinine_phosphokinase", "time"} and value < 0:
                        errors.append(f"{field}:negative")
                except (ValueError, TypeError):
                    errors.append(f"{field}:invalid_numeric")
            if errors:
                excluded.append(
                    {
                        "patient_id": patient_id,
                        "source_row": row_number,
                        "reason": "invalid_record",
                        "fields": errors,
                    }
                )
                continue
            facts = {
                field: bool(values[field]) if field in BINARY_FIELDS else values[field]
                for field in FEATURES
            }
            features[patient_id] = {
                "patient_id": patient_id,
                "source_row": row_number,
                "facts": facts,
            }
            outcomes[patient_id] = {
                "DEATH_EVENT": int(values["DEATH_EVENT"]),
                "time": values["time"],
            }
            # Retain plausible extremes; these are review flags rather than clipping rules.
            if values["serum_creatinine"] > 5 or values["creatinine_phosphokinase"] > 5000:
                warnings.append({"patient_id": patient_id, "code": "unusual_value_retained"})
    duplicates = Counter(
        tuple(record["facts"][field] for field in FEATURES) for record in features.values()
    )
    if count := sum(n for n in duplicates.values() if n > 1):
        warnings.append({"code": "duplicate_feature_rows_retained", "count": count})
    if verify_bundled and (source_count != 299 or len(features) != 299):
        raise DomainError("unexpected_cohort", "Bundled cohort must contain 299 accepted records.")
    if not features:
        raise DomainError("empty_cohort", "No records passed validation.")
    manifest = {
        "cohort_id": COHORT_ID if verify_bundled else f"fixture-{digest[:12]}",
        "source_hash": digest,
        "schema_version": SCHEMA_VERSION,
        "accepted_ids": list(features),
        "accepted_count": len(features),
        "source_count": source_count,
        "excluded_count": len(excluded),
        "missing_rows": missing_rows,
        "missing_cells": missing_cells,
        "exclusions": excluded,
        "warnings": warnings,
        "feature_allowlist": list(FEATURES),
        "source": "UCI Heart Failure Clinical Records",
        "license": "CC BY 4.0",
    }
    return Ingestion(Cohort(features, manifest), outcomes)
