"""Setup pengujian: membuat database PostgreSQL uji yang bersih.

Jalankan:
    TEST_DATABASE_ADMIN_URL="postgresql://postgres@localhost:5432/postgres" pytest -q
"""
import os
import pathlib
import sys

import psycopg
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ADMIN_URL = os.environ.get("TEST_DATABASE_ADMIN_URL", "postgresql://postgres@localhost:5432/postgres")
TEST_DB = "eventcal_pytest"
TEST_URL = ADMIN_URL.rsplit("/", 1)[0] + "/" + TEST_DB

os.environ["DATABASE_URL"] = TEST_URL
os.environ["APP_SECRET"] = "test-secret"
os.environ["ADMIN_SESSION_TIMEOUT_MINUTES"] = "30"


@pytest.fixture(scope="session", autouse=True)
def database():
    with psycopg.connect(ADMIN_URL, autocommit=True) as conn:
        conn.execute(f"drop database if exists {TEST_DB} with (force)")
        conn.execute(f"create database {TEST_DB}")
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        conn.execute((ROOT / "sql" / "schema.sql").read_text())
    yield TEST_URL
    import database as db
    db.close_pool()


@pytest.fixture(autouse=True)
def clean_tables(database):
    with psycopg.connect(database, autocommit=True) as conn:
        conn.execute("""truncate events, booking_requests, notifications, audit_logs, admin_sessions,
                        rate_limits restart identity cascade""")
        conn.execute("delete from calendar_dates where updated_by <> 'system'")
        conn.execute("update calendar_dates set lock_status = 'open'")
        # Periode uji relatif terhadap hari ini agar tes tetap valid kapan pun dijalankan
        conn.execute("""update calendar_settings set start_date = current_date - 10, end_date = current_date + 200,
                        day_start_time='06:00', day_end_time='22:00', booking_open=true, max_pending_per_whatsapp=5""")
    yield


@pytest.fixture
def admin_ctx():
    import secrets

    import database as db
    token = secrets.token_urlsafe(32)
    db.create_admin_session(token, "Ketua Uji", "client-admin")
    return db.AdminContext(token=token, admin_label="Ketua Uji")
