"""Fungsi bantu umum: tanggal Indonesia, validasi input, nomor WhatsApp, kode referensi."""
from __future__ import annotations

import html
import re
import secrets
from datetime import date, datetime, time, timedelta
from urllib.parse import quote

from config import TZ

HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN = [
    "", "Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
    "Agustus", "September", "Oktober", "November", "Desember",
]
BULAN_SINGKAT = ["", "Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]

# Alfabet tanpa karakter yang mudah tertukar (0/O, 1/I)
_REF_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"  # 32 karakter = 5 bit/karakter
_REF_RE = re.compile(r"^BK-[2-9A-HJ-NP-Z]{4}-[2-9A-HJ-NP-Z]{4}-[2-9A-HJ-NP-Z]{4}$")


class ValidationError(ValueError):
    """Kesalahan input yang pesannya aman ditampilkan ke pengguna."""


# ---------------------------------------------------------------------------
# Waktu
# ---------------------------------------------------------------------------
def now_local() -> datetime:
    return datetime.now(TZ)


def today_local() -> date:
    return now_local().date()


def fmt_date(d: date | None, with_day: bool = True) -> str:
    if not d:
        return "-"
    s = f"{d.day} {BULAN[d.month]} {d.year}"
    return f"{HARI[d.weekday()]}, {s}" if with_day else s


def fmt_date_short(d: date | None) -> str:
    if not d:
        return "-"
    return f"{d.day} {BULAN_SINGKAT[d.month]} {d.year}"


def fmt_time(t: time | None) -> str:
    return t.strftime("%H:%M") if t else "-"


def fmt_time_range(start: time, end: time) -> str:
    return f"{fmt_time(start)}–{fmt_time(end)} WIB"


def fmt_datetime(dt: datetime | None) -> str:
    if not dt:
        return "-"
    dt = dt.astimezone(TZ)
    return f"{fmt_date_short(dt.date())} {dt.strftime('%H:%M')}"


def month_label(year: int, month: int) -> str:
    return f"{BULAN_SINGKAT[month]} {year}"


def iter_months(start: date, end: date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def time_options(step_minutes: int = 30, start: time = time(0, 0), end: time = time(23, 30)) -> list[time]:
    out, cur = [], datetime.combine(date.today(), start)
    stop = datetime.combine(date.today(), end)
    while cur <= stop:
        out.append(cur.time())
        cur += timedelta(minutes=step_minutes)
    return out


def minutes_between(start: time, end: time) -> int:
    return (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)


# ---------------------------------------------------------------------------
# WhatsApp
# ---------------------------------------------------------------------------
def normalize_whatsapp(raw: str | None) -> str:
    """Ubah 0812-3456-789 / +62 812... / 812... menjadi 628123456789."""
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("0"):
        digits = "62" + digits[1:]
    elif digits.startswith("8"):
        digits = "62" + digits
    if not re.fullmatch(r"62\d{8,13}", digits):
        raise ValidationError("Nomor WhatsApp tidak valid. Contoh yang benar: 081234567890.")
    return digits


def mask_whatsapp(wa: str | None) -> str:
    if not wa:
        return "-"
    return f"+{wa[:4]}••••{wa[-3:]}"


def display_whatsapp(wa: str | None) -> str:
    if not wa:
        return "-"
    local = "0" + wa[2:] if wa.startswith("62") else wa
    return "-".join([local[:4], local[4:8], local[8:]]).strip("-")


def wa_link(wa: str, message: str) -> str:
    """Tautan click-to-chat WhatsApp (gratis, tanpa API)."""
    return f"https://wa.me/{wa}?text={quote(message)}"


# ---------------------------------------------------------------------------
# Kode referensi booking
# ---------------------------------------------------------------------------
def generate_booking_reference() -> str:
    """Kode acak kriptografis 60-bit, contoh: BK-7KQ2-M9XD-4TPA."""
    chars = "".join(secrets.choice(_REF_ALPHABET) for _ in range(12))
    return f"BK-{chars[0:4]}-{chars[4:8]}-{chars[8:12]}"


def normalize_reference(raw: str | None) -> str | None:
    s = re.sub(r"[^0-9A-Za-z]", "", (raw or "")).upper()
    if s.startswith("BK"):
        s = s[2:]
    if len(s) != 12:
        return None
    ref = f"BK-{s[0:4]}-{s[4:8]}-{s[8:12]}"
    return ref if _REF_RE.match(ref) else None


# ---------------------------------------------------------------------------
# Validasi teks
# ---------------------------------------------------------------------------
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(value: str | None, field: str, *, required: bool = True,
               min_len: int = 0, max_len: int = 500) -> str | None:
    v = _CONTROL_RE.sub("", (value or "")).strip()
    v = re.sub(r"[ \t]+", " ", v)
    if not v:
        if required:
            raise ValidationError(f"{field} wajib diisi.")
        return None
    if len(v) < min_len:
        raise ValidationError(f"{field} minimal {min_len} karakter.")
    if len(v) > max_len:
        raise ValidationError(f"{field} maksimal {max_len} karakter.")
    return v


def esc(value) -> str:
    """Escape HTML untuk teks yang ditampilkan via unsafe_allow_html."""
    return html.escape("" if value is None else str(value))
