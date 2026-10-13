from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://voicely:voicely@postgres:5432/voicely"
    redis_url: str = "redis://redis:6379/0"
    data_dir: Path = Path("/data")

    # Signs login tokens and file links. Must be set to a long random value.
    secret_key: str = "change-me"
    access_token_days: int = 7
    file_link_minutes: int = 240
    allow_registration: bool = True

    max_upload_mb: int = 200          # one audio upload
    max_model_mb: int = 600           # .pth plus .index
    max_audio_minutes: int = 10       # per conversion / cover
    max_tts_chars: int = 3000
    max_active_jobs_per_user: int = 3
    max_dataset_minutes: int = 90     # per voice

    # A running job with no worker heartbeat for this long is marked failed.
    job_stale_seconds: int = 120


settings = Settings()
