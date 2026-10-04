"""Local scaffold settings; provider integration remains owned by each workstream."""

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    root: Path = ROOT
    session_id: str = "demo"
    origins: list[str] = field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    @classmethod
    def from_env(cls):
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
        return cls(
            session_id=os.getenv("HF_SESSION_ID", "demo"),
            origins=os.getenv(
                "HF_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
            ).split(","),
        )
