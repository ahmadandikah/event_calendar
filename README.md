# 📅 Kalender Kegiatan Panitia — Online Event Booking Calendar

Aplikasi web **Streamlit + Supabase PostgreSQL** untuk mengatur jadwal kegiatan kepanitiaan
periode **November 2026 – Idul Adha 1448 H (17 Mei 2027)**.

* **Tanpa login & registrasi** — siapa pun yang memiliki link dapat melihat kalender dan mengajukan booking.
* **Admin Mode ber-PIN** untuk Ketua Panitia (approval, kelola agenda, kunci tanggal, audit log).
* **Anti double-booking berlapis** (advisory lock + validasi + exclusion constraint di database).
* Data permanen di Supabase — tidak hilang saat aplikasi restart, aman dipakai banyak orang bersamaan.

---

## Daftar isi
1. [Fitur](#1-fitur)
2. [Arsitektur](#2-arsitektur)
3. [Struktur database](#3-struktur-database)
4. [Struktur project](#4-struktur-project)
5. [Menjalankan di komputer sendiri](#5-menjalankan-di-komputer-sendiri)
6. [Deployment online (pemula)](#6-deployment-online-langkah-demi-langkah)
7. [Bootstrap Admin (PIN pertama)](#7-bootstrap-admin-pin-pertama)
8. [Keamanan](#8-keamanan)
9. [Notifikasi](#9-notifikasi)
10. [Pengujian](#10-pengujian)
11. [Pemecahan masalah](#11-pemecahan-masalah)

Panduan pemakaian untuk **Ketua Panitia** dan **pengguna umum** ada di
[`PANDUAN_PENGGUNAAN.md`](PANDUAN_PENGGUNAAN.md).

---

## 1. Fitur

| Area | Fitur |
|---|---|
| **Kalender interaktif** | Tampilan Bulanan, Mingguan, dan Agenda (list); navigasi bulan, tombol *Hari ini*, lompat ke bulan; dibatasi ke periode kalender. Warna berbeda untuk agenda disetujui, pending (garis putus-putus), tanggal kosong, libur nasional/cuti bersama, hari raya Islam (🕌), tanggal dikunci (🔒), tanggal eksklusif (⭐) + legenda. Klik tanggal → detail + formulir booking; klik agenda → popup detail. Filter kategori, pencarian, toggle pending. |
| **Booking tanpa akun** | Nama pemohon, WhatsApp, penanggung jawab, nama kegiatan, kategori, tanggal, jam mulai/selesai, lokasi, jumlah peserta, deskripsi, catatan. Menampilkan jam yang sudah terisi sebelum mengisi. Menghasilkan **Kode Referensi** acak (mis. `BK-7KQ2-M9XD-4TPA`). |
| **Cek status** | Masukkan kode → status, riwayat notifikasi, catatan/alasan dari Ketua. Batalkan sendiri (kode + nomor WA) selama masih pending. |
| **Approval Management** | Daftar pending + deteksi bentrok otomatis, setujui / tolak (alasan wajib), ubah tanggal & jam sebelum menyetujui, catatan untuk pemohon, **override konflik** dengan konfirmasi, tombol *Kabari via WhatsApp*. Tab semua pengajuan + filter + unduh CSV. |
| **Kelola Agenda** | Tambah agenda resmi, edit/ubah jadwal (pemohon otomatis mendapat notifikasi), batalkan (alasan), hapus permanen (konfirmasi), filter kategori/status/PJ/tanggal, pencarian, unduh CSV. |
| **Tanggal & Hari Libur** | Tambah/ubah hari libur & hari raya, kunci tanggal, tetapkan tanggal eksklusif (hanya 1 agenda), kunci rentang tanggal sekaligus. |
| **Dashboard** | KPI: total agenda, disetujui, pending, tanggal tersedia, agenda bulan ini; grafik per bulan & per kategori; agenda terdekat; pengajuan terbaru. Refresh otomatis tiap 60 detik. |
| **Audit Log** | Siapa membuat, menyetujui, mengubah, membatalkan, menghapus — beserta waktu & detail sebelum/sesudah. Filter + unduh CSV. |
| **Pengaturan** | Periode kalender, jam operasional, buka/tutup booking, batas pending per nomor WA, pengumuman dashboard, cabut semua sesi admin. |

Hari libur 2026–2027 sudah terisi dari **SKB 3 Menteri No. 1205/2026, 3/2026, 2/2026**
(Idul Fitri 1448 H: 10–11 Maret 2027; Idul Adha 1448 H: 17 Mei 2027). Tanggal hari raya final
ditetapkan Kementerian Agama melalui sidang isbat — Ketua dapat memperbaruinya di menu
**Tanggal & Hari Libur**, lalu menyesuaikan akhir periode di **Pengaturan**.

---

## 2. Arsitektur

```text
 Browser (HP / laptop)                Streamlit Community Cloud                   Supabase
┌────────────────────┐  HTTPS/WS  ┌──────────────────────────────────┐  TLS  ┌──────────────────────┐
│ Kalender (FullCal.)│◄──────────►│ app.py  ─ st.navigation           │◄─────►│ PostgreSQL           │
│ Formulir, dialog   │            │   ├─ views/*  (halaman UI)        │ pool  │  events              │
└────────────────────┘            │   ├─ auth.py  (Admin Mode, PIN)   │       │  booking_requests    │
                                  │   ├─ database.py (semua query,    │       │  calendar_settings   │
                                  │   │   lock, validasi, otorisasi)  │       │  calendar_dates      │
                                  │   └─ utils/ (kalender, notifikasi)│       │  audit_logs, notif., │
                                  │ Secrets: DATABASE_URL, PIN hash   │       │  admin_sessions,     │
                                  └──────────────────────────────────┘       │  rate_limits (RLS on)│
                                         │ opsional                           └──────────────────────┘
                                         └─► Email SMTP / ntfy push / tautan wa.me
```

**Alur booking**

```text
Publik isi form ─► validasi input ─► rate-limit & anti-spam ─► LOCK tanggal (pg_advisory_xact_lock)
   ─► cek tanggal dikunci/eksklusif ─► cek bentrok (agenda disetujui + pending) ─► simpan (pending)
   ─► kode referensi + notifikasi admin ─► Ketua: Setujui (cek bentrok lagi + exclusion constraint)
   ─► agenda resmi muncul di kalender + notifikasi untuk pemohon
```

Keputusan desain penting:

* **Tanpa Session State sebagai database.** Semua data dibaca/ditulis ke PostgreSQL di setiap aksi.
  Session State hanya menyimpan hal sementara (posisi kalender, token sesi admin).
* **Otorisasi di server.** Halaman admin hanya didaftarkan ke navigasi bila sesi admin valid, setiap
  halaman admin memanggil `require_admin()`, dan **setiap fungsi admin di `database.py` memverifikasi
  ulang token sesi di database dalam transaksi yang sama**. Menyembunyikan tombol bukan satu-satunya proteksi.
* **Folder halaman bernama `views/` (bukan `pages/`).** Streamlit otomatis menjalankan file di
  folder `pages/` sebagai halaman mandiri sebelum `st.navigation` aktif; memakai `views/` menutup
  celah tersebut sehingga halaman hanya dapat diakses melalui `app.py`.
* **Tabel `users` dihapus** sesuai konsep Private Link Access. Identitas pemohon disimpan langsung di
  `booking_requests`.

---

## 3. Struktur database

File lengkap: [`sql/schema.sql`](sql/schema.sql) (aman dijalankan ulang).

| Tabel | Isi | Kolom utama |
|---|---|---|
| `booking_requests` | Pengajuan publik | `booking_id`, `booking_reference` (unik, acak), `requester_name`, `requester_whatsapp`, `person_in_charge`, `event_name`, `category`, `requested_date`, `start_time`, `end_time`, `location`, `participants`, `description`, `notes`, `approval_status` (pending/approved/rejected/cancelled), `rejection_reason`, `admin_note`, `reviewed_by`, `reviewed_at`, `client_hash`, `created_at`, `updated_at` |
| `events` | Agenda resmi | `event_id`, `booking_id` (FK), `event_name`, `category`, `event_date`, `start_time`, `end_time`, `person_in_charge`, `pic_whatsapp`, `location`, `participants`, `description`, `status` (approved/cancelled), `conflict_override`, `cancel_reason`, `created_by`, `approved_by`, `created_at`, `updated_at` |
| `calendar_settings` | Pengaturan (1 baris) | `start_date`, `end_date`, `day_start_time`, `day_end_time`, `booking_open`, `max_pending_per_whatsapp`, `announcement` |
| `calendar_dates` | Hari libur & kunci per tanggal | `calendar_date`, `holiday_name`, `holiday_type`, `lock_status` (open/locked/exclusive), `notes` |
| `audit_logs` | Jejak aktivitas | `actor_type`, `actor_label`, `action`, `entity_type`, `entity_id`, `details` (JSON sebelum/sesudah), `created_at` |
| `notifications` | Notifikasi in-app | `audience` (admin/public), `booking_id`, `kind`, `title`, `message`, `is_read` |
| `admin_sessions` | Sesi Admin Mode | `token_hash` (SHA-256, token asli tidak disimpan), `admin_label`, `last_activity`, `expires_at`, `revoked` |
| `rate_limits` | Percobaan PIN / cek kode / pembatalan | `action`, `key_hash`, `success`, `created_at` |

> Catatan: tabel *Calendar Settings* pada rancangan awal (yang mencampur periode, hari libur, dan
> status kunci dalam satu tabel) dipecah menjadi `calendar_settings` + `calendar_dates` agar satu
> tanggal bisa sekaligus hari libur dan dikunci tanpa duplikasi.

**Pertahanan double booking**
1. `pg_advisory_xact_lock(namespace, tanggal)` — pengajuan/approval pada tanggal yang sama diproses
   berurutan meski dikirim bersamaan.
2. Pengecekan bentrok jam di dalam lock (agenda disetujui **dan** pengajuan pending). Jam yang
   bersebelahan (selesai 11:00, mulai 11:00) tidak dianggap bentrok.
3. `EXCLUDE USING gist (tsrange(...) WITH &&) WHERE status='approved' AND NOT conflict_override` —
   database menolak dua agenda disetujui yang beririsan, apa pun yang terjadi di aplikasi.
4. Override hanya oleh admin, dengan centang konfirmasi, dan tercatat `conflict_override = true` di audit log.

**Keamanan Supabase:** semua tabel memakai **Row Level Security tanpa policy** dan hak akses
`anon`/`authenticated` dicabut, sehingga API publik Supabase tidak bisa membaca data apa pun.
Aplikasi terhubung lewat koneksi Postgres server-side.

---

## 4. Struktur project

```text
event_calendar/
├── app.py                     # titik masuk: tema, navigasi, Admin Mode, notifikasi
├── config.py                  # konstanta, warna, kategori, batas keamanan, pembaca Secrets
├── database.py                # koneksi pool, semua query, lock, validasi, otorisasi admin
├── auth.py                    # PIN (PBKDF2), sesi admin, sidik jari klien
├── requirements.txt
├── .streamlit/
│   ├── config.toml            # tema navy/biru, keamanan server
│   └── secrets.toml.example
├── views/                     # halaman (pengganti pages/, lihat bagian Arsitektur)
│   ├── dashboard.py
│   ├── calendar.py
│   ├── booking.py
│   ├── my_bookings.py         # cek status via kode referensi
│   ├── approvals.py           # admin
│   ├── event_management.py    # admin
│   ├── date_management.py     # admin (pengganti user_management.py — tidak ada akun)
│   ├── audit_log.py           # admin
│   └── settings.py            # admin
├── utils/
│   ├── calendar_utils.py      # event & opsi FullCalendar, legenda
│   ├── notification.py        # notifikasi in-app + email/ntfy opsional
│   ├── helpers.py             # tanggal Indonesia, WA, kode referensi, validasi teks
│   └── ui.py                  # CSS, kartu KPI, formulir booking, dialog
├── assets/                    # logo
├── sql/
│   ├── schema.sql             # buat semua tabel + data hari libur
│   └── sample_data.sql        # data contoh untuk uji coba
├── scripts/
│   ├── generate_admin_secrets.py   # bootstrap admin (hash PIN, APP_SECRET, access key)
│   └── init_db.py                  # opsional: jalankan SQL dari komputer
├── tests/                     # 43 pengujian otomatis
├── PANDUAN_PENGGUNAAN.md
└── README.md
```

---

## 5. Menjalankan di komputer sendiri

Butuh **Python 3.11–3.13** dan database PostgreSQL (Supabase gratis atau PostgreSQL lokal).

```bash
cd event_calendar
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

# 1) Buat tabel: tempel sql/schema.sql di Supabase SQL Editor → Run
#    (atau: python scripts/init_db.py "postgresql://..." --sample)

# 2) Buat rahasia admin
python scripts/generate_admin_secrets.py

# 3) Salin contoh secrets lalu isi
cp .streamlit/secrets.toml.example .streamlit/secrets.toml

# 4) Jalankan
streamlit run app.py
```

Buka `http://localhost:8501`.

---

## 6. Deployment online (langkah demi langkah)

Semua layanan di bawah memiliki paket **gratis**.

### A. Supabase (database)
1. Daftar di **supabase.com** → **New project**. Isi nama, buat **Database Password** yang kuat
   (simpan baik-baik), pilih region **Southeast Asia (Singapore)**.
2. Tunggu project siap (± 2 menit).
3. Menu kiri **SQL Editor** → **New query** → salin seluruh isi `sql/schema.sql` → **Run**.
   Harus muncul *Success. No rows returned*.
4. (Opsional) Jalankan juga `sql/sample_data.sql` untuk data contoh. Hapus nanti dengan perintah
   di bagian atas file tersebut.
5. Klik tombol **Connect** (atas halaman) → tab **Connection String** → pilih **Session pooler**.
   Salin URI-nya, contoh:
   `postgresql://postgres.abcd1234:[YOUR-PASSWORD]@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres`
   Ganti `[YOUR-PASSWORD]` dengan Database Password Anda, lalu tambahkan `?sslmode=require` di akhir.
   > Gunakan **Session pooler**, bukan *Direct connection*: Streamlit Cloud hanya mendukung IPv4,
   > sedangkan direct connection Supabase memakai IPv6.
   > Bila password mengandung karakter khusus (`@ # / :` dll.), ubah ke format URL-encode
   > (mis. `@` → `%40`).

### B. GitHub (kode)
1. Daftar/masuk **github.com** → **New repository** → nama mis. `kalender-panitia` →
   **Private** (disarankan) → Create.
2. Unggah seluruh isi folder `event_calendar/` (tombol **Add file → Upload files**, seret semua
   file & folder) → **Commit changes**.
   **Jangan** unggah `.streamlit/secrets.toml` (yang diunggah hanya `secrets.toml.example`).

### C. Rahasia admin
Di komputer Anda jalankan `python scripts/generate_admin_secrets.py`, masukkan PIN (min. 8
karakter). Salin tiga baris hasilnya (`ADMIN_PIN_HASH`, `APP_SECRET`, `ADMIN_ACCESS_KEY`).
Tanpa Python? Lihat [bagian 7](#7-bootstrap-admin-pin-pertama).

### D. Streamlit Community Cloud (hosting)
1. Buka **share.streamlit.io** → masuk dengan akun GitHub → **Create app** →
   **Deploy a public app from GitHub**.
2. Pilih repository, branch `main`, **Main file path**: `app.py`.
   Buka **Advanced settings** → Python **3.12**.
3. Pada kotak **Secrets**, tempel:
   ```toml
   DATABASE_URL = "postgresql://postgres.abcd1234:PASSWORD@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres?sslmode=require"
   ADMIN_PIN_HASH = "pbkdf2_sha256$390000$....$...."
   APP_SECRET = "....64 karakter...."
   ADMIN_ACCESS_KEY = ""          # isi bila ingin lapisan kedua
   APP_URL = "https://kalender-panitia.streamlit.app"
   ```
4. Atur **App URL** (mis. `kalender-panitia`) → **Deploy**. Tunggu 2–4 menit.
5. Buka URL publik, coba ajukan booking, lalu masuk **Admin Mode** dengan PIN Anda.
6. Bagikan link aplikasi ke anggota panitia (grup WhatsApp, dsb.). Jangan bagikan PIN.

**Memperbarui aplikasi:** ubah file di GitHub → Streamlit Cloud otomatis redeploy.
**Data aman:** semua data di Supabase; restart/redeploy tidak menghapus data.

> Paket gratis Streamlit Cloud menidurkan aplikasi yang lama tidak dibuka; pengunjung
> pertama cukup klik *“Yes, get this app back up!”*. Project Supabase gratis dijeda setelah ±7 hari
> tanpa aktivitas — buka dashboard Supabase dan klik *Restore* bila terjadi. Penggunaan rutin
> panitia biasanya mencegah keduanya.

---

## 7. Bootstrap Admin (PIN pertama)

Tidak ada akun admin di database. Admin Mode diverifikasi dengan **hash PIN** yang hanya ada di
Secrets, sehingga PIN tidak pernah tersimpan dalam bentuk asli di kode, GitHub, atau database.

```bash
python scripts/generate_admin_secrets.py
```

* `ADMIN_PIN_HASH` — hash PBKDF2-SHA256 (390.000 iterasi, salt acak).
* `APP_SECRET` — kunci HMAC untuk menyamarkan sidik jari perangkat pada rate limit.
* `ADMIN_ACCESS_KEY` *(opsional, sangat disarankan)* — token acak 192-bit. Bila diisi, Admin
  Mode memerlukan **PIN + Access Key**. Ketua cukup menyimpan tautan rahasia
  `https://APP-ANDA.streamlit.app/?ak=<ADMIN_ACCESS_KEY>` di bookmark/password manager: kunci
  dipindahkan ke memori server lalu langsung dihapus dari URL, kemudian dialog PIN terbuka.

**Ganti PIN:** jalankan script lagi → ganti `ADMIN_PIN_HASH` di Secrets → simpan. Lalu di
**Pengaturan → Keluarkan semua sesi admin lain**.

Alternatif tanpa Python lokal: isi sementara `ADMIN_PIN = "PIN-anda"` di Secrets (aplikasi
menerimanya, tetapi menandainya *kurang disarankan* di halaman Pengaturan), lalu ganti ke
`ADMIN_PIN_HASH` sesegera mungkin.

---

## 8. Keamanan

| Ancaman | Mitigasi |
|---|---|
| Menebak PIN | Maks. 5 salah per perangkat & 25 salah total per 15 menit (tercatat di DB, tidak bisa direset dengan refresh), jeda 0,6 detik per percobaan gagal, hash PBKDF2, opsi Access Key acak 192-bit. |
| Akses admin lewat URL/parameter | Tidak ada parameter yang memberi hak admin. Halaman admin tidak terdaftar untuk publik, `require_admin()` di setiap halaman, verifikasi token di setiap operasi DB. |
| Pencurian sesi | Token 256-bit di memori server Streamlit (tidak di URL/cookie); DB hanya menyimpan hash. Timeout tidak aktif 30 menit, maks. 12 jam, logout & cabut semua sesi. |
| Spam booking | Captcha hitungan sederhana, maks. 5 pengajuan/jam per perangkat, 120/jam total, maks. 5 pending per nomor WA, validasi panjang & format input. |
| Menebak kode referensi | Kode acak kriptografis 60-bit; maks. 15 kode salah per 15 menit per perangkat. Pembatalan butuh kode **dan** nomor WA (maks. 5 gagal per 30 menit). |
| Kebocoran data pribadi | Nomor WA tidak pernah dikirim ke tampilan publik; identitas pemohon di dashboard hanya untuk admin. Semua teks pengguna di-escape (anti-XSS). |
| API publik Supabase | RLS aktif tanpa policy + `revoke` untuk role `anon`/`authenticated`. |
| Rahasia di kode | Semua dari Streamlit Secrets/env vars; `.gitignore` mengecualikan `secrets.toml`. |
| Jejak perubahan | Audit log untuk pengajuan, approval, penolakan, perubahan jadwal, pembatalan, penghapusan, kunci tanggal, pengaturan, login/logout admin, dan PIN salah. |

Catatan: Admin Mode tersimpan di sesi browser yang sedang terbuka. Menutup tab atau me-refresh
halaman otomatis mengakhiri Admin Mode (perilaku yang disengaja demi keamanan).

---

## 9. Notifikasi

| Kejadian | Ketua Panitia | Pemohon |
|---|---|---|
| Pengajuan baru | 🔔 lonceng sidebar (+ email/ntfy bila diaktifkan) | Halaman Cek Status |
| Disetujui / ditolak | — | Halaman Cek Status + tombol *Kabari via WhatsApp* untuk admin |
| Jadwal diubah / dibatalkan | — | Halaman Cek Status + tombol WhatsApp |
| Dibatalkan pemohon | 🔔 lonceng sidebar | Halaman Cek Status |

Semua notifikasi inti gratis dan tidak bergantung layanan luar. Integrasi tambahan (opsional, gratis):

* **Email ke Ketua** — isi `ADMIN_EMAIL`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`
  (Gmail: buat *App Password* di myaccount.google.com/apppasswords).
* **Push ke HP Ketua** — pasang aplikasi **ntfy** (Android/iOS), subscribe ke topik acak, isi
  `NTFY_TOPIC` di Secrets.
* **WhatsApp ke pemohon** — tombol `wa.me` membuka WhatsApp dengan pesan yang sudah terisi
  (tanpa API berbayar).

---

## 10. Pengujian

Pengujian berjalan pada database PostgreSQL uji yang dibuat & dihapus otomatis.

```bash
pip install pytest
TEST_DATABASE_ADMIN_URL="postgresql://postgres:password@localhost:5432/postgres" pytest -q
```

Cakupan (43 tes, semua lulus):
* **Double booking:** slot sama ditolak, jam bersebelahan boleh, tanggal eksklusif, tanggal dikunci.
* **Konkurensi:** 12 pengajuan slot yang sama dikirim serentak → tepat 1 berhasil; 2 approval
  bentrok serentak → tepat 1 berhasil; exclusion constraint menolak insert langsung ke DB.
* **Akses tanpa izin:** semua operasi admin dengan konteks kosong/token palsu/sesi kedaluwarsa/
  sesi logout ditolak; halaman admin tidak terdaftar & skripnya berhenti bila dibuka tanpa sesi.
* **Rate limit:** PIN, pengajuan per perangkat, pending per WA, tebak kode, pembatalan.
* **Alur:** approve (dengan/ tanpa ubah jadwal), reject (alasan wajib), override, reschedule &
  cancel menjalar ke pemohon, hapus agenda, dashboard, audit log, notifikasi.
* **UI (Streamlit AppTest):** semua halaman publik & admin dirender tanpa error, pengisian
  formulir booking end-to-end.

---

## 11. Pemecahan masalah

| Gejala | Solusi |
|---|---|
| “Aplikasi belum terhubung ke database” | Periksa `DATABASE_URL` (pakai **Session pooler**, password benar, `?sslmode=require`). |
| “Tabel database belum dibuat” | Jalankan `sql/schema.sql` di Supabase SQL Editor. |
| `password authentication failed` | Reset Database Password di Supabase → *Project Settings → Database*, perbarui Secrets. |
| Admin Mode “PIN belum dikonfigurasi” | Isi `ADMIN_PIN_HASH` di Secrets lalu *Reboot app*. |
| “Terlalu banyak percobaan PIN” | Tunggu 15 menit. Bila ada serangan, ganti PIN & aktifkan `ADMIN_ACCESS_KEY`. |
| Kalender kosong/abu-abu | Periksa periode di **Pengaturan**; tanggal di luar periode tidak ditampilkan. |
| Perubahan Secrets tidak terbaca | Streamlit Cloud → *Manage app → ⋮ → Reboot app*. |

---

Dibangun dengan Streamlit, streamlit-calendar (FullCalendar, lisensi MIT untuk tampilan standar),
psycopg 3, Plotly, dan Supabase PostgreSQL.
