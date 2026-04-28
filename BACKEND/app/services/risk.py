from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ComplianceError, Submission
from app.schemas import VendorRiskOut
from app.services.ai_agent import GeminiComplianceAgent


SEVERITY_POINTS = {"LOW": 2, "MEDIUM": 6, "HIGH": 12, "CRITICAL": 20}


def _risk_level(score: float) -> str:
    if score >= 80:
        return "LOW"
    if score >= 55:
        return "MEDIUM"
    return "HIGH"


def calculate_vendor_risk(db: Session) -> list[VendorRiskOut]:
    submissions = db.execute(select(Submission)).scalars().all()
    errors = db.execute(select(ComplianceError).join(Submission)).scalars().all()
    submission_by_id = {submission.id: submission for submission in submissions}

    vendors: dict[str, dict[str, float | int | set]] = defaultdict(
        lambda: {
            "submissions": 0,
            "rows": 0,
            "errors": 0,
            "severity": 0.0,
            "repeated_failures": 0,
            "errored_submissions": set(),
            "errored_rows": set(),
        }
    )

    for submission in submissions:
        metrics = vendors[submission.vendor_email]
        metrics["submissions"] = int(metrics["submissions"]) + 1
        metrics["rows"] = int(metrics["rows"]) + submission.total_rows
        metrics["errors"] = int(metrics["errors"]) + submission.error_count
        if submission.error_count:
            cast_set = metrics["errored_submissions"]
            if isinstance(cast_set, set):
                cast_set.add(submission.id)

    for error in errors:
        submission = submission_by_id.get(error.submission_id)
        if not submission:
            continue
        metrics = vendors[submission.vendor_email]
        metrics["severity"] = float(metrics["severity"]) + SEVERITY_POINTS.get(error.severity.upper(), 4)
        cast_rows = metrics["errored_rows"]
        if isinstance(cast_rows, set) and error.row_number > 0:
            cast_rows.add((submission.id, error.row_number))
        if error.error_type == "SYSTEMIC":
            metrics["repeated_failures"] = int(metrics["repeated_failures"]) + 1

    results: list[VendorRiskOut] = []
    ai_agent = GeminiComplianceAgent()
    for vendor_email, metrics in vendors.items():
        total_rows = int(metrics["rows"])
        error_count = int(metrics["errors"])
        row_failures = metrics["errored_rows"]
        row_failure_count = len(row_failures) if isinstance(row_failures, set) else min(error_count, total_rows)
        error_rate = row_failure_count / total_rows if total_rows else 0.0
        submissions_count = int(metrics["submissions"])
        errored_submissions = metrics["errored_submissions"]
        errored_submission_count = len(errored_submissions) if isinstance(errored_submissions, set) else 0
        severity_ratio = min(float(metrics["severity"]) / max(total_rows * SEVERITY_POINTS["CRITICAL"], 1), 1.0)
        quality_penalty = error_rate * 55
        severity_weight = severity_ratio * 25
        systemic_penalty = min(int(metrics["repeated_failures"]) * 2, 12)
        recurrence_penalty = (errored_submission_count / submissions_count * 8) if submissions_count else 0
        risk_score = max(
            0.0,
            round(100 - (quality_penalty + severity_weight + systemic_penalty + recurrence_penalty), 2),
        )
        risk_level = _risk_level(risk_score)
        risk_metrics = {
            "vendor_email": vendor_email,
            "submissions": int(metrics["submissions"]),
            "total_rows": total_rows,
            "error_count": error_count,
            "error_rate": round(error_rate, 4),
            "severity_weight": round(severity_weight, 2),
            "repeated_failures": int(metrics["repeated_failures"]),
            "risk_score": risk_score,
            "risk_level": risk_level,
        }

        results.append(
            VendorRiskOut(
                vendor_email=vendor_email,
                submissions=int(metrics["submissions"]),
                total_rows=total_rows,
                error_count=error_count,
                error_rate=round(error_rate, 4),
                severity_weight=round(severity_weight, 2),
                repeated_failures=int(metrics["repeated_failures"]),
                average_response_delay_hours=None,
                risk_score=risk_score,
                risk_level=risk_level,
                ai_insight=ai_agent.summarize_vendor_risk(risk_metrics),
            )
        )

    return sorted(results, key=lambda item: item.risk_score)
