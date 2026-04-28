from app.models import ComplianceError, Submission
from app.services.ai_agent import GeminiComplianceAgent
from app.services.email_service import EmailService


def build_correction_email(submission: Submission, errors: list[ComplianceError]) -> tuple[str, str]:
    subject = f"Corrections required: {submission.file_name}"
    error_rows = [
        {
            "row_number": error.row_number,
            "error_code": error.error_code,
            "severity": error.severity,
            "error_type": error.error_type,
            "message": error.message,
        }
        for error in errors
    ]
    body = GeminiComplianceAgent().draft_correction_email(
        vendor_email=submission.vendor_email,
        file_name=submission.file_name,
        error_rows=error_rows,
    )
    return subject, body


def send_correction_email_if_needed(submission: Submission, errors: list[ComplianceError]) -> bool:
    if not errors:
        return False

    subject, body = build_correction_email(submission, errors)
    EmailService().send_email(to_email=submission.vendor_email, subject=subject, body=body)
    return True
