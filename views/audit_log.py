"""Audit Log — histori seluruh aktivitas penting (khusus Ketua Panitia)."""
import json

import pandas as pd
import streamlit as st

import auth
import database as db
from utils import ui
from utils.helpers import fmt_datetime

ctx = auth.require_admin()
ui.page_header("Audit Log", "Siapa melakukan apa dan kapan — termasuk pengajuan, approval, perubahan, dan pembatalan.")

ACTION_LABEL = {
    "booking_created": "Pengajuan dibuat",
    "booking_approved": "Pengajuan disetujui",
    "booking_rejected": "Pengajuan ditolak",
    "booking_cancelled_by_requester": "Dibatalkan pemohon",
    "event_created": "Agenda dibuat admin",
    "event_updated": "Agenda diubah",
    "event_rescheduled": "Jadwal diubah",
    "event_cancelled": "Agenda dibatalkan",
    "event_deleted": "Agenda dihapus",
    "date_locked": "Tanggal dikunci",
    "date_set_exclusive": "Tanggal eksklusif",
    "date_updated": "Tanggal diperbarui",
    "date_cleared": "Penanda tanggal dihapus",
    "dates_bulk_locked": "Rentang dikunci",
    "dates_bulk_open": "Rentang dibuka",
    "dates_bulk_exclusive": "Rentang eksklusif",
    "settings_updated": "Pengaturan diubah",
    "admin_login": "Admin masuk",
    "admin_logout": "Admin keluar",
    "admin_pin_failed": "PIN salah",
    "revoke_all_sessions": "Semua sesi admin dicabut",
}

with st.container(border=True):
    c1, c2, c3, c4, c5 = st.columns([2, 1.5, 1, 1, 1])
    q = c1.text_input("Cari", placeholder="Nama pelaku, kode booking, isi detail…")
    actions = db.admin_audit_actions(ctx)
    action = c2.selectbox("Aksi", ["Semua"] + actions, format_func=lambda a: ACTION_LABEL.get(a, a))
    actor = c3.selectbox("Pelaku", ["Semua", "admin", "public", "system"])
    dfrom = c4.date_input("Dari", value=None, format="DD/MM/YYYY")
    dto = c5.date_input("Sampai", value=None, format="DD/MM/YYYY")

logs = db.admin_list_audit(ctx, action=None if action == "Semua" else action, actor_type=None if actor == "Semua" else actor,
                           search=q or None, date_from=dfrom, date_to=dto)
st.caption(f"{len(logs)} catatan (maks. 1000 terbaru).")
if logs:
    df = pd.DataFrame([{
        "Waktu": fmt_datetime(r["created_at"]), "Pelaku": r["actor_label"],
        "Jenis pelaku": {"admin": "Admin", "public": "Publik", "system": "Sistem"}[r["actor_type"]],
        "Aksi": ACTION_LABEL.get(r["action"], r["action"]), "Objek": r["entity_type"],
        "ID": r.get("entity_id") or "", "Detail": json.dumps(r["details"], ensure_ascii=False, default=str),
    } for r in logs])
    st.dataframe(df, hide_index=True, width="stretch", height=520)
    st.download_button("Unduh CSV", df.to_csv(index=False).encode("utf-8"), "audit_log.csv", "text/csv",
                       icon=":material/download:")
