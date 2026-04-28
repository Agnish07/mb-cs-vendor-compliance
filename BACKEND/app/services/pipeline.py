from pathlib import Path
from datetime import timedelta
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ComplianceError, Submission, SubmissionRow
from app.models.compliance import utc_now
from app.services.ai_agent import GeminiComplianceAgent
from app.services.classification import classify_errors
from app.services.normalization import normalize_file
from app.services.remediation import send_correction_email_if_needed
from app.services.validation import validate_rows


def _save_upload(file: UploadFile) -> tuple[Path, str]:
    settings = get_settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    original_name = Path(file.filename or "vendor_submission.csv").name
    saved_path = settings.upload_dir / f"{uuid4().hex}_{original_name}"
    with saved_path.open("wb") as target:
        target.write(file.file.read())

    return saved_path, original_name


def process_upload(db: Session, file: UploadFile, vendor_email: str) -> Submission:
    file_path, original_name = _save_upload(file)
    return process_saved_file(db, file_path, original_name, vendor_email)


def process_saved_file(
    db: Session,
    file_path: Path,
    original_file_name: str,
    vendor_email: str,
) -> Submission:
    settings = get_settings()
    rows = normalize_file(file_path)
    validation_errors = validate_rows(rows, set(settings.hsn_master_codes))
    classified_errors = classify_errors(db, vendor_email, validation_errors)
    now = utc_now()
    status = "PENDING_CORRECTION" if classified_errors else "ACCEPTED"

    submission = Submission(
        vendor_email=vendor_email,
        file_name=original_file_name,
        total_rows=len(rows),
        error_count=len(classified_errors),
        status=status,
        correction_due_at=now + timedelta(hours=settings.correction_sla_hours) if classified_errors else None,
    )
    db.add(submission)
    db.flush()

    ai_agent = GeminiComplianceAgent()
    error_rows = [
        {
            "row_number": validation_error.row_number,
            "error_code": validation_error.error_code,
            "severity": validation_error.severity,
            "error_type": error_type,
            "message": validation_error.message,
        }
        for validation_error, error_type in classified_errors
    ]
    triage = ai_agent.triage_errors(error_rows)

    persisted_errors: list[ComplianceError] = []
    errors_by_row: dict[int, list[str]] = {}
    for validation_error, error_type in classified_errors:
        errors_by_row.setdefault(validation_error.row_number, []).append(validation_error.error_code)
        triage_item = triage.get(
            f"{validation_error.row_number}:{validation_error.error_code}",
            {
                "triage_category": "VENDOR_DATA_QUALITY",
                "ai_recommendation": validation_error.message,
            },
        )
        error = ComplianceError(
            submission_id=submission.id,
            row_number=validation_error.row_number,
            error_code=validation_error.error_code,
            severity=validation_error.severity,
            error_type=error_type,
            message=validation_error.message,
            triage_category=triage_item["triage_category"],
            ai_recommendation=triage_item["ai_recommendation"],
        )
        db.add(error)
        persisted_errors.append(error)

    for row in rows:
        row_number = int(row["row_number"])
        db.add(
            SubmissionRow(
                submission_id=submission.id,
                row_number=row_number,
                part_number=_clean_text(row.get("part_number")),
                description=_clean_text(row.get("description")),
                hsn_code=_clean_text(row.get("hsn_code")),
                bcd=_clean_number(row.get("bcd")),
                cvd=_clean_number(row.get("cvd")),
                sws=_clean_number(row.get("sws")),
                igst=_clean_number(row.get("igst")),
                is_valid=row_number not in errors_by_row,
                error_summary=", ".join(errors_by_row.get(row_number, [])),
            )
        )

    if persisted_errors:
        submission.remediation_sent_at = now
    else:
        submission.resolved_at = now
        _resolve_prior_vendor_exceptions(db, vendor_email, now)

    submission.ai_audit_summary = ai_agent.generate_audit_summary(
        {
            "vendor_email": vendor_email,
            "file_name": original_file_name,
            "total_rows": len(rows),
            "error_count": len(classified_errors),
            "status": submission.status,
            "correction_due_at": submission.correction_due_at,
            "error_rows": error_rows[:20],
        }
    )

    db.commit()
    db.refresh(submission)
    for error in persisted_errors:
        db.refresh(error)

    send_correction_email_if_needed(submission, persisted_errors)
    return submission


def _resolve_prior_vendor_exceptions(db: Session, vendor_email: str, resolved_at) -> None:
    prior_submissions = db.execute(
        select(Submission).where(
            Submission.vendor_email == vendor_email,
            Submission.status.in_(["PENDING_CORRECTION", "ESCALATED"]),
        )
    ).scalars()

    for prior in prior_submissions:
        prior.status = "RESOLVED"
        prior.resolved_at = resolved_at


def _clean_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _clean_number(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(str(value).replace("%", "").strip())
    except ValueError:
        return None
