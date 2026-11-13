"""Pengujian logika inti: double booking, konkurensi, akses tanpa izin, rate limit, alur approval."""
import threading
from datetime import time, timedelta

import psycopg
import pytest

import auth
import database as db
from utils.helpers import (
    ValidationError, generate_booking_reference, normalize_reference, normalize_whatsapp, today_local,
)

TODAY = today_local()
D1 = TODAY + timedelta(days=20)
D2 = TODAY + timedelta(days=21)


def payload(**kw):
    base = dict(requester_name="Budi Santoso", requester_whatsapp="0812-3456-7890", person_in_charge="",
                event_name="Rapat Seksi Acara", category="Rapat", requested_date=D1,
                start_time=time(9, 0), end_time=time(11, 0), location="Aula", participants=10,
                description="Koordinasi persiapan acara", notes=None)
    base.update(kw)
    return base


# ----------------------------------------------------------------------------- helpers
def test_pin_hash_roundtrip():
    h = auth.hash_pin("rahasia123")
    assert h.startswith("pbkdf2_sha256$")
    assert auth.verify_pin_hash("rahasia123", h)
    assert not auth.verify_pin_hash("rahasia124", h)
    assert not auth.verify_pin_hash("rahasia123", "rusak")


def test_reference_is_random_and_normalizable():
    refs = {generate_booking_reference() for _ in range(2000)}
    assert len(refs) == 2000
    r = next(iter(refs))
    assert normalize_reference(r.lower().replace("-", " ")) == r
    assert normalize_reference("BK-1234") is None
    assert normalize_reference("bk-0000-0000-0000") is None  # karakter 0 tidak dipakai


def test_whatsapp_normalization():
    assert normalize_whatsapp("0812-3456-7890") == "6281234567890"
    assert normalize_whatsapp("+62 812 3456 7890") == "6281234567890"
    assert normalize_whatsapp("81234567890") == "6281234567890"
    with pytest.raises(ValidationError):
        normalize_whatsapp("12345")


# ----------------------------------------------------------------------------- booking publik
def test_create_booking_success():
    r = db.create_booking_request(payload(), "client-a")
    assert r["reference"].startswith("BK-")
    b = db.lookup_booking(r["reference"], "client-a")
    assert b["approval_status"] == "pending"
    assert b["person_in_charge"] == "Budi Santoso"  # default = pemohon
    assert b["notifications"][0]["kind"] == "submitted"
    adm = db.get_calendar_data(D1, D1)
    assert len(adm["pending"]) == 1


def test_validation_errors():
    with pytest.raises(ValidationError):
        db.create_booking_request(payload(end_time=time(8, 0)), "c")
    with pytest.raises(ValidationError):
        db.create_booking_request(payload(category="Pesta"), "c")
    with pytest.raises(ValidationError):
        db.create_booking_request(payload(event_name="  "), "c")
    with pytest.raises(db.BookingError):
        db.create_booking_request(payload(requested_date=TODAY - timedelta(days=1)), "c")
    with pytest.raises(db.BookingError):
        db.create_booking_request(payload(requested_date=TODAY + timedelta(days=400)), "c")
    with pytest.raises(db.BookingError):
        db.create_booking_request(payload(start_time=time(5, 0), end_time=time(7, 0)), "c")


def test_double_booking_same_slot_rejected():
    db.create_booking_request(payload(), "c1")
    with pytest.raises(db.ConflictError):
        db.create_booking_request(payload(requester_whatsapp="081111111111", start_time=time(10, 0),
                                          end_time=time(12, 0)), "c2")


def test_same_day_non_overlapping_allowed():
    db.create_booking_request(payload(), "c1")
    # bersebelahan (selesai 11:00, mulai 11:00) bukan bentrok
    db.create_booking_request(payload(requester_whatsapp="081111111111", start_time=time(11, 0),
                                      end_time=time(12, 0)), "c2")
    db.create_booking_request(payload(requester_whatsapp="081111111112", start_time=time(13, 0),
                                      end_time=time(15, 0)), "c3")
    assert len(db.get_calendar_data(D1, D1)["pending"]) == 3


def test_concurrent_submissions_only_one_wins():
    results, errors = [], []
    barrier = threading.Barrier(12)

    def worker(i):
        barrier.wait()
        try:
            results.append(db.create_booking_request(
                payload(requester_whatsapp=f"0812000000{i:02d}", requester_name=f"Pemohon {i}"), f"client-{i}"))
        except db.ConflictError as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(results) == 1
    assert len(errors) == 11


def test_locked_and_exclusive_dates(admin_ctx):
    db.admin_upsert_calendar_date(admin_ctx, D1, holiday_name=None, holiday_type=None, lock_status="locked")
    with pytest.raises(db.BookingError, match="dikunci"):
        db.create_booking_request(payload(), "c1")
    db.admin_upsert_calendar_date(admin_ctx, D2, holiday_name="Hari Khusus", holiday_type="khusus",
                                  lock_status="exclusive")
    db.create_booking_request(payload(requested_date=D2), "c1")
    with pytest.raises(db.ConflictError, match="EKSKLUSIF"):
        db.create_booking_request(payload(requested_date=D2, requester_whatsapp="081111111111",
                                          start_time=time(15, 0), end_time=time(16, 0)), "c2")


def test_booking_closed(admin_ctx):
    db.admin_update_calendar_settings(admin_ctx, booking_open=False)
    with pytest.raises(db.BookingError, match="ditutup"):
        db.create_booking_request(payload(), "c1")


# ----------------------------------------------------------------------------- anti-spam
def test_rate_limit_per_client():
    for i in range(5):
        db.create_booking_request(payload(requester_whatsapp=f"08120000001{i}", start_time=time(8 + 2 * i, 0),
                                          end_time=time(9 + 2 * i, 0)), "spammer")
    with pytest.raises(db.RateLimitError):
        db.create_booking_request(payload(requested_date=D2, requester_whatsapp="081299999999"), "spammer")


def test_max_pending_per_whatsapp():
    for i in range(5):
        db.create_booking_request(payload(start_time=time(8 + 2 * i, 0), end_time=time(9 + 2 * i, 0)), f"c{i}")
    with pytest.raises(db.RateLimitError, match="WhatsApp"):
        db.create_booking_request(payload(requested_date=D2), "c-other")


def test_pin_rate_limit():
    for _ in range(5):
        assert db.pin_attempt_status("attacker")[0]
        db.record_pin_attempt("attacker", False)
    allowed, msg = db.pin_attempt_status("attacker")
    assert not allowed and "Terlalu banyak" in msg
    assert db.pin_attempt_status("someone-else")[0]


# ----------------------------------------------------------------------------- otorisasi admin
@pytest.mark.parametrize("ctx", [None, db.AdminContext(token="", admin_label="x"),
                                 db.AdminContext(token="token-palsu-tebakan", admin_label="Ketua Panitia")])
def test_admin_operations_require_valid_session(ctx):
    r = db.create_booking_request(payload(), "c1")
    bid = db.lookup_booking(r["reference"], "c1")["booking_id"]
    calls = [
        lambda: db.admin_approve_booking(ctx, bid),
        lambda: db.admin_reject_booking(ctx, bid, "tidak boleh"),
        lambda: db.admin_list_bookings(ctx),
        lambda: db.admin_create_event(ctx, {"event_name": "Hack", "category": "Rapat", "event_date": D2,
                                            "start_time": time(9), "end_time": time(10), "person_in_charge": "Xavier"}),
        lambda: db.admin_upsert_calendar_date(ctx, D2, holiday_name=None, holiday_type=None, lock_status="locked"),
        lambda: db.admin_update_calendar_settings(ctx, booking_open=False),
        lambda: db.admin_list_audit(ctx),
        lambda: db.admin_revoke_all_sessions(ctx),
    ]
    for call in calls:
        with pytest.raises(db.AuthorizationError):
            call()
    assert db.lookup_booking(r["reference"], "c1")["approval_status"] == "pending"


def test_session_timeout_and_logout(admin_ctx, database):
    assert db.validate_admin_session(admin_ctx.token) == "Ketua Uji"
    with psycopg.connect(database, autocommit=True) as conn:
        conn.execute("update admin_sessions set last_activity = now() - interval '31 minutes'")
    assert db.validate_admin_session(admin_ctx.token) is None
    with pytest.raises(db.AuthorizationError):
        db.admin_list_bookings(admin_ctx)


def test_logout_revokes(admin_ctx):
    db.end_admin_session(admin_ctx.token)
    with pytest.raises(db.AuthorizationError):
        db.admin_list_bookings(admin_ctx)


# ----------------------------------------------------------------------------- alur approval
def _pending_id(ref):
    return db.lookup_booking(ref, "x")["booking_id"]


def test_approve_creates_official_event(admin_ctx):
    r = db.create_booking_request(payload(), "c1")
    res = db.admin_approve_booking(admin_ctx, _pending_id(r["reference"]), admin_note="Silakan siapkan sound")
    data = db.get_calendar_data(D1, D1)
    assert len(data["events"]) == 1 and len(data["pending"]) == 0
    b = db.lookup_booking(r["reference"], "c1")
    assert b["approval_status"] == "approved" and b["admin_note"] == "Silakan siapkan sound"
    assert any(n["kind"] == "approved" for n in b["notifications"])
    assert "DISETUJUI" in res["message"]
    # tidak bisa diproses dua kali
    with pytest.raises(db.BookingError):
        db.admin_approve_booking(admin_ctx, b["booking_id"])


def test_approve_with_reschedule(admin_ctx):
    r = db.create_booking_request(payload(), "c1")
    res = db.admin_approve_booking(admin_ctx, _pending_id(r["reference"]), event_date=D2,
                                   start_time=time(13, 0), end_time=time(14, 0))
    assert "disesuaikan" in res["message"]
    ev = db.get_calendar_data(D2, D2)["events"][0]
    assert ev["start_time"] == time(13, 0)


def test_new_booking_blocked_by_approved_event(admin_ctx):
    r = db.create_booking_request(payload(), "c1")
    db.admin_approve_booking(admin_ctx, _pending_id(r["reference"]))
    with pytest.raises(db.ConflictError):
        db.create_booking_request(payload(requester_whatsapp="081111111111", start_time=time(10, 30),
                                          end_time=time(11, 30)), "c2")


def test_admin_conflict_requires_override(admin_ctx):
    ev = {"event_name": "Agenda Ketua", "category": "Rapat", "event_date": D1, "start_time": time(9),
          "end_time": time(12), "person_in_charge": "Ketua"}
    db.admin_create_event(admin_ctx, ev)
    with pytest.raises(db.ConflictError, match="Override"):
        db.admin_create_event(admin_ctx, {**ev, "event_name": "Agenda Kedua", "start_time": time(10)})
    res = db.admin_create_event(admin_ctx, {**ev, "event_name": "Agenda Kedua", "start_time": time(10)}, override=True)
    full = db.admin_get_event(admin_ctx, res["event_id"])
    assert full["conflict_override"] is True


def test_admin_locked_date_requires_override(admin_ctx):
    db.admin_upsert_calendar_date(admin_ctx, D1, holiday_name=None, holiday_type=None, lock_status="locked")
    ev = {"event_name": "Agenda Ketua", "category": "Rapat", "event_date": D1, "start_time": time(9),
          "end_time": time(12), "person_in_charge": "Ketua"}
    with pytest.raises(db.ConflictError, match="DIKUNCI"):
        db.admin_create_event(admin_ctx, ev)
    db.admin_create_event(admin_ctx, ev, override=True)


def test_database_exclusion_constraint_is_last_line_of_defense(database):
    with psycopg.connect(database, autocommit=True) as conn:
        sql = """insert into events (event_name, category, event_date, start_time, end_time, person_in_charge, created_by)
                 values (%s, 'Rapat', %s, %s, %s, 'X', 'test')"""
        conn.execute(sql, ("Satu", D1, time(9), time(11)))
        with pytest.raises(psycopg.errors.ExclusionViolation):
            conn.execute(sql, ("Dua", D1, time(10), time(12)))


def test_concurrent_approvals_only_one_wins(admin_ctx, database):
    # Dua pengajuan bentrok yang lolos (mis. dibuat sebelum aturan berubah) disetujui bersamaan
    with psycopg.connect(database, autocommit=True) as conn:
        for i, ref in enumerate(["BK-AAAA-AAAA-AAA2", "BK-AAAA-AAAA-AAA3"]):
            conn.execute("""insert into booking_requests (booking_reference, requester_name, requester_whatsapp,
                              person_in_charge, event_name, category, requested_date, start_time, end_time, description)
                            values (%s, 'Pemohon', '6281200000000', 'Pemohon', %s, 'Rapat', %s, '09:00', '11:00', 'desc')""",
                         (ref, f"Kegiatan {i}", D1))
        ids = [r[0] for r in conn.execute("select booking_id::text from booking_requests order by booking_reference")]
    ok, conflict = [], []
    barrier = threading.Barrier(2)

    def worker(bid):
        barrier.wait()
        try:
            ok.append(db.admin_approve_booking(admin_ctx, bid))
        except db.ConflictError:
            conflict.append(bid)

    ts = [threading.Thread(target=worker, args=(b,)) for b in ids]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(ok) == 1 and len(conflict) == 1
    assert len(db.get_calendar_data(D1, D1)["events"]) == 1


def test_reject_requires_reason(admin_ctx):
    r = db.create_booking_request(payload(), "c1")
    bid = _pending_id(r["reference"])
    with pytest.raises(ValidationError):
        db.admin_reject_booking(admin_ctx, bid, "")
    db.admin_reject_booking(admin_ctx, bid, "Bentrok dengan agenda masjid")
    b = db.lookup_booking(r["reference"], "c1")
    assert b["approval_status"] == "rejected" and "Bentrok" in b["rejection_reason"]


def test_reschedule_and_cancel_event_propagate_to_requester(admin_ctx):
    r = db.create_booking_request(payload(), "c1")
    res = db.admin_approve_booking(admin_ctx, _pending_id(r["reference"]))
    eid = res["event_id"]
    ev = db.admin_get_event(admin_ctx, eid)
    upd = db.admin_update_event(admin_ctx, eid, {**ev, "event_date": D2, "start_time": time(14),
                                                 "end_time": time(15)})
    assert upd["schedule_changed"]
    b = db.lookup_booking(r["reference"], "c1")
    assert b["requested_date"] == D2 and any(n["kind"] == "rescheduled" for n in b["notifications"])
    db.admin_cancel_event(admin_ctx, eid, "Hujan deras")
    b = db.lookup_booking(r["reference"], "c1")
    assert b["approval_status"] == "cancelled"
    assert db.get_calendar_data(D2, D2)["events"] == []
    db.admin_delete_event(admin_ctx, eid)
    assert db.admin_get_event(admin_ctx, eid) is None


# ----------------------------------------------------------------------------- pembatalan oleh pemohon
def test_requester_cancel_requires_matching_whatsapp():
    r = db.create_booking_request(payload(), "c1")
    with pytest.raises(db.BookingError, match="tidak cocok"):
        db.cancel_booking_by_reference(r["reference"], "089999999999", "c1")
    db.cancel_booking_by_reference(r["reference"], "+62 812 3456 7890", "c1", "Acara diundur")
    b = db.lookup_booking(r["reference"], "c1")
    assert b["approval_status"] == "cancelled"
    # slot kembali tersedia
    db.create_booking_request(payload(requester_whatsapp="081111111111"), "c2")


def test_requester_cannot_cancel_approved(admin_ctx):
    r = db.create_booking_request(payload(), "c1")
    db.admin_approve_booking(admin_ctx, _pending_id(r["reference"]))
    with pytest.raises(db.BookingError, match="Hanya pengajuan"):
        db.cancel_booking_by_reference(r["reference"], "081234567890", "c1")


def test_cancel_bruteforce_rate_limited():
    r = db.create_booking_request(payload(), "c1")
    for _ in range(5):
        with pytest.raises(db.BookingError):
            db.cancel_booking_by_reference(r["reference"], "089999999999", "bf")
    with pytest.raises(db.RateLimitError):
        db.cancel_booking_by_reference(r["reference"], "081234567890", "bf")


def test_lookup_bruteforce_rate_limited():
    for _ in range(15):
        assert db.lookup_booking(generate_booking_reference(), "guesser") is None
    with pytest.raises(db.RateLimitError):
        db.lookup_booking(generate_booking_reference(), "guesser")


# ----------------------------------------------------------------------------- dashboard & audit
def test_dashboard_and_audit(admin_ctx):
    r = db.create_booking_request(payload(), "c1")
    db.admin_approve_booking(admin_ctx, _pending_id(r["reference"]))
    db.create_booking_request(payload(requested_date=D2), "c1")
    s = db.dashboard_stats()
    assert s["approved"] == 1 and s["pending"] == 1 and s["total"] == 2
    assert "requester_name" not in s["latest"][0]  # publik tidak melihat identitas
    assert "requester_name" in db.dashboard_stats(include_private=True)["latest"][0]
    actions = {a["action"] for a in db.admin_list_audit(admin_ctx)}
    assert {"booking_created", "booking_approved", "admin_login"} <= actions
    n = db.admin_notifications(admin_ctx)
    assert n["unread"] >= 2
    db.admin_mark_notifications_read(admin_ctx)
    assert db.admin_notifications(admin_ctx)["unread"] == 0


def test_public_calendar_data_hides_whatsapp():
    db.create_booking_request(payload(), "c1")
    data = db.get_calendar_data(D1, D1)
    for row in data["pending"] + data["events"]:
        assert not any("whatsapp" in k for k in row)
