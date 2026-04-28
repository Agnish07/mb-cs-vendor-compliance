from pathlib import Path
import re
from typing import Any

import pandas as pd
from pypdf import PdfReader

from app.services.ai_agent import GeminiComplianceAgent


CANONICAL_FIELDS = ["part_number", "description", "hsn_code", "bcd", "cvd", "sws", "igst"]

COLUMN_ALIASES = {
    "part_number": {"part_number", "part no", "part_no", "part number", "material", "material code", "sku"},
    "description": {"description", "desc", "item description", "product description", "goods description"},
    "hsn_code": {"hsn", "hsn code", "ritc", "ritc code", "tariff", "tariff code", "customs tariff"},
    "bcd": {"bcd", "basic customs duty", "basic duty"},
    "cvd": {"cvd", "countervailing duty"},
    "sws": {"sws", "social welfare surcharge", "social welfare"},
    "igst": {"igst", "integrated gst", "gst"},
}


def _normalize_header(value: Any) -> str:
    return str(value).strip().lower().replace("-", " ").replace("_", " ")


def _canonical_column_map(columns: list[str]) -> dict[str, str]:
    normalized = {_normalize_header(column): column for column in columns}
    mapping: dict[str, str] = {}

    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                mapping[canonical] = normalized[alias]
                break

    return mapping


def read_vendor_file(file_path: Path) -> pd.DataFrame:
    suffix = file_path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(file_path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(file_path)
    if suffix == ".pdf":
        return read_pdf_vendor_file(file_path)
    raise ValueError("Only CSV, XLSX, XLS, and PDF files are supported")


def read_pdf_vendor_file(file_path: Path) -> pd.DataFrame:
    reader = PdfReader(str(file_path))
    text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    if not text:
        raise ValueError("PDF did not contain extractable text")

    rows = _parse_pipe_delimited_pdf_rows(text)
    if not rows:
        rows = _parse_vertical_pdf_rows(text)
    if not rows:
        rows = GeminiComplianceAgent().extract_pdf_rows(text, CANONICAL_FIELDS)
    if not rows:
        raise ValueError("No part-level duty rows could be extracted from PDF")
    return pd.DataFrame(rows)


def _parse_pipe_delimited_pdf_rows(text: str) -> list[dict[str, Any]]:
    lines = [line.strip() for line in text.splitlines() if "|" in line]
    if len(lines) < 2:
        return []

    header_index = next(
        (
            index
            for index, line in enumerate(lines)
            if "part" in line.lower() and ("hsn" in line.lower() or "ritc" in line.lower())
        ),
        None,
    )
    if header_index is None:
        return []

    headers = [cell.strip() for cell in lines[header_index].split("|")]
    column_map = _canonical_column_map(headers)
    if not {"part_number", "description", "hsn_code"}.issubset(column_map):
        return []

    rows: list[dict[str, Any]] = []
    for line in lines[header_index + 1 :]:
        cells = [cell.strip() or None for cell in line.split("|")]
        if len(cells) < len(headers):
            cells.extend([None] * (len(headers) - len(cells)))

        source = dict(zip(headers, cells, strict=False))
        row = {
            field: source.get(column_map[field]) if field in column_map else None
            for field in CANONICAL_FIELDS
        }
        if any(row.values()):
            rows.append(row)

    return rows


def _parse_vertical_pdf_rows(text: str) -> list[dict[str, Any]]:
    tokens = [line.strip() for line in text.splitlines() if line.strip()]
    normalized_tokens = [_normalize_header(token) for token in tokens]

    header_positions: list[int] = []
    for field in CANONICAL_FIELDS:
        aliases = COLUMN_ALIASES[field] | {field}
        position = next(
            (
                index
                for index, normalized in enumerate(normalized_tokens)
                if normalized in {_normalize_header(alias) for alias in aliases}
            ),
            None,
        )
        if position is None:
            return []
        header_positions.append(position)

    expected_header_positions = list(range(header_positions[0], header_positions[0] + len(CANONICAL_FIELDS)))
    if header_positions != expected_header_positions:
        return []

    values = tokens[header_positions[-1] + 1 :]
    if not values:
        return []

    part_starts = [
        index
        for index, value in enumerate(values)
        if re.match(r"^[A-Za-z]{1,5}[-_]?\d+[A-Za-z0-9-]*$", value)
    ]
    if part_starts:
        rows_from_starts: list[dict[str, Any]] = []
        for position, start in enumerate(part_starts):
            end = part_starts[position + 1] if position + 1 < len(part_starts) else len(values)
            chunk = values[start:end]
            row = _row_from_vertical_chunk(chunk)
            if row:
                rows_from_starts.append(row)
        if rows_from_starts:
            return rows_from_starts

    if len(values) % len(CANONICAL_FIELDS) != 0:
        return []

    rows: list[dict[str, Any]] = []
    width = len(CANONICAL_FIELDS)
    for start in range(0, len(values), width):
        chunk = values[start : start + width]
        row = dict(zip(CANONICAL_FIELDS, chunk, strict=True))
        if any(row.values()):
            rows.append(row)

    return rows


def _row_from_vertical_chunk(chunk: list[str]) -> dict[str, Any] | None:
    if len(chunk) == len(CANONICAL_FIELDS):
        return dict(zip(CANONICAL_FIELDS, chunk, strict=True))

    if len(chunk) == len(CANONICAL_FIELDS) - 1:
        if _looks_like_hsn(chunk[2]):
            return {
                "part_number": chunk[0],
                "description": chunk[1],
                "hsn_code": chunk[2],
                "bcd": chunk[3],
                "cvd": None,
                "sws": chunk[4],
                "igst": chunk[5],
            }

        return {
            "part_number": chunk[0],
            "description": chunk[1],
            "hsn_code": None,
            "bcd": chunk[2],
            "cvd": chunk[3],
            "sws": chunk[4],
            "igst": chunk[5],
        }

    return None


def _looks_like_hsn(value: str) -> bool:
    return bool(re.fullmatch(r"\d{4,8}", value.strip()))


def normalize_file(file_path: Path) -> list[dict[str, Any]]:
    raw = read_vendor_file(file_path)
    column_map = _canonical_column_map(list(raw.columns))
    column_map = GeminiComplianceAgent().infer_column_mapping(
        source_columns=list(raw.columns),
        canonical_fields=CANONICAL_FIELDS,
        existing_mapping=column_map,
    )

    normalized = pd.DataFrame()
    for field in CANONICAL_FIELDS:
        normalized[field] = raw[column_map[field]] if field in column_map else None

    normalized = normalized.where(pd.notna(normalized), None)

    records: list[dict[str, Any]] = []
    for index, row in normalized.iterrows():
        record = row.to_dict()
        record["row_number"] = int(index) + 2
        records.append(record)

    return records
