from dataclasses import dataclass
from email import policy
from email import message_from_bytes
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path
import imaplib
import logging
import smtplib
from uuid import uuid4

from app.config import get_settings

SUPPORTED_ATTACHMENT_EXTENSIONS = {".csv", ".xlsx", ".xls", ".pdf"}
logger = logging.getLogger(__name__)


@dataclass(slots=True)
class IngestedAttachment:
    vendor_email: str
    file_name: str
    file_path: Path


class EmailService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def fetch_unread_attachments(self) -> list[IngestedAttachment]:
        if not self.settings.imap_host or not self.settings.imap_username or not self.settings.imap_password:
            return []

        self.settings.upload_dir.mkdir(parents=True, exist_ok=True)
        attachments: list[IngestedAttachment] = []

        with imaplib.IMAP4_SSL(self.settings.imap_host, self.settings.imap_port) as mailbox:
            mailbox.login(self.settings.imap_username, self.settings.imap_password)
            mailbox.select(self.settings.imap_mailbox)
            status, ids = mailbox.uid("search", None, "UNSEEN")
            if status != "OK" or not ids or not ids[0]:
                return attachments

            message_ids = list(reversed(ids[0].split()))[: self.settings.imap_max_messages_per_poll]

            for message_id in message_ids:
                try:
                    status, payload = mailbox.uid("fetch", message_id, "(BODY.PEEK[])")
                except imaplib.IMAP4.abort as exc:
                    logger.warning("Gmail aborted while fetching message UID %s: %s", message_id.decode(), exc)
                    break

                if status != "OK" or not payload or not isinstance(payload[0], tuple):
                    logger.warning("Skipping unread message UID %s because FETCH returned %s", message_id.decode(), status)
                    continue

                message = message_from_bytes(payload[0][1], policy=policy.default)
                vendor_email = parseaddr(message.get("From", ""))[1]
                found_supported_attachment = False

                for part in message.walk():
                    filename = part.get_filename()
                    if not filename or Path(filename).suffix.lower() not in SUPPORTED_ATTACHMENT_EXTENSIONS:
                        continue

                    payload_bytes = part.get_payload(decode=True)
                    if not payload_bytes:
                        logger.warning("Skipping empty attachment %s from %s", filename, vendor_email)
                        continue

                    safe_name = f"{uuid4().hex}_{Path(filename).name}"
                    file_path = self.settings.upload_dir / safe_name
                    file_path.write_bytes(payload_bytes)
                    attachments.append(
                        IngestedAttachment(
                            vendor_email=vendor_email,
                            file_name=filename,
                            file_path=file_path,
                        )
                    )
                    found_supported_attachment = True

                if found_supported_attachment:
                    mailbox.uid("store", message_id, "+FLAGS", r"(\Seen)")

        return attachments

    def send_email(self, to_email: str, subject: str, body: str) -> None:
        if not self.settings.email_automation_enabled:
            return
        if not self.settings.smtp_host or not self.settings.smtp_username or not self.settings.smtp_password:
            return

        message = EmailMessage()
        message["From"] = self.settings.smtp_from_email
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(body)

        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port) as smtp:
            smtp.starttls()
            smtp.login(self.settings.smtp_username, self.settings.smtp_password)
            smtp.send_message(message)
