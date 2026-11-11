"""Server configuration. A user's OpenAI key is never an environment setting."""

from pathlib import Path
from urllib.parse import urlsplit
import re

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="GOLF_", env_file=BACKEND_ROOT / ".env", extra="ignore"
    )
    api_token: SecretStr = Field(min_length=24, max_length=512)
    cors_origins: list[str] = ["http://localhost:3000"]
    pose_weights: Path = BACKEND_ROOT / "models" / "yolov8n-pose.pt"
    pose_device: str = "cpu"
    pose_image_size: int = Field(default=960, ge=320, le=1920)
    filter_cutoff_hz: float = Field(default=8, gt=0, le=100, allow_inf_nan=False)
    max_video_bytes: int = Field(default=100 * 1024 * 1024, ge=1024, le=500 * 1024 * 1024)
    max_result_bytes: int = Field(default=64 * 1024 * 1024, ge=1024)
    worker_timeout_seconds: float = Field(default=180, gt=0, le=900, allow_inf_nan=False)
    worker_memory_mb: int = Field(default=8192, ge=1024, le=65_536)
    max_concurrent_analyses: int = Field(default=1, ge=1, le=4)
    upload_timeout_seconds: float = Field(default=60, gt=0, le=300, allow_inf_nan=False)
    openai_model: str = Field(default="gpt-4.1-mini", min_length=1, max_length=100)
    openai_timeout_seconds: float = Field(default=25, gt=0, le=120, allow_inf_nan=False)
    supabase_url: str | None = None
    supabase_service_key: SecretStr | None = None
    storage_bucket: str = "swings"
    storage_prefix: str = "swings"

    @model_validator(mode="after")
    def configuration_is_safe(self):
        if self.api_token.get_secret_value().startswith("replace-with"):
            raise ValueError("Generate a unique backend API token before starting the server.")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", self.api_token.get_secret_value()):
            raise ValueError(
                "The backend token must use ASCII letters, digits, underscores or hyphens."
            )
        if not self.pose_weights.is_absolute():
            self.pose_weights = BACKEND_ROOT / self.pose_weights
        if not self.cors_origins or "*" in self.cors_origins:
            raise ValueError("Configure explicit browser origins.")
        for origin in self.cors_origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in ("http", "https")
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
                or parsed.path not in ("", "/")
            ):
                raise ValueError("CORS origins must contain only scheme, host and optional port.")
        if self.supabase_url is not None:
            parsed = urlsplit(self.supabase_url)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
                or parsed.path not in ("", "/")
            ):
                raise ValueError("Supabase must use a configured HTTPS origin.")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", self.storage_bucket):
            raise ValueError("Invalid storage bucket name.")
        if (
            not self.storage_prefix
            or self.storage_prefix.startswith("/")
            or any(part in ("", ".", "..") for part in self.storage_prefix.split("/"))
        ):
            raise ValueError("Configure a nonempty, relative storage prefix.")
        return self
