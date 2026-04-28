from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Submission
from app.models.compliance import utc_now
from app.services.ai_agent import GeminiComplianceAgent
from app.services.email_service import EmailService


OPEN_STATUSES = ["PENDING_CORRECTION", "ESCALATED"]


def list_open_escalations(db: Session) -> list[Submission]:
    now = utc_now()
    return list(
        db.execute(
            select(Submission)
            .where(
                Submission.status.in_(OPEN_STATUSES),
                Submission.correction_due_at.is_not(None),
                Submission.correction_due_at <= now,
            )
            .order_by(Submission.correction_due_at.asc())
        ).scalars()
    )


def run_escalation_cycle(db: Session) -> list[Submission]:
    overdue = list_open_escalations(db)
    ai_agent = GeminiComplianceAgent()
    email_service = EmailService()
    now = utc_now()

    for submission in overdue:
        submission.status = "ESCALATED"
        submission.escalation_level += 1
        context = {
            "vendor_email": submission.vendor_email,
            "file_name": submission.file_name,
            "error_count": submission.error_count,
            "status": submission.status,
            "correction_due_at": submission.correction_due_at,
            "escalation_level": submission.escalation_level,
            "upload_time": submission.upload_time,
        }
        body = ai_agent.draft_escalation_email(context)
        subject = f"Escalation {submission.escalation_level}: overdue customs duty correction"
        email_service.send_email(submission.vendor_email, subject, body)
        submission.ai_audit_summary = ai_agent.generate_audit_summary(
            {
                **context,
                "event": "Correction SLA breached; escalation generated.",
                "escalated_at": now,
            }
        )

    db.commit()
    for submission in overdue:
        db.refresh(submission)
    return overdue
