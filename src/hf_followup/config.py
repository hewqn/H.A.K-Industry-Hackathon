"""Server settings. Provider secrets must never enter frontend configuration."""

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
    elevenlabs_api_key: str = field(default="", repr=False)
    elevenlabs_agent_id: str = ""
    voice_max_duration_seconds: int = 300
    voice_session_requests_per_minute: int = 5

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
            model_bundle_dir=bundle_dir,
            default_method=os.getenv("HF_DEFAULT_METHOD", "auto"),
            origins=os.getenv(
                "HF_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
            ).split(","),
            elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY", "").strip(),
            elevenlabs_agent_id=os.getenv("ELEVENLABS_AGENT_ID", "").strip(),
            voice_max_duration_seconds=max(30, min(900, int(os.getenv("HF_VOICE_MAX_DURATION_SECONDS", "300")))),
            voice_session_requests_per_minute=max(1, min(30, int(os.getenv("HF_VOICE_SESSION_REQUESTS_PER_MINUTE", "5")))),
        )
