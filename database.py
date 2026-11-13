"""Lapisan database (PostgreSQL / Supabase).

Prinsip keamanan:
* Semua operasi admin menerima `AdminContext` dan MEMVERIFIKASI ULANG sesi admin
  di database pada transaksi yang sama (`_verify_admin`). Menyembunyikan tombol di
  UI bukan satu-satunya proteksi.
* Pencegahan double booking berlapis:
  1. `pg_advisory_xact_lock` per tanggal → pengajuan/approval pada tanggal yang
     sama diproses berurutan walau dikirim bersamaan.
  2. Pengecekan bentrok jam (agenda disetujui + pengajuan pending) di dalam lock.
  3. Exclusion constraint `no_overlapping_approved_events` di tabel events sebagai
     pertahanan terakhir di level database.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import random
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

import config
from config import CATEGORIES, get_settings
from utils import notification as notif
from utils.helpers import (
    ValidationError, clean_text, fmt_date, fmt_time_range, generate_booking_reference,
    iter_months, minutes_between, normalize_reference, normalize_whatsapp, today_local,
    daterange,
)

_LOCK_NAMESPACE = 91731  # namespace advisory lock untuk tanggal booking


# ---------------------------------------------------------------------------
# Error yang aman ditampilkan ke pengguna
# ---------------------------------------------------------------------------
class DatabaseNotConfigured(RuntimeError):
    pass


class BookingError(Exception):
    """Kesalahan bisnis (pesan aman untuk pengguna)."""


class ConflictError(BookingError):
    def __init__(self, message: str, conflicts: list[dict]):
        super().__init__(message)
        self.conflicts = conflicts


class RateLimitError(BookingError):
    pass


class AuthorizationError(PermissionError):
    pass


@dataclass(frozen=True)
class AdminContext:
    token: str
    admin_label: str


# ---------------------------------------------------------------------------
# Koneksi
# ---------------------------------------------------------------------------
_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                url = get_settings().database_url
                if not url:
                    raise DatabaseNotConfigured(
                        "DATABASE_URL belum diatur di Streamlit Secrets / environment variables."
                    )
                _pool = ConnectionPool(
                    conninfo=url,
                    min_size=1,
                    max_size=int(config.get_secret("DB_POOL_MAX", 8)),
                    kwargs={
                        "row_factory": dict_row,
                        # aman untuk Supabase pooler (transaction mode tidak mendukung prepared stmt)
                        "prepare_threshold": None,
                        "connect_timeout": 10,
                    },
                    timeout=20,
                    max_idle=300,
                    check=ConnectionPool.check_connection,
                    open=True,
                )
    return _pool


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def tx():
    """Satu transaksi database. Commit otomatis bila tanpa error, rollback bila error."""
    with get_pool().connection() as conn:
        with conn.transaction():
            with conn.cursor() as cur:
                yield cur


def health_check() -> tuple[bool, str]:
    try:
        with tx() as cur:
            cur.execute("select count(*) as n from calendar_settings")
            if cur.fetchone()["n"] == 0:
                return False, "Tabel calendar_settings kosong. Jalankan ulang sql/schema.sql."
        return True, "OK"
    except DatabaseNotConfigured as e:
        return False, str(e)
    except psycopg.errors.UndefinedTable:
        return False, "Tabel database belum dibuat. Jalankan sql/schema.sql di Supabase SQL Editor."
    except Exception as e:  # noqa: BLE001
        return False, f"Tidak dapat terhubung ke database: {type(e).__name__}"


# ---------------------------------------------------------------------------
# Utilitas internal
# ---------------------------------------------------------------------------
def _json(obj) -> Jsonb:
    return Jsonb(obj, dumps=lambda o: json.dumps(o, default=str, ensure_ascii=False))


def _audit(cur, *, actor_type: str, actor_label: str, action: str, entity_type: str,
           entity_id=None, details: dict | None = None, client_hash: str | None = None) -> None:
    cur.execute(
        """insert into audit_logs (actor_type, actor_label, action, entity_type, entity_id, details, client_hash)
           values (%s, %s, %s, %s, %s, %s, %s)""",
        (actor_type, actor_label, action, entity_type,
         str(entity_id) if entity_id else None, _json(details or {}), client_hash),
    )


def _lock_dates(cur, *dates: date) -> None:
    for d in sorted({d for d in dates if d}):  # urutan tetap → bebas deadlock
        cur.execute("select pg_advisory_xact_lock(%s, %s)", (_LOCK_NAMESPACE, d.toordinal()))


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _verify_admin(cur, ctx: AdminContext | None) -> str:
    """Verifikasi sesi admin di database. Mengembalikan label admin."""
    if not isinstance(ctx, AdminContext) or not ctx.token:
        raise AuthorizationError("Aksi ini hanya untuk Ketua Panitia (Admin Mode).")
    cur.execute(
        """update admin_sessions set last_activity = now()
            where token_hash = %s and not revoked and expires_at > now()
              and last_activity > now() - make_interval(mins => %s)
        returning admin_label""",
        (_token_hash(ctx.token), get_settings().session_timeout_minutes),
    )
    row = cur.fetchone()
    if not row:
        raise AuthorizationError("Sesi Admin Mode sudah berakhir. Silakan masuk kembali.")
    return row["admin_label"]


def _get_calendar_settings(cur) -> dict:
    cur.execute("select * from calendar_settings where setting_id = 1")
    row = cur.fetchone()
    if not row:
        raise BookingError("Pengaturan kalender belum ada. Jalankan sql/schema.sql.")
    return row


def _get_date_info(cur, d: date) -> dict | None:
    cur.execute("select * from calendar_dates where calendar_date = %s", (d,))
    return cur.fetchone()


def _find_conflicts(cur, d: date, start: time, end: time, *, exclusive: bool = False,
                    exclude_event_id=None, exclude_booking_id=None,
                    include_pending: bool = True) -> list[dict]:
    """Cari agenda/pengajuan yang bentrok. Bila tanggal eksklusif, semua agenda di tanggal itu bentrok."""
    time_clause = "" if exclusive else "and start_time < %(end)s and end_time > %(start)s"
    params = {"d": d, "start": start, "end": end,
              "ex_ev": str(exclude_event_id) if exclude_event_id else None,
              "ex_bk": str(exclude_booking_id) if exclude_booking_id else None}
    cur.execute(
        f"""select 'event' as kind, event_id::text as id, event_name, start_time, end_time,
                   'approved' as status, person_in_charge
              from events
             where event_date = %(d)s and status = 'approved' {time_clause}
               and (%(ex_ev)s::uuid is null or event_id <> %(ex_ev)s::uuid)
               and (%(ex_bk)s::uuid is null or booking_id is null or booking_id <> %(ex_bk)s::uuid)
             order by start_time""",
        params,
    )
    rows = list(cur.fetchall())
    if include_pending:
        cur.execute(
            f"""select 'booking' as kind, booking_id::text as id, event_name, start_time, end_time,
                       'pending' as status, person_in_charge
                  from booking_requests
                 where requested_date = %(d)s and approval_status = 'pending' {time_clause}
                   and (%(ex_bk)s::uuid is null or booking_id <> %(ex_bk)s::uuid)
                 order by start_time""",
            params,
        )
        rows += list(cur.fetchall())
    return rows


def _conflict_message(conflicts: list[dict], exclusive: bool) -> str:
    parts = [f"• {c['event_name']} ({c['start_time']:%H:%M}–{c['end_time']:%H:%M}, "
             f"{'disetujui' if c['status'] == 'approved' else 'menunggu persetujuan'})"
             for c in conflicts if c.get("kind") != "locked"]
    head = ("Tanggal ini ditetapkan EKSKLUSIF (hanya untuk satu agenda) dan sudah terisi:"
            if exclusive else "Jadwal bentrok dengan agenda lain pada jam yang sama:")
    return head + ("\n" + "\n".join(parts) if parts else "")


# ---------------------------------------------------------------------------
# Validasi payload booking / event
# ---------------------------------------------------------------------------
def _validate_times(start: time, end: time) -> None:
    if not isinstance(start, time) or not isinstance(end, time):
        raise ValidationError("Waktu mulai dan selesai wajib diisi.")
    if end <= start:
        raise ValidationError("Waktu selesai harus setelah waktu mulai.")
    dur = minutes_between(start, end)
    if dur < config.MIN_BOOKING_MINUTES:
        raise ValidationError(f"Durasi kegiatan minimal {config.MIN_BOOKING_MINUTES} menit.")
    if dur > config.MAX_BOOKING_HOURS * 60:
        raise ValidationError(f"Durasi kegiatan maksimal {config.MAX_BOOKING_HOURS} jam.")


def validate_booking_payload(p: dict) -> dict:
    out = {
        "requester_name": clean_text(p.get("requester_name"), "Nama pemohon", min_len=2, max_len=100),
        "requester_whatsapp": normalize_whatsapp(p.get("requester_whatsapp")),
        "event_name": clean_text(p.get("event_name"), "Nama kegiatan", min_len=3, max_len=150),
        "category": p.get("category"),
        "requested_date": p.get("requested_date"),
        "start_time": p.get("start_time"),
        "end_time": p.get("end_time"),
        "location": clean_text(p.get("location"), "Lokasi", required=False, max_len=150),
        "description": clean_text(p.get("description"), "Deskripsi kegiatan", min_len=5, max_len=2000),
        "notes": clean_text(p.get("notes"), "Catatan tambahan", required=False, max_len=1000),
    }
    pic = clean_text(p.get("person_in_charge"), "Penanggung jawab", required=False, min_len=2, max_len=100)
    out["person_in_charge"] = pic or out["requester_name"]
    if out["category"] not in CATEGORIES:
        raise ValidationError("Kategori kegiatan tidak valid.")
    if not isinstance(out["requested_date"], date):
        raise ValidationError("Tanggal kegiatan wajib diisi.")
    _validate_times(out["start_time"], out["end_time"])
    part = p.get("participants")
    if part in (None, "", 0):
        out["participants"] = None
    else:
        try:
            part = int(part)
        except (TypeError, ValueError):
            raise ValidationError("Jumlah peserta harus berupa angka.")
        if not 1 <= part <= 100000:
            raise ValidationError("Jumlah peserta harus antara 1 dan 100.000.")
        out["participants"] = part
    return out


def validate_event_payload(p: dict) -> dict:
    out = {
        "event_name": clean_text(p.get("event_name"), "Nama kegiatan", min_len=3, max_len=150),
        "category": p.get("category"),
        "event_date": p.get("event_date"),
        "start_time": p.get("start_time"),
        "end_time": p.get("end_time"),
        "person_in_charge": clean_text(p.get("person_in_charge"), "Penanggung jawab", min_len=2, max_len=100),
        "location": clean_text(p.get("location"), "Lokasi", required=False, max_len=150),
        "description": clean_text(p.get("description"), "Deskripsi", required=False, max_len=2000),
    }
    wa = p.get("pic_whatsapp")
    out["pic_whatsapp"] = normalize_whatsapp(wa) if (wa or "").strip() else None
    if out["category"] not in CATEGORIES:
        raise ValidationError("Kategori kegiatan tidak valid.")
    if not isinstance(out["event_date"], date):
        raise ValidationError("Tanggal kegiatan wajib diisi.")
    _validate_times(out["start_time"], out["end_time"])
    part = p.get("participants")
    out["participants"] = int(part) if part not in (None, "", 0) else None
    return out


def _check_in_period(settings: dict, d: date) -> None:
    if not settings["start_date"] <= d <= settings["end_date"]:
        raise BookingError(
            f"Tanggal di luar periode kalender ({fmt_date(settings['start_date'], False)} – "
            f"{fmt_date(settings['end_date'], False)})."
        )


def _check_day_hours(settings: dict, start: time, end: time) -> None:
    if start < settings["day_start_time"] or end > settings["day_end_time"]:
        raise BookingError(
            f"Jam kegiatan harus di antara {settings['day_start_time']:%H:%M} dan "
            f"{settings['day_end_time']:%H:%M} WIB."
        )


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------
def _count_attempts(cur, action: str, minutes: int, key_hash: str | None = None,
                    success: bool | None = None) -> int:
    q = "select count(*) as n from rate_limits where action = %s and created_at > now() - make_interval(mins => %s)"
    params: list = [action, minutes]
    if key_hash is not None:
        q += " and key_hash = %s"
        params.append(key_hash)
    if success is not None:
        q += " and success = %s"
        params.append(success)
    cur.execute(q, params)
    return cur.fetchone()["n"]


def _record_attempt(cur, action: str, key_hash: str, success: bool) -> None:
    cur.execute("insert into rate_limits (action, key_hash, success) values (%s, %s, %s)",
                (action, key_hash or "unknown", success))
    if random.random() < 0.02:  # bersih-bersih berkala
        cur.execute("delete from rate_limits where created_at < now() - interval '3 days'")


def pin_attempt_status(client_hash: str) -> tuple[bool, str | None]:
    """Cek apakah perangkat ini masih boleh mencoba PIN."""
    with tx() as cur:
        w = config.PIN_WINDOW_MINUTES
        if _count_attempts(cur, "admin_pin", w, client_hash, success=False) >= config.PIN_MAX_FAILS_PER_CLIENT:
            return False, f"Terlalu banyak percobaan PIN yang salah. Coba lagi dalam {w} menit."
        if _count_attempts(cur, "admin_pin", w, success=False) >= config.PIN_MAX_FAILS_GLOBAL:
            return False, f"Admin Mode dikunci sementara karena banyak percobaan gagal. Coba lagi dalam {w} menit."
    return True, None


def record_pin_attempt(client_hash: str, success: bool) -> None:
    with tx() as cur:
        _record_attempt(cur, "admin_pin", client_hash, success)
        if not success:
            _audit(cur, actor_type="public", actor_label="anonim", action="admin_pin_failed",
                   entity_type="admin_session", client_hash=client_hash)


# ---------------------------------------------------------------------------
# Sesi admin
# ---------------------------------------------------------------------------
def create_admin_session(token: str, admin_label: str, client_hash: str) -> None:
    s = get_settings()
    with tx() as cur:
        cur.execute(
            """insert into admin_sessions (token_hash, admin_label, client_hash, expires_at)
               values (%s, %s, %s, now() + make_interval(hours => %s))""",
            (_token_hash(token), admin_label, client_hash, s.session_max_hours),
        )
        _record_attempt(cur, "admin_pin", client_hash, True)
        _audit(cur, actor_type="admin", actor_label=admin_label, action="admin_login",
               entity_type="admin_session", client_hash=client_hash)
        cur.execute("delete from admin_sessions where expires_at < now() - interval '7 days'")


def validate_admin_session(token: str | None) -> str | None:
    """Mengembalikan label admin bila sesi masih aktif (sekaligus memperpanjang aktivitas)."""
    if not token:
        return None
    try:
        with tx() as cur:
            return _verify_admin(cur, AdminContext(token=token, admin_label=""))
    except AuthorizationError:
        return None


def end_admin_session(token: str | None, reason: str = "logout") -> None:
    if not token:
        return
    with tx() as cur:
        cur.execute("update admin_sessions set revoked = true where token_hash = %s and not revoked "
                    "returning admin_label", (_token_hash(token),))
        row = cur.fetchone()
        if row:
            _audit(cur, actor_type="admin", actor_label=row["admin_label"], action=f"admin_{reason}",
                   entity_type="admin_session")


def admin_revoke_all_sessions(ctx: AdminContext) -> int:
    with tx() as cur:
        label = _verify_admin(cur, ctx)
        cur.execute("update admin_sessions set revoked = true where not revoked and token_hash <> %s",
                    (_token_hash(ctx.token),))
        n = cur.rowcount
        _audit(cur, actor_type="admin", actor_label=label, action="revoke_all_sessions",
               entity_type="admin_session", details={"revoked": n})
        return n


# ---------------------------------------------------------------------------
# PUBLIK — baca data
# ---------------------------------------------------------------------------
def get_calendar_settings() -> dict:
    with tx() as cur:
        return _get_calendar_settings(cur)


def get_calendar_data(start: date, end: date) -> dict:
    """Data untuk kalender publik (tanpa nomor WhatsApp)."""
    with tx() as cur:
        settings = _get_calendar_settings(cur)
        cur.execute(
            """select event_id::text as id, event_name, category, event_date, start_time, end_time,
                      person_in_charge, location, participants, description, conflict_override
                 from events where status = 'approved' and event_date between %s and %s
                order by event_date, start_time""", (start, end))
        events = list(cur.fetchall())
        cur.execute(
            """select booking_id::text as id, event_name, category, requested_date, start_time, end_time
                 from booking_requests where approval_status = 'pending' and requested_date between %s and %s
                order by requested_date, start_time""", (start, end))
        pending = list(cur.fetchall())
        cur.execute("select * from calendar_dates where calendar_date between %s and %s order by calendar_date",
                    (start, end))
        dates = list(cur.fetchall())
    return {"settings": settings, "events": events, "pending": pending, "dates": dates}


def count_pending() -> int:
    with tx() as cur:
        cur.execute("select count(*) n from booking_requests where approval_status = 'pending'")
        return cur.fetchone()["n"]


def get_day_detail(d: date) -> dict:
    with tx() as cur:
        settings = _get_calendar_settings(cur)
        info = _get_date_info(cur, d)
        cur.execute(
            """select event_id::text as id, event_name, category, start_time, end_time, person_in_charge,
                      location, participants, description
                 from events where status = 'approved' and event_date = %s order by start_time""", (d,))
        events = list(cur.fetchall())
        cur.execute(
            """select booking_id::text as id, event_name, category, start_time, end_time
                 from booking_requests where approval_status = 'pending' and requested_date = %s
                order by start_time""", (d,))
        pending = list(cur.fetchall())
    return {"settings": settings, "info": info, "events": events, "pending": pending}


def get_public_event(event_id: str) -> dict | None:
    with tx() as cur:
        cur.execute(
            """select event_id::text as id, event_name, category, event_date, start_time, end_time,
                      person_in_charge, location, participants, description, status
                 from events where event_id = %s::uuid and status = 'approved'""", (event_id,))
        return cur.fetchone()


def get_public_pending(booking_id: str) -> dict | None:
    with tx() as cur:
        cur.execute(
            """select booking_id::text as id, event_name, category, requested_date, start_time, end_time
                 from booking_requests where booking_id = %s::uuid and approval_status = 'pending'""",
            (booking_id,))
        return cur.fetchone()


def dashboard_stats(include_private: bool = False) -> dict:
    today = today_local()
    with tx() as cur:
        st_ = _get_calendar_settings(cur)
        p_start, p_end = st_["start_date"], st_["end_date"]
        cur.execute("""select count(*) n from events where status='approved' and event_date between %s and %s""",
                    (p_start, p_end))
        approved = cur.fetchone()["n"]
        cur.execute("select count(*) n from booking_requests where approval_status='pending'")
        pending = cur.fetchone()["n"]
        cur.execute("""select count(*) n from events where status='approved'
                        and date_trunc('month', event_date) = date_trunc('month', %s::date)""", (today,))
        this_month = cur.fetchone()["n"]
        cur.execute("""select distinct event_date from events where status='approved' and event_date between %s and %s""",
                    (p_start, p_end))
        busy = {r["event_date"] for r in cur.fetchall()}
        cur.execute("select calendar_date from calendar_dates where lock_status = 'locked'")
        locked = {r["calendar_date"] for r in cur.fetchall()}
        first = max(today, p_start)
        available = sum(1 for d in daterange(first, p_end) if d not in busy and d not in locked) if first <= p_end else 0

        cur.execute("""select date_trunc('month', event_date)::date m, count(*) n from events
                        where status='approved' and event_date between %s and %s group by 1""", (p_start, p_end))
        per_month_raw = {(r["m"].year, r["m"].month): r["n"] for r in cur.fetchall()}
        per_month = [{"year": y, "month": m, "count": per_month_raw.get((y, m), 0)} for y, m in iter_months(p_start, p_end)]

        cur.execute("""select category, count(*) n from events where status='approved' and event_date between %s and %s
                        group by category""", (p_start, p_end))
        cat_raw = {r["category"]: r["n"] for r in cur.fetchall()}
        per_category = [{"category": c, "count": cat_raw.get(c, 0)} for c in CATEGORIES]

        cur.execute("""select event_id::text id, event_name, category, event_date, start_time, end_time, person_in_charge, location
                         from events where status='approved' and event_date >= %s
                        order by event_date, start_time limit 8""", (today,))
        upcoming = list(cur.fetchall())

        cols = "booking_reference, requester_name, " if include_private else ""
        cur.execute(f"""select {cols} event_name, category, requested_date, start_time, end_time, approval_status, created_at
                          from booking_requests order by created_at desc limit 8""")
        latest = list(cur.fetchall())
    return {
        "total": approved + pending, "approved": approved, "pending": pending,
        "available_dates": available, "this_month": this_month,
        "per_month": per_month, "per_category": per_category,
        "upcoming": upcoming, "latest": latest, "settings": st_,
    }


# ---------------------------------------------------------------------------
# PUBLIK — pengajuan booking
# ---------------------------------------------------------------------------
def create_booking_request(payload: dict, client_hash: str) -> dict:
    data = validate_booking_payload(payload)
    d = data["requested_date"]
    with tx() as cur:
        settings = _get_calendar_settings(cur)
        if not settings["booking_open"]:
            raise BookingError("Pengajuan booking sedang ditutup sementara oleh Ketua Panitia.")
        _check_in_period(settings, d)
        if d < today_local():
            raise BookingError("Tanggal kegiatan sudah lewat.")
        _check_day_hours(settings, data["start_time"], data["end_time"])

        # Anti-spam
        cur.execute("""select count(*) n from booking_requests
                        where client_hash = %s and created_at > now() - interval '1 hour'""", (client_hash,))
        if cur.fetchone()["n"] >= config.BOOKING_MAX_PER_CLIENT_HOUR:
            raise RateLimitError("Terlalu banyak pengajuan dari perangkat ini. Silakan coba lagi 1 jam lagi.")
        cur.execute("select count(*) n from booking_requests where created_at > now() - interval '1 hour'")
        if cur.fetchone()["n"] >= config.BOOKING_MAX_GLOBAL_HOUR:
            raise RateLimitError("Sistem sedang menerima banyak pengajuan. Silakan coba beberapa saat lagi.")
        cur.execute("""select count(*) n from booking_requests
                        where requester_whatsapp = %s and approval_status = 'pending'""",
                    (data["requester_whatsapp"],))
        if cur.fetchone()["n"] >= settings["max_pending_per_whatsapp"]:
            raise RateLimitError(
                f"Nomor WhatsApp ini sudah memiliki {settings['max_pending_per_whatsapp']} pengajuan yang "
                "menunggu persetujuan. Tunggu hingga diproses atau batalkan salah satunya.")

        # Kunci tanggal → cek bentrok → simpan (atomik)
        _lock_dates(cur, d)
        info = _get_date_info(cur, d) or {}
        if info.get("lock_status") == "locked":
            raise BookingError("Tanggal ini dikunci oleh Ketua Panitia dan tidak dapat dibooking.")
        exclusive = info.get("lock_status") == "exclusive"
        conflicts = _find_conflicts(cur, d, data["start_time"], data["end_time"], exclusive=exclusive)
        if conflicts:
            raise ConflictError(_conflict_message(conflicts, exclusive), conflicts)

        for _ in range(5):
            ref = generate_booking_reference()
            cur.execute("select 1 from booking_requests where booking_reference = %s", (ref,))
            if not cur.fetchone():
                break
        cur.execute(
            """insert into booking_requests (booking_reference, requester_name, requester_whatsapp, person_in_charge,
                       event_name, category, requested_date, start_time, end_time, location, participants,
                       description, notes, client_hash)
               values (%(ref)s, %(requester_name)s, %(requester_whatsapp)s, %(person_in_charge)s, %(event_name)s,
                       %(category)s, %(requested_date)s, %(start_time)s, %(end_time)s, %(location)s,
                       %(participants)s, %(description)s, %(notes)s, %(client_hash)s)
               returning booking_id""",
            {**data, "ref": ref, "client_hash": client_hash},
        )
        booking_id = cur.fetchone()["booking_id"]
        when = f"{fmt_date(d)} {fmt_time_range(data['start_time'], data['end_time'])}"
        notif.add_notification(
            cur, audience="admin", kind="new_booking", booking_id=booking_id,
            title="Pengajuan booking baru",
            message=f"{data['event_name']} — {when} oleh {data['requester_name']} ({ref})")
        notif.add_notification(
            cur, audience="public", kind="submitted", booking_id=booking_id,
            title="Pengajuan diterima",
            message="Pengajuan Anda sudah diterima dan menunggu persetujuan Ketua Panitia.")
        _audit(cur, actor_type="public", actor_label=data["requester_name"], action="booking_created",
               entity_type="booking", entity_id=booking_id, client_hash=client_hash,
               details={"reference": ref, "event_name": data["event_name"], "date": d,
                        "start": data["start_time"], "end": data["end_time"]})
    notif.notify_admin_external("Pengajuan booking baru",
                                f"{data['event_name']}\n{when}\nPemohon: {data['requester_name']}\nKode: {ref}")
    return {"booking_id": str(booking_id), "reference": ref, **data}


def lookup_booking(reference_raw: str, client_hash: str) -> dict | None:
    """Cek status booking via kode referensi (dengan pembatasan percobaan)."""
    with tx() as cur:
        if _count_attempts(cur, "lookup", config.LOOKUP_WINDOW_MINUTES, client_hash, success=False) \
                >= config.LOOKUP_MAX_FAILS_PER_CLIENT:
            raise RateLimitError("Terlalu banyak kode yang salah. Coba lagi dalam beberapa menit.")
        ref = normalize_reference(reference_raw)
        row = None
        if ref:
            cur.execute(
                """select booking_id::text as booking_id, booking_reference, requester_name, requester_whatsapp,
                          person_in_charge, event_name, category, requested_date, start_time, end_time, location,
                          participants, description, notes, approval_status, rejection_reason, admin_note,
                          reviewed_at, created_at, updated_at
                     from booking_requests where booking_reference = %s""", (ref,))
            row = cur.fetchone()
        if not row:
            _record_attempt(cur, "lookup", client_hash, False)
            return None
        cur.execute("""select title, message, kind, created_at from notifications
                        where audience = 'public' and booking_id = %s::uuid order by created_at desc""",
                    (row["booking_id"],))
        row["notifications"] = list(cur.fetchall())
        return row


def cancel_booking_by_reference(reference_raw: str, whatsapp_raw: str, client_hash: str,
                                reason: str | None = None) -> dict:
    ref = normalize_reference(reference_raw)
    if not ref:
        raise ValidationError("Format kode referensi tidak valid.")
    wa = normalize_whatsapp(whatsapp_raw)
    mismatch = False
    with tx() as cur:
        if _count_attempts(cur, "cancel", config.CANCEL_WINDOW_MINUTES, client_hash, success=False) \
                >= config.CANCEL_MAX_FAILS_PER_CLIENT:
            raise RateLimitError("Terlalu banyak percobaan pembatalan yang gagal. Coba lagi nanti.")
        cur.execute("select * from booking_requests where booking_reference = %s for update", (ref,))
        b = cur.fetchone()
        if not b or not hmac.compare_digest(b["requester_whatsapp"], wa):
            _record_attempt(cur, "cancel", client_hash, False)  # harus ter-commit → raise di luar transaksi
            mismatch = True
        elif b["approval_status"] != "pending":
            raise BookingError("Hanya pengajuan berstatus 'Menunggu Persetujuan' yang dapat dibatalkan sendiri. "
                               "Hubungi Ketua Panitia untuk perubahan agenda yang sudah disetujui.")
        else:
            _do_requester_cancel(cur, b, ref, reason, client_hash)
    if mismatch:
        raise BookingError("Kode referensi atau nomor WhatsApp tidak cocok.")
    return {"reference": ref, "event_name": b["event_name"]}


def _do_requester_cancel(cur, b: dict, ref: str, reason: str | None, client_hash: str) -> None:
    reason = clean_text(reason, "Alasan", required=False, max_len=300)
    cur.execute("""update booking_requests set approval_status = 'cancelled', updated_at = now(),
                          rejection_reason = %s where booking_id = %s""",
                (f"Dibatalkan oleh pemohon{': ' + reason if reason else ''}", b["booking_id"]))
    notif.add_notification(cur, audience="admin", kind="booking_cancelled", booking_id=b["booking_id"],
                           title="Pengajuan dibatalkan pemohon",
                           message=f"{b['event_name']} ({ref}) dibatalkan oleh {b['requester_name']}.")
    notif.add_notification(cur, audience="public", kind="cancelled", booking_id=b["booking_id"],
                           title="Pengajuan dibatalkan", message="Anda telah membatalkan pengajuan ini.")
    _audit(cur, actor_type="public", actor_label=b["requester_name"], action="booking_cancelled_by_requester",
           entity_type="booking", entity_id=b["booking_id"], client_hash=client_hash,
           details={"reference": ref, "reason": reason})
    _record_attempt(cur, "cancel", client_hash, True)


# ---------------------------------------------------------------------------
# ADMIN — pengajuan
# ---------------------------------------------------------------------------
def admin_list_bookings(ctx: AdminContext, *, status: str | None = None, search: str | None = None,
                        category: str | None = None, date_from: date | None = None,
                        date_to: date | None = None, limit: int = 500) -> list[dict]:
    with tx() as cur:
        _verify_admin(cur, ctx)
        q = ["select *, booking_id::text as id from booking_requests where true"]
        params: list = []
        if status:
            q.append("and approval_status = %s"); params.append(status)
        if category:
            q.append("and category = %s"); params.append(category)
        if date_from:
            q.append("and requested_date >= %s"); params.append(date_from)
        if date_to:
            q.append("and requested_date <= %s"); params.append(date_to)
        if search:
            q.append("""and (event_name ilike %s or requester_name ilike %s or person_in_charge ilike %s
                         or booking_reference ilike %s or requester_whatsapp ilike %s)""")
            like = f"%{search.strip()}%"
            params += [like] * 5
        q.append("order by (approval_status = 'pending') desc, requested_date, start_time limit %s")
        params.append(limit)
        cur.execute(" ".join(q), params)
        return list(cur.fetchall())


def admin_preview_conflicts(ctx: AdminContext, d: date, start: time, end: time, *,
                            exclude_event_id=None, exclude_booking_id=None) -> dict:
    with tx() as cur:
        _verify_admin(cur, ctx)
        info = _get_date_info(cur, d) or {}
        exclusive = info.get("lock_status") == "exclusive"
        conflicts = _find_conflicts(cur, d, start, end, exclusive=exclusive, exclude_event_id=exclude_event_id,
                                    exclude_booking_id=exclude_booking_id)
        return {"conflicts": conflicts, "lock_status": info.get("lock_status", "open"),
                "holiday_name": info.get("holiday_name")}


def _blocking_conflicts(cur, d, start, end, *, exclude_event_id=None, exclude_booking_id=None):
    """Konflik yang memblokir aksi admin (agenda disetujui, tanggal dikunci/eksklusif)."""
    info = _get_date_info(cur, d) or {}
    exclusive = info.get("lock_status") == "exclusive"
    blocking = _find_conflicts(cur, d, start, end, exclusive=exclusive, exclude_event_id=exclude_event_id,
                               exclude_booking_id=exclude_booking_id, include_pending=False)
    if info.get("lock_status") == "locked":
        blocking = [{"kind": "locked", "id": None, "event_name": "Tanggal dikunci", "start_time": time(0),
                     "end_time": time(23, 59), "status": "locked", "person_in_charge": "-"}] + blocking
    warnings = [c for c in _find_conflicts(cur, d, start, end, exclusive=exclusive,
                                           exclude_booking_id=exclude_booking_id)
                if c["status"] == "pending"]
    return blocking, warnings, exclusive


def _raise_admin_conflict(blocking, exclusive):
    locked = any(c["kind"] == "locked" for c in blocking)
    msg = _conflict_message(blocking, exclusive)
    if locked:
        msg = "Tanggal ini berstatus DIKUNCI. " + msg
    raise ConflictError(msg + "\nCentang 'Override konflik' bila tetap ingin melanjutkan.", blocking)


def admin_approve_booking(ctx: AdminContext, booking_id: str, *, event_date: date | None = None,
                          start_time: time | None = None, end_time: time | None = None,
                          admin_note: str | None = None, override: bool = False) -> dict:
    admin_note = clean_text(admin_note, "Catatan admin", required=False, max_len=1000)
    with tx() as cur:
        label = _verify_admin(cur, ctx)
        cur.execute("select * from booking_requests where booking_id = %s::uuid for update", (booking_id,))
        b = cur.fetchone()
        if not b:
            raise BookingError("Pengajuan tidak ditemukan.")
        if b["approval_status"] != "pending":
            raise BookingError(f"Pengajuan ini sudah berstatus {config.BOOKING_STATUS_LABEL[b['approval_status']]}.")
        d = event_date or b["requested_date"]
        s, e = start_time or b["start_time"], end_time or b["end_time"]
        _validate_times(s, e)
        settings = _get_calendar_settings(cur)
        _check_in_period(settings, d)
        _lock_dates(cur, d, b["requested_date"])
        blocking, warnings, exclusive = _blocking_conflicts(cur, d, s, e, exclude_booking_id=booking_id)
        if blocking and not override:
            _raise_admin_conflict(blocking, exclusive)
        changed = (d, s, e) != (b["requested_date"], b["start_time"], b["end_time"])
        try:
            cur.execute("savepoint ins_event")
            cur.execute(
                """insert into events (booking_id, event_name, category, event_date, start_time, end_time,
                          person_in_charge, pic_whatsapp, location, participants, description, status,
                          conflict_override, created_by, approved_by)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'approved', %s, %s, %s)
                   returning event_id""",
                (b["booking_id"], b["event_name"], b["category"], d, s, e, b["person_in_charge"],
                 b["requester_whatsapp"], b["location"], b["participants"], b["description"],
                 bool(blocking and override), f"Publik: {b['requester_name']}", label))
        except psycopg.errors.ExclusionViolation:
            cur.execute("rollback to savepoint ins_event")
            raise ConflictError("Jadwal bentrok dengan agenda yang baru saja disetujui. Muat ulang halaman.", [])
        event_id = cur.fetchone()["event_id"]
        cur.execute(
            """update booking_requests set approval_status = 'approved', requested_date = %s, start_time = %s,
                      end_time = %s, admin_note = %s, reviewed_by = %s, reviewed_at = now(), updated_at = now()
                where booking_id = %s""",
            (d, s, e, admin_note, label, b["booking_id"]))
        when = f"{fmt_date(d)} {fmt_time_range(s, e)}"
        msg = f"Pengajuan '{b['event_name']}' DISETUJUI untuk {when}."
        if changed:
            msg += (f" Jadwal disesuaikan oleh Ketua Panitia (semula {fmt_date(b['requested_date'])} "
                    f"{fmt_time_range(b['start_time'], b['end_time'])}).")
        if admin_note:
            msg += f" Catatan: {admin_note}"
        notif.add_notification(cur, audience="public", kind="approved", booking_id=b["booking_id"],
                               event_id=event_id, title="Booking disetujui", message=msg)
        _audit(cur, actor_type="admin", actor_label=label, action="booking_approved", entity_type="booking",
               entity_id=b["booking_id"],
               details={"reference": b["booking_reference"], "event_id": event_id, "date": d, "start": s, "end": e,
                        "schedule_changed": changed, "override": bool(blocking and override),
                        "conflicts": [c["event_name"] for c in blocking]})
    return {"event_id": str(event_id), "message": msg, "whatsapp": b["requester_whatsapp"],
            "requester_name": b["requester_name"], "reference": b["booking_reference"],
            "pending_warnings": warnings}


def admin_reject_booking(ctx: AdminContext, booking_id: str, reason: str, admin_note: str | None = None) -> dict:
    reason = clean_text(reason, "Alasan penolakan", min_len=3, max_len=500)
    admin_note = clean_text(admin_note, "Catatan admin", required=False, max_len=1000)
    with tx() as cur:
        label = _verify_admin(cur, ctx)
        cur.execute("select * from booking_requests where booking_id = %s::uuid for update", (booking_id,))
        b = cur.fetchone()
        if not b:
            raise BookingError("Pengajuan tidak ditemukan.")
        if b["approval_status"] != "pending":
            raise BookingError(f"Pengajuan ini sudah berstatus {config.BOOKING_STATUS_LABEL[b['approval_status']]}.")
        cur.execute("""update booking_requests set approval_status = 'rejected', rejection_reason = %s,
                              admin_note = %s, reviewed_by = %s, reviewed_at = now(), updated_at = now()
                        where booking_id = %s""", (reason, admin_note, label, b["booking_id"]))
        msg = f"Pengajuan '{b['event_name']}' DITOLAK. Alasan: {reason}"
        if admin_note:
            msg += f" Catatan: {admin_note}"
        notif.add_notification(cur, audience="public", kind="rejected", booking_id=b["booking_id"],
                               title="Booking ditolak", message=msg)
        _audit(cur, actor_type="admin", actor_label=label, action="booking_rejected", entity_type="booking",
               entity_id=b["booking_id"], details={"reference": b["booking_reference"], "reason": reason})
    return {"message": msg, "whatsapp": b["requester_whatsapp"], "requester_name": b["requester_name"],
            "reference": b["booking_reference"]}


# ---------------------------------------------------------------------------
# ADMIN — agenda
# ---------------------------------------------------------------------------
def admin_list_events(ctx: AdminContext, *, status: str | None = None, category: str | None = None,
                      pic: str | None = None, search: str | None = None, date_from: date | None = None,
                      date_to: date | None = None) -> list[dict]:
    with tx() as cur:
        _verify_admin(cur, ctx)
        q = ["""select e.*, e.event_id::text as id, b.booking_reference
                  from events e left join booking_requests b on b.booking_id = e.booking_id where true"""]
        params: list = []
        if status:
            q.append("and e.status = %s"); params.append(status)
        if category:
            q.append("and e.category = %s"); params.append(category)
        if pic:
            q.append("and e.person_in_charge ilike %s"); params.append(f"%{pic.strip()}%")
        if date_from:
            q.append("and e.event_date >= %s"); params.append(date_from)
        if date_to:
            q.append("and e.event_date <= %s"); params.append(date_to)
        if search:
            q.append("and (e.event_name ilike %s or e.description ilike %s or e.location ilike %s)")
            params += [f"%{search.strip()}%"] * 3
        q.append("order by e.event_date, e.start_time")
        cur.execute(" ".join(q), params)
        return list(cur.fetchall())


def admin_get_event(ctx: AdminContext, event_id: str) -> dict | None:
    with tx() as cur:
        _verify_admin(cur, ctx)
        cur.execute("""select e.*, e.event_id::text as id, b.booking_reference, b.requester_name
                         from events e left join booking_requests b on b.booking_id = e.booking_id
                        where e.event_id = %s::uuid""", (event_id,))
        return cur.fetchone()


def admin_create_event(ctx: AdminContext, payload: dict, override: bool = False) -> dict:
    data = validate_event_payload(payload)
    d = data["event_date"]
    with tx() as cur:
        label = _verify_admin(cur, ctx)
        _check_in_period(_get_calendar_settings(cur), d)
        _lock_dates(cur, d)
        blocking, warnings, exclusive = _blocking_conflicts(cur, d, data["start_time"], data["end_time"])
        if blocking and not override:
            _raise_admin_conflict(blocking, exclusive)
        try:
            cur.execute("savepoint ins_event")
            cur.execute(
                """insert into events (event_name, category, event_date, start_time, end_time, person_in_charge,
                          pic_whatsapp, location, participants, description, status, conflict_override,
                          created_by, approved_by)
                   values (%(event_name)s, %(category)s, %(event_date)s, %(start_time)s, %(end_time)s,
                           %(person_in_charge)s, %(pic_whatsapp)s, %(location)s, %(participants)s, %(description)s,
                           'approved', %(ov)s, %(label)s, %(label)s) returning event_id""",
                {**data, "ov": bool(blocking and override), "label": label})
        except psycopg.errors.ExclusionViolation:
            cur.execute("rollback to savepoint ins_event")
            raise ConflictError("Jadwal bentrok dengan agenda lain yang baru saja disimpan.", [])
        event_id = cur.fetchone()["event_id"]
        _audit(cur, actor_type="admin", actor_label=label, action="event_created", entity_type="event",
               entity_id=event_id, details={**data, "override": bool(blocking and override)})
    return {"event_id": str(event_id), "pending_warnings": warnings}


def admin_update_event(ctx: AdminContext, event_id: str, payload: dict, override: bool = False) -> dict:
    data = validate_event_payload(payload)
    with tx() as cur:
        label = _verify_admin(cur, ctx)
        cur.execute("select * from events where event_id = %s::uuid for update", (event_id,))
        old = cur.fetchone()
        if not old:
            raise BookingError("Agenda tidak ditemukan.")
        if old["status"] != "approved":
            raise BookingError("Agenda yang sudah dibatalkan tidak dapat diedit. Buat agenda baru bila perlu.")
        d = data["event_date"]
        _check_in_period(_get_calendar_settings(cur), d)
        _lock_dates(cur, d, old["event_date"])
        blocking, warnings, exclusive = _blocking_conflicts(
            cur, d, data["start_time"], data["end_time"], exclude_event_id=event_id,
            exclude_booking_id=old["booking_id"])
        if blocking and not override:
            _raise_admin_conflict(blocking, exclusive)
        try:
            cur.execute("savepoint upd_event")
            cur.execute(
                """update events set event_name=%(event_name)s, category=%(category)s, event_date=%(event_date)s,
                          start_time=%(start_time)s, end_time=%(end_time)s, person_in_charge=%(person_in_charge)s,
                          pic_whatsapp=%(pic_whatsapp)s, location=%(location)s, participants=%(participants)s,
                          description=%(description)s, conflict_override=%(ov)s, updated_at=now()
                    where event_id = %(id)s::uuid""",
                {**data, "ov": bool(blocking and override), "id": event_id})
        except psycopg.errors.ExclusionViolation:
            cur.execute("rollback to savepoint upd_event")
            raise ConflictError("Jadwal bentrok dengan agenda lain yang baru saja disimpan.", [])
        schedule_changed = (d, data["start_time"], data["end_time"]) != (old["event_date"], old["start_time"], old["end_time"])
        msg = None
        if old["booking_id"]:
            cur.execute("""update booking_requests set requested_date=%s, start_time=%s, end_time=%s,
                                  event_name=%s, updated_at=now() where booking_id=%s""",
                        (d, data["start_time"], data["end_time"], data["event_name"], old["booking_id"]))
            if schedule_changed:
                msg = (f"Jadwal '{data['event_name']}' DIUBAH menjadi {fmt_date(d)} "
                       f"{fmt_time_range(data['start_time'], data['end_time'])} (semula {fmt_date(old['event_date'])} "
                       f"{fmt_time_range(old['start_time'], old['end_time'])}).")
                notif.add_notification(cur, audience="public", kind="rescheduled", booking_id=old["booking_id"],
                                       event_id=event_id, title="Jadwal diubah", message=msg)
        before = {k: old[k] for k in ("event_name", "category", "event_date", "start_time", "end_time",
                                      "person_in_charge", "location")}
        _audit(cur, actor_type="admin", actor_label=label,
               action="event_rescheduled" if schedule_changed else "event_updated", entity_type="event",
               entity_id=event_id, details={"before": before, "after": data,
                                            "override": bool(blocking and override)})
    return {"message": msg, "whatsapp": old["pic_whatsapp"], "schedule_changed": schedule_changed,
            "pending_warnings": warnings}


def admin_cancel_event(ctx: AdminContext, event_id: str, reason: str) -> dict:
    reason = clean_text(reason, "Alasan pembatalan", min_len=3, max_len=500)
    with tx() as cur:
        label = _verify_admin(cur, ctx)
        cur.execute("select * from events where event_id = %s::uuid for update", (event_id,))
        ev = cur.fetchone()
        if not ev:
            raise BookingError("Agenda tidak ditemukan.")
        if ev["status"] == "cancelled":
            raise BookingError("Agenda sudah dibatalkan.")
        cur.execute("""update events set status='cancelled', cancel_reason=%s, updated_at=now()
                        where event_id=%s""", (reason, ev["event_id"]))
        msg = (f"Agenda '{ev['event_name']}' pada {fmt_date(ev['event_date'])} "
               f"{fmt_time_range(ev['start_time'], ev['end_time'])} DIBATALKAN. Alasan: {reason}")
        if ev["booking_id"]:
            cur.execute("""update booking_requests set approval_status='cancelled', rejection_reason=%s,
                                  reviewed_by=%s, updated_at=now() where booking_id=%s""",
                        (f"Dibatalkan Ketua Panitia: {reason}", label, ev["booking_id"]))
            notif.add_notification(cur, audience="public", kind="cancelled", booking_id=ev["booking_id"],
                                   event_id=ev["event_id"], title="Jadwal dibatalkan", message=msg)
        _audit(cur, actor_type="admin", actor_label=label, action="event_cancelled", entity_type="event",
               entity_id=ev["event_id"], details={"event_name": ev["event_name"], "date": ev["event_date"],
                                                  "reason": reason})
    return {"message": msg, "whatsapp": ev["pic_whatsapp"]}


def admin_delete_event(ctx: AdminContext, event_id: str) -> None:
    with tx() as cur:
        label = _verify_admin(cur, ctx)
        cur.execute("select * from events where event_id = %s::uuid for update", (event_id,))
        ev = cur.fetchone()
        if not ev:
            raise BookingError("Agenda tidak ditemukan.")
        if ev["booking_id"]:
            cur.execute("""update booking_requests set approval_status='cancelled',
                                  rejection_reason='Agenda dihapus oleh Ketua Panitia', updated_at=now()
                            where booking_id=%s and approval_status='approved'""", (ev["booking_id"],))
            if ev["status"] == "approved":
                notif.add_notification(cur, audience="public", kind="cancelled", booking_id=ev["booking_id"],
                                       title="Jadwal dibatalkan",
                                       message=f"Agenda '{ev['event_name']}' dihapus oleh Ketua Panitia.")
        cur.execute("delete from events where event_id = %s", (ev["event_id"],))
        _audit(cur, actor_type="admin", actor_label=label, action="event_deleted", entity_type="event",
               entity_id=ev["event_id"], details={k: ev[k] for k in ("event_name", "event_date", "start_time",
                                                                     "end_time", "person_in_charge", "status")})


# ---------------------------------------------------------------------------
# ADMIN — tanggal, hari libur, pengaturan
# ---------------------------------------------------------------------------
def list_calendar_dates() -> list[dict]:
    with tx() as cur:
        cur.execute("select * from calendar_dates order by calendar_date")
        return list(cur.fetchall())


def admin_upsert_calendar_date(ctx: AdminContext, d: date, *, holiday_name: str | None,
                               holiday_type: str | None, lock_status: str = "open",
                               notes: str | None = None) -> str:
    holiday_name = clean_text(holiday_name, "Nama hari libur", required=False, max_len=150)
    notes = clean_text(notes, "Catatan", required=False, max_len=500)
    if lock_status not in config.LOCK_STATUS_LABEL:
        raise ValidationError("Status kunci tidak valid.")
    if holiday_type and holiday_type not in config.HOLIDAY_TYPE_LABEL:
        raise ValidationError("Jenis hari libur tidak valid.")
    if holiday_name and not holiday_type:
        holiday_type = "khusus"
    if not holiday_name:
        holiday_type = None
    with tx() as cur:
        label = _verify_admin(cur, ctx)
        before = _get_date_info(cur, d)
        if not holiday_name and lock_status == "open" and not notes:
            cur.execute("delete from calendar_dates where calendar_date = %s", (d,))
            action = "date_cleared"
        else:
            cur.execute(
                """insert into calendar_dates (calendar_date, holiday_name, holiday_type, lock_status, notes, updated_by)
                   values (%s, %s, %s, %s, %s, %s)
                   on conflict (calendar_date) do update set holiday_name=excluded.holiday_name,
                       holiday_type=excluded.holiday_type, lock_status=excluded.lock_status,
                       notes=excluded.notes, updated_by=excluded.updated_by, updated_at=now()""",
                (d, holiday_name, holiday_type, lock_status, notes, label))
            action = {"locked": "date_locked", "exclusive": "date_set_exclusive"}.get(lock_status, "date_updated")
        _audit(cur, actor_type="admin", actor_label=label, action=action, entity_type="calendar_date",
               entity_id=d.isoformat(), details={"before": before, "holiday_name": holiday_name,
                                                 "holiday_type": holiday_type, "lock_status": lock_status})
    return action


def admin_bulk_lock(ctx: AdminContext, start: date, end: date, lock_status: str, notes: str | None = None) -> int:
    if end < start:
        raise ValidationError("Tanggal akhir harus setelah tanggal awal.")
    if (end - start).days > 366:
        raise ValidationError("Rentang maksimal 1 tahun.")
    if lock_status not in config.LOCK_STATUS_LABEL:
        raise ValidationError("Status kunci tidak valid.")
    notes = clean_text(notes, "Catatan", required=False, max_len=500)
    with tx() as cur:
        label = _verify_admin(cur, ctx)
        n = 0
        for d in daterange(start, end):
            cur.execute(
                """insert into calendar_dates (calendar_date, lock_status, notes, updated_by)
                   values (%s, %s, %s, %s)
                   on conflict (calendar_date) do update set lock_status=excluded.lock_status,
                       notes=coalesce(excluded.notes, calendar_dates.notes), updated_by=excluded.updated_by,
                       updated_at=now()""", (d, lock_status, notes, label))
            n += 1
        # Bersihkan baris yang tidak lagi membawa informasi
        cur.execute("""delete from calendar_dates where lock_status='open' and holiday_name is null
                        and notes is null and calendar_date between %s and %s""", (start, end))
        _audit(cur, actor_type="admin", actor_label=label, action=f"dates_bulk_{lock_status}",
               entity_type="calendar_date", entity_id=f"{start}..{end}", details={"days": n, "notes": notes})
    return n


def admin_update_calendar_settings(ctx: AdminContext, **fields) -> None:
    allowed = {"start_date", "end_date", "day_start_time", "day_end_time", "max_pending_per_whatsapp",
               "booking_open", "announcement", "notes"}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if "announcement" in fields:
        fields["announcement"] = clean_text(fields["announcement"], "Pengumuman", required=False, max_len=500)
    if fields.get("start_date") and fields.get("end_date") and fields["end_date"] < fields["start_date"]:
        raise ValidationError("Tanggal akhir periode harus setelah tanggal mulai.")
    if fields.get("day_start_time") and fields.get("day_end_time") and fields["day_end_time"] <= fields["day_start_time"]:
        raise ValidationError("Jam tutup harus setelah jam buka.")
    if not fields:
        return
    with tx() as cur:
        label = _verify_admin(cur, ctx)
        before = _get_calendar_settings(cur)
        sets = ", ".join(f"{k} = %({k})s" for k in fields)
        cur.execute(f"update calendar_settings set {sets}, updated_at = now() where setting_id = 1", fields)
        _audit(cur, actor_type="admin", actor_label=label, action="settings_updated", entity_type="settings",
               entity_id="1", details={"before": {k: before[k] for k in fields}, "after": fields})


# ---------------------------------------------------------------------------
# ADMIN — audit log & notifikasi
# ---------------------------------------------------------------------------
def admin_list_audit(ctx: AdminContext, *, action: str | None = None, actor_type: str | None = None,
                     search: str | None = None, date_from: date | None = None, date_to: date | None = None,
                     limit: int = 1000) -> list[dict]:
    with tx() as cur:
        _verify_admin(cur, ctx)
        q = ["select * from audit_logs where true"]
        params: list = []
        if action:
            q.append("and action = %s"); params.append(action)
        if actor_type:
            q.append("and actor_type = %s"); params.append(actor_type)
        if date_from:
            q.append("and created_at >= %s"); params.append(datetime.combine(date_from, time(0), config.TZ))
        if date_to:
            q.append("and created_at < %s"); params.append(datetime.combine(date_to + timedelta(days=1), time(0), config.TZ))
        if search:
            q.append("and (actor_label ilike %s or details::text ilike %s or entity_id ilike %s)")
            params += [f"%{search.strip()}%"] * 3
        q.append("order by created_at desc limit %s"); params.append(limit)
        cur.execute(" ".join(q), params)
        return list(cur.fetchall())


def admin_audit_actions(ctx: AdminContext) -> list[str]:
    with tx() as cur:
        _verify_admin(cur, ctx)
        cur.execute("select distinct action from audit_logs order by action")
        return [r["action"] for r in cur.fetchall()]


def admin_notifications(ctx: AdminContext, limit: int = 15) -> dict:
    with tx() as cur:
        _verify_admin(cur, ctx)
        cur.execute("select count(*) n from notifications where audience='admin' and not is_read")
        unread = cur.fetchone()["n"]
        cur.execute("""select notification_id, kind, title, message, is_read, created_at from notifications
                        where audience='admin' order by created_at desc limit %s""", (limit,))
        return {"unread": unread, "items": list(cur.fetchall())}


def admin_mark_notifications_read(ctx: AdminContext) -> None:
    with tx() as cur:
        _verify_admin(cur, ctx)
        cur.execute("update notifications set is_read = true where audience='admin' and not is_read")
