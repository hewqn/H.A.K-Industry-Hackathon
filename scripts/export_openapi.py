"""Export the actual API schema without connecting providers or starting an API process."""

import json

from hf_followup.api.main import create_app
from hf_followup.config import ROOT

if __name__ == "__main__":
    path = ROOT / "contracts/openapi.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(create_app().openapi(), indent=2) + "\n")
    print("Wrote contracts/openapi.json")
