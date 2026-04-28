from __future__ import annotations

import json
import re
from functools import cached_property
from typing import Any

from app.config import get_settings


class GeminiComplianceAgent:
    def __init__(self) -> None:
        self.settings = get_settings()

    @cached_property
    def enabled(self) -> bool:
        return bool(self.settings.ai_agent_enabled and self.settings.gemini_api_key)

    @cached_property
    def client(self) -> Any | None:
        if not self.enabled:
            return None
        try:
            from google import genai
        except ImportError:
            return None
        return genai.Client(api_key=self.settings.gemini_api_key)

    def generate_text(self, prompt: str, fallback: str, max_length: int = 4000) -> str:
        if not self.client:
            return fallback

        try:
            response = self.client.models.generate_content(
                model=self.settings.gemini_model,
                contents=prompt,
            )
        except Exception:
            return fallback

        text = (getattr(response, "text", None) or "").strip()
        if not text:
            return fallback
        return text[:max_length]

    def infer_column_mapping(
        self,
        source_columns: list[str],
        canonical_fields: list[str],
        existing_mapping: dict[str, str],
    ) -> dict[str, str]:
        missing_fields = [field for field in canonical_fields if field not in existing_mapping]
        if not missing_fields:
            return existing_mapping

        fallback = json.dumps({})
        prompt = f"""
You are an enterprise customs compliance data-mapping agent.
Map messy vendor spreadsheet columns to this canonical schema:
{json.dumps(canonical_fields)}

Source columns:
{json.dumps(source_columns)}

Already mapped:
{json.dumps(existing_mapping)}

Return only strict JSON. Keys must be canonical field names, values must exactly match one source column.
Only include mappings you are confident about.
"""
        text = self.generate_text(prompt=prompt, fallback=fallback, max_length=1200)
        ai_mapping = self._parse_json_object(text)
        if not isinstance(ai_mapping, dict):
            return existing_mapping

        allowed_fields = set(canonical_fields)
        allowed_columns = set(source_columns)
        merged = dict(existing_mapping)
        for field, column in ai_mapping.items():
            if field in allowed_fields and column in allowed_columns and field not in merged:
                merged[field] = column

        return merged

    def extract_pdf_rows(self, pdf_text: str, canonical_fields: list[str]) -> list[dict[str, Any]]:
        fallback: list[dict[str, Any]] = []
        prompt = f"""
You are a customs duty PDF extraction agent.
Extract part-level customs duty rows from this vendor PDF text into a canonical JSON array.

Canonical fields:
{json.dumps(canonical_fields)}

Rules:
- Return only strict JSON.
- Shape: {{"rows": [{{"part_number": "...", "description": "...", "hsn_code": "...", "bcd": 0, "cvd": 0, "sws": 0, "igst": 18}}]}}
- Use null when a field is not present.
- Do not invent rows.
- Duty values must be numbers when possible.

PDF text:
{pdf_text[:18000]}
"""
        text = self.generate_text(prompt=prompt, fallback=json.dumps({"rows": []}), max_length=12000)
        parsed = self._parse_json_object(text)
        if not parsed or not isinstance(parsed.get("rows"), list):
            return fallback

        rows: list[dict[str, Any]] = []
        for item in parsed["rows"]:
            if not isinstance(item, dict):
                continue
            rows.append({field: item.get(field) for field in canonical_fields})
        return rows

    def draft_correction_email(self, vendor_email: str, file_name: str, error_rows: list[dict[str, Any]]) -> str:
        fallback = self._fallback_email_body(file_name, error_rows)
        prompt = f"""
You are an autonomous vendor compliance remediation agent.
Draft a concise, professional correction email for vendor {vendor_email}.

File: {file_name}
Validation errors:
{json.dumps(error_rows, default=str)}

Requirements:
- Mention that the corrected CSV/XLSX should be sent as a reply attachment.
- Include a compact error table.
- Be specific and polite.
- Do not invent errors.
"""
        return self.generate_text(prompt=prompt, fallback=fallback, max_length=6000)

    def triage_errors(self, error_rows: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
        fallback = {
            self._error_key(error): self._fallback_triage(error)
            for error in error_rows
        }
        prompt = f"""
You are an autonomous customs compliance exception triage agent.
Classify each validation error into exactly one triage_category:
- VENDOR_DATA_QUALITY
- INVALID_MASTER_REFERENCE
- DUTY_COMPUTATION_RISK
- STRUCTURAL_FILE_DEFECT
- SYSTEMIC_VENDOR_FAILURE

For each error, provide a short ai_recommendation that tells operations/vendor what to fix.

Errors:
{json.dumps(error_rows, default=str)}

Return only strict JSON in this shape:
{{
  "items": [
    {{
      "key": "row_number:error_code",
      "triage_category": "VENDOR_DATA_QUALITY",
      "ai_recommendation": "..."
    }}
  ]
}}
"""
        text = self.generate_text(prompt=prompt, fallback=json.dumps({"items": []}), max_length=5000)
        parsed = self._parse_json_object(text)
        if not parsed or not isinstance(parsed.get("items"), list):
            return fallback

        allowed_categories = {
            "VENDOR_DATA_QUALITY",
            "INVALID_MASTER_REFERENCE",
            "DUTY_COMPUTATION_RISK",
            "STRUCTURAL_FILE_DEFECT",
            "SYSTEMIC_VENDOR_FAILURE",
        }
        triage = dict(fallback)
        for item in parsed["items"]:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key", ""))
            category = str(item.get("triage_category", ""))
            recommendation = str(item.get("ai_recommendation", "")).strip()
            if key in triage and category in allowed_categories and recommendation:
                triage[key] = {
                    "triage_category": category,
                    "ai_recommendation": recommendation[:800],
                }

        return triage

    def generate_audit_summary(self, submission_context: dict[str, Any]) -> str:
        fallback = self._fallback_audit_summary(submission_context)
        prompt = f"""
You are an audit narrative agent for customs duty compliance.
Write a concise audit trail for this automated submission review.

Context:
{json.dumps(submission_context, default=str)}

Requirements:
- 3 to 5 sentences.
- State intake outcome, validation result, remediation/escalation status, and residual risk.
- Do not invent facts.
"""
        return self.generate_text(prompt=prompt, fallback=fallback, max_length=1800)

    def draft_escalation_email(self, submission_context: dict[str, Any]) -> str:
        fallback = self._fallback_escalation_email(submission_context)
        prompt = f"""
You are a vendor governance escalation agent.
Draft a concise escalation email for an overdue customs duty correction.

Context:
{json.dumps(submission_context, default=str)}

Requirements:
- Mention the correction SLA breach.
- Ask for an updated CSV/XLSX attachment.
- Include current escalation level and error count.
- Keep a professional, firm tone.
"""
        return self.generate_text(prompt=prompt, fallback=fallback, max_length=4000)

    def summarize_vendor_risk(self, metrics: dict[str, Any]) -> str:
        fallback = self._fallback_risk_summary(metrics)
        prompt = f"""
You are a vendor governance risk agent.
Create one short operational risk insight for this vendor. Use plain business language.
Do not recommend legal action. Do not invent data.

Metrics:
{json.dumps(metrics, default=str)}
"""
        return self.generate_text(prompt=prompt, fallback=fallback, max_length=600)

    def summarize_trend_insight(self, trend_context: dict[str, Any]) -> str:
        fallback = self._fallback_trend_summary(trend_context)
        prompt = f"""
You are an autonomous customs-duty compliance trend-mining agent for MB India.

Business context:
- Vendors submit heterogeneous duty files by email only.
- The system must detect part-level data quality failures before they cause customs, audit, penalty, or cash-flow exposure.
- A row-failure rate is the percentage of submitted rows with at least one validation error. It is capped between 0% and 100%.
- Trajectory describes direction only: STABLE means the vendor is not improving or deteriorating materially. It does not mean low risk.
- Risk band describes current governance severity: LOW, MEDIUM, or HIGH.

Vendor trend context:
{json.dumps(trend_context, default=str)}

Write exactly one concise dashboard insight sentence.
Requirements:
- 22 to 42 words.
- Use the supplied risk_band, trajectory, row_failure_rate_percent, forecast_next_percent, and dominant_error_code.
- Mention the most important operational action or governance implication.
- Do not invent facts, laws, penalties, or new numbers.
- Do not use markdown, bullets, greetings, or labels.
"""
        text = self.generate_text(prompt=prompt, fallback=fallback, max_length=700)
        return " ".join(text.split())[:700]

    def _parse_json_object(self, text: str) -> dict[str, Any] | None:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
            stripped = re.sub(r"```$", "", stripped).strip()

        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        candidate = match.group(0) if match else stripped
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    def _error_key(self, error: dict[str, Any]) -> str:
        return f"{error.get('row_number')}:{error.get('error_code')}"

    def _fallback_triage(self, error: dict[str, Any]) -> dict[str, str]:
        error_code = str(error.get("error_code", ""))
        error_type = str(error.get("error_type", ""))
        if error_type == "SYSTEMIC":
            category = "SYSTEMIC_VENDOR_FAILURE"
        elif error_code == "INVALID_HSN_CODE":
            category = "INVALID_MASTER_REFERENCE"
        elif error_code == "DUTY_OUT_OF_RANGE":
            category = "DUTY_COMPUTATION_RISK"
        elif error_code in {"MISSING_MANDATORY_FIELD", "MISSING_DUTY_COMPONENT"}:
            category = "VENDOR_DATA_QUALITY"
        else:
            category = "STRUCTURAL_FILE_DEFECT"

        return {
            "triage_category": category,
            "ai_recommendation": str(error.get("message", "Review and correct this row."))[:800],
        }

    def _fallback_email_body(self, file_name: str, error_rows: list[dict[str, Any]]) -> str:
        lines = [
            "Hello,",
            "",
            f"Your customs duty submission {file_name} needs corrections before it can be accepted.",
            "Please correct the rows below and reply with a revised CSV/XLSX attachment.",
            "",
            "row_number,error_code,severity,error_type,message",
        ]
        for error in error_rows:
            lines.append(
                f"{error['row_number']},{error['error_code']},{error['severity']},"
                f"{error['error_type']},{error['message']}"
            )
        lines.extend(["", "Regards,", "Vendor Compliance Automation"])
        return "\n".join(lines)

    def _fallback_risk_summary(self, metrics: dict[str, Any]) -> str:
        risk_level = metrics.get("risk_level", "UNKNOWN")
        error_count = metrics.get("error_count", 0)
        submissions = metrics.get("submissions", 0)
        return f"{risk_level.title()} risk based on {error_count} errors across {submissions} submissions."

    def _fallback_trend_summary(self, context: dict[str, Any]) -> str:
        vendor = context.get("vendor_email", "This vendor")
        risk_band = str(context.get("risk_band", "UNKNOWN")).lower()
        trajectory = str(context.get("trajectory", "STABLE")).lower()
        recent = context.get("row_failure_rate_percent", 0)
        forecast = context.get("forecast_next_percent", 0)
        dominant = context.get("dominant_error_code") or "no dominant error"
        return (
            f"{vendor} is {trajectory} with {risk_band} current risk, "
            f"{recent}% recent row failure, and a {forecast}% next-submission forecast; "
            f"prioritize correction of {dominant} before acceptance."
        )

    def _fallback_audit_summary(self, context: dict[str, Any]) -> str:
        status = context.get("status", "RECEIVED")
        file_name = context.get("file_name", "submission")
        error_count = context.get("error_count", 0)
        if error_count:
            return (
                f"{file_name} was ingested and reviewed by the automated compliance pipeline. "
                f"The submission produced {error_count} validation exceptions and is currently {status}. "
                "A remediation request was prepared for vendor correction before compliance acceptance."
            )
        return (
            f"{file_name} was ingested, normalized, and validated with no exceptions. "
            "The submission is accepted with no residual validation risk identified by the current rules."
        )

    def _fallback_escalation_email(self, context: dict[str, Any]) -> str:
        return "\n".join(
            [
                "Hello,",
                "",
                f"Correction for {context.get('file_name', 'your submission')} is overdue.",
                f"Escalation level: {context.get('escalation_level', 1)}",
                f"Open error count: {context.get('error_count', 0)}",
                "",
                "Please reply with the corrected CSV/XLSX attachment at the earliest.",
                "",
                "Regards,",
                "Vendor Compliance Automation",
            ]
        )
