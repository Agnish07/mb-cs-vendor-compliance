import asyncio
import logging

from app.config import get_settings
from app.database import SessionLocal
from app.services.ingestion import ingest_unread_email_attachments

logger = logging.getLogger(__name__)


async def email_polling_loop() -> None:
    settings = get_settings()
    if not settings.email_polling_enabled:
        return

    while True:
        try:
            processed_ids = await asyncio.to_thread(_run_ingestion_cycle)
            if processed_ids:
                logger.info("Processed email submissions: %s", processed_ids)
        except Exception:
            logger.exception("Email polling cycle failed")

        await asyncio.sleep(settings.email_poll_interval_seconds)


def _run_ingestion_cycle() -> list[int]:
    with SessionLocal() as db:
        return ingest_unread_email_attachments(db)
