from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ErrorOut(BaseModel):
    id: int
    submission_id: int
    row_number: int
    error_code: str
    severity: str
    error_type: str
    message: str
    triage_category: str
    ai_recommendation: str

    model_config = ConfigDict(from_attributes=True)


class SubmissionOut(BaseModel):
    id: int
    vendor_email: str
    file_name: str
    upload_time: datetime
    total_rows: int
    error_count: int
    status: str
    correction_due_at: datetime | None
    remediation_sent_at: datetime | None
    escalation_level: int
    resolved_at: datetime | None
    ai_audit_summary: str

    model_config = ConfigDict(from_attributes=True)


class UploadResult(BaseModel):
    submission: SubmissionOut
    errors: list[ErrorOut]


class CorrectEntryOut(BaseModel):
    id: int
    submission_id: int
    vendor_email: str
    file_name: str
    upload_time: datetime
    row_number: int
    part_number: str
    description: str
    hsn_code: str
    bcd: float | None
    cvd: float | None
    sws: float | None
    igst: float | None

    model_config = ConfigDict(from_attributes=True)


class VendorRiskOut(BaseModel):
    vendor_email: str
    submissions: int
    total_rows: int
    error_count: int
    error_rate: float
    severity_weight: float
    repeated_failures: int
    average_response_delay_hours: float | None
    risk_score: float
    risk_level: str
    ai_insight: str | None = None


class EscalationOut(BaseModel):
    id: int
    vendor_email: str
    file_name: str
    status: str
    upload_time: datetime
    correction_due_at: datetime | None
    escalation_level: int
    error_count: int
    ai_audit_summary: str

    model_config = ConfigDict(from_attributes=True)


class VendorTrendOut(BaseModel):
    vendor_email: str
    submissions: int
    latest_error_rate: float
    baseline_error_rate: float
    recent_error_rate: float
    trend_slope: float
    forecast_next_error_rate: float
    trajectory: str
    risk_signal: int
    risk_band: str
    dominant_error_code: str | None
    dominant_error_count: int
    insight: str


class TrendTimelineOut(BaseModel):
    submission_id: int
    vendor_email: str
    file_name: str
    upload_time: datetime
    error_rate: float
    error_count: int
    total_rows: int


class TrendCountOut(BaseModel):
    error_code: str | None = None
    triage_category: str | None = None
    count: int


class TrendInsightsOut(BaseModel):
    vendors: list[VendorTrendOut]
    timeline: list[TrendTimelineOut]
    top_error_codes: list[TrendCountOut]
    top_triage_categories: list[TrendCountOut]
