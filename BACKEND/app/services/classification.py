from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ComplianceError, Submission
from app.services.validation import ValidationErrorItem


def classify_errors(
    db: Session,
    vendor_email: str,
    validation_errors: list[ValidationErrorItem],
) -> list[tuple[ValidationErrorItem, str]]:
    current_counts = Counter(error.error_code for error in validation_errors)
    historical_codes = set(
        db.execute(
            select(ComplianceError.error_code)
            .join(Submission)
            .where(Submission.vendor_email == vendor_email)
            .distinct()
        ).scalars()
    )

    classified: list[tuple[ValidationErrorItem, str]] = []
    for error in validation_errors:
        if error.error_code in historical_codes:
            error_type = "SYSTEMIC"
        elif current_counts[error.error_code] >= 3:
            error_type = "PATTERN"
        else:
            error_type = "ISOLATED"
        classified.append((error, error_type))

    return classified
