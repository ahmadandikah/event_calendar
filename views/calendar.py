"""Kalender interaktif (FullCalendar): bulanan, mingguan, dan agenda/list."""
from datetime import date

import streamlit as st
from streamlit_calendar import calendar as fc_calendar

import auth
import database as db
from config import CATEGORIES
from utils import ui
from utils.calendar_utils import (
    CALENDAR_CSS, VIEW_LABELS, build_events, calendar_options, legend_html, parse_callback, view_state_from,
)
from utils.helpers import today_local

ui.page_header("Kalender Kegiatan", "Klik tanggal untuk melihat detail atau mengajukan booking. "
                                    "Klik agenda untuk melihat informasinya.")

today = today_local()
settings = db.get_calendar_settings()
period_start, period_end = settings["start_date"], settings["end_date"]

ss = st.session_state
ss.setdefault("cal_nonce", 0)
ss.setdefault("cal_view", "dayGridMonth")
if "cal_date" not in ss:
    ss["cal_date"] = min(max(today, period_start), period_end)

# ---------------------------------------------------------------- filter & pencarian
top1, top2 = st.columns([3, 1])
with top2:
    if st.button("Ajukan booking baru", icon=":material/add:", type="primary", width="stretch"):
        st.switch_page("views/booking.py")
with top1.expander("🔎 Filter, pencarian & tampilan", expanded=bool(st.session_state.get("cal_search") or st.session_state.get("cal_cats"))):
    f1, f2, f3, f4 = st.columns([2, 2, 1.3, 1.3])
    search = f1.text_input("Cari agenda", placeholder="Nama kegiatan, PJ, lokasi…", label_visibility="collapsed",
                           key="cal_search")
    cats = f2.multiselect("Kategori", CATEGORIES, placeholder="Semua kategori", label_visibility="collapsed",
                          key="cal_cats")
    show_pending = f3.toggle("Tampilkan pending", value=True, key="cal_show_pending")
    show_available = f4.toggle("Tanggal kosong", value=True, key="cal_show_available")
    j1, j2 = st.columns(2)
    months = []
    y, m = period_start.year, period_start.month
    while (y, m) <= (period_end.year, period_end.month):
        months.append(date(y, m, 1))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    from utils.helpers import BULAN
    cur_month = date(ss["cal_date"].year, ss["cal_date"].month, 1)
    jump = j1.selectbox("Lompat ke bulan", months, index=months.index(cur_month) if cur_month in months else 0,
                        format_func=lambda d: f"{BULAN[d.month]} {d.year}", key=f"cal_jump_{ss['cal_nonce']}")
    view_choice = j2.selectbox("Tampilan", list(VIEW_LABELS), index=list(VIEW_LABELS).index(ss["cal_view"]),
                               format_func=lambda v: VIEW_LABELS[v], key=f"cal_viewsel_{ss['cal_nonce']}")
    if jump != cur_month or view_choice != ss["cal_view"]:
        ss["cal_date"] = jump if jump != cur_month else ss["cal_date"]
        ss["cal_view"] = view_choice
        ss["cal_nonce"] += 1
        st.rerun()

st.markdown(legend_html(), unsafe_allow_html=True)

# ---------------------------------------------------------------- kalender
data = db.get_calendar_data(period_start, period_end)
events = build_events(data, today=today, show_pending=show_pending, show_available=show_available,
                      categories=cats or None, search=search)
options = calendar_options(settings, initial_view=ss["cal_view"], initial_date=ss["cal_date"], today=today)

with st.container(border=True):
    value = fc_calendar(events=events, options=options, custom_css=CALENDAR_CSS,
                        callbacks=["dateClick", "eventClick"], key=f"calendar_{ss['cal_nonce']}")

action = parse_callback(value)
if action:
    # Ingat posisi tampilan, lalu ganti key komponen agar klik berikutnya (meski tanggal sama) terdeteksi
    vtype, vdate = view_state_from(action.get("view") or {})
    if vtype:
        ss["cal_view"] = vtype
    clicked = action["date"] if action["type"] == "date" else (
        date.fromisoformat(action["start"]) if action.get("start") else None)
    focus = clicked or vdate
    if focus:
        ss["cal_date"] = min(max(focus, period_start), period_end)
    ss["cal_nonce"] += 1
    if action["type"] == "date":
        ui.day_dialog(action["date"], action["time"])
    elif action["type"] == "event":
        eid = action["id"]
        if eid.startswith(("ev:", "bk:", "hd:")):
            ui.event_dialog(eid)
        elif action.get("start"):
            ui.day_dialog(date.fromisoformat(action["start"]), None)

# ---------------------------------------------------------------- ringkasan teks (aksesibel & ramah HP)
n_ev = sum(1 for e in events if e["id"].startswith("ev:"))
n_pd = sum(1 for e in events if e["id"].startswith("bk:"))
st.caption(f"Menampilkan {n_ev} agenda disetujui dan {n_pd} pengajuan menunggu persetujuan"
           f"{' (terfilter)' if (search or cats) else ''}. Waktu dalam WIB.")
if auth.get_admin() is None:
    st.caption("Ingin mengelola kalender? Ketua Panitia dapat masuk melalui tombol **Admin Mode** di sidebar.")
