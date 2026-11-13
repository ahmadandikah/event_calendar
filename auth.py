"""Akses tanpa login + Admin Mode ber-PIN.

* Pengguna umum: tidak perlu login. Siapa pun yang memiliki link dapat melihat
  kalender dan mengajukan booking.
* Ketua Panitia: tombol "Admin Mode" → masukkan PIN (opsional + Admin Access Key).
  - PIN disimpan sebagai hash PBKDF2 di Streamlit Secrets (ADMIN_PIN_HASH).
  - Percobaan PIN dibatasi (rate limit) dan dicatat di database.
  - Setelah berhasil, server membuat token sesi acak 256-bit; hanya hash-nya yang
    disimpan di tabel admin_sessions. Token disimpan di session state server
    (tidak pernah dikirim ke URL/browser).
  - Sesi berakhir otomatis setelah tidak aktif (ADMIN_SESSION_TIMEOUT_MINUTES).
  - SETIAP operasi admin di database.py memverifikasi ulang token ini.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time as _time

import streamlit as st

import database as db
from config import get_settings

_PBKDF2_ITER = 390_000
_SESSION_KEY = "_admin_token"
_LABEL_KEY = "_admin_label"
_LAST_CHECK_KEY = "_admin_last_check"


# ---------------------------------------------------------------------------
# Hash PIN
# ---------------------------------------------------------------------------
def hash_pin(pin: str, iterations: int = _PBKDF2_ITER) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(
        iterations, base64.b64encode(salt).decode(), base64.b64encode(dk).decode())


def verify_pin_hash(pin: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, hash_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", pin.encode(), base64.b64decode(salt_b64), int(iters))
        return hmac.compare_digest(dk, base64.b64decode(hash_b64))
    except Exception:
        return False


def _check_pin(pin: str) -> bool:
    s = get_settings()
    if s.admin_pin_hash:
        return verify_pin_hash(pin, s.admin_pin_hash)
    if s.admin_pin_plain:  # fallback (kurang disarankan)
        return hmac.compare_digest(pin.encode(), str(s.admin_pin_plain).encode())
    return False


def _check_access_key(key: str | None) -> bool:
    expected = get_settings().admin_access_key
    if not expected:
        return True  # access key tidak diwajibkan
    return bool(key) and hmac.compare_digest(key.strip().encode(), str(expected).encode())


def access_key_required() -> bool:
    return bool(get_settings().admin_access_key)


# ---------------------------------------------------------------------------
# Sidik jari klien (anonim) untuk rate limit & anti-spam
# ---------------------------------------------------------------------------
def client_fingerprint() -> str:
    """HMAC dari IP + User-Agent. Tidak menyimpan IP mentah."""
    ip, ua = "", ""
    try:
        ip = st.context.ip_address or ""
    except Exception:
        pass
    try:
        headers = st.context.headers
        fwd = headers.get("X-Forwarded-For") or headers.get("x-forwarded-for") or ""
        if fwd:
            ip = fwd.split(",")[0].strip()
        ua = headers.get("User-Agent") or headers.get("user-agent") or ""
    except Exception:
        pass
    s = get_settings()
    secret = (s.app_secret or hashlib.sha256((s.database_url or "local").encode()).hexdigest()).encode()
    return hmac.new(secret, f"{ip}|{ua}".encode(), hashlib.sha256).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Admin Mode
# ---------------------------------------------------------------------------
def login_admin(pin: str, access_key: str | None = None, admin_label: str | None = None) -> tuple[bool, str]:
    s = get_settings()
    if not s.admin_configured:
        return False, "Admin PIN belum dikonfigurasi di Streamlit Secrets (ADMIN_PIN_HASH)."
    client = client_fingerprint()
    allowed, msg = db.pin_attempt_status(client)
    if not allowed:
        return False, msg
    pin = (pin or "").strip()
    ok = bool(pin) and _check_access_key(access_key) and _check_pin(pin)
    if not ok:
        _time.sleep(0.6)  # memperlambat brute force
        db.record_pin_attempt(client, False)
        return False, "PIN atau Admin Access Key salah."
    label = (admin_label or "").strip()[:60] or "Ketua Panitia"
    token = secrets.token_urlsafe(32)
    db.create_admin_session(token, label, client)
    st.session_state[_SESSION_KEY] = token
    st.session_state[_LABEL_KEY] = label
    st.session_state[_LAST_CHECK_KEY] = _time.time()
    return True, f"Admin Mode aktif. Selamat datang, {label}."


def logout_admin(reason: str = "logout") -> None:
    token = st.session_state.pop(_SESSION_KEY, None)
    st.session_state.pop(_LABEL_KEY, None)
    st.session_state.pop(_LAST_CHECK_KEY, None)
    try:
        db.end_admin_session(token, reason)
    except Exception:
        pass


def current_admin() -> db.AdminContext | None:
    """Kembalikan konteks admin bila sesi masih valid di database, selain itu None."""
    token = st.session_state.get(_SESSION_KEY)
    if not token:
        return None
    label = db.validate_admin_session(token)
    if not label:
        st.session_state.pop(_SESSION_KEY, None)
        st.session_state.pop(_LABEL_KEY, None)
        st.session_state["_flash"] = ("warning", "Sesi Admin Mode berakhir karena tidak aktif. Silakan masuk lagi.")
        return None
    return db.AdminContext(token=token, admin_label=label)


def is_admin() -> bool:
    return st.session_state.get("_ctx_admin") is not None


def get_admin() -> db.AdminContext | None:
    """Konteks admin yang sudah divalidasi pada rerun ini (diset oleh app.py)."""
    return st.session_state.get("_ctx_admin")


def require_admin() -> db.AdminContext:
    ctx = get_admin()
    if ctx is None:
        st.error("🔒 Halaman ini khusus Ketua Panitia. Aktifkan **Admin Mode** dari sidebar.")
        st.stop()
    return ctx
