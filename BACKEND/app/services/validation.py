from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


MANDATORY_TEXT_FIELDS = ["part_number", "description", "hsn_code"]
DUTY_FIELDS = ["bcd", "cvd", "sws", "igst"]


@dataclass(slots=True)
class ValidationErrorItem:
    row_number: int
    error_code: str
    severity: str
    message: str


def _is_blank(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def _to_decimal(value: Any) -> Decimal | None:
    if _is_blank(value):
        return None
    try:
        decimal_value = Decimal(str(value).replace("%", "").strip())
    except InvalidOperation:
        return None
    return decimal_value if decimal_value.is_finite() else None


def validate_rows(rows: list[dict[str, Any]], hsn_master_codes: set[str]) -> list[ValidationErrorItem]:
    errors: list[ValidationErrorItem] = []

    for row in rows:
        row_number = int(row["row_number"])

        for field in MANDATORY_TEXT_FIELDS:
            if _is_blank(row.get(field)):
                errors.append(
                    ValidationErrorItem(
                        row_number=row_number,
                        error_code="MISSING_MANDATORY_FIELD",
                        severity="HIGH",
                        message=f"Missing mandatory field: {field}",
                    )
                )

        hsn_code = "" if _is_blank(row.get("hsn_code")) else str(row.get("hsn_code")).strip()
        if hsn_code and not _is_valid_hsn(hsn_code, hsn_master_codes):
            errors.append(
                ValidationErrorItem(
                    row_number=row_number,
                    error_code="INVALID_HSN_CODE",
                    severity="HIGH",
                    message=f"HSN/RITC code {hsn_code} is not present in the master list",
                )
            )

        for field in DUTY_FIELDS:
            duty = _to_decimal(row.get(field))
            if duty is None:
                errors.append(
                    ValidationErrorItem(
                        row_number=row_number,
                        error_code="MISSING_DUTY_COMPONENT",
                        severity="MEDIUM",
                        message=f"Missing or non-numeric duty component: {field}",
                    )
                )
                continue

            if duty < 0 or duty > 100:
                errors.append(
                    ValidationErrorItem(
                        row_number=row_number,
                        error_code="DUTY_OUT_OF_RANGE",
                        severity="MEDIUM",
                        message=f"Duty component {field} must be between 0 and 100",
                    )
                )

    return errors


def _is_valid_hsn(hsn_code: str, hsn_master_codes: set[str]) -> bool:
    normalized_code = hsn_code.replace(".", "").strip()
    normalized_master = {code.replace(".", "").strip() for code in hsn_master_codes}
    if normalized_code in normalized_master:
        return True

    return any(
        master.startswith(normalized_code) or normalized_code.startswith(master)
        for master in normalized_master
    )
