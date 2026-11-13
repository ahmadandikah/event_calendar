-- =====================================================================
--  SAMPLE DATA untuk pengujian (opsional). Jalankan SETELAH schema.sql.
--  Hapus data contoh dengan:  delete from booking_requests where booking_reference like 'BK-SMPL-%';
--                             delete from events where created_by = 'sample';
-- =====================================================================

-- Agenda resmi yang dibuat langsung oleh admin
insert into events (event_name, category, event_date, start_time, end_time, person_in_charge, pic_whatsapp,
                    location, participants, description, created_by, approved_by)
select v.n, v.c, v.d::date, v.s::time, v.e::time, v.p, v.w, v.l, v.q, v.x, v.cb, v.ab from (values
 ('Rapat Pleno Pembentukan Panitia', 'Kegiatan kepanitiaan', '2026-11-20', '19:30', '21:30', 'Ahmad (Ketua)', '6281200000001', 'Aula Masjid', 40, 'Penetapan struktur dan program kerja panitia.', 'sample', 'sample'),
 ('Rapat Koordinasi Seksi Acara', 'Rapat', '2026-11-27', '19:30', '21:00', 'Siti (Sie Acara)', '6281200000002', 'Ruang Rapat', 15, 'Penyusunan rundown kegiatan.', 'sample', 'sample'),
 ('Bakti Sosial Lingkungan', 'Kegiatan sosial', '2026-12-06', '07:00', '11:00', 'Budi (Sie Sosial)', '6281200000003', 'Lingkungan RW 05', 80, 'Kerja bakti dan pembagian sembako.', 'sample', 'sample'),
 ('Kajian Akhir Tahun', 'Kegiatan keagamaan', '2026-12-30', '18:30', '21:00', 'Ust. Hasan', '6281200000004', 'Masjid', 150, 'Kajian dan doa bersama akhir tahun.', 'sample', 'sample'),
 ('Persiapan Ramadan', 'Kegiatan kepanitiaan', '2027-02-07', '09:00', '12:00', 'Ahmad (Ketua)', '6281200000001', 'Aula Masjid', 30, 'Rapat persiapan kegiatan Ramadan.', 'sample', 'sample'),
 ('Buka Puasa Bersama', 'Kegiatan umum', '2027-02-27', '16:30', '19:30', 'Rina (Sie Konsumsi)', '6281200000005', 'Halaman Masjid', 200, 'Buka puasa bersama warga.', 'sample', 'sample'),
 ('Halal Bihalal Panitia', 'Kegiatan umum', '2027-03-21', '09:00', '12:00', 'Ahmad (Ketua)', '6281200000001', 'Aula Masjid', 100, 'Silaturahmi pasca Idul Fitri.', 'sample', 'sample'),
 ('Rapat Persiapan Qurban', 'Rapat', '2027-04-25', '19:30', '21:30', 'Dedi (Sie Qurban)', '6281200000006', 'Ruang Rapat', 20, 'Pendataan hewan qurban dan pembagian tugas.', 'sample', 'sample')
) as v(n, c, d, s, e, p, w, l, q, x, cb, ab)
where not exists (select 1 from events where created_by = 'sample');

-- Pengajuan booking dari publik (menunggu persetujuan)
insert into booking_requests (booking_reference, requester_name, requester_whatsapp, person_in_charge, event_name,
                              category, requested_date, start_time, end_time, location, participants, description)
values
 ('BK-SMPL-AAAA-2345', 'Fajar', '6281300000011', 'Fajar', 'Latihan Hadroh Remaja', 'Kegiatan keagamaan', '2026-11-22', '15:30', '17:30', 'Serambi Masjid', 20, 'Latihan rutin untuk penampilan acara.'),
 ('BK-SMPL-BBBB-2345', 'Nisa', '6281300000012', 'Nisa', 'Rapat Seksi Dokumentasi', 'Rapat', '2026-11-27', '16:00', '17:30', 'Ruang Rapat', 8, 'Pembagian tugas dokumentasi.'),
 ('BK-SMPL-CCCC-2345', 'Rahmat', '6281300000013', 'Rahmat', 'Santunan Anak Yatim', 'Kegiatan sosial', '2026-12-13', '09:00', '12:00', 'Aula Masjid', 60, 'Penyaluran santunan.')
on conflict do nothing;

insert into notifications (audience, booking_id, kind, title, message)
select 'admin', booking_id, 'new_booking', 'Pengajuan booking baru', event_name || ' (' || booking_reference || ')'
  from booking_requests where booking_reference like 'BK-SMPL-%'
   and not exists (select 1 from notifications n where n.booking_id = booking_requests.booking_id);
