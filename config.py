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

    # Meta WhatsApp Cloud API
    meta_phone_number_id: str = os.getenv("META_PHONE_NUMBER_ID", "")
    meta_access_token: str = os.getenv("META_ACCESS_TOKEN", "")
    meta_verify_token: str = os.getenv("META_VERIFY_TOKEN", "")
    meta_app_secret: str = os.getenv("META_APP_SECRET", "")
    # App ID (no APP_SECRET) — visible en el dashboard de Meta for Developers,
    # junto al nombre de la app. Habilita el chequeo periódico de salud del
    # webhook (check_webhook_health en main.py); sin esto el chequeo se salta.
    meta_app_id: str = os.getenv("META_APP_ID", "")
    # Human-readable WhatsApp number for the bot, used only in message copy
    # (e.g. "escribinos al +54 9 381 619-9195") — not used for API calls,
    # those go through meta_phone_number_id.
    bot_display_phone: str = os.getenv("BOT_DISPLAY_PHONE", "+54 9 381 619-9195")

    # Supabase
    supabase_url: Optional[str] = os.getenv("SUPABASE_URL")
    supabase_service_key: Optional[str] = os.getenv("SUPABASE_SERVICE_KEY")

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
        """Validate required settings for core functionality (WhatsApp + Anthropic)."""
        required = [
            "anthropic_api_key",
            "meta_phone_number_id",
            "meta_access_token",
            "meta_verify_token",
        ]
        missing = [key for key in required if not getattr(self, key)]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
        if not self.meta_app_secret:
            import logging
            logging.getLogger(__name__).warning(
                "META_APP_SECRET no configurado: /webhook acepta requests SIN "
                "verificar firma X-Hub-Signature-256 (cualquiera puede falsificar "
                "mensajes de WhatsApp). Configuralo en Railway ASAP."
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get application settings (cached singleton)."""
    import logging
    logger = logging.getLogger(__name__)
    settings = Settings()
    logger.info(f"Settings loaded: supabase_url={'SET' if settings.supabase_url else 'NOT SET'}, supabase_service_key={'SET' if settings.supabase_service_key else 'NOT SET'}")
    settings.validate()
    return settings
