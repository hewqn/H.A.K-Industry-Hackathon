"""Merged configuration must retain both frozen ML and private voice settings."""

from hf_followup.config import ROOT, Settings


def test_env_loads_ml_and_voice_together(monkeypatch):
    monkeypatch.setenv("HF_MODEL_BUNDLE_DIR", "runtime/test-models")
    monkeypatch.setenv("HF_DEFAULT_METHOD", "heart_risk")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-secret")
    monkeypatch.setenv("ELEVENLABS_AGENT_ID", "test-agent")
    monkeypatch.setenv("HF_VOICE_MAX_DURATION_SECONDS", "120")
    settings = Settings.from_env()
    assert settings.model_bundle_dir == ROOT / "runtime/test-models"
    assert settings.default_method == "heart_risk"
    assert settings.elevenlabs_agent_id == "test-agent"
    assert settings.elevenlabs_api_key == "test-secret"
    assert settings.voice_max_duration_seconds == 120
    assert "test-secret" not in repr(settings)


def test_blank_bundle_disables_ml_without_disabling_voice(monkeypatch):
    monkeypatch.setenv("HF_MODEL_BUNDLE_DIR", "")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-secret")
    monkeypatch.setenv("ELEVENLABS_AGENT_ID", "test-agent")
    settings = Settings.from_env()
    assert settings.model_bundle_dir is None
    assert settings.elevenlabs_api_key
