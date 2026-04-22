"""Configuration and environment variables for AuditBot."""

import os
from functools import lru_cache
from typing import Optional
from dotenv import load_dotenv

# Load .env file
load_dotenv()


class Settings:
    """Application settings loaded from environment variables."""

    # Anthropic API
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")

    # OpenAI API (Whisper)
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")

    # Twilio (WhatsApp)
    twilio_account_sid: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    twilio_auth_token: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    twilio_phone_number: str = os.getenv("TWILIO_PHONE_NUMBER", "")

    # Google Sheets
    google_sheets_id: str = os.getenv("GOOGLE_SHEETS_ID", "")
    google_service_account_json: Optional[str] = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")

    # Google Drive
    google_drive_folder_id: str = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")

    # FastAPI
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"

    # Coordinator notifications
    coordinador_tel: str = os.getenv("COORDINADOR_TEL", "")

    # Cache TTL (seconds)
    cache_ttl: int = 300  # 5 minutes

    # Confirmation timeout (minutes)
    confirmation_timeout: int = 5

    # Background job intervals
    timeout_check_interval: int = 2  # minutes
    daily_summary_time: str = "20:00"  # ART (23:00 UTC)

    # Severity configuration
    severity_deadlines: dict = {
        "Alta": 24,      # hours
        "Media": 72,
        "Baja": 168,     # 7 days
    }

    def validate(self) -> None:
        """Validate required settings."""
        required = [
            "anthropic_api_key",
            "openai_api_key",
            "google_sheets_id",
            "google_service_account_json",
            "google_drive_folder_id",
            "twilio_account_sid",
            "twilio_auth_token",
            "twilio_phone_number",
        ]
        missing = [key for key in required if not getattr(self, key)]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get application settings (cached singleton)."""
    settings = Settings()
    settings.validate()
    return settings
