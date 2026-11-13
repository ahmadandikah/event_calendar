"""Approval Management — khusus Ketua Panitia."""
import pandas as pd
import streamlit as st

import auth
import database as db
from config import BOOKING_STATUS_LABEL, CATEGORIES
from utils import ui
from utils.helpers import (
    ValidationError, display_whatsapp, esc, fmt_date, fmt_datetime, fmt_time_range, time_options,
)

ctx = auth.require_admin()
ui.page_header("Approval Management", "Setujui, tolak, atau sesuaikan jadwal pengajuan booking.")

settings = db.get_calendar_settings()
opts = time_options(30, settings["day_start_time"], settings["day_end_time"])

last = st.session_state.pop("approval_result", None)
if last:
    with st.container(border=True):
        st.success(last["message"])
        if last.get("pending_warnings"):
            st.warning("Ada pengajuan lain yang menunggu dan jamnya bentrok dengan agenda ini. "
                       "Pertimbangkan untuk menolaknya / menyesuaikan jadwalnya:")
            ui.show_conflicts(last["pending_warnings"])
        ui.wa_button(f"Kabari {last['requester_name']} via WhatsApp", last["whatsapp"],
                     f"Assalamu'alaikum {last['requester_name']}. {last['message']} Kode booking: {last['reference']}")

tab_pending, tab_all = st.tabs(["⏳ Menunggu persetujuan", "📋 Semua pengajuan"])

with tab_pending:
    f1, f2 = st.columns([2, 1])
    q = f1.text_input("Cari", placeholder="Nama kegiatan / pemohon / kode / WA", key="ap_q")
    cat = f2.selectbox("Kategori", ["Semua"] + CATEGORIES, key="ap_cat")
    pend = db.admin_list_bookings(ctx, status="pending", search=q or None, category=None if cat == "Semua" else cat)
    if not pend:
        st.success("Tidak ada pengajuan yang menunggu persetujuan. 🎉")
    for b in pend:
        bid = b["id"]
        preview = db.admin_preview_conflicts(ctx, b["requested_date"], b["start_time"], b["end_time"],
                                             exclude_booking_id=bid)
        conflicts = preview["conflicts"]
        flag = " ⚠️ BENTROK" if conflicts else ""
        title = (f"{b['event_name']} — {fmt_date(b['requested_date'])}, "
                 f"{fmt_time_range(b['start_time'], b['end_time'])}{flag}")
        with st.expander(title, expanded=len(pend) <= 3):
            c1, c2 = st.columns([3, 2])
            with c1:
                st.markdown(
                    '<div class="kv">'
                    f'<div class="k">Kode</div><div><code>{esc(b["booking_reference"])}</code></div>'
                    f'<div class="k">Pemohon</div><div>{esc(b["requester_name"])}</div>'
                    f'<div class="k">WhatsApp</div><div>{esc(display_whatsapp(b["requester_whatsapp"]))}</div>'
                    f'<div class="k">Penanggung jawab</div><div>{esc(b["person_in_charge"])}</div>'
                    f'<div class="k">Kategori</div><div>{esc(b["category"])}</div>'
                    f'<div class="k">Lokasi</div><div>{esc(b.get("location") or "-")}</div>'
                    f'<div class="k">Peserta</div><div>{esc(b.get("participants") or "-")}</div>'
                    f'<div class="k">Deskripsi</div><div>{esc(b["description"])}</div>'
                    f'<div class="k">Catatan</div><div>{esc(b.get("notes") or "-")}</div>'
                    f'<div class="k">Diajukan</div><div>{esc(fmt_datetime(b["created_at"]))}</div></div>',
                    unsafe_allow_html=True)
            with c2:
                if preview.get("holiday_name"):
                    st.info(f"🎌 {preview['holiday_name']}")
                if preview["lock_status"] != "open":
                    st.warning(f"Status tanggal: **{preview['lock_status'].upper()}**")
                if conflicts:
                    st.error("Bentrok dengan:")
                    ui.show_conflicts(conflicts)
                else:
                    st.success("Tidak ada bentrok jadwal.")
                ui.wa_button("Chat pemohon", b["requester_whatsapp"],
                             f"Assalamu'alaikum {b['requester_name']}, terkait pengajuan '{b['event_name']}' "
                             f"({b['booking_reference']}).")

            with st.form(f"review_{bid}", border=True):
                st.markdown("**Keputusan**")
                d1, d2, d3 = st.columns(3)
                new_date = d1.date_input("Tanggal", value=b["requested_date"], min_value=settings["start_date"],
                                         max_value=settings["end_date"], format="DD/MM/YYYY")
                s_val = b["start_time"] if b["start_time"] in opts else opts[0]
                e_val = b["end_time"] if b["end_time"] in opts else opts[-1]
                start = d2.selectbox("Mulai", opts, index=opts.index(s_val), format_func=lambda t: t.strftime("%H:%M"))
                end = d3.selectbox("Selesai", opts, index=opts.index(e_val), format_func=lambda t: t.strftime("%H:%M"))
                note = st.text_area("Catatan untuk pemohon (opsional)", max_chars=1000, height=70)
                reason = st.text_input("Alasan penolakan (wajib bila menolak)", max_chars=500)
                override = st.checkbox("Override konflik — saya sadar jadwal ini bentrok/dikunci dan tetap menyetujui")
                b1, b2 = st.columns(2)
                approve = b1.form_submit_button("Setujui", type="primary", icon=":material/check_circle:",
                                                width="stretch")
                reject = b2.form_submit_button("Tolak", icon=":material/block:", width="stretch")

            if approve:
                try:
                    with st.spinner("Menyetujui..."):
                        res = db.admin_approve_booking(ctx, bid, event_date=new_date, start_time=start, end_time=end,
                                                       admin_note=note, override=override)
                    st.session_state["approval_result"] = res
                    ui.flash("success", "Pengajuan disetujui dan tampil di kalender.")
                    st.rerun()
                except db.ConflictError as e:
                    st.error(str(e))
                    ui.show_conflicts(e.conflicts)
                except (ValidationError, db.BookingError, db.AuthorizationError) as e:
                    st.error(str(e))
            if reject:
                if not reason.strip():
                    st.error("Isi alasan penolakan terlebih dahulu.")
                else:
                    def _do_reject(bid=bid, reason=reason, note=note):
                        st.session_state["approval_result"] = db.admin_reject_booking(ctx, bid, reason, note)
                    ui.confirm_dialog("Tolak pengajuan ini?",
                                      f"Pengajuan **{esc(b['event_name'])}** akan ditolak dengan alasan: "
                                      f"_{esc(reason)}_", _do_reject, "Pengajuan ditolak.",
                                      confirm_label="Ya, tolak")

with tab_all:
    f1, f2, f3, f4 = st.columns([2, 1, 1, 1])
    q2 = f1.text_input("Cari", placeholder="Nama kegiatan / pemohon / kode / WA", key="all_q")
    status = f2.selectbox("Status", ["Semua"] + list(BOOKING_STATUS_LABEL), key="all_status",
                          format_func=lambda s: BOOKING_STATUS_LABEL.get(s, s))
    cat2 = f3.selectbox("Kategori", ["Semua"] + CATEGORIES, key="all_cat")
    pic = f4.text_input("Penanggung jawab", key="all_pic")
    rows = db.admin_list_bookings(ctx, status=None if status == "Semua" else status, search=q2 or None,
                                  category=None if cat2 == "Semua" else cat2)
    if pic:
        rows = [r for r in rows if pic.lower() in r["person_in_charge"].lower()]
    if rows:
        df = pd.DataFrame([{
            "Kode": r["booking_reference"], "Kegiatan": r["event_name"], "Tanggal": r["requested_date"],
            "Waktu": fmt_time_range(r["start_time"], r["end_time"]), "Kategori": r["category"],
            "Pemohon": r["requester_name"], "WhatsApp": display_whatsapp(r["requester_whatsapp"]),
            "PJ": r["person_in_charge"], "Status": BOOKING_STATUS_LABEL[r["approval_status"]],
            "Alasan/Catatan": r.get("rejection_reason") or r.get("admin_note") or "",
            "Ditinjau oleh": r.get("reviewed_by") or "", "Diajukan": fmt_datetime(r["created_at"]),
        } for r in rows])
        st.dataframe(df, hide_index=True, width="stretch",
                     column_config={"Tanggal": st.column_config.DateColumn(format="DD/MM/YYYY")})
        st.download_button("Unduh CSV", df.to_csv(index=False).encode("utf-8"), "pengajuan_booking.csv",
                           "text/csv", icon=":material/download:")
    else:
        st.info("Tidak ada data sesuai filter.")
