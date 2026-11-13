"""Smoke test UI dengan Streamlit AppTest: semua halaman dirender tanpa error, halaman admin terlindungi."""
import os
import secrets
from datetime import time, timedelta

import pytest
from streamlit.testing.v1 import AppTest

import auth
import config
import database as db
from utils.helpers import today_local

APP = os.path.join(os.path.dirname(__file__), "..", "app.py")
PUBLIC_PAGES = ["views/dashboard.py", "views/calendar.py", "views/booking.py", "views/my_bookings.py"]
ADMIN_PAGES = ["views/approvals.py", "views/event_management.py", "views/date_management.py",
               "views/audit_log.py", "views/settings.py"]


@pytest.fixture(autouse=True)
def pin_secret(monkeypatch):
    monkeypatch.setenv("ADMIN_PIN_HASH", auth.hash_pin("Uji12345"))
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


def seed():
    d = today_local() + timedelta(days=5)
    r = db.create_booking_request(dict(
        requester_name="Pemohon Uji", requester_whatsapp="081234567890", event_name="Rapat Uji",
        category="Rapat", requested_date=d, start_time=time(9), end_time=time(10),
        description="Deskripsi uji coba"), "seed")
    return r


def new_app():
    at = AppTest.from_file(APP, default_timeout=60)
    return at


def assert_ok(at):
    assert not at.exception, [e.value for e in at.exception]


def test_public_pages_render():
    seed()
    at = new_app()
    at.run()
    assert_ok(at)
    assert any("Kalender Kegiatan Panitia" in m.value for m in at.markdown)
    for page in PUBLIC_PAGES[1:]:
        at.switch_page(page).run()
        assert_ok(at)


def test_admin_pages_blocked_for_public():
    at = new_app()
    at.run()
    for page in ADMIN_PAGES:
        # halaman admin tidak didaftarkan di navigasi publik
        with pytest.raises(ValueError, match="Could not find a navigation page"):
            at.switch_page(page)


@pytest.mark.parametrize("page", ADMIN_PAGES)
def test_admin_page_script_guard(page):
    """Walau skrip halaman admin dieksekusi langsung, require_admin() menghentikannya."""
    at = AppTest.from_file(os.path.join(os.path.dirname(__file__), "..", page), default_timeout=30)
    at.run()
    assert_ok(at)
    assert any("khusus Ketua Panitia" in e.value for e in at.error)
    assert len(at.dataframe) == 0 and len(at.expander) == 0


def test_forged_token_is_rejected():
    at = new_app()
    at.session_state["_admin_token"] = "token-palsu"
    at.run()
    assert_ok(at)
    assert at.session_state["_ctx_admin"] is None


def test_admin_pages_render_with_valid_session():
    seed()
    token = secrets.token_urlsafe(32)
    db.create_admin_session(token, "Ketua Uji", "test")
    at = new_app()
    at.session_state["_admin_token"] = token
    at.run()
    assert_ok(at)
    assert at.session_state["_ctx_admin"] is not None
    for page in ADMIN_PAGES + PUBLIC_PAGES:
        at.switch_page(page).run()
        assert_ok(at)
    at.switch_page("views/approvals.py").run()
    assert any("Rapat Uji" in e.label for e in at.expander)


def test_booking_form_submission_end_to_end():
    at = new_app()
    at.run()
    at.switch_page("views/booking.py").run()
    assert_ok(at)
    key = f"_captcha_booking_form_{at.session_state['booking_date'].isoformat()}"
    a, b = at.session_state[key]
    at.text_input[0].input("Siti Aminah")          # nama pemohon
    at.text_input[1].input("0812 9876 5432")       # WhatsApp
    at.text_input[3].input("Latihan Paduan Suara")  # nama kegiatan
    at.selectbox[0].select("Kegiatan umum")
    at.text_area[0].input("Latihan rutin persiapan acara")
    at.number_input[1].set_value(a + b)
    at.checkbox[0].check()
    submit = next(btn for btn in at.button if "Kirim Pengajuan" in btn.label)
    submit.click().run()
    assert_ok(at)
    assert at.session_state["last_booking"]["reference"].startswith("BK-")
    assert any("Kode Referensi Booking" in m.value for m in at.markdown)
