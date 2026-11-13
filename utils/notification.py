"""Sistem notifikasi.

1. Notifikasi dalam aplikasi (wajib, gratis) — disimpan di tabel `notifications`.
   * audience='admin'  → lonceng notifikasi Admin Mode.
   * audience='public' → tampil di halaman Cek Status Booking milik pemohon.
2. Integrasi tambahan opsional & gratis (aplikasi TETAP berjalan tanpa ini):
   * Email ke ketua panitia via SMTP (mis. Gmail + App Password).
   * Push notification ke HP ketua via ntfy.sh (aplikasi ntfy gratis).
   * Tautan WhatsApp click-to-chat (wa.me) untuk mengabari pemohon.
"""
from __future__ import annotations

import logging
import smtplib
import threading
import urllib.request
from email.message import EmailMessage

from config import APP_NAME, get_settings

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# In-app (dipanggil di dalam transaksi database yang sama)
# ---------------------------------------------------------------------------
def add_notification(cur, *, audience: str, kind: str, title: str, message: str,
                     booking_id=None, event_id=None) -> None:
    cur.execute(
        """insert into notifications (audience, booking_id, event_id, kind, title, message)
           values (%s, %s, %s, %s, %s, %s)""",
        (audience, booking_id, event_id, kind, title, message),
    )


# ---------------------------------------------------------------------------
# Eksternal (dipanggil SETELAH commit, di thread terpisah, tidak pernah memblokir)
# ---------------------------------------------------------------------------
def _send_email(subject: str, body: str) -> None:
    s = get_settings()
    if not s.email_enabled:
        return
    msg = EmailMessage()
    msg["Subject"] = f"[{APP_NAME}] {subject}"
    msg["From"] = s.smtp_sender or s.smtp_user
    msg["To"] = s.admin_email
    msg.set_content(body + (f"\n\nBuka aplikasi: {s.app_url}" if s.app_url else ""))
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as smtp:
        smtp.starttls()
        smtp.login(s.smtp_user, s.smtp_password)
        smtp.send_message(msg)


def _send_ntfy(title: str, body: str) -> None:
    s = get_settings()
    if not s.ntfy_enabled:
        return
    url = f"{s.ntfy_server.rstrip('/')}/{s.ntfy_topic}"
    req = urllib.request.Request(url, data=body.encode("utf-8"), method="POST")
    req.add_header("Title", title.encode("ascii", "ignore").decode() or "Notifikasi")
    req.add_header("Tags", "calendar")
    if s.app_url:
        req.add_header("Click", s.app_url)
    urllib.request.urlopen(req, timeout=8).read()


def _dispatch(title: str, body: str) -> None:
    for fn in (_send_email, _send_ntfy):
        try:
            fn(title, body)
        except Exception as exc:  # integrasi opsional tidak boleh mengganggu aplikasi
            log.warning("Notifikasi eksternal %s gagal: %s", fn.__name__, exc)


def notify_admin_external(title: str, body: str) -> None:
    s = get_settings()
    if not (s.email_enabled or s.ntfy_enabled):
        return
    threading.Thread(target=_dispatch, args=(title, body), daemon=True).start()


def external_channels_status() -> dict[str, bool]:
    s = get_settings()
    return {"Email (SMTP)": s.email_enabled, "Push HP (ntfy)": s.ntfy_enabled}
