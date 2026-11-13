"""Pembentukan data & opsi FullCalendar (via streamlit-calendar)."""
from __future__ import annotations

from datetime import date, time, timedelta

from config import COLORS
from utils.helpers import daterange, esc

ISLAMIC_KEYWORDS = ("idul fitri", "idulfitri", "idul adha", "iduladha", "isra", "maulid", "tahun baru islam", "muharram")

VIEW_LABELS = {"dayGridMonth": "Bulanan", "timeGridWeek": "Mingguan", "listMonth": "Agenda"}


def _is_islamic(row: dict) -> bool:
    name = (row.get("holiday_name") or "").lower()
    return row.get("holiday_type") == "hari_raya_islam" or any(k in name for k in ISLAMIC_KEYWORDS)


def _iso(d: date, t: time | None = None) -> str:
    return f"{d.isoformat()}T{t.strftime('%H:%M:%S')}" if t else d.isoformat()


def build_events(data: dict, *, today: date, show_pending: bool = True, show_available: bool = True,
                 categories: list[str] | None = None, search: str | None = None) -> list[dict]:
    """Ubah data database menjadi daftar event FullCalendar."""
    q = (search or "").strip().lower()

    def keep(name: str, cat: str, extra: str = "") -> bool:
        if categories and cat not in categories:
            return False
        return not q or q in f"{name} {extra}".lower()

    events: list[dict] = []
    busy_dates: set[date] = set()

    for e in data["events"]:
        busy_dates.add(e["event_date"])
        if not keep(e["event_name"], e["category"], f"{e.get('person_in_charge', '')} {e.get('location') or ''}"):
            continue
        events.append({
            "id": f"ev:{e['id']}",
            "title": e["event_name"],
            "start": _iso(e["event_date"], e["start_time"]),
            "end": _iso(e["event_date"], e["end_time"]),
            "backgroundColor": COLORS["approved"],
            "borderColor": COLORS["approved"],
            "textColor": "#FFFFFF",
            "classNames": ["ev-approved"],
            "extendedProps": {"kind": "approved", "category": e["category"]},
        })

    if show_pending:
        for p in data["pending"]:
            if not keep(p["event_name"], p["category"]):
                continue
            events.append({
                "id": f"bk:{p['id']}",
                "title": f"⏳ {p['event_name']}",
                "start": _iso(p["requested_date"], p["start_time"]),
                "end": _iso(p["requested_date"], p["end_time"]),
                "backgroundColor": COLORS["pending_bg"],
                "borderColor": COLORS["pending"],
                "textColor": "#92400E",
                "classNames": ["ev-pending"],
                "extendedProps": {"kind": "pending", "category": p["category"]},
            })

    locked: set[date] = set()
    for row in data["dates"]:
        d = row["calendar_date"]
        nxt = (d + timedelta(days=1)).isoformat()
        if row.get("holiday_name"):
            islamic = _is_islamic(row)
            events.append({
                "id": f"hd:{d.isoformat()}",
                "title": ("🕌 " if islamic else "🎌 ") + row["holiday_name"],
                "start": d.isoformat(), "end": nxt, "allDay": True,
                "backgroundColor": COLORS["islamic_bg"] if islamic else COLORS["holiday_bg"],
                "borderColor": COLORS["islamic_text"] if islamic else COLORS["holiday_text"],
                "textColor": COLORS["islamic_text"] if islamic else COLORS["holiday_text"],
                "classNames": ["ev-holiday"], "display": "block",
                "extendedProps": {"kind": "holiday"},
            })
            events.append({
                "id": f"hb:{d.isoformat()}", "start": d.isoformat(), "end": nxt, "allDay": True,
                "display": "background",
                "backgroundColor": COLORS["islamic_bg"] if islamic else COLORS["holiday_bg"],
                "classNames": ["bg-holiday"],
            })
        if row.get("lock_status") == "locked":
            locked.add(d)
            events.append({"id": f"lk:{d.isoformat()}", "title": "🔒 Dikunci", "start": d.isoformat(), "end": nxt,
                           "allDay": True, "display": "background", "backgroundColor": COLORS["locked_bg"],
                           "classNames": ["bg-locked"]})
        elif row.get("lock_status") == "exclusive":
            events.append({"id": f"ex:{d.isoformat()}", "title": "⭐ Eksklusif", "start": d.isoformat(), "end": nxt,
                           "allDay": True, "display": "background", "backgroundColor": COLORS["exclusive_bg"],
                           "classNames": ["bg-exclusive"]})

    if show_available:
        s = data["settings"]
        first = max(today, s["start_date"])
        holiday_dates = {r["calendar_date"] for r in data["dates"] if r.get("holiday_name")}
        for d in daterange(first, s["end_date"]):
            if d in busy_dates or d in locked or d in holiday_dates:
                continue
            events.append({"id": f"av:{d.isoformat()}", "start": d.isoformat(),
                           "end": (d + timedelta(days=1)).isoformat(), "allDay": True, "display": "background",
                           "backgroundColor": COLORS["available_bg"], "classNames": ["bg-available"]})
    return events


def calendar_options(settings: dict, *, initial_view: str, initial_date: date, today: date) -> dict:
    day_start = settings["day_start_time"].strftime("%H:%M:%S")
    day_end = settings["day_end_time"].strftime("%H:%M:%S")
    hm = {"hour": "2-digit", "minute": "2-digit", "hour12": False}
    return {
        "initialView": initial_view,
        "initialDate": initial_date.isoformat(),
        "now": today.isoformat() + "T08:00:00",
        "timeZone": "UTC",  # waktu ditampilkan apa adanya (WIB) tanpa konversi browser
        "locale": "id",
        "firstDay": 1,
        "headerToolbar": {"left": "prev,next today", "center": "title",
                          "right": "dayGridMonth,timeGridWeek,listMonth"},
        "buttonText": {"today": "Hari ini", "month": "Bulan", "week": "Minggu", "list": "Agenda"},
        "allDayText": "Hari",
        "moreLinkText": "lainnya",
        "noEventsText": "Tidak ada agenda pada periode ini",
        "validRange": {"start": settings["start_date"].isoformat(),
                       "end": (settings["end_date"] + timedelta(days=1)).isoformat()},
        "slotMinTime": day_start,
        "slotMaxTime": day_end,
        "slotDuration": "00:30:00",
        "eventTimeFormat": hm,
        "slotLabelFormat": hm,
        "dayMaxEvents": 3,
        "navLinks": False,
        "selectable": False,
        "editable": False,
        "nowIndicator": False,
        "height": "auto",
        "expandRows": True,
        "stickyHeaderDates": True,
        "fixedWeekCount": False,
        "eventDisplay": "block",
        "listDayFormat": {"weekday": "long", "day": "numeric", "month": "long"},
        "listDaySideFormat": {"year": "numeric"},
    }


CALENDAR_CSS = f"""
:root {{ --fc-border-color: #E3E8F0; --fc-today-bg-color: #EFF6FF; --fc-page-bg-color: #FFFFFF;
         --fc-neutral-bg-color: #F8FAFC; --fc-list-event-hover-bg-color: #EFF6FF; }}
.fc {{ font-family: 'Inter', -apple-system, 'Segoe UI', Roboto, sans-serif; font-size: 0.86rem; color: #0F172A; }}
.fc .fc-toolbar {{ flex-wrap: wrap; gap: 8px; }}
.fc .fc-toolbar-title {{ font-size: 1.25rem; font-weight: 700; color: {COLORS['navy']}; text-transform: capitalize; }}
.fc .fc-button {{ background: #FFFFFF; color: {COLORS['navy']}; border: 1px solid #CBD5E1; border-radius: 8px;
                  text-transform: capitalize; font-weight: 600; padding: 6px 12px; box-shadow: none; transition: all .15s; }}
.fc .fc-button:hover {{ background: {COLORS['blue_soft']}; border-color: {COLORS['blue']}; color: {COLORS['blue']}; }}
.fc .fc-button-primary:not(:disabled).fc-button-active, .fc .fc-button-primary:not(:disabled):active {{
    background: {COLORS['navy']}; color: #fff; border-color: {COLORS['navy']}; }}
.fc .fc-button:disabled {{ opacity: .45; }}
.fc .fc-button-group > .fc-button {{ border-radius: 0; }}
.fc .fc-button-group > .fc-button:first-child {{ border-radius: 8px 0 0 8px; }}
.fc .fc-button-group > .fc-button:last-child {{ border-radius: 0 8px 8px 0; }}
.fc .fc-col-header-cell {{ background: #F8FAFC; padding: 6px 0; font-weight: 600; color: #475569; text-transform: capitalize; }}
.fc .fc-daygrid-day {{ cursor: pointer; transition: background .15s; }}
.fc .fc-daygrid-day:hover {{ background: #F1F5FF; }}
.fc .fc-daygrid-day-number {{ font-weight: 600; color: #334155; padding: 6px 8px; }}
.fc .fc-day-today .fc-daygrid-day-number {{ background: {COLORS['blue']}; color: #fff; border-radius: 999px;
                                            min-width: 26px; text-align: center; margin: 4px; padding: 3px 6px; }}
.fc .fc-day-past {{ opacity: .55; }}
.fc .fc-day-disabled {{ background: #F1F5F9; }}
.fc-event {{ border-radius: 6px; padding: 1px 4px; font-weight: 500; cursor: pointer; transition: transform .1s, box-shadow .15s; }}
.fc-event:hover {{ transform: translateY(-1px); box-shadow: 0 3px 8px rgba(15,23,42,.18); }}
.fc .ev-pending {{ border-style: dashed !important; border-width: 1.5px !important; }}
.fc .ev-holiday {{ font-weight: 600; font-size: .78rem; }}
.fc .fc-daygrid-event-dot {{ border-color: currentColor; }}
.fc .fc-bg-event {{ opacity: 1; }}
.fc .fc-bg-event .fc-event-title {{ font-style: normal; font-size: .7rem; font-weight: 600; color: #475569; margin: 2px 4px; }}
.fc .fc-daygrid-block-event .fc-event-main {{ white-space: normal; line-height: 1.25; padding: 1px 0; }}
.fc .fc-daygrid-block-event .fc-event-main-frame {{ display: block; }}
.fc .fc-daygrid-block-event .fc-event-time {{ display: inline; font-weight: 700; margin-right: 4px; overflow: visible; }}
.fc .fc-daygrid-block-event .fc-event-title-container {{ display: inline; }}
.fc .fc-daygrid-block-event .fc-event-title {{ display: inline; overflow: visible; }}
.fc .fc-list-event {{ cursor: pointer; }}
.fc .fc-list-day-cushion {{ background: #F1F5F9; text-transform: capitalize; }}
.fc .fc-timegrid-slot {{ height: 2.2em; }}
.fc .fc-more-link {{ color: {COLORS['blue']}; font-weight: 600; }}
@media (max-width: 640px) {{
  .fc .fc-toolbar {{ flex-direction: column; align-items: stretch; }}
  .fc .fc-toolbar-chunk {{ display: flex; justify-content: center; }}
  .fc .fc-toolbar-title {{ font-size: 1.05rem; text-align: center; }}
  .fc .fc-button {{ padding: 5px 9px; font-size: .8rem; }}
  .fc {{ font-size: .74rem; }}
  .fc .fc-daygrid-event {{ font-size: .66rem; }}
  .fc .fc-daygrid-event .fc-event-time {{ display: none; }}
  .fc .fc-daygrid-day-number {{ padding: 3px 4px; }}
}}
"""


LEGEND_ITEMS = [
    ("legend-approved", COLORS["approved"], COLORS["approved"], "Agenda disetujui"),
    ("legend-pending", COLORS["pending_bg"], COLORS["pending"], "Menunggu persetujuan"),
    ("legend-available", COLORS["available_bg"], "#10B981", "Tanggal tersedia"),
    ("legend-holiday", COLORS["holiday_bg"], COLORS["holiday_text"], "Libur nasional / cuti bersama"),
    ("legend-islamic", COLORS["islamic_bg"], COLORS["islamic_text"], "Hari raya Islam"),
    ("legend-locked", COLORS["locked_bg"], "#6B7280", "Tanggal dikunci"),
    ("legend-exclusive", COLORS["exclusive_bg"], "#7C3AED", "Tanggal eksklusif"),
]


def legend_html() -> str:
    items = "".join(
        f'<span class="legend-item"><span class="legend-swatch" style="background:{bg};border-color:{bd}"></span>'
        f"{esc(label)}</span>" for _, bg, bd, label in LEGEND_ITEMS
    )
    return f'<div class="legend">{items}</div>'


def parse_callback(value) -> dict | None:
    """Ubah nilai balik komponen kalender menjadi aksi sederhana."""
    if not isinstance(value, dict) or "callback" not in value:
        return None
    cb = value["callback"]
    view = {}
    if cb == "dateClick":
        payload = value.get("dateClick", {})
        raw = payload.get("date", "")
        view = payload.get("view") or {}
        try:
            d = date.fromisoformat(raw[:10])
        except ValueError:
            return None
        t = None
        if not payload.get("allDay") and len(raw) >= 16:
            t = time(int(raw[11:13]), int(raw[14:16]))
        return {"type": "date", "date": d, "time": t, "view": view}
    if cb == "eventClick":
        payload = value.get("eventClick", {})
        ev = payload.get("event") or {}
        view = payload.get("view") or {}
        eid = ev.get("id") or ""
        start = (ev.get("start") or "")[:10]
        return {"type": "event", "id": eid, "start": start, "view": view}
    return None


def view_state_from(view: dict) -> tuple[str | None, date | None]:
    vtype = view.get("type") if isinstance(view, dict) else None
    start = (view.get("currentStart") or view.get("activeStart") or "")[:10] if isinstance(view, dict) else ""
    try:
        d = date.fromisoformat(start) if start else None
    except ValueError:
        d = None
    return (vtype if vtype in VIEW_LABELS else None), d
