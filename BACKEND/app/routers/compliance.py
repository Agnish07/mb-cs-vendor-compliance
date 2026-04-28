from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import ComplianceError, Submission, SubmissionRow
from app.schemas import CorrectEntryOut, ErrorOut, EscalationOut, SubmissionOut, TrendInsightsOut, UploadResult, VendorRiskOut
from app.services.escalation import list_open_escalations, run_escalation_cycle
from app.services.ingestion import ingest_unread_email_attachments
from app.services.pipeline import process_upload
from app.services.risk import calculate_vendor_risk
from app.services.trends import calculate_trend_insights

router = APIRouter(tags=["compliance"])


@router.get("/submissions", response_model=list[SubmissionOut])
def list_submissions(db: Session = Depends(get_db)) -> list[Submission]:
    return list(db.execute(select(Submission).order_by(Submission.upload_time.desc())).scalars())


@router.get("/errors", response_model=list[ErrorOut])
def list_errors(db: Session = Depends(get_db)) -> list[ComplianceError]:
    return list(db.execute(select(ComplianceError).order_by(ComplianceError.id.desc())).scalars())


@router.get("/correct-entries", response_model=list[CorrectEntryOut])
def correct_entries(db: Session = Depends(get_db)) -> list[CorrectEntryOut]:
    rows = db.execute(
        select(SubmissionRow, Submission)
        .join(Submission)
        .where(SubmissionRow.is_valid.is_(True))
        .order_by(Submission.upload_time.desc(), SubmissionRow.row_number.asc())
    ).all()

    return [
        CorrectEntryOut(
            id=row.id,
            submission_id=row.submission_id,
            vendor_email=submission.vendor_email,
            file_name=submission.file_name,
            upload_time=submission.upload_time,
            row_number=row.row_number,
            part_number=row.part_number,
            description=row.description,
            hsn_code=row.hsn_code,
            bcd=float(row.bcd) if row.bcd is not None else None,
            cvd=float(row.cvd) if row.cvd is not None else None,
            sws=float(row.sws) if row.sws is not None else None,
            igst=float(row.igst) if row.igst is not None else None,
        )
        for row, submission in rows
    ]


@router.get("/vendor-risk", response_model=list[VendorRiskOut])
def vendor_risk(db: Session = Depends(get_db)) -> list[VendorRiskOut]:
    return calculate_vendor_risk(db)


@router.get("/trend-insights", response_model=TrendInsightsOut)
def trend_insights(db: Session = Depends(get_db)) -> dict:
    return calculate_trend_insights(db)


@router.get("/escalations", response_model=list[EscalationOut])
def escalations(db: Session = Depends(get_db)) -> list[Submission]:
    return list_open_escalations(db)


@router.post("/run-escalations", response_model=list[EscalationOut])
def run_escalations(db: Session = Depends(get_db)) -> list[Submission]:
    return run_escalation_cycle(db)


@router.post("/upload", response_model=UploadResult)
def upload_submission(
    file: UploadFile = File(...),
    vendor_email: str = Form("manual-upload@example.com"),
    db: Session = Depends(get_db),
) -> UploadResult:
    try:
        submission = process_upload(db=db, file=file, vendor_email=vendor_email)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    persisted = db.execute(
        select(Submission)
        .where(Submission.id == submission.id)
        .options(selectinload(Submission.errors))
    ).scalar_one()
    return UploadResult(submission=persisted, errors=persisted.errors)


@router.post("/ingest-emails")
def ingest_emails(db: Session = Depends(get_db)) -> dict[str, list[int] | int]:
    submission_ids = ingest_unread_email_attachments(db)
    return {"processed": len(submission_ids), "submission_ids": submission_ids}
