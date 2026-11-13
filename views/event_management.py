"""Event Management — kelola seluruh agenda resmi (khusus Ketua Panitia)."""
from datetime import time

import pandas as pd
import streamlit as st

import auth
import database as db
from config import CATEGORIES, EVENT_STATUS_LABEL
from utils import ui
from utils.helpers import (
    ValidationError, display_whatsapp, esc, fmt_date, fmt_time_range, time_options, today_local,
)

ctx = auth.require_admin()
ui.page_header("Kelola Agenda", "Tambah, ubah jadwal, batalkan, atau hapus agenda resmi.")

ss = st.session_state
settings = db.get_calendar_settings()
opts = time_options(30, time(0, 0), time(23, 30))
fmt_t = lambda t: t.strftime("%H:%M")  # noqa: E731

last = ss.pop("event_result", None)
if last and last.get("message"):
    with st.container(border=True):
        st.info(last["message"])
        ui.wa_button("Kabari penanggung jawab via WhatsApp", last.get("whatsapp"),
                     f"Assalamu'alaikum. {last['message']}")
if last and last.get("pending_warnings"):
    st.warning("Catatan: ada pengajuan pending yang jamnya bentrok dengan agenda ini. Tinjau di menu Approval.")
    ui.show_conflicts(last["pending_warnings"])

modes = ["Daftar agenda", "Tambah agenda"]
if "new_event_date" in ss:
    ss["em_mode"] = "Tambah agenda"
ss.setdefault("em_mode", modes[0])
mode = st.segmented_control("Mode", modes, key="em_mode", label_visibility="collapsed") or modes[0]


def event_form(key: str, ev: dict | None, default_date=None) -> tuple[dict | None, bool]:
    ev = ev or {}
    with st.form(key, border=True):
        c1, c2 = st.columns([2, 1])
        name = c1.text_input("Nama kegiatan *", value=ev.get("event_name", ""), max_chars=150)
        cat = c2.selectbox("Kategori *", CATEGORIES,
                           index=CATEGORIES.index(ev["category"]) if ev.get("category") in CATEGORIES else 0)
        c1, c2, c3 = st.columns(3)
        d = c1.date_input("Tanggal *", value=ev.get("event_date") or default_date or max(today_local(), settings["start_date"]),
                          min_value=settings["start_date"], max_value=settings["end_date"], format="DD/MM/YYYY")
        s_def = ev.get("start_time") if ev.get("start_time") in opts else time(9, 0)
        e_def = ev.get("end_time") if ev.get("end_time") in opts else time(11, 0)
        start = c2.selectbox("Mulai *", opts, index=opts.index(s_def), format_func=fmt_t)
        end = c3.selectbox("Selesai *", opts, index=opts.index(e_def), format_func=fmt_t)
        c1, c2 = st.columns(2)
        pic = c1.text_input("Penanggung jawab *", value=ev.get("person_in_charge", ""), max_chars=100)
        wa = c2.text_input("WhatsApp penanggung jawab", value=ev.get("pic_whatsapp") or "", max_chars=20)
        c1, c2 = st.columns([2, 1])
        loc = c1.text_input("Lokasi", value=ev.get("location") or "", max_chars=150)
        part = c2.number_input("Jumlah peserta", min_value=0, max_value=100000, value=int(ev.get("participants") or 0))
        desc = st.text_area("Deskripsi", value=ev.get("description") or "", max_chars=2000, height=90)
        override = st.checkbox("Override konflik (izinkan meski bentrok / tanggal dikunci)")
        submitted = st.form_submit_button("Simpan", type="primary", icon=":material/save:", width="stretch")
    if not submitted:
        return None, False
    return ({"event_name": name, "category": cat, "event_date": d, "start_time": start, "end_time": end,
             "person_in_charge": pic, "pic_whatsapp": wa, "location": loc, "participants": part or None,
             "description": desc}, override)


# ======================================================================= TAMBAH
if mode == "Tambah agenda":
    st.markdown("#### Tambah agenda resmi")
    st.caption("Agenda yang dibuat admin langsung berstatus **Disetujui** dan tampil di kalender.")
    payload, override = event_form("new_event", None, default_date=ss.pop("new_event_date", None))
    if payload:
        try:
            with st.spinner("Menyimpan..."):
                res = db.admin_create_event(ctx, payload, override=override)
            ss["event_result"] = res
            ss["manage_event_id"] = res["event_id"]
            ui.flash("success", "Agenda berhasil ditambahkan.")
            ss.pop("em_mode", None)
            st.rerun()
        except db.ConflictError as e:
            st.error(str(e))
            ui.show_conflicts(e.conflicts)
        except (ValidationError, db.BookingError) as e:
            st.error(str(e))
    st.stop()

# ======================================================================= KELOLA AGENDA TERPILIH
sel_id = ss.get("manage_event_id")
if sel_id:
    ev = db.admin_get_event(ctx, sel_id)
    if not ev:
        ss.pop("manage_event_id", None)
        st.rerun()
    with st.container(border=True):
        h1, h2 = st.columns([4, 1])
        h1.markdown(f"#### ✏️ {esc(ev['event_name'])}")
        if h2.button("Tutup", icon=":material/close:", width="stretch"):
            ss.pop("manage_event_id", None)
            ss.pop("em_table", None)
            st.rerun()
        badge = ('<span class="badge b-approved">Disetujui</span>' if ev["status"] == "approved"
                 else '<span class="badge b-cancelled">Dibatalkan</span>')
        st.markdown(
            f"{badge} {ui.category_badge(ev['category'])} &nbsp; {esc(fmt_date(ev['event_date']))}, "
            f"{esc(fmt_time_range(ev['start_time'], ev['end_time']))} · PJ: {esc(ev['person_in_charge'])} "
            f"({esc(display_whatsapp(ev.get('pic_whatsapp')))}) · "
            f"{'Kode ' + esc(ev['booking_reference']) if ev.get('booking_reference') else 'Dibuat oleh admin'}",
            unsafe_allow_html=True)
        if ev["status"] == "cancelled":
            st.warning(f"Agenda ini dibatalkan. Alasan: {ev.get('cancel_reason') or '-'}")
        else:
            t_edit, t_cancel = st.tabs(["Ubah agenda / jadwal", "Batalkan agenda"])
            with t_edit:
                payload, override = event_form(f"edit_{sel_id}", ev)
                if payload:
                    try:
                        with st.spinner("Menyimpan perubahan..."):
                            res = db.admin_update_event(ctx, sel_id, payload, override=override)
                        ss["event_result"] = res
                        ui.flash("success", "Perubahan agenda tersimpan.")
                        st.rerun()
                    except db.ConflictError as e:
                        st.error(str(e))
                        ui.show_conflicts(e.conflicts)
                    except (ValidationError, db.BookingError) as e:
                        st.error(str(e))
            with t_cancel:
                reason = st.text_input("Alasan pembatalan *", key=f"cancel_reason_{sel_id}", max_chars=500)
                if st.button("Batalkan agenda", icon=":material/event_busy:", key=f"cancel_btn_{sel_id}"):
                    if not reason.strip():
                        st.error("Isi alasan pembatalan.")
                    else:
                        def _do_cancel(eid=sel_id, r=reason):
                            ss["event_result"] = db.admin_cancel_event(ctx, eid, r)
                        ui.confirm_dialog("Batalkan agenda?",
                                          f"Agenda **{esc(ev['event_name'])}** akan dibatalkan dan hilang dari "
                                          "kalender. Pemohon akan melihat notifikasi pembatalan.",
                                          _do_cancel, "Agenda dibatalkan.", confirm_label="Ya, batalkan")
        st.divider()
        if st.button("Hapus permanen", icon=":material/delete_forever:", key=f"del_{sel_id}"):
            def _do_delete(eid=sel_id):
                db.admin_delete_event(ctx, eid)
                ss.pop("manage_event_id", None)
                ss.pop("em_table", None)
            ui.confirm_dialog("Hapus agenda secara permanen?",
                              f"Agenda **{esc(ev['event_name'])}** akan dihapus dari database. Tindakan ini "
                              "tercatat di audit log dan **tidak dapat dibatalkan**. "
                              "Gunakan *Batalkan agenda* bila ingin tetap menyimpan riwayatnya.",
                              _do_delete, "Agenda dihapus.", confirm_label="Ya, hapus")

# ======================================================================= DAFTAR
st.markdown("#### Daftar agenda")
with st.container(border=True):
    f1, f2, f3, f4 = st.columns([2, 1, 1, 1])
    q = f1.text_input("Cari agenda", placeholder="Nama, deskripsi, lokasi", key="em_q")
    cat = f2.selectbox("Kategori", ["Semua"] + CATEGORIES, key="em_cat")
    status = f3.selectbox("Status", ["approved", "cancelled", "Semua"], key="em_status",
                          format_func=lambda s: EVENT_STATUS_LABEL.get(s, s))
    pic = f4.text_input("Penanggung jawab", key="em_pic")
    r1, r2, _ = st.columns([1, 1, 2])
    dfrom = r1.date_input("Dari tanggal", value=None, format="DD/MM/YYYY", key="em_from")
    dto = r2.date_input("Sampai tanggal", value=None, format="DD/MM/YYYY", key="em_to")

rows = db.admin_list_events(ctx, status=None if status == "Semua" else status,
                            category=None if cat == "Semua" else cat, pic=pic or None, search=q or None,
                            date_from=dfrom, date_to=dto)
if not rows:
    st.info("Belum ada agenda sesuai filter. Gunakan mode **Tambah agenda** untuk membuat agenda baru.")
    st.stop()

df = pd.DataFrame([{
    "Tanggal": r["event_date"], "Waktu": fmt_time_range(r["start_time"], r["end_time"]), "Kegiatan": r["event_name"],
    "Kategori": r["category"], "PJ": r["person_in_charge"], "WhatsApp PJ": display_whatsapp(r.get("pic_whatsapp")),
    "Lokasi": r.get("location") or "", "Status": EVENT_STATUS_LABEL[r["status"]],
    "Override": "Ya" if r["conflict_override"] else "", "Sumber": r.get("booking_reference") or "Admin",
} for r in rows])
st.caption("Klik satu baris untuk mengelola agenda tersebut.")
event = st.dataframe(df, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
                     key="em_table", column_config={"Tanggal": st.column_config.DateColumn(format="DD/MM/YYYY")})
picked = event.selection.rows if event and event.selection else []
if picked:
    new_id = rows[picked[0]]["id"]
    if new_id != ss.get("manage_event_id"):
        ss["manage_event_id"] = new_id
        st.rerun()
st.download_button("Unduh CSV", df.to_csv(index=False).encode("utf-8"), "agenda.csv", "text/csv",
                   icon=":material/download:")
