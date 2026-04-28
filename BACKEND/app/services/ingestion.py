import logging

from sqlalchemy.orm import Session

from app.services.email_service import EmailService
from app.services.pipeline import process_saved_file

logger = logging.getLogger(__name__)


def ingest_unread_email_attachments(db: Session) -> list[int]:
    submission_ids: list[int] = []
    email_service = EmailService()
    for attachment in email_service.fetch_unread_attachments():
        try:
            submission = process_saved_file(
                db=db,
                file_path=attachment.file_path,
                original_file_name=attachment.file_name,
                vendor_email=attachment.vendor_email,
            )
        except ValueError as exc:
            logger.warning(
                "Skipping attachment %s from %s: %s",
                attachment.file_name,
                attachment.vendor_email,
                exc,
            )
            email_service.send_email(
                to_email=attachment.vendor_email,
                subject=f"Unable to process customs duty file: {attachment.file_name}",
                body=(
                    "Hello,\n\n"
                    f"We received {attachment.file_name}, but the automated compliance system "
                    f"could not extract part-level duty rows from it.\n\n"
                    "Please resend the submission as CSV/XLSX, or use a text-based PDF containing "
                    "part number, description, HSN/RITC code, BCD, CVD, SWS, and IGST columns.\n\n"
                    f"Technical detail: {exc}\n\n"
                    "Regards,\n"
                    "Vendor Compliance Automation"
                ),
            )
            continue
        except Exception:
            logger.exception(
                "Failed to process attachment %s from %s",
                attachment.file_name,
                attachment.vendor_email,
            )
            continue

        submission_ids.append(submission.id)
    return submission_ids
