from collections.abc import Generator
import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
logger = logging.getLogger(__name__)

if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
elif settings.database_url.startswith("postgresql"):
    connect_args = {
        "connect_timeout": settings.db_connect_timeout_seconds,
        "options": (
            f"-c statement_timeout={settings.db_statement_timeout_ms} "
            f"-c lock_timeout={settings.db_lock_timeout_ms}"
        ),
    }
else:
    connect_args = {}

engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app.models import compliance  # noqa: F401

    logger.info("Initializing database schema")
    Base.metadata.create_all(bind=engine)
    ensure_schema_compatibility()
    logger.info("Database schema is ready")


def ensure_schema_compatibility() -> None:
    """Add columns introduced after an early local schema was created."""
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    if "errors" not in table_names or "submissions" not in table_names:
        return

    if "submission_rows" not in table_names:
        return

    submission_columns = {column["name"] for column in inspector.get_columns("submissions")}
    error_columns = {column["name"] for column in inspector.get_columns("errors")}
    statements: list[str] = []

    if "status" not in submission_columns:
        statements.append("ALTER TABLE submissions ADD COLUMN status VARCHAR(40) NOT NULL DEFAULT 'RECEIVED'")
    if "correction_due_at" not in submission_columns:
        statements.append("ALTER TABLE submissions ADD COLUMN correction_due_at TIMESTAMP WITH TIME ZONE")
    if "remediation_sent_at" not in submission_columns:
        statements.append("ALTER TABLE submissions ADD COLUMN remediation_sent_at TIMESTAMP WITH TIME ZONE")
    if "escalation_level" not in submission_columns:
        statements.append("ALTER TABLE submissions ADD COLUMN escalation_level INTEGER NOT NULL DEFAULT 0")
    if "resolved_at" not in submission_columns:
        statements.append("ALTER TABLE submissions ADD COLUMN resolved_at TIMESTAMP WITH TIME ZONE")
    if "ai_audit_summary" not in submission_columns:
        statements.append("ALTER TABLE submissions ADD COLUMN ai_audit_summary VARCHAR(2000) NOT NULL DEFAULT ''")

    if "error_type" not in error_columns:
        statements.append(
            "ALTER TABLE errors ADD COLUMN error_type VARCHAR(20) NOT NULL DEFAULT 'ISOLATED'"
        )
    if "message" not in error_columns:
        statements.append("ALTER TABLE errors ADD COLUMN message VARCHAR(500) NOT NULL DEFAULT ''")
    if "triage_category" not in error_columns:
        statements.append("ALTER TABLE errors ADD COLUMN triage_category VARCHAR(60) NOT NULL DEFAULT 'DATA_QUALITY'")
    if "ai_recommendation" not in error_columns:
        statements.append("ALTER TABLE errors ADD COLUMN ai_recommendation VARCHAR(800) NOT NULL DEFAULT ''")

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
