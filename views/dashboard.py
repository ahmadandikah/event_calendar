"""Dashboard: KPI, grafik, agenda terdekat, pengajuan terbaru (selalu dari database)."""
import plotly.graph_objects as go
import streamlit as st

import auth
import database as db
from config import APP_NAME, COLORS
from utils import ui
from utils.helpers import BULAN, esc, fmt_date, month_label, today_local

def _bar_layout(fig: go.Figure, height: int = 300) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=8, r=8, t=8, b=8), plot_bgcolor="#FFFFFF", paper_bgcolor="#FFFFFF",
        font=dict(family="Inter, sans-serif", size=12, color="#334155"), showlegend=False,
        hoverlabel=dict(bgcolor="#0B1F3A", font_color="#FFFFFF", bordercolor="#0B1F3A"), bargap=0.35)
    fig.update_xaxes(showgrid=False, linecolor="#CBD5E1", tickfont=dict(color="#475569"))
    fig.update_yaxes(gridcolor="#EEF2F7", zeroline=False, tickfont=dict(color="#64748B"), rangemode="tozero")
    return fig


@st.fragment(run_every="60s")
def dashboard_body() -> None:
    ctx = auth.get_admin()
    today = today_local()

    with st.spinner("Memuat data..."):
        s = db.dashboard_stats(include_private=ctx is not None)
    settings = s["settings"]

    announce = f'<div class="announce">📢 {esc(settings["announcement"])}</div>' if settings.get("announcement") else ""
    st.markdown(
        f'<div class="hero"><h1>{esc(APP_NAME)}</h1>'
        f'<p>Periode {esc(fmt_date(settings["start_date"], False))} – {esc(fmt_date(settings["end_date"], False))} · '
        f'Hari ini {esc(fmt_date(today))}</p>{announce}</div>', unsafe_allow_html=True)

    if not settings["booking_open"]:
        st.warning("Pengajuan booking sedang **ditutup sementara** oleh Ketua Panitia.", icon="⏸️")

    ui.kpi_cards([
        ("Total Agenda", s["total"], "Disetujui + menunggu", "calendar", COLORS["navy"]),
        ("Disetujui", s["approved"], "Agenda resmi", "check", COLORS["approved"]),
        ("Menunggu Persetujuan", s["pending"], "Pengajuan pending", "clock", COLORS["pending"]),
        ("Tanggal Tersedia", s["available_dates"], "Hari kosong s.d. akhir periode", "sun", "#059669"),
        ("Agenda Bulan Ini", s["this_month"], f"{BULAN[today.month]} {today.year}", "month", "#7C3AED"),
    ])

    c1, c2, c3 = st.columns(3)
    if c1.button("Lihat Kalender", icon=":material/calendar_month:", width="stretch"):
        st.switch_page("views/calendar.py")
    if c2.button("Ajukan Booking", icon=":material/add_circle:", type="primary", width="stretch"):
        st.switch_page("views/booking.py")
    if ctx and s["pending"]:
        if c3.button(f"Proses {s['pending']} pengajuan", icon=":material/fact_check:", width="stretch"):
            st.switch_page("views/approvals.py")
    elif c3.button("Cek Status Booking", icon=":material/confirmation_number:", width="stretch"):
        st.switch_page("views/my_bookings.py")

    st.write("")


    g1, g2 = st.columns([3, 2])
    with g1:
        with st.container(border=True):
            st.markdown("**Jumlah agenda disetujui per bulan**")
            pm = s["per_month"]
            fig = go.Figure(go.Bar(
                x=[month_label(r["year"], r["month"]) for r in pm], y=[r["count"] for r in pm],
                marker=dict(color=COLORS["blue"], cornerradius=4),
                hovertemplate="%{x}<br><b>%{y} agenda</b><extra></extra>"))
            fig.update_yaxes(dtick=1 if max([r["count"] for r in pm] + [0]) < 10 else None)
            st.plotly_chart(_bar_layout(fig), width="stretch", config={"displayModeBar": False})
    with g2:
        with st.container(border=True):
            st.markdown("**Agenda berdasarkan kategori**")
            pc = sorted(s["per_category"], key=lambda r: r["count"])
            fig = go.Figure(go.Bar(
                y=[r["category"] for r in pc], x=[r["count"] for r in pc], orientation="h",
                marker=dict(color=COLORS["navy"], cornerradius=4),
                text=[r["count"] or "" for r in pc], textposition="outside", cliponaxis=False,
                hovertemplate="%{y}<br><b>%{x} agenda</b><extra></extra>"))
            fig.update_xaxes(showgrid=False, showticklabels=False)
            st.plotly_chart(_bar_layout(fig), width="stretch", config={"displayModeBar": False})

    l1, l2 = st.columns(2)
    with l1:
        with st.container(border=True):
            st.markdown("**📌 Agenda terdekat**")
            st.markdown(ui.agenda_list_html(s["upcoming"]), unsafe_allow_html=True)
    with l2:
        with st.container(border=True):
            st.markdown("**🆕 Pengajuan booking terbaru**")
            st.markdown(ui.agenda_list_html(s["latest"], date_key="requested_date", show_status=True),
                        unsafe_allow_html=True)
            if not ctx:
                st.caption("Identitas pemohon hanya terlihat oleh Ketua Panitia.")

    st.caption("Data diperbarui otomatis dari database setiap 60 detik.")
    if st.button("Muat ulang data", icon=":material/refresh:"):
        st.rerun(scope="fragment")


dashboard_body()
