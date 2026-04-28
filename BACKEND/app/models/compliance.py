from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    vendor_email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    upload_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="RECEIVED", nullable=False, index=True)
    correction_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    remediation_sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    escalation_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    ai_audit_summary: Mapped[str] = mapped_column(String(2000), default="", nullable=False)

    errors: Mapped[list["ComplianceError"]] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
    )
    rows: Mapped[list["SubmissionRow"]] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
    )


class SubmissionRow(Base):
    __tablename__ = "submission_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id"), nullable=False, index=True)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    part_number: Mapped[str] = mapped_column(String(255), default="", nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    hsn_code: Mapped[str] = mapped_column(String(50), default="", nullable=False, index=True)
    bcd: Mapped[float] = mapped_column(Numeric(8, 2), nullable=True)
    cvd: Mapped[float] = mapped_column(Numeric(8, 2), nullable=True)
    sws: Mapped[float] = mapped_column(Numeric(8, 2), nullable=True)
    igst: Mapped[float] = mapped_column(Numeric(8, 2), nullable=True)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    error_summary: Mapped[str] = mapped_column(String(800), default="", nullable=False)

    submission: Mapped[Submission] = relationship(back_populates="rows")


class ComplianceError(Base):
    __tablename__ = "errors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id"), nullable=False, index=True)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    error_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    error_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    triage_category: Mapped[str] = mapped_column(String(60), default="DATA_QUALITY", nullable=False, index=True)
    ai_recommendation: Mapped[str] = mapped_column(String(800), default="", nullable=False)

    submission: Mapped[Submission] = relationship(back_populates="errors")
