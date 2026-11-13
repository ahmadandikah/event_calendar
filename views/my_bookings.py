"""Cek status & pembatalan booking menggunakan Kode Referensi (tanpa login)."""
import streamlit as st

import auth
import database as db
from utils import ui
from utils.helpers import (
    ValidationError, display_whatsapp, esc, fmt_date, fmt_datetime, fmt_time_range, normalize_reference,
)

ui.page_header("Cek Status Booking", "Masukkan Kode Referensi Booking untuk melihat status pengajuan Anda.")

ss = st.session_state
recent = ss.get("my_refs", [])

with st.form("lookup_form", border=True):
    c1, c2 = st.columns([3, 1])
    ref_input = c1.text_input("Kode Referensi", value=ss.pop("lookup_ref", ""), placeholder="BK-XXXX-XXXX-XXXX",
                              label_visibility="collapsed")
    submitted = c2.form_submit_button("Cek Status", type="primary", icon=":material/search:", width="stretch")

if recent:
    st.caption("Kode yang Anda buat di perangkat ini (selama sesi browser ini):")
    cols = st.columns(min(len(recent), 4))
    for i, r in enumerate(recent[:8]):
        if cols[i % len(cols)].button(r, key=f"recent_{r}", width="stretch"):
            ss["active_ref"] = r
            st.rerun()

if submitted:
    if not normalize_reference(ref_input):
        st.error("Format kode tidak valid. Contoh: BK-7KQ2-M9XD-4TPA")
    else:
        ss["active_ref"] = normalize_reference(ref_input)

ref = ss.get("active_ref")
if not ref:
    st.info("Kode referensi diberikan saat Anda mengirim pengajuan booking (format **BK-XXXX-XXXX-XXXX**).", icon="💡")
    st.stop()

try:
    b = db.lookup_booking(ref, auth.client_fingerprint())
except db.RateLimitError as e:
    st.error(str(e))
    st.stop()

if not b:
    st.error(f"Kode **{esc(ref)}** tidak ditemukan. Periksa kembali penulisan kode.")
    ss.pop("active_ref", None)
    st.stop()

status = b["approval_status"]
with st.container(border=True):
    h1, h2 = st.columns([3, 1])
    h1.markdown(f"### {esc(b['event_name'])}")
    h1.markdown(f"Kode: `{b['booking_reference']}`")
    h2.markdown(f"<div style='text-align:right;margin-top:10px'>{ui.status_badge(status)}</div>",
                unsafe_allow_html=True)
    rows = [
        ("Tanggal", esc(fmt_date(b["requested_date"]))),
        ("Waktu", esc(fmt_time_range(b["start_time"], b["end_time"]))),
        ("Kategori", esc(b["category"])),
        ("Pemohon", esc(b["requester_name"])),
        ("WhatsApp", esc(display_whatsapp(b["requester_whatsapp"])[:-4] + "••••")),
        ("Penanggung jawab", esc(b["person_in_charge"])),
        ("Lokasi", esc(b.get("location") or "-")),
        ("Deskripsi", esc(b["description"])),
        ("Diajukan", esc(fmt_datetime(b["created_at"]))),
    ]
    if b.get("rejection_reason"):
        rows.append(("Alasan", f"<b>{esc(b['rejection_reason'])}</b>"))
    if b.get("admin_note"):
        rows.append(("Catatan Ketua", f"<b>{esc(b['admin_note'])}</b>"))
    st.markdown('<div class="kv">' + "".join(f'<div class="k">{k}</div><div>{v}</div>' for k, v in rows) + "</div>",
                unsafe_allow_html=True)

    msg = {
        "pending": ("info", "Pengajuan Anda sedang menunggu persetujuan Ketua Panitia."),
        "approved": ("success", "Selamat! Agenda Anda sudah disetujui dan tampil di kalender sebagai agenda resmi."),
        "rejected": ("error", "Mohon maaf, pengajuan ini ditolak. Anda dapat mengajukan jadwal lain."),
        "cancelled": ("warning", "Pengajuan/agenda ini sudah dibatalkan."),
    }[status]
    getattr(st, msg[0])(msg[1])

st.markdown("#### Riwayat notifikasi")
for n in b["notifications"]:
    st.markdown(f'<div class="timeline-item"><b>{esc(n["title"])}</b> · '
                f'<span class="muted">{esc(fmt_datetime(n["created_at"]))}</span><br>{esc(n["message"])}</div>',
                unsafe_allow_html=True)

if status == "pending":
    st.markdown("#### Batalkan pengajuan")
    with st.form("cancel_form", border=True):
        st.caption("Untuk keamanan, masukkan nomor WhatsApp yang dipakai saat mengajukan.")
        wa = st.text_input("Nomor WhatsApp pemohon", placeholder="08xxxxxxxxxx")
        reason = st.text_input("Alasan pembatalan (opsional)", max_chars=300)
        go_cancel = st.form_submit_button("Batalkan Pengajuan", icon=":material/cancel:")
    if go_cancel:
        def _do_cancel():
            db.cancel_booking_by_reference(ref, wa, auth.client_fingerprint(), reason)
        try:
            from utils.helpers import normalize_whatsapp
            normalize_whatsapp(wa)
            ui.confirm_dialog("Batalkan pengajuan ini?",
                              f"Pengajuan **{esc(b['event_name'])}** ({ref}) akan dibatalkan dan tidak dapat "
                              "dipulihkan. Anda perlu mengajukan ulang bila berubah pikiran.",
                              _do_cancel, "Pengajuan berhasil dibatalkan.", confirm_label="Ya, batalkan")
        except ValidationError as e:
            st.error(str(e))
elif status == "approved":
    st.caption("Perubahan agenda yang sudah disetujui hanya dapat dilakukan oleh Ketua Panitia. "
               "Silakan hubungi Ketua Panitia.")

if st.button("Cek kode lain", icon=":material/restart_alt:"):
    ss.pop("active_ref", None)
    st.rerun()
