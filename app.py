"""Online Event Booking Calendar — titik masuk aplikasi Streamlit.

Jalankan:  streamlit run app.py
"""
from __future__ import annotations

import os

import streamlit as st

from config import APP_NAME, get_settings

st.set_page_config(page_title=APP_NAME, page_icon="📅", layout="wide", initial_sidebar_state="auto")

import auth  # noqa: E402
import database as db  # noqa: E402
from utils import ui  # noqa: E402
from utils.helpers import esc, fmt_date, fmt_datetime  # noqa: E402

ui.inject_css()
_ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
st.logo(os.path.join(_ASSETS, "logo.svg"), size="large", icon_image=os.path.join(_ASSETS, "icon.svg"))


@st.cache_data(ttl=30, show_spinner=False)
def _health() -> tuple[bool, str]:
    return db.health_check()


def setup_page(message: str) -> None:
    ui.page_header("⚙️ Aplikasi belum terhubung ke database", APP_NAME)
    st.error(message)
    st.markdown("""
**Langkah singkat untuk administrator:**
1. Buat project di **Supabase** → buka **SQL Editor** → jalankan isi file `sql/schema.sql`.
2. Salin *connection string* dari **Connect → Session pooler** (port 5432).
3. Isi **Secrets** aplikasi (Streamlit Cloud → *Settings → Secrets*, atau file `.streamlit/secrets.toml` lokal)
   dengan `DATABASE_URL`, `ADMIN_PIN_HASH`, dan `APP_SECRET` — lihat `secrets.toml.example`.
4. Buat hash PIN dengan perintah: `python scripts/generate_admin_secrets.py`.
5. Muat ulang halaman ini.

Panduan lengkap ada di `README.md`.
""")
    if st.button("Coba hubungkan lagi", icon=":material/refresh:", type="primary"):
        _health.clear()
        st.rerun()


ok, health_msg = _health()
if not ok:
    _health.clear()
    setup_page(health_msg)
    st.stop()

# ---------------------------------------------------------------------------
# Status Admin Mode (divalidasi ke database setiap rerun)
# ---------------------------------------------------------------------------
ctx = auth.current_admin()
st.session_state["_ctx_admin"] = ctx

# Admin Access Key dapat dikirim via tautan rahasia ?ak=... → dipindah ke memori server lalu dihapus dari URL
if "ak" in st.query_params:
    st.session_state["_prefill_ak"] = st.query_params.get("ak", "")
    del st.query_params["ak"]
    if ctx is None:
        st.session_state["_open_admin_login"] = True


@st.dialog("Masuk Admin Mode")
def admin_login_dialog() -> None:
    s = get_settings()
    st.caption("Khusus Ketua Panitia. Percobaan PIN dibatasi dan dicatat di audit log.")
    if not s.admin_configured:
        st.error("ADMIN_PIN_HASH belum diatur di Secrets. Lihat README bagian *Bootstrap Admin*.")
        return
    with st.form("admin_login_form", border=False):
        label = st.text_input("Nama Anda", value="Ketua Panitia", max_chars=60,
                              help="Dicatat di audit log sebagai pelaku perubahan.")
        access_key = None
        if auth.access_key_required():
            access_key = st.text_input("Admin Access Key", type="password",
                                       value=st.session_state.get("_prefill_ak", ""),
                                       help="Kunci akses panjang yang hanya dimiliki Ketua Panitia.")
        pin = st.text_input("PIN Admin", type="password", max_chars=64)
        submitted = st.form_submit_button("Masuk", type="primary", icon=":material/lock_open:", width="stretch")
    if submitted:
        with st.spinner("Memverifikasi..."):
            success, msg = auth.login_admin(pin, access_key, label)
        if success:
            st.session_state.pop("_prefill_ak", None)
            ui.flash("success", msg)
            st.rerun()
        st.error(msg)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    if ctx:
        st.markdown(f'<span class="mode-pill mode-admin">ADMIN MODE · {esc(ctx.admin_label)}</span>',
                    unsafe_allow_html=True)
    else:
        st.markdown('<span class="mode-pill mode-public">Akses Publik</span>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Navigasi (halaman admin hanya didaftarkan bila sesi admin valid)
# ---------------------------------------------------------------------------
public_pages = [
    st.Page("views/dashboard.py", title="Dashboard", icon=":material/dashboard:", default=True),
    st.Page("views/calendar.py", title="Kalender", icon=":material/calendar_month:"),
    st.Page("views/booking.py", title="Ajukan Booking", icon=":material/add_circle:"),
    st.Page("views/my_bookings.py", title="Cek Status Booking", icon=":material/confirmation_number:"),
]
sections: dict[str, list] = {"Menu": public_pages}
if ctx:
    pending_n = db.count_pending()
    sections["Ketua Panitia"] = [
        st.Page("views/approvals.py", title=f"Approval ({pending_n})" if pending_n else "Approval",
                icon=":material/fact_check:"),
        st.Page("views/event_management.py", title="Kelola Agenda", icon=":material/edit_calendar:"),
        st.Page("views/date_management.py", title="Tanggal & Hari Libur", icon=":material/event_busy:"),
        st.Page("views/audit_log.py", title="Audit Log", icon=":material/history:"),
        st.Page("views/settings.py", title="Pengaturan", icon=":material/settings:"),
    ]
nav = st.navigation(sections, position="sidebar", expanded=True)

with st.sidebar:
    st.divider()
    if ctx:
        try:
            notes = db.admin_notifications(ctx, limit=12)
        except db.AuthorizationError:
            notes = {"unread": 0, "items": []}
        label = f"Notifikasi ({notes['unread']})" if notes["unread"] else "Notifikasi"
        with st.expander(label, icon=":material/notifications:", expanded=False):
            if not notes["items"]:
                st.caption("Belum ada notifikasi.")
            for n in notes["items"]:
                dot = "🔵 " if not n["is_read"] else ""
                st.markdown(f"{dot}**{esc(n['title'])}**  \n{esc(n['message'])}  \n"
                            f"<small>{fmt_datetime(n['created_at'])}</small>", unsafe_allow_html=True)
            if notes["unread"] and st.button("Tandai semua sudah dibaca", icon=":material/done_all:"):
                db.admin_mark_notifications_read(ctx)
                st.rerun()
        if st.button("Logout Admin", icon=":material/logout:", width="stretch"):
            auth.logout_admin()
            ui.flash("success", "Anda telah keluar dari Admin Mode.")
            st.rerun()
        st.caption(f"Sesi berakhir otomatis setelah {get_settings().session_timeout_minutes} menit tidak aktif.")
    else:
        if st.button("Admin Mode", icon=":material/admin_panel_settings:", width="stretch"):
            admin_login_dialog()
        elif st.session_state.pop("_open_admin_login", False):
            admin_login_dialog()
    try:
        cs = db.get_calendar_settings()
        st.caption(f"Periode kalender: {fmt_date(cs['start_date'], False)} – {fmt_date(cs['end_date'], False)}")
    except Exception:
        pass

ui.show_flash()
nav.run()
