from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Autonomous Vendor Compliance"
    database_url: str = "sqlite:///./vendor_compliance.db"
    db_connect_timeout_seconds: int = 5
    db_statement_timeout_ms: int = 10000
    db_lock_timeout_ms: int = 5000
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    upload_dir: Path = Path("data/uploads")
    hsn_master_codes: list[str] = [
        "01012100",
        "27101990",
        "30049099",
        "39269099",
        "40169330",
        "73181500",
        "84713010",
        "8409",
        "8413",
        "8421",
        "8507",
        "85044090",
        "8511",
        "8512",
        "85176290",
        "8708",
        "87089900",
    ]

    imap_host: str | None = None
    imap_port: int = 993
    imap_username: str | None = None
    imap_password: str | None = None
    imap_mailbox: str = "INBOX"
    imap_max_messages_per_poll: int = 25
    email_polling_enabled: bool = False
    email_poll_interval_seconds: int = 300

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str = "compliance@example.com"
    email_automation_enabled: bool = False
    correction_sla_hours: int = 48

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    ai_agent_enabled: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
