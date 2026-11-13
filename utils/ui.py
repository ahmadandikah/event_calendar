"""Komponen UI bersama: CSS, kartu KPI, badge, formulir booking, dialog detail & konfirmasi."""
from __future__ import annotations

import random
from datetime import date, time

import streamlit as st

import auth
import database as db
from config import BOOKING_STATUS_LABEL, CATEGORIES, COLORS, HOLIDAY_TYPE_LABEL
from utils.helpers import (
    ValidationError, display_whatsapp, esc, fmt_date, fmt_time, fmt_time_range, time_options,
    today_local, wa_link,
)

# ---------------------------------------------------------------------------
# Ikon SVG (gaya garis, konsisten)
# ---------------------------------------------------------------------------
_ICON_PATHS = {
    "calendar": '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    "check": '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "sun": '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M3 10h18M8 15h.01M12 15h.01M16 15h.01"/>',
    "month": '<path d="M3 3v18h18"/><path d="m7 15 4-4 3 3 5-6"/>',
    "list": '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
}


def icon(name: str, color: str = "currentColor", size: int = 20) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" '
            f'fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            f'{_ICON_PATHS[name]}</svg>')


# ---------------------------------------------------------------------------
# CSS global
# ---------------------------------------------------------------------------
def inject_css() -> None:
    c = COLORS
    st.markdown(f"""
<style>
#MainMenu, footer, [data-testid="stAppDeployButton"] {{ visibility: hidden; display: none; }}
.block-container {{ padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1280px; }}
@media (max-width: 640px) {{ .block-container {{ padding-top: 4.2rem; padding-left: .8rem; padding-right: .8rem; }}
                            .page-head h1 {{ font-size: 1.35rem; }} }}
h1, h2, h3 {{ color: {c['navy']}; letter-spacing: -0.01em; }}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {{ color: #CBD5E1; }}
.brand {{ display:flex; align-items:center; gap:10px; padding: 4px 0 10px 0; }}
.brand-logo {{ width:38px; height:38px; border-radius:10px; background:linear-gradient(135deg,{c['blue']},#60A5FA);
              display:flex; align-items:center; justify-content:center; color:#fff; font-size:20px; }}
.brand-name {{ color:#fff; font-weight:700; font-size:1.02rem; line-height:1.15; }}
.brand-sub {{ color:#94A3B8; font-size:.75rem; }}
.mode-pill {{ display:inline-block; padding:3px 10px; border-radius:999px; font-size:.72rem; font-weight:700; }}
.mode-admin {{ background:#FDE68A; color:#78350F; }}
.mode-public {{ background:rgba(255,255,255,.12); color:#E2E8F0; }}

.page-head {{ margin-bottom: 1.1rem; }}
.page-head h1 {{ font-size: 1.65rem; font-weight: 750; margin: 0; padding: 0; }}
.page-head p {{ color: {c['muted']}; margin: .25rem 0 0 0; font-size: .95rem; }}

.hero {{ background: linear-gradient(120deg, {c['navy']} 0%, #1E3A8A 60%, {c['blue']} 100%); color:#fff;
        border-radius: 16px; padding: 22px 26px; margin-bottom: 18px; box-shadow: 0 10px 30px rgba(11,31,58,.18); }}
.hero h1 {{ color:#fff; font-size:1.55rem; margin:0; padding:0; }}
.hero p {{ color:#DBEAFE; margin:.35rem 0 0 0; }}
.hero .announce {{ margin-top:12px; background:rgba(255,255,255,.12); border-radius:10px; padding:8px 12px; font-size:.9rem; }}

.kpi-grid {{ display:grid; grid-template-columns: repeat(5, minmax(0,1fr)); gap: 14px; margin-bottom: 18px; }}
@media (max-width: 1100px) {{ .kpi-grid {{ grid-template-columns: repeat(3, minmax(0,1fr)); }} }}
@media (max-width: 640px)  {{ .kpi-grid {{ grid-template-columns: repeat(2, minmax(0,1fr)); gap:10px; }}
                              .hero {{ padding: 16px 18px; }} .hero h1 {{ font-size:1.25rem; }} }}
.kpi {{ background:#fff; border:1px solid {c['border']}; border-radius:14px; padding:14px 16px;
       box-shadow: 0 1px 2px rgba(15,23,42,.04); transition: transform .15s, box-shadow .15s; }}
.kpi:hover {{ transform: translateY(-2px); box-shadow: 0 8px 20px rgba(15,23,42,.08); }}
.kpi-top {{ display:flex; align-items:center; justify-content:space-between; color:{c['muted']}; font-size:.8rem; font-weight:600; }}
.kpi-icon {{ width:34px; height:34px; border-radius:10px; display:flex; align-items:center; justify-content:center; }}
.kpi-value {{ font-size:1.9rem; font-weight:750; color:{c['navy']}; margin-top:6px; line-height:1.1; }}
.kpi-hint {{ font-size:.75rem; color:{c['muted']}; margin-top:2px; }}

.card {{ background:#fff; border:1px solid {c['border']}; border-radius:14px; padding:16px 18px; margin-bottom:12px;
        transition: box-shadow .15s, border-color .15s; }}
.card:hover {{ box-shadow: 0 6px 18px rgba(15,23,42,.07); border-color:#C7D2FE; }}
.card-title {{ font-weight:700; color:{c['navy']}; font-size:1rem; margin:0 0 4px 0; }}
.card-meta {{ color:{c['muted']}; font-size:.85rem; }}

.agenda-item {{ display:flex; gap:12px; align-items:flex-start; padding:10px 4px; border-bottom:1px solid #EEF2F7; }}
.agenda-item:last-child {{ border-bottom:none; }}
.date-chip {{ min-width:52px; text-align:center; border-radius:10px; background:{c['blue_soft']}; color:{c['navy']}; padding:6px 4px; }}
.date-chip .d {{ font-size:1.2rem; font-weight:800; line-height:1; }}
.date-chip .m {{ font-size:.7rem; font-weight:700; text-transform:uppercase; color:{c['blue']}; }}
.agenda-title {{ font-weight:650; color:{c['text']}; }}
.agenda-meta {{ font-size:.8rem; color:{c['muted']}; }}

.badge {{ display:inline-block; padding:2px 10px; border-radius:999px; font-size:.75rem; font-weight:700; white-space:nowrap; }}
.b-pending {{ background:#FEF3C7; color:#92400E; }}
.b-approved {{ background:#DBEAFE; color:#1E40AF; }}
.b-rejected {{ background:#FEE2E2; color:#991B1B; }}
.b-cancelled {{ background:#F1F5F9; color:#475569; }}
.b-cat {{ background:#F1F5F9; color:#334155; font-weight:600; }}

.legend {{ display:flex; flex-wrap:wrap; gap:8px 16px; margin: 4px 0 12px 0; font-size:.8rem; color:#334155; }}
.legend-item {{ display:inline-flex; align-items:center; gap:6px; }}
.legend-swatch {{ width:14px; height:14px; border-radius:4px; border:2px solid; display:inline-block; }}

.ref-box {{ background: linear-gradient(135deg,#EFF6FF,#fff); border:2px dashed {c['blue']}; border-radius:14px;
           padding:18px; text-align:center; margin: 10px 0; }}
.ref-code {{ font-family: 'JetBrains Mono', ui-monospace, monospace; font-size:1.7rem; font-weight:800;
            color:{c['navy']}; letter-spacing:.06em; }}
.kv {{ display:grid; grid-template-columns: 150px 1fr; gap:6px 12px; font-size:.9rem; }}
.kv .k {{ color:{c['muted']}; }}
@media (max-width: 640px) {{ .kv {{ grid-template-columns: 1fr; }} .kv .k {{ margin-top:6px; }} .ref-code {{ font-size:1.25rem; }} }}
.timeline-item {{ border-left:3px solid {c['blue_soft']}; padding: 2px 0 10px 12px; }}
.timeline-item b {{ color:{c['navy']}; }}
.muted {{ color:{c['muted']}; font-size:.85rem; }}
div[data-testid="stForm"] {{ background:#fff; border-radius:14px; border:1px solid {c['border']}; }}
div[data-testid="stExpander"] details {{ background:#fff; border-radius:12px; }}
.stButton button, .stFormSubmitButton button, .stLinkButton a {{ border-radius:10px; font-weight:600; transition: all .15s; }}
.stButton button:hover, .stFormSubmitButton button:hover {{ transform: translateY(-1px); }}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Komponen kecil
# ---------------------------------------------------------------------------
def page_header(title: str, subtitle: str = "") -> None:
    st.markdown(f'<div class="page-head"><h1>{esc(title)}</h1>'
                f'{f"<p>{esc(subtitle)}</p>" if subtitle else ""}</div>', unsafe_allow_html=True)


def kpi_cards(items: list[tuple[str, str | int, str, str, str]]) -> None:
    """items: (label, value, hint, icon_name, accent_color)"""
    html = "".join(
        f'<div class="kpi"><div class="kpi-top"><span>{esc(label)}</span>'
        f'<span class="kpi-icon" style="background:{color}1A">{icon(ic, color, 18)}</span></div>'
        f'<div class="kpi-value">{esc(value)}</div><div class="kpi-hint">{esc(hint)}</div></div>'
        for label, value, hint, ic, color in items
    )
    st.markdown(f'<div class="kpi-grid">{html}</div>', unsafe_allow_html=True)


def status_badge(status: str) -> str:
    return f'<span class="badge b-{esc(status)}">{esc(BOOKING_STATUS_LABEL.get(status, status))}</span>'


def category_badge(cat: str) -> str:
    return f'<span class="badge b-cat">{esc(cat)}</span>'


def agenda_list_html(rows: list[dict], *, date_key: str = "event_date", show_status: bool = False) -> str:
    from utils.helpers import BULAN_SINGKAT, HARI
    if not rows:
        return '<div class="muted">Belum ada data.</div>'
    out = []
    for r in rows:
        d: date = r[date_key]
        meta = f"{HARI[d.weekday()]} · {fmt_time_range(r['start_time'], r['end_time'])}"
        if r.get("person_in_charge"):
            meta += f" · PJ: {esc(r['person_in_charge'])}"
        if r.get("requester_name"):
            meta += f" · Pemohon: {esc(r['requester_name'])}"
        right = status_badge(r["approval_status"]) if show_status and r.get("approval_status") else category_badge(r["category"])
        out.append(
            f'<div class="agenda-item"><div class="date-chip"><div class="d">{d.day}</div>'
            f'<div class="m">{BULAN_SINGKAT[d.month]}</div></div><div style="flex:1;min-width:0">'
            f'<div class="agenda-title">{esc(r["event_name"])}</div><div class="agenda-meta">{meta}</div></div>'
            f'<div>{right}</div></div>'
        )
    return "".join(out)


def flash(kind: str, message: str) -> None:
    """Simpan pesan untuk ditampilkan setelah st.rerun()."""
    st.session_state["_flash"] = (kind, message)


def show_flash() -> None:
    item = st.session_state.pop("_flash", None)
    if not item:
        return
    kind, msg = item
    if kind == "success":
        st.toast(msg, icon="✅")
    elif kind == "error":
        st.error(msg, icon="⛔")
    elif kind == "warning":
        st.warning(msg, icon="⚠️")
    else:
        st.info(msg)


def wa_button(label: str, whatsapp: str | None, message: str, key: str | None = None) -> None:
    if whatsapp:
        st.link_button(label, wa_link(whatsapp, message), icon=":material/chat:")


def show_conflicts(conflicts: list[dict]) -> None:
    if not conflicts:
        return
    rows = [{"Agenda": c["event_name"],
             "Jam": "Seharian" if c["kind"] == "locked" else f"{fmt_time(c['start_time'])}–{fmt_time(c['end_time'])}",
             "Status": {"approved": "Disetujui", "pending": "Menunggu", "locked": "Dikunci"}.get(c["status"], c["status"])}
            for c in conflicts]
    st.dataframe(rows, hide_index=True, width="stretch")


# ---------------------------------------------------------------------------
# Formulir booking (dipakai di halaman Booking & dialog kalender)
# ---------------------------------------------------------------------------
def _captcha(key: str) -> tuple[int, int]:
    ck = f"_captcha_{key}"
    if ck not in st.session_state:
        st.session_state[ck] = (random.randint(2, 9), random.randint(2, 9))
    return st.session_state[ck]


def _reset_captcha(key: str) -> None:
    st.session_state.pop(f"_captcha_{key}", None)


def day_schedule(d: date) -> None:
    """Tampilkan jadwal yang sudah terisi pada suatu tanggal (membantu memilih jam kosong)."""
    detail = db.get_day_detail(d)
    info = detail["info"] or {}
    if info.get("holiday_name"):
        st.info(f"🎌 **{info['holiday_name']}** ({HOLIDAY_TYPE_LABEL.get(info.get('holiday_type'), 'Hari libur')})")
    if info.get("lock_status") == "locked":
        st.error("🔒 Tanggal ini **dikunci** oleh Ketua Panitia dan tidak dapat dibooking.")
    elif info.get("lock_status") == "exclusive":
        st.warning("⭐ Tanggal ini **eksklusif**: hanya boleh ada satu agenda di hari ini.")
    if info.get("notes"):
        st.caption(f"Catatan: {info['notes']}")
    busy = [("Disetujui", r) for r in detail["events"]] + [("Menunggu", r) for r in detail["pending"]]
    if busy:
        st.markdown("**Jam yang sudah terisi:**")
        st.dataframe(
            [{"Jam": f"{fmt_time(r['start_time'])}–{fmt_time(r['end_time'])}", "Kegiatan": r["event_name"],
              "Status": s} for s, r in sorted(busy, key=lambda x: x[1]["start_time"])],
            hide_index=True, width="stretch")
    else:
        st.success("✅ Belum ada agenda pada tanggal ini — semua jam masih tersedia.")
    return detail


def booking_form(key: str, booking_date: date, settings: dict, default_start: time | None = None) -> dict | None:
    """Render formulir booking. Mengembalikan hasil bila pengajuan berhasil."""
    opts = time_options(30, settings["day_start_time"], settings["day_end_time"])
    start_default = default_start if default_start in opts else (time(9, 0) if time(9, 0) in opts else opts[0])
    s_idx = opts.index(start_default)
    e_idx = min(s_idx + 4, len(opts) - 1)
    a, b = _captcha(key)

    with st.form(key, clear_on_submit=False, border=True):
        st.markdown(f"**📅 Tanggal kegiatan:** {fmt_date(booking_date)}")
        st.markdown("##### 👤 Data pemohon")
        c1, c2 = st.columns(2)
        requester = c1.text_input("Nama pemohon *", max_chars=100, placeholder="Nama lengkap")
        wa = c2.text_input("Nomor WhatsApp *", max_chars=20, placeholder="08xxxxxxxxxx",
                           help="Dipakai Ketua Panitia untuk konfirmasi dan untuk membatalkan pengajuan Anda.")
        pic = st.text_input("Penanggung jawab kegiatan", max_chars=100,
                            placeholder="Kosongkan bila sama dengan pemohon")

        st.markdown("##### 📝 Detail kegiatan")
        c1, c2 = st.columns([2, 1])
        event_name = c1.text_input("Nama kegiatan *", max_chars=150, placeholder="Contoh: Rapat koordinasi seksi acara")
        category = c2.selectbox("Kategori *", CATEGORIES, index=None, placeholder="Pilih kategori")
        c1, c2, c3 = st.columns(3)
        start = c1.selectbox("Waktu mulai *", opts, index=s_idx, format_func=lambda t: t.strftime("%H:%M"))
        end = c2.selectbox("Waktu selesai *", opts, index=e_idx, format_func=lambda t: t.strftime("%H:%M"))
        participants = c3.number_input("Jumlah peserta", min_value=0, max_value=100000, value=0, step=1,
                                       help="Opsional. Biarkan 0 bila belum diketahui.")
        location = st.text_input("Lokasi", max_chars=150, placeholder="Opsional, contoh: Aula masjid")
        description = st.text_area("Deskripsi kegiatan *", max_chars=2000, height=100,
                                   placeholder="Jelaskan singkat tujuan dan susunan kegiatan")
        notes = st.text_area("Catatan tambahan", max_chars=1000, height=70, placeholder="Opsional")

        c1, c2 = st.columns([1, 2])
        answer = c1.number_input(f"Verifikasi: {a} + {b} = ?", min_value=0, max_value=99, value=None, step=1)
        c2.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        agree = c2.checkbox("Saya menyatakan data yang diisi benar.")
        submitted = st.form_submit_button("Kirim Pengajuan Booking", type="primary", icon=":material/send:",
                                          width="stretch")

    if not submitted:
        return None
    if answer != a + b:
        st.error("Jawaban verifikasi salah. Silakan hitung ulang.")
        return None
    if not agree:
        st.error("Centang pernyataan bahwa data yang diisi benar.")
        return None
    try:
        with st.spinner("Mengirim pengajuan..."):
            result = db.create_booking_request({
                "requester_name": requester, "requester_whatsapp": wa, "person_in_charge": pic,
                "event_name": event_name, "category": category, "requested_date": booking_date,
                "start_time": start, "end_time": end, "location": location,
                "participants": participants or None, "description": description, "notes": notes,
            }, auth.client_fingerprint())
    except db.ConflictError as e:
        st.error(str(e), icon="⛔")
        return None
    except (ValidationError, db.BookingError) as e:
        st.error(str(e), icon="⚠️")
        return None
    _reset_captcha(key)
    refs = st.session_state.setdefault("my_refs", [])
    if result["reference"] not in refs:
        refs.insert(0, result["reference"])
    st.session_state["last_booking"] = result
    return result


def booking_success(result: dict) -> None:
    ref = result["reference"]
    st.success("Pengajuan booking berhasil dikirim dan sedang **menunggu persetujuan** Ketua Panitia.", icon="✅")
    st.markdown(f'<div class="ref-box"><div class="muted">Kode Referensi Booking Anda</div>'
                f'<div class="ref-code">{esc(ref)}</div>'
                f'<div class="muted">Simpan kode ini untuk mengecek status atau membatalkan pengajuan.</div></div>',
                unsafe_allow_html=True)
    st.code(ref, language=None)
    msg = (f"Kode booking saya: {ref}\nKegiatan: {result['event_name']}\n"
           f"Tanggal: {fmt_date(result['requested_date'])} {fmt_time_range(result['start_time'], result['end_time'])}")
    c1, c2 = st.columns(2)
    with c1:
        st.link_button("Simpan kode ke WhatsApp saya", wa_link(result["requester_whatsapp"], msg),
                       icon=":material/chat:", width="stretch")
    with c2:
        if st.button("Cek status booking", icon=":material/search:", width="stretch", key=f"goto_status_{ref}"):
            st.session_state["lookup_ref"] = ref
            st.switch_page("views/my_bookings.py")


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------
def _kv(rows: list[tuple[str, str]]) -> str:
    return '<div class="kv">' + "".join(f'<div class="k">{esc(k)}</div><div>{v}</div>' for k, v in rows) + "</div>"


@st.dialog("Detail Agenda", width="large", on_dismiss="rerun")
def event_dialog(event_ref: str) -> None:
    kind, _, ident = event_ref.partition(":")
    ctx = auth.get_admin()
    if kind == "ev":
        ev = db.admin_get_event(ctx, ident) if ctx else db.get_public_event(ident)
        if not ev or ev.get("status") == "cancelled" and not ctx:
            st.warning("Agenda tidak ditemukan atau sudah dibatalkan.")
            return
        st.markdown(f"### {esc(ev['event_name'])}")
        st.markdown(f'<span class="badge b-approved">Agenda resmi · Disetujui</span> {category_badge(ev["category"])}',
                    unsafe_allow_html=True)
        rows = [("Tanggal", esc(fmt_date(ev["event_date"]))),
                ("Waktu", esc(fmt_time_range(ev["start_time"], ev["end_time"]))),
                ("Penanggung jawab", esc(ev["person_in_charge"])),
                ("Lokasi", esc(ev.get("location") or "-")),
                ("Jumlah peserta", esc(ev.get("participants") or "-")),
                ("Deskripsi", esc(ev.get("description") or "-"))]
        if ctx:
            rows += [("WhatsApp PJ", esc(display_whatsapp(ev.get("pic_whatsapp")))),
                     ("Kode booking", esc(ev.get("booking_reference") or "Dibuat langsung oleh admin")),
                     ("Disetujui oleh", esc(ev.get("approved_by") or "-")),
                     ("Override konflik", "Ya" if ev.get("conflict_override") else "Tidak")]
        st.markdown(_kv(rows), unsafe_allow_html=True)
        if ctx:
            st.divider()
            c1, c2 = st.columns(2)
            if c1.button("Kelola agenda ini", icon=":material/edit_calendar:", width="stretch"):
                st.session_state["manage_event_id"] = ident
                st.switch_page("views/event_management.py")
            if ev.get("pic_whatsapp"):
                with c2:
                    wa_button("Hubungi PJ via WhatsApp", ev["pic_whatsapp"],
                              f"Assalamu'alaikum, terkait agenda '{ev['event_name']}' pada {fmt_date(ev['event_date'])}.")
    elif kind == "bk":
        bk = db.get_public_pending(ident)
        if not bk:
            st.info("Pengajuan ini sudah diproses. Muat ulang kalender.")
            return
        st.markdown(f"### ⏳ {esc(bk['event_name'])}")
        st.markdown(f'{status_badge("pending")} {category_badge(bk["category"])}', unsafe_allow_html=True)
        st.markdown(_kv([("Tanggal", esc(fmt_date(bk["requested_date"]))),
                         ("Waktu", esc(fmt_time_range(bk["start_time"], bk["end_time"])))]), unsafe_allow_html=True)
        st.caption("Slot ini sedang diajukan dan menunggu keputusan Ketua Panitia.")
        if ctx and st.button("Buka Approval Management", icon=":material/fact_check:", type="primary"):
            st.switch_page("views/approvals.py")
    elif kind == "hd":
        day_dialog_body(date.fromisoformat(ident), None)


def day_dialog_body(d: date, t: time | None) -> None:
    st.markdown(f"### {esc(fmt_date(d))}")
    detail = day_schedule(d)
    settings = detail["settings"]
    info = detail["info"] or {}
    today = today_local()
    ctx = auth.get_admin()
    if d < today:
        st.caption("Tanggal sudah lewat — tidak dapat diajukan booking.")
        return
    if not settings["booking_open"]:
        st.warning("Pengajuan booking sedang ditutup sementara oleh Ketua Panitia.")
        return
    if info.get("lock_status") == "locked" and not ctx:
        return
    if ctx:
        st.caption("Sebagai admin, Anda dapat menambah agenda resmi langsung dari menu **Kelola Agenda**.")
        if st.button("Tambah agenda resmi di tanggal ini", icon=":material/add:", type="primary"):
            st.session_state["new_event_date"] = d
            st.switch_page("views/event_management.py")
        return
    st.divider()
    st.markdown("#### Ajukan booking di tanggal ini")
    key = f"dlg_form_{d.isoformat()}"
    result = booking_form(key, d, settings, default_start=t)
    if result:
        booking_success(result)


@st.dialog("Detail Tanggal", width="large", on_dismiss="rerun")
def day_dialog(d: date, t: time | None = None) -> None:
    day_dialog_body(d, t)


@st.dialog("Konfirmasi", on_dismiss="ignore")
def confirm_dialog(title: str, message: str, action, success_message: str, *, danger: bool = True,
                   confirm_label: str = "Ya, lanjutkan") -> None:
    st.markdown(f"#### {esc(title)}")
    st.markdown(message)
    c1, c2 = st.columns(2)
    if c1.button("Batal", width="stretch"):
        st.rerun()
    if c2.button(confirm_label, type="primary", width="stretch",
                 icon=":material/delete:" if danger else ":material/check:"):
        try:
            with st.spinner("Memproses..."):
                action()
        except (ValidationError, db.BookingError, db.AuthorizationError) as e:
            st.error(str(e))
            return
        flash("success", success_message)
        st.rerun()
