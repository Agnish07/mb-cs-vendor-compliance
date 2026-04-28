# Autonomous Vendor Compliance System

Full-stack compliance platform for vendor customs duty submissions. It supports CSV/XLSX intake, canonical normalization, rule-based validation, error classification, remediation email generation, vendor risk scoring, and a React monitoring dashboard.

## Backend

```bash
cd BACKEND
python -m venv venv
source venv/bin/activate
pip install -r ../requirements.txt
touch .env
uvicorn app.main:app --reload --port 8010
```

Use PostgreSQL by setting `DATABASE_URL` in `BACKEND/.env`:

```bash
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/vendor_compliance
```

To enable Gemini-powered agentic AI, add these keys to `BACKEND/.env`:

```bash
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash
AI_AGENT_ENABLED=true
```

The AI layer enhances column mapping, exception triage, remediation emails, escalation emails, audit narratives, and vendor risk insights. If the key is missing or the API call fails, the backend falls back to deterministic rules.

The backend runs at `http://localhost:8010` by default in this project. It exposes:

- `GET /health`
- `GET /submissions`
- `GET /errors`
- `GET /vendor-risk`
- `POST /upload`
- `POST /ingest-emails`
- `GET /escalations`
- `POST /run-escalations`
- `GET /ai/status`
- `GET /email/status`

## Agentic Governance Layer

The system includes these autonomous agents:

- Ingestion Agent: reads email attachments and manual uploads.
- Normalization Agent: maps heterogeneous vendor files into the canonical schema, with Gemini assistance for messy headers.
- Validation Agent: applies auditable HSN and duty checks.
- Classification Agent: marks issues as isolated, pattern, or systemic.
- Exception Triage Agent: assigns root-cause categories and recommendations.
- Remediation Agent: drafts and sends vendor correction guidance.
- Escalation Agent: detects overdue correction loops and escalates automatically.
- Audit Narrative Agent: produces submission-level compliance audit summaries.
- Risk Agent: scores vendors and generates AI risk insights.

## Frontend

```bash
cd frontend
npm install
touch .env
npm run dev
```

Open `http://localhost:5173`.

If you need a custom API URL, add this to `frontend/.env`:

```bash
VITE_API_BASE_URL=http://localhost:8010
```

## Email Automation

Set IMAP/SMTP values in `BACKEND/.env`. When `EMAIL_AUTOMATION_ENABLED=true`, remediation emails are sent through SMTP. IMAP ingestion can be triggered with `POST /ingest-emails`, which fetches unread CSV/XLSX attachments and runs the same processing pipeline.

For fully automatic Gmail polling, add:

```bash
EMAIL_POLLING_ENABLED=true
EMAIL_POLL_INTERVAL_SECONDS=300
```

When the backend is running, it checks unread Gmail messages on that interval, extracts `.csv`, `.xlsx`, `.xls`, and text-based `.pdf` attachments, identifies the vendor from the sender email, runs the full validation/AI governance pipeline, sends correction emails when needed, and records the submission in PostgreSQL.
