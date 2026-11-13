"""Konfigurasi aplikasi & pembacaan rahasia (Streamlit Secrets / environment variables).

Tidak ada password, PIN, atau API key yang ditulis di source code. Semua nilai
sensitif dibaca dari `.streamlit/secrets.toml` (lokal), menu *Secrets* di
Streamlit Community Cloud, atau environment variables.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Identitas & tampilan
# ---------------------------------------------------------------------------
APP_NAME = "Kalender Kegiatan Panitia"
APP_TAGLINE = "Booking jadwal kegiatan secara online"
APP_ICON = "📅"
TIMEZONE_NAME = "Asia/Jakarta"
TZ = ZoneInfo(TIMEZONE_NAME)

# Palet warna (navy, putih, aksen biru)
COLORS = {
    "navy": "#0B1F3A",
    "navy_2": "#132B4F",
    "blue": "#2563EB",
    "blue_soft": "#DBEAFE",
    "bg": "#F5F7FB",
    "card": "#FFFFFF",
    "border": "#E3E8F0",
    "text": "#0F172A",
    "muted": "#64748B",
    # Status kalender
    "approved": "#1D4ED8",
    "pending": "#D97706",
    "pending_bg": "#FEF3C7",
    "available_bg": "#ECFDF5",
    "holiday_bg": "#FEE2E2",
    "holiday_text": "#B91C1C",
    "islamic_bg": "#D1FAE5",
    "islamic_text": "#047857",
    "locked_bg": "#E5E7EB",
    "exclusive_bg": "#EDE9FE",
    "rejected": "#DC2626",
    "cancelled": "#6B7280",
}

CATEGORIES = [
    "Rapat",
    "Kegiatan sosial",
    "Kegiatan keagamaan",
    "Kegiatan kepanitiaan",
    "Kegiatan umum",
    "Lainnya",
]

BOOKING_STATUS_LABEL = {
    "pending": "Menunggu Persetujuan",
    "approved": "Disetujui",
    "rejected": "Ditolak",
    "cancelled": "Dibatalkan",
}
EVENT_STATUS_LABEL = {"approved": "Disetujui", "cancelled": "Dibatalkan"}

HOLIDAY_TYPE_LABEL = {
    "libur_nasional": "Libur nasional",
    "cuti_bersama": "Cuti bersama",
    "hari_raya_islam": "Hari raya Islam",
    "khusus": "Penanda khusus",
}
LOCK_STATUS_LABEL = {
    "open": "Terbuka",
    "locked": "Dikunci (tidak bisa dibooking)",
    "exclusive": "Eksklusif (hanya 1 agenda)",
}

# ---------------------------------------------------------------------------
# Batas keamanan (rate limit & anti-spam)
# ---------------------------------------------------------------------------
PIN_MAX_FAILS_PER_CLIENT = 5        # per perangkat/IP dalam jendela waktu
PIN_MAX_FAILS_GLOBAL = 25           # total semua perangkat dalam jendela waktu
PIN_WINDOW_MINUTES = 15

BOOKING_MAX_PER_CLIENT_HOUR = 5     # pengajuan per perangkat per jam
BOOKING_MAX_GLOBAL_HOUR = 120       # pengajuan total per jam (rem darurat)

LOOKUP_MAX_FAILS_PER_CLIENT = 15    # salah kode referensi per perangkat
LOOKUP_WINDOW_MINUTES = 15

CANCEL_MAX_FAILS_PER_CLIENT = 5     # salah nomor WA saat membatalkan
CANCEL_WINDOW_MINUTES = 30

MIN_BOOKING_MINUTES = 15
MAX_BOOKING_HOURS = 16


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------
def get_secret(name: str, default=None):
    """Baca nilai dari environment variable (prioritas) lalu Streamlit Secrets."""
    if os.environ.get(name) not in (None, ""):
        return os.environ[name]
    try:
        import streamlit as st

        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return default


def _as_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    admin_pin_hash: str | None
    admin_pin_plain: str | None
    admin_access_key: str | None
    app_secret: str | None
    session_timeout_minutes: int
    session_max_hours: int
    app_url: str | None
    # Notifikasi opsional (gratis)
    admin_email: str | None
    smtp_host: str | None
    smtp_port: int
    smtp_user: str | None
    smtp_password: str | None
    smtp_sender: str | None
    ntfy_topic: str | None
    ntfy_server: str

    @property
    def admin_configured(self) -> bool:
        return bool(self.admin_pin_hash or self.admin_pin_plain)

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_password and self.admin_email)

    @property
    def ntfy_enabled(self) -> bool:
        return bool(self.ntfy_topic)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        database_url=get_secret("DATABASE_URL"),
        admin_pin_hash=get_secret("ADMIN_PIN_HASH"),
        admin_pin_plain=get_secret("ADMIN_PIN"),
        admin_access_key=get_secret("ADMIN_ACCESS_KEY") or None,
        app_secret=get_secret("APP_SECRET"),
        session_timeout_minutes=_as_int(get_secret("ADMIN_SESSION_TIMEOUT_MINUTES"), 30),
        session_max_hours=_as_int(get_secret("ADMIN_SESSION_MAX_HOURS"), 12),
        app_url=get_secret("APP_URL"),
        admin_email=get_secret("ADMIN_EMAIL"),
        smtp_host=get_secret("SMTP_HOST"),
        smtp_port=_as_int(get_secret("SMTP_PORT"), 587),
        smtp_user=get_secret("SMTP_USER"),
        smtp_password=get_secret("SMTP_PASSWORD"),
        smtp_sender=get_secret("SMTP_SENDER"),
        ntfy_topic=get_secret("NTFY_TOPIC"),
        ntfy_server=get_secret("NTFY_SERVER", "https://ntfy.sh"),
    )
