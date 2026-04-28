# Autonomous Vendor Compliance Backend

FastAPI service for ingesting vendor customs files, normalizing columns, validating HSN/duty data, classifying errors, sending remediation emails, and calculating vendor risk.

## Run

```bash
cd BACKEND
python -m venv venv
source venv/bin/activate
pip install -r ../requirements.txt
touch .env
uvicorn app.main:app --reload --port 8010
```

Set `DATABASE_URL` in `.env` to PostgreSQL for production. The default code fallback is SQLite so the demo can start without database provisioning.

For Gemini agentic AI, add:

```bash
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash
AI_AGENT_ENABLED=true
```

Gemini is used for messy column inference, exception triage, correction emails, escalation emails, audit narratives, and vendor risk insights. Core compliance validation remains deterministic for auditability.

For automatic Gmail polling:

```bash
EMAIL_POLLING_ENABLED=true
EMAIL_POLL_INTERVAL_SECONDS=300
```

Supported email attachments: `.csv`, `.xlsx`, `.xls`, and text-based `.pdf`.
