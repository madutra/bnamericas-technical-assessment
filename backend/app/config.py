import socket

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Read from env vars prefixed EDITOR_ (or backend/.env)."""

    model_config = SettingsConfigDict(env_prefix="EDITOR_", env_file=".env", extra="ignore")

    upstream_url: str = "http://127.0.0.1:8081"
    upstream_api_key: str = "local-dev-key"
    # Must exceed the upstream's ~2 s slow GET.
    upstream_timeout_seconds: float = 5.0
    save_attempts: int = 3
    database_url: str = "mysql+aiomysql://root@127.0.0.1:3306/project_editor"
    lock_timeout_seconds: int = 5
    instance_id: str = socket.gethostname()
