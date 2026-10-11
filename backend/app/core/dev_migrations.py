"""
Tiny, idempotent schema upgrades for existing dev databases.

`Base.metadata.create_all` only creates missing TABLES; it never alters an
existing one. Databases created before the patient role existed therefore
need two small changes. Real deployments should use Alembic instead
(alembic is already in requirements.txt).
"""
import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

log = logging.getLogger("medisight.migrations")


def upgrade_for_patient_role(engine: Engine) -> None:
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return  # fresh database: create_all already built the new schema

    # 1) users.patient_id (links a patient login to its clinical record)
    columns = {c["name"] for c in inspector.get_columns("users")}
    if "patient_id" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE users ADD COLUMN patient_id INTEGER REFERENCES patients(id)"))
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_patient_id ON users (patient_id)"))
        log.info("Added users.patient_id")

    # 2) PostgreSQL stores UserRole as a native ENUM that needs the new value.
    #    SQLite stores it as plain text, so nothing to do there.
    if engine.dialect.name == "postgresql":
        try:
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
                conn.execute(text("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'PATIENT'"))
        except Exception as exc:  # pragma: no cover - depends on the deployment
            log.warning("Could not extend userrole enum automatically: %s", exc)
