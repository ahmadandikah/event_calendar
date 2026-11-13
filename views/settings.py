"""Pengaturan aplikasi (khusus Ketua Panitia)."""
from datetime import time

import streamlit as st

import auth
import database as db
from config import get_settings
from utils import ui
from utils.helpers import ValidationError, time_options
from utils.notification import external_channels_status

ctx = auth.require_admin()
ui.page_header("Pengaturan", "Periode kalender, jam operasional, aturan booking, keamanan, dan notifikasi.")

cs = db.get_calendar_settings()
opts = time_options(30, time(0, 0), time(23, 30))

with st.form("settings_form", border=True):
    st.markdown("##### 📅 Periode & jam operasional")
    c1, c2 = st.columns(2)
    start = c1.date_input("Awal periode", value=cs["start_date"], format="DD/MM/YYYY")
    end = c2.date_input("Akhir periode (Idul Adha)", value=cs["end_date"], format="DD/MM/YYYY")
    c1, c2 = st.columns(2)
    d_start = c1.selectbox("Jam buka", opts, index=opts.index(cs["day_start_time"]) if cs["day_start_time"] in opts else 12,
                           format_func=lambda t: t.strftime("%H:%M"))
    d_end = c2.selectbox("Jam tutup", opts, index=opts.index(cs["day_end_time"]) if cs["day_end_time"] in opts else 44,
                         format_func=lambda t: t.strftime("%H:%M"))
    st.markdown("##### 📝 Aturan booking")
    c1, c2 = st.columns(2)
    open_ = c1.toggle("Pengajuan booking dibuka untuk publik", value=cs["booking_open"])
    max_pend = c2.number_input("Maks. pengajuan pending per nomor WhatsApp", 1, 50, int(cs["max_pending_per_whatsapp"]))
    announce = st.text_area("Pengumuman di Dashboard (opsional)", value=cs.get("announcement") or "", max_chars=500)
    save = st.form_submit_button("Simpan pengaturan", type="primary", icon=":material/save:")
if save:
    try:
        db.admin_update_calendar_settings(ctx, start_date=start, end_date=end, day_start_time=d_start,
                                          day_end_time=d_end, booking_open=open_, max_pending_per_whatsapp=max_pend,
                                          announcement=announce)
        ui.flash("success", "Pengaturan tersimpan.")
        st.rerun()
    except (ValidationError, db.AuthorizationError) as e:
        st.error(str(e))

s = get_settings()
c1, c2 = st.columns(2)
with c1:
    with st.container(border=True):
        st.markdown("##### 🔐 Keamanan Admin Mode")
        st.markdown(f"""
- Metode PIN: **{'Hash PBKDF2 (disarankan)' if s.admin_pin_hash else 'PIN teks biasa — segera ganti ke ADMIN_PIN_HASH'}**
- Admin Access Key: **{'Aktif' if s.admin_access_key else 'Tidak diwajibkan'}**
- Timeout tidak aktif: **{s.session_timeout_minutes} menit** · Maks. sesi: **{s.session_max_hours} jam**
- APP_SECRET: **{'Terpasang' if s.app_secret else 'Belum diatur (disarankan diisi)'}**
""")
        if st.button("Keluarkan semua sesi admin lain", icon=":material/devices:"):
            ui.confirm_dialog("Cabut semua sesi admin lain?",
                              "Semua perangkat lain yang sedang dalam Admin Mode akan langsung keluar. "
                              "Lakukan ini bila PIN mungkin bocor, lalu ganti PIN di Secrets.",
                              lambda: db.admin_revoke_all_sessions(ctx), "Semua sesi admin lain dicabut.",
                              confirm_label="Ya, cabut")
with c2:
    with st.container(border=True):
        st.markdown("##### 🔔 Notifikasi")
        st.markdown("- Notifikasi dalam aplikasi: **Aktif** (lonceng di sidebar & halaman Cek Status)")
        for name, on in external_channels_status().items():
            st.markdown(f"- {name}: **{'Aktif' if on else 'Tidak aktif (opsional)'}**")
        st.markdown("- WhatsApp: tombol *Kabari via WhatsApp* (wa.me, gratis) di halaman Approval & Kelola Agenda")
        st.caption("Email/ntfy diatur lewat Secrets — lihat README bagian Notifikasi.")

with st.container(border=True):
    st.markdown("##### 🔗 Bagikan aplikasi")
    if s.app_url:
        st.code(s.app_url, language=None)
    else:
        st.caption("Isi APP_URL di Secrets agar tautan tampil di sini dan di notifikasi.")
    st.caption("Bagikan link aplikasi hanya kepada anggota panitia. Jangan pernah membagikan PIN atau Admin Access Key.")
