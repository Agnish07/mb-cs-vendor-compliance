from collections import Counter, defaultdict
from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ComplianceError, Submission
from app.services.ai_agent import GeminiComplianceAgent


def calculate_trend_insights(db: Session) -> dict:
    submissions = db.execute(select(Submission).order_by(Submission.upload_time.asc())).scalars().all()
    errors = db.execute(select(ComplianceError).join(Submission)).scalars().all()
    submissions_by_id = {submission.id: submission for submission in submissions}

    error_counter = Counter(error.error_code for error in errors)
    triage_counter = Counter(error.triage_category for error in errors)
    vendor_submissions: dict[str, list[Submission]] = defaultdict(list)
    vendor_error_codes: dict[str, Counter] = defaultdict(Counter)
    vendor_triage_categories: dict[str, Counter] = defaultdict(Counter)
    vendor_severities: dict[str, Counter] = defaultdict(Counter)
    errored_rows_by_submission: dict[int, set[int]] = defaultdict(set)

    for submission in submissions:
        vendor_submissions[submission.vendor_email].append(submission)

    for error in errors:
        submission = submissions_by_id.get(error.submission_id)
        if submission:
            vendor_error_codes[submission.vendor_email][error.error_code] += 1
            vendor_triage_categories[submission.vendor_email][error.triage_category] += 1
            vendor_severities[submission.vendor_email][error.severity] += 1
            if error.row_number > 0:
                errored_rows_by_submission[submission.id].add(error.row_number)

    ai_agent = GeminiComplianceAgent()

    vendor_trends = [
        _build_vendor_trend(
            ai_agent,
            vendor_email,
            vendor_rows,
            vendor_error_codes[vendor_email],
            vendor_triage_categories[vendor_email],
            vendor_severities[vendor_email],
            errored_rows_by_submission,
        )
        for vendor_email, vendor_rows in vendor_submissions.items()
    ]

    timeline = [
        {
            "submission_id": submission.id,
            "vendor_email": submission.vendor_email,
            "file_name": submission.file_name,
            "upload_time": submission.upload_time,
            "error_rate": round(_row_failure_rate(submission, errored_rows_by_submission), 4),
            "error_count": submission.error_count,
            "total_rows": submission.total_rows,
        }
        for submission in submissions
    ]

    return {
        "vendors": sorted(vendor_trends, key=lambda item: item["risk_signal"], reverse=True),
        "timeline": timeline,
        "top_error_codes": [
            {"error_code": code, "count": count}
            for code, count in error_counter.most_common(8)
        ],
        "top_triage_categories": [
            {"triage_category": category, "count": count}
            for category, count in triage_counter.most_common(8)
        ],
    }


def _build_vendor_trend(
    ai_agent: GeminiComplianceAgent,
    vendor_email: str,
    submissions: list[Submission],
    error_codes: Counter,
    triage_categories: Counter,
    severities: Counter,
    errored_rows_by_submission: dict[int, set[int]],
) -> dict:
    ordered = sorted(submissions, key=lambda item: item.upload_time)
    rates = [_row_failure_rate(submission, errored_rows_by_submission) for submission in ordered]
    first_window = rates[: max(1, len(rates) // 2)]
    last_window = rates[max(0, len(rates) - max(1, len(rates) // 2)) :]

    baseline = mean(first_window) if first_window else 0
    recent = mean(last_window) if last_window else 0
    slope = _linear_slope(rates)
    forecast = min(max((rates[-1] if rates else 0) + slope, 0), 1.0)
    trajectory = _trajectory(slope, recent, baseline)
    risk_signal = _risk_signal(recent, slope, ordered)
    risk_band = _risk_band(recent)
    dominant_error_code = error_codes.most_common(1)[0][0] if error_codes else None
    trend_context = _trend_context(
        vendor_email=vendor_email,
        ordered=ordered,
        rates=rates,
        baseline=baseline,
        recent=recent,
        forecast=forecast,
        trajectory=trajectory,
        risk_band=risk_band,
        risk_signal=risk_signal,
        error_codes=error_codes,
        triage_categories=triage_categories,
        severities=severities,
        errored_rows_by_submission=errored_rows_by_submission,
    )

    return {
        "vendor_email": vendor_email,
        "submissions": len(ordered),
        "latest_error_rate": round(rates[-1] if rates else 0, 4),
        "baseline_error_rate": round(baseline, 4),
        "recent_error_rate": round(recent, 4),
        "trend_slope": round(slope, 4),
        "forecast_next_error_rate": round(forecast, 4),
        "trajectory": trajectory,
        "risk_signal": risk_signal,
        "risk_band": risk_band,
        "dominant_error_code": dominant_error_code,
        "dominant_error_count": error_codes.most_common(1)[0][1] if error_codes else 0,
        "insight": ai_agent.summarize_trend_insight(trend_context),
    }


def _row_failure_rate(submission: Submission, errored_rows_by_submission: dict[int, set[int]]) -> float:
    if not submission.total_rows:
        return 0
    failed_rows = len(errored_rows_by_submission.get(submission.id, set()))
    return min(failed_rows, submission.total_rows) / submission.total_rows


def _linear_slope(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0

    x_mean = mean(range(len(values)))
    y_mean = mean(values)
    denominator = sum((index - x_mean) ** 2 for index in range(len(values)))
    if denominator == 0:
        return 0.0
    numerator = sum((index - x_mean) * (value - y_mean) for index, value in enumerate(values))
    return numerator / denominator


def _trajectory(slope: float, recent: float, baseline: float) -> str:
    if slope > 0.05 and recent > baseline:
        return "DETERIORATING"
    if slope < -0.05 and recent < baseline:
        return "IMPROVING"
    return "STABLE"


def _risk_signal(recent: float, slope: float, submissions: list[Submission]) -> int:
    overdue_or_escalated = sum(1 for submission in submissions if submission.status == "ESCALATED")
    return int((recent * 100) + max(slope, 0) * 100 + overdue_or_escalated * 15)


def _risk_band(recent: float) -> str:
    if recent >= 0.6:
        return "HIGH"
    if recent >= 0.25:
        return "MEDIUM"
    return "LOW"


def _trend_context(
    vendor_email: str,
    ordered: list[Submission],
    rates: list[float],
    baseline: float,
    recent: float,
    forecast: float,
    trajectory: str,
    risk_band: str,
    risk_signal: int,
    error_codes: Counter,
    triage_categories: Counter,
    severities: Counter,
    errored_rows_by_submission: dict[int, set[int]],
) -> dict:
    total_rows = sum(submission.total_rows for submission in ordered)
    error_count = sum(submission.error_count for submission in ordered)
    failed_rows = sum(len(errored_rows_by_submission.get(submission.id, set())) for submission in ordered)
    return {
        "vendor_email": vendor_email,
        "submissions": len(ordered),
        "total_rows": total_rows,
        "failed_rows": failed_rows,
        "validation_error_count": error_count,
        "row_failure_rate_percent": round(recent * 100),
        "latest_row_failure_rate_percent": round((rates[-1] if rates else 0) * 100),
        "baseline_row_failure_rate_percent": round(baseline * 100),
        "forecast_next_percent": round(forecast * 100),
        "trajectory": trajectory,
        "risk_band": risk_band,
        "risk_signal": risk_signal,
        "dominant_error_code": error_codes.most_common(1)[0][0] if error_codes else None,
        "top_error_codes": [{"error_code": code, "count": count} for code, count in error_codes.most_common(5)],
        "triage_mix": [{"triage_category": category, "count": count} for category, count in triage_categories.most_common(5)],
        "severity_mix": [{"severity": severity, "count": count} for severity, count in severities.most_common(5)],
        "recent_submissions": [
            {
                "submission_id": submission.id,
                "file_name": submission.file_name,
                "status": submission.status,
                "total_rows": submission.total_rows,
                "failed_rows": len(errored_rows_by_submission.get(submission.id, set())),
                "validation_error_count": submission.error_count,
                "row_failure_rate_percent": round(
                    _row_failure_rate(submission, errored_rows_by_submission) * 100
                ),
                "uploaded_at": submission.upload_time,
            }
            for submission in ordered[-5:]
        ],
    }
