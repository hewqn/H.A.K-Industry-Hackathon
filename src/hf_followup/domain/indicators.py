"""Organ indicators visualize measurements independently of overall model rank."""


def organ_indicators(facts: dict) -> dict:
    def indicator(field: str, unit: str, predicate, evidence_id: str) -> dict:
        value = facts.get(field)
        state = "unknown" if value is None else "flagged" if predicate(value) else "not_flagged"
        return {
            "state": state,
            "value": value,
            "unit": unit,
            "label": {
                "flagged": "prototype threshold crossed",
                "not_flagged": "threshold not crossed",
                "unknown": "unknown",
            }[state],
            "evidence_ids": [evidence_id],
        }

    kidney = indicator(
        "serum_creatinine", "mg/dL", lambda value: value > 1.5, "creatinine_measurement"
    )
    return {
        "heart": indicator("ejection_fraction", "%", lambda value: value < 35, "ef_measurement"),
        "kidney_left": dict(kidney),
        "kidney_right": dict(kidney),
    }
