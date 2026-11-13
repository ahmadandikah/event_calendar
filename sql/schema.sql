-- =====================================================================
--  EVENT BOOKING CALENDAR — SKEMA DATABASE (Supabase / PostgreSQL 14+)
--  Konsep: Private Link Access (tanpa login) + Admin Mode ber-PIN.
--
--  Cara pakai: buka Supabase → SQL Editor → New query → tempel seluruh
--  isi file ini → Run. Script aman dijalankan ulang (idempotent).
-- =====================================================================

create extension if not exists btree_gist;   -- untuk constraint anti-bentrok jadwal
create extension if not exists pgcrypto;     -- gen_random_uuid()

-- ---------------------------------------------------------------------
-- 1. CALENDAR SETTINGS — pengaturan periode kalender (satu baris saja)
-- ---------------------------------------------------------------------
create table if not exists calendar_settings (
    setting_id        smallint primary key default 1 check (setting_id = 1),
    start_date        date        not null,
    end_date          date        not null,
    day_start_time    time        not null default '06:00',
    day_end_time      time        not null default '22:00',
    max_pending_per_whatsapp smallint not null default 5,
    booking_open      boolean     not null default true,
    announcement      text,
    notes             text,
    updated_at        timestamptz not null default now(),
    constraint chk_period check (end_date >= start_date),
    constraint chk_day_hours check (day_end_time > day_start_time)
);

-- ---------------------------------------------------------------------
-- 2. CALENDAR DATES — hari libur, hari raya, dan status kunci per tanggal
--    lock_status: open | locked (tidak bisa dibooking) | exclusive (hanya 1 agenda)
-- ---------------------------------------------------------------------
create table if not exists calendar_dates (
    calendar_date   date primary key,
    holiday_name    text,
    holiday_type    text check (holiday_type in
                     ('libur_nasional','cuti_bersama','hari_raya_islam','khusus')),
    lock_status     text not null default 'open'
                     check (lock_status in ('open','locked','exclusive')),
    notes           text,
    updated_by      text,
    updated_at      timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- 3. BOOKING REQUESTS — pengajuan dari publik (tanpa akun)
-- ---------------------------------------------------------------------
create table if not exists booking_requests (
    booking_id          uuid primary key default gen_random_uuid(),
    booking_reference   text not null unique,                -- kode acak, mis. BK-7KQ2-M9XD-4TPA
    requester_name      text not null check (char_length(requester_name) between 2 and 100),
    requester_whatsapp  text not null check (requester_whatsapp ~ '^62[0-9]{8,13}$'),
    person_in_charge    text not null check (char_length(person_in_charge) between 2 and 100),
    event_name          text not null check (char_length(event_name) between 3 and 150),
    category            text not null,
    requested_date      date not null,
    start_time          time not null,
    end_time            time not null,
    location            text,
    participants        integer check (participants is null or participants between 1 and 100000),
    description         text not null check (char_length(description) <= 2000),
    notes               text check (notes is null or char_length(notes) <= 1000),
    approval_status     text not null default 'pending'
                         check (approval_status in ('pending','approved','rejected','cancelled')),
    rejection_reason    text,
    admin_note          text,
    reviewed_by         text,
    reviewed_at         timestamptz,
    client_hash         text,                                -- sidik jari anonim (anti-spam)
    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now(),
    constraint chk_booking_time check (end_time > start_time)
);
create index if not exists idx_booking_date   on booking_requests (requested_date);
create index if not exists idx_booking_status on booking_requests (approval_status);
create index if not exists idx_booking_wa     on booking_requests (requester_whatsapp);

-- ---------------------------------------------------------------------
-- 4. EVENTS — agenda resmi (hasil approval atau dibuat langsung oleh admin)
-- ---------------------------------------------------------------------
create table if not exists events (
    event_id          uuid primary key default gen_random_uuid(),
    booking_id        uuid unique references booking_requests(booking_id) on delete set null,
    event_name        text not null check (char_length(event_name) between 3 and 150),
    category          text not null,
    event_date        date not null,
    start_time        time not null,
    end_time          time not null,
    person_in_charge  text not null,
    pic_whatsapp      text,
    location          text,
    participants      integer,
    description       text,
    status            text not null default 'approved'
                       check (status in ('approved','cancelled')),
    conflict_override boolean not null default false,   -- true = admin sengaja mengizinkan bentrok
    cancel_reason     text,
    created_by        text not null,
    approved_by       text,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),
    constraint chk_event_time check (end_time > start_time),
    -- Lapis pertahanan terakhir anti double-booking: dua agenda approved
    -- (tanpa override) tidak boleh memiliki rentang waktu yang beririsan.
    constraint no_overlapping_approved_events exclude using gist (
        tsrange(event_date + start_time, event_date + end_time, '[)') with &&
    ) where (status = 'approved' and conflict_override = false)
);
create index if not exists idx_events_date   on events (event_date);
create index if not exists idx_events_status on events (status);

-- ---------------------------------------------------------------------
-- 5. AUDIT LOGS — jejak semua perubahan penting
-- ---------------------------------------------------------------------
create table if not exists audit_logs (
    log_id       bigserial primary key,
    actor_type   text not null check (actor_type in ('public','admin','system')),
    actor_label  text not null,
    action       text not null,
    entity_type  text not null,
    entity_id    text,
    details      jsonb not null default '{}'::jsonb,
    client_hash  text,
    created_at   timestamptz not null default now()
);
create index if not exists idx_audit_created on audit_logs (created_at desc);

-- ---------------------------------------------------------------------
-- 6. NOTIFICATIONS — notifikasi dalam aplikasi
--    audience = 'admin'  → tampil di lonceng admin
--    audience = 'public' → tampil di halaman Cek Status (berdasarkan booking_id)
-- ---------------------------------------------------------------------
create table if not exists notifications (
    notification_id bigserial primary key,
    audience     text not null check (audience in ('admin','public')),
    booking_id   uuid references booking_requests(booking_id) on delete cascade,
    event_id     uuid references events(event_id) on delete cascade,
    kind         text not null,
    title        text not null,
    message      text not null,
    is_read      boolean not null default false,
    created_at   timestamptz not null default now()
);
create index if not exists idx_notif_audience on notifications (audience, is_read, created_at desc);

-- ---------------------------------------------------------------------
-- 7. ADMIN SESSIONS — sesi Admin Mode (hanya hash token yang disimpan)
-- ---------------------------------------------------------------------
create table if not exists admin_sessions (
    session_id     uuid primary key default gen_random_uuid(),
    token_hash     text not null unique,
    admin_label    text not null,
    client_hash    text,
    created_at     timestamptz not null default now(),
    last_activity  timestamptz not null default now(),
    expires_at     timestamptz not null,
    revoked        boolean not null default false
);

-- ---------------------------------------------------------------------
-- 8. RATE LIMITS — pencatatan percobaan PIN, booking, dan cek status
-- ---------------------------------------------------------------------
create table if not exists rate_limits (
    id          bigserial primary key,
    action      text not null,
    key_hash    text not null,
    success     boolean not null default false,
    created_at  timestamptz not null default now()
);
create index if not exists idx_rate_lookup on rate_limits (action, key_hash, created_at desc);
create index if not exists idx_rate_action on rate_limits (action, created_at desc);

-- ---------------------------------------------------------------------
-- 9. KEAMANAN SUPABASE: aktifkan Row Level Security TANPA policy.
--    Artinya API publik Supabase (anon / authenticated key) TIDAK bisa
--    membaca/menulis tabel apa pun. Aplikasi Streamlit terhubung langsung
--    lewat koneksi Postgres server-side (role postgres) sehingga tetap jalan.
-- ---------------------------------------------------------------------
alter table calendar_settings enable row level security;
alter table calendar_dates    enable row level security;
alter table booking_requests  enable row level security;
alter table events            enable row level security;
alter table audit_logs        enable row level security;
alter table notifications     enable row level security;
alter table admin_sessions    enable row level security;
alter table rate_limits       enable row level security;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    execute 'revoke all on all tables    in schema public from anon, authenticated';
    execute 'revoke all on all sequences in schema public from anon, authenticated';
  end if;
end $$;

-- ---------------------------------------------------------------------
-- 10. DATA AWAL: periode kalender & hari libur resmi
--     Sumber: SKB 3 Menteri No. 1205/2026, 3/2026, 2/2026 tentang
--     Hari Libur Nasional dan Cuti Bersama 2027. Tanggal Idul Fitri &
--     Idul Adha final ditetapkan Keputusan Menteri Agama (sidang isbat) —
--     admin dapat memperbaruinya di menu "Tanggal & Hari Libur".
-- ---------------------------------------------------------------------
insert into calendar_settings (setting_id, start_date, end_date, notes)
values (1, '2026-11-01', '2027-05-17', 'Periode: November 2026 s.d. Idul Adha 1448 H')
on conflict (setting_id) do nothing;

insert into calendar_dates (calendar_date, holiday_name, holiday_type, updated_by) values
  ('2026-12-24', 'Cuti Bersama Kelahiran Yesus Kristus',      'cuti_bersama',    'system'),
  ('2026-12-25', 'Kelahiran Yesus Kristus (Natal)',           'libur_nasional',  'system'),
  ('2027-01-01', 'Tahun Baru 2027 Masehi',                    'libur_nasional',  'system'),
  ('2027-01-05', 'Isra Mikraj Nabi Muhammad SAW 1448 H',      'hari_raya_islam', 'system'),
  ('2027-02-05', 'Cuti Bersama Tahun Baru Imlek',             'cuti_bersama',    'system'),
  ('2027-02-06', 'Tahun Baru Imlek 2578 Kongzili',            'libur_nasional',  'system'),
  ('2027-03-08', 'Hari Suci Nyepi Tahun Baru Saka 1949',      'libur_nasional',  'system'),
  ('2027-03-09', 'Cuti Bersama Idul Fitri 1448 H',            'cuti_bersama',    'system'),
  ('2027-03-10', 'Hari Raya Idul Fitri 1448 H (hari ke-1)',   'hari_raya_islam', 'system'),
  ('2027-03-11', 'Hari Raya Idul Fitri 1448 H (hari ke-2)',   'hari_raya_islam', 'system'),
  ('2027-03-12', 'Cuti Bersama Idul Fitri 1448 H',            'cuti_bersama',    'system'),
  ('2027-03-15', 'Cuti Bersama Idul Fitri 1448 H',            'cuti_bersama',    'system'),
  ('2027-03-25', 'Cuti Bersama Wafat Yesus Kristus',          'cuti_bersama',    'system'),
  ('2027-03-26', 'Wafat Yesus Kristus',                       'libur_nasional',  'system'),
  ('2027-03-28', 'Kebangkitan Yesus Kristus (Paskah)',        'libur_nasional',  'system'),
  ('2027-05-01', 'Hari Buruh Internasional',                  'libur_nasional',  'system'),
  ('2027-05-06', 'Kenaikan Yesus Kristus',                    'libur_nasional',  'system'),
  ('2027-05-17', 'Hari Raya Idul Adha 1448 H',                'hari_raya_islam', 'system'),
  ('2027-05-18', 'Cuti Bersama Idul Adha 1448 H',             'cuti_bersama',    'system')
on conflict (calendar_date) do nothing;
