"""Tanggal & Hari Libur — kunci/buka tanggal, tanggal eksklusif, hari raya (khusus Ketua Panitia)."""
import pandas as pd
import streamlit as st

import auth
import database as db
from config import HOLIDAY_TYPE_LABEL, LOCK_STATUS_LABEL
from utils import ui
from utils.helpers import ValidationError, esc, fmt_date

ctx = auth.require_admin()
ui.page_header("Tanggal & Hari Libur",
               "Atur hari libur/hari raya, kunci tanggal, atau tetapkan tanggal eksklusif.")

settings = db.get_calendar_settings()
rows = db.list_calendar_dates()
by_date = {r["calendar_date"]: r for r in rows}

st.info("Tanggal Idul Fitri & Idul Adha mengikuti SKB 3 Menteri 2027 (Idul Fitri 10–11 Maret 2027, Idul Adha "
        "17 Mei 2027). Penetapan final dilakukan Kementerian Agama melalui sidang isbat — perbarui di sini bila "
        "ada perubahan, lalu sesuaikan akhir periode di menu **Pengaturan**.", icon="🕌")

t_single, t_bulk, t_list = st.tabs(["Atur satu tanggal", "Kunci rentang tanggal", "Daftar tanggal khusus"])

with t_single:
    d = st.date_input("Pilih tanggal", value=settings["start_date"], format="DD/MM/YYYY", key="dm_date")
    cur = by_date.get(d, {})
    st.caption(fmt_date(d))
    with st.form(f"dm_form_{d.isoformat()}", border=True):
        c1, c2 = st.columns([2, 1])
        name = c1.text_input("Nama hari libur / penanda (kosongkan bila bukan hari libur)",
                             value=cur.get("holiday_name") or "", max_chars=150)
        types = list(HOLIDAY_TYPE_LABEL)
        htype = c2.selectbox("Jenis", types, index=types.index(cur["holiday_type"]) if cur.get("holiday_type") in types else 0,
                             format_func=HOLIDAY_TYPE_LABEL.get)
        locks = list(LOCK_STATUS_LABEL)
        lock = st.radio("Status booking tanggal ini", locks, index=locks.index(cur.get("lock_status", "open")),
                        format_func=LOCK_STATUS_LABEL.get, horizontal=True)
        notes = st.text_input("Catatan", value=cur.get("notes") or "", max_chars=500)
        save = st.form_submit_button("Simpan tanggal", type="primary", icon=":material/save:")
    if save:
        try:
            db.admin_upsert_calendar_date(ctx, d, holiday_name=name, holiday_type=htype if name.strip() else None,
                                          lock_status=lock, notes=notes)
            ui.flash("success", f"Pengaturan {fmt_date(d)} tersimpan.")
            st.rerun()
        except (ValidationError, db.AuthorizationError) as e:
            st.error(str(e))
    if cur and st.button("Hapus semua penanda tanggal ini", icon=":material/delete:"):
        ui.confirm_dialog("Hapus penanda tanggal?",
                          f"Status libur/kunci untuk **{esc(fmt_date(d))}** akan dihapus (tanggal kembali terbuka).",
                          lambda: db.admin_upsert_calendar_date(ctx, d, holiday_name=None, holiday_type=None,
                                                                lock_status="open", notes=None),
                          "Penanda tanggal dihapus.", confirm_label="Ya, hapus")

with t_bulk:
    st.caption("Contoh: kunci seluruh pekan libur Idul Fitri agar tidak bisa dibooking.")
    with st.form("bulk_form", border=True):
        c1, c2 = st.columns(2)
        start = c1.date_input("Dari", value=settings["start_date"], format="DD/MM/YYYY")
        end = c2.date_input("Sampai", value=settings["start_date"], format="DD/MM/YYYY")
        lock = st.radio("Terapkan status", list(LOCK_STATUS_LABEL), format_func=LOCK_STATUS_LABEL.get,
                        horizontal=True, index=1)
        notes = st.text_input("Catatan (opsional)", max_chars=500)
        go_bulk = st.form_submit_button("Terapkan", type="primary", icon=":material/lock:")
    if go_bulk:
        if end < start:
            st.error("Tanggal akhir harus setelah tanggal awal.")
        else:
            n = (end - start).days + 1
            ui.confirm_dialog(
                "Terapkan ke rentang tanggal?",
                f"Status **{LOCK_STATUS_LABEL[lock]}** akan diterapkan ke {n} hari "
                f"({esc(fmt_date(start, False))} – {esc(fmt_date(end, False))}). Nama hari libur tetap dipertahankan.",
                lambda: db.admin_bulk_lock(ctx, start, end, lock, notes),
                f"Status diterapkan ke {n} hari.", danger=False, confirm_label="Ya, terapkan")

with t_list:
    if rows:
        df = pd.DataFrame([{
            "Tanggal": r["calendar_date"], "Hari": fmt_date(r["calendar_date"]).split(",")[0],
            "Nama": r.get("holiday_name") or "", "Jenis": HOLIDAY_TYPE_LABEL.get(r.get("holiday_type"), ""),
            "Status booking": LOCK_STATUS_LABEL[r["lock_status"]], "Catatan": r.get("notes") or "",
            "Diubah oleh": r.get("updated_by") or "",
        } for r in rows])
        st.dataframe(df, hide_index=True, width="stretch",
                     column_config={"Tanggal": st.column_config.DateColumn(format="DD/MM/YYYY")})
    else:
        st.info("Belum ada tanggal khusus.")
