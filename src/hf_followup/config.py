"""Local scaffold settings; provider integration remains owned by each workstream."""

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    root: Path = ROOT
    session_id: str = "demo"
    model_bundle_dir: Path | None = None
    default_method: str = "auto"
    origins: list[str] = field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    @classmethod
    def from_env(cls):
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
        configured_bundle = os.getenv("HF_MODEL_BUNDLE_DIR", "runtime/ml-models").strip()
        bundle_dir = Path(configured_bundle).expanduser() if configured_bundle else None
        if bundle_dir is not None and not bundle_dir.is_absolute():
            bundle_dir = ROOT / bundle_dir
        return cls(
            session_id=os.getenv("HF_SESSION_ID", "demo"),
            origins=os.getenv(
                "HF_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
            ).split(","),
            model_bundle_dir=bundle_dir,
            default_method=os.getenv("HF_DEFAULT_METHOD", "auto"),
        )
