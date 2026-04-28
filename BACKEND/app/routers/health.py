from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ai/status")
def ai_status() -> dict[str, bool | str]:
    settings = get_settings()
    try:
        from google import genai  # noqa: F401

        sdk_installed = True
    except ImportError:
        sdk_installed = False

    return {
        "ai_agent_enabled": settings.ai_agent_enabled,
        "gemini_key_configured": bool(settings.gemini_api_key),
        "gemini_sdk_installed": sdk_installed,
        "gemini_model": settings.gemini_model,
        "ready": bool(settings.ai_agent_enabled and settings.gemini_api_key and sdk_installed),
    }


@router.get("/email/status")
def email_status() -> dict[str, bool | int | str]:
    settings = get_settings()
    return {
        "email_polling_enabled": settings.email_polling_enabled,
        "email_poll_interval_seconds": settings.email_poll_interval_seconds,
        "imap_configured": bool(settings.imap_host and settings.imap_username and settings.imap_password),
        "smtp_configured": bool(settings.smtp_host and settings.smtp_username and settings.smtp_password),
        "email_automation_enabled": settings.email_automation_enabled,
        "supported_attachments": "csv,xlsx,xls,pdf",
        "ready": bool(
            settings.email_polling_enabled
            and settings.imap_host
            and settings.imap_username
            and settings.imap_password
        ),
    }
