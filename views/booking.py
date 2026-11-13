"""Halaman pengajuan booking (tanpa akun)."""

import streamlit as st

import auth
import database as db
from utils import ui
from utils.helpers import fmt_date, today_local

ui.page_header("Ajukan Booking Kegiatan",
               "Tidak perlu membuat akun. Setelah dikirim, Anda akan menerima Kode Referensi Booking.")

settings = db.get_calendar_settings()
today = today_local()

if auth.get_admin():
    st.info("Anda sedang dalam Admin Mode. Agenda resmi bisa langsung dibuat di menu **Kelola Agenda**; "
            "formulir ini tetap dapat dipakai untuk mencoba alur pemohon.", icon="ℹ️")

if not settings["booking_open"]:
    st.warning("Pengajuan booking sedang ditutup sementara oleh Ketua Panitia. Silakan cek kembali nanti.", icon="⏸️")
    st.stop()

min_d = max(today, settings["start_date"])
max_d = settings["end_date"]
if min_d > max_d:
    st.error("Periode kalender sudah berakhir. Tidak ada tanggal yang dapat dibooking.")
    st.stop()

last = st.session_state.get("last_booking")
if last and st.session_state.get("show_last_booking"):
    ui.booking_success(last)
    if st.button("Ajukan booking lain", icon=":material/add:"):
        st.session_state["show_last_booking"] = False
        st.rerun()
    st.stop()

left, right = st.columns([3, 2], gap="large")
with right:
    with st.container(border=True):
        st.markdown("##### 1. Pilih tanggal")
        default = st.session_state.pop("prefill_date", None) or min_d
        default = min(max(default, min_d), max_d)
        d = st.date_input("Tanggal kegiatan", value=default, min_value=min_d, max_value=max_d,
                          format="DD/MM/YYYY", key="booking_date")
        st.caption(fmt_date(d))
        st.markdown("##### Jadwal di tanggal ini")
        detail = ui.day_schedule(d)
        st.caption(f"Jam operasional: {settings['day_start_time']:%H:%M}–{settings['day_end_time']:%H:%M} WIB. "
                   "Kegiatan berbeda boleh di tanggal yang sama asal jamnya tidak bertabrakan.")
    with st.expander("ℹ️ Alur booking"):
        st.markdown("""
1. Isi formulir dan kirim pengajuan.
2. Simpan **Kode Referensi Booking** yang muncul.
3. Ketua Panitia meninjau: **Disetujui** / **Ditolak** (bisa juga menyesuaikan jam).
4. Cek status kapan saja di menu **Cek Status Booking**.
5. Selama belum disetujui, Anda bisa membatalkan pengajuan dengan kode + nomor WhatsApp.
""")

with left:
    st.markdown("##### 2. Isi formulir")
    locked = (detail["info"] or {}).get("lock_status") == "locked"
    if locked:
        st.error("Tanggal yang dipilih dikunci. Silakan pilih tanggal lain.")
    else:
        result = ui.booking_form(f"booking_form_{d.isoformat()}", d, settings)
        if result:
            st.session_state["show_last_booking"] = True
            st.rerun()
