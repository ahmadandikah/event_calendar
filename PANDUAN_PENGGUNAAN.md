# Panduan Penggunaan — Kalender Kegiatan Panitia

Aplikasi bisa dibuka dari HP maupun komputer melalui link yang dibagikan Ketua Panitia.
**Tidak perlu daftar atau login.**

---

## A. Untuk Pengguna Umum (anggota panitia / pemohon)

### 1. Melihat kalender
1. Buka menu **Kalender**.
2. Pilih tampilan **Bulan**, **Minggu**, atau **Agenda** (daftar). Tombol ‹ › untuk pindah bulan,
   **Hari ini** untuk kembali ke tanggal sekarang.
3. Arti warna:
   | Warna | Arti |
   |---|---|
   | 🟦 Biru tua | Agenda resmi (sudah disetujui) |
   | 🟨 Kuning, garis putus-putus, ⏳ | Pengajuan yang menunggu persetujuan |
   | 🟩 Latar hijau muda | Tanggal masih kosong |
   | 🟥 Merah muda | Libur nasional / cuti bersama |
   | 🕌 Hijau | Hari raya Islam (Idul Fitri, Idul Adha, Isra Mikraj) |
   | 🔒 Abu-abu | Tanggal dikunci — tidak bisa dibooking |
   | ⭐ Ungu | Tanggal eksklusif — hanya boleh satu agenda |
4. Klik sebuah **agenda** untuk melihat detailnya. Gunakan **Filter, pencarian & tampilan** untuk
   menyaring kategori atau mencari nama kegiatan.

### 2. Mengajukan booking
**Cara cepat:** klik tanggal di kalender → lihat jam yang sudah terisi → isi formulir di bawahnya.
**Cara lain:** menu **Ajukan Booking** → pilih tanggal → isi formulir.

Isi: nama pemohon, nomor WhatsApp, (penanggung jawab bila berbeda), nama kegiatan, kategori, jam
mulai & selesai, lokasi, jumlah peserta, deskripsi, catatan. Jawab soal verifikasi, centang
pernyataan, lalu **Kirim Pengajuan Booking**.

Setelah terkirim muncul **Kode Referensi Booking**, contoh `BK-7KQ2-M9XD-4TPA`.
👉 **Simpan kode ini.** Tekan **Simpan kode ke WhatsApp saya** agar kode terkirim ke chat Anda sendiri.

Aturan:
* Kegiatan berbeda boleh di tanggal yang sama asal **jamnya tidak bertabrakan**.
* Jam yang sudah dipakai agenda lain atau pengajuan lain yang masih menunggu tidak bisa dipilih.
* Satu nomor WhatsApp maksimal memiliki 5 pengajuan yang masih menunggu.

### 3. Mengecek status
Menu **Cek Status Booking** → masukkan kode → **Cek Status**. Anda akan melihat:
* Status: **Menunggu Persetujuan**, **Disetujui**, **Ditolak**, atau **Dibatalkan**.
* Catatan atau alasan dari Ketua Panitia, dan bila jadwal Anda disesuaikan.
* Riwayat notifikasi (diterima, disetujui, jadwal diubah, dll.).

### 4. Membatalkan pengajuan
Hanya bisa selama status **Menunggu Persetujuan**. Di halaman Cek Status, isi **nomor WhatsApp yang
sama** dengan saat mengajukan → **Batalkan Pengajuan** → konfirmasi.
Agenda yang sudah disetujui hanya dapat diubah/dibatalkan oleh Ketua Panitia — silakan hubungi beliau.

---

## B. Untuk Ketua Panitia (Admin)

### 1. Masuk & keluar Admin Mode
1. Klik **Admin Mode** di sidebar (di HP: ketuk ikon » di kiri atas untuk membuka sidebar).
2. Isi nama Anda (tercatat di audit log), **Admin Access Key** bila diminta, dan **PIN Admin** → **Masuk**.
   Tip: simpan tautan rahasia `…/?ak=KUNCI-ANDA` di bookmark, maka Access Key terisi otomatis.
3. Menu khusus muncul di bagian **Ketua Panitia**.
4. Keluar dengan **Logout Admin**. Admin Mode juga berakhir otomatis setelah 30 menit tidak aktif
   atau ketika halaman di-refresh/ditutup.

> Jangan pernah membagikan PIN atau Access Key. Bila curiga bocor: ganti PIN (lihat README
> bagian 7) lalu **Pengaturan → Keluarkan semua sesi admin lain**.

### 2. Notifikasi
Tombol **Notifikasi (n)** di sidebar berisi pengajuan baru dan pembatalan oleh pemohon. Klik
**Tandai semua sudah dibaca** setelah ditinjau. Menu **Approval (n)** menunjukkan jumlah pengajuan
yang menunggu.

### 3. Menyetujui / menolak (menu Approval)
1. Tab **Menunggu persetujuan** menampilkan setiap pengajuan beserta identitas & nomor WA pemohon.
   Tanda **⚠️ BENTROK** muncul bila jamnya beririsan dengan agenda lain.
2. Di kotak **Keputusan**:
   * Ubah **tanggal/jam** bila perlu (pemohon akan diberi tahu jadwal yang disesuaikan).
   * Tulis **catatan untuk pemohon** (opsional).
   * **Setujui** → agenda langsung tampil di kalender sebagai agenda resmi.
   * **Tolak** → wajib isi **alasan penolakan**, lalu konfirmasi.
3. Bila bentrok/tanggal dikunci tetapi Anda tetap ingin menyetujui, centang **Override konflik**.
   Tindakan ini tercatat di audit log.
4. Setelah memutuskan, klik **Kabari … via WhatsApp** — WhatsApp terbuka dengan pesan siap kirim.
5. Tab **Semua pengajuan**: cari/filter berdasarkan status, kategori, penanggung jawab; unduh CSV.

### 4. Mengelola agenda (menu Kelola Agenda)
* **Tambah agenda**: agenda dari Ketua langsung berstatus disetujui.
* **Daftar agenda**: klik satu baris tabel untuk membuka panel kelola:
  * **Ubah agenda / jadwal** — ubah nama, tanggal, jam, PJ, lokasi, dsb. Bila agenda berasal dari
    pengajuan publik, pemohon menerima notifikasi “Jadwal diubah”.
  * **Batalkan agenda** — isi alasan → konfirmasi. Agenda hilang dari kalender, riwayat tetap tersimpan.
  * **Hapus permanen** — hanya untuk data yang salah input; tidak dapat dibatalkan.
* Dari kalender, klik agenda → **Kelola agenda ini**, atau klik tanggal → **Tambah agenda resmi di
  tanggal ini**.

### 5. Mengatur tanggal (menu Tanggal & Hari Libur)
* **Atur satu tanggal**: beri nama hari libur/penanda, jenisnya, dan status booking:
  * **Terbuka** — normal.
  * **Dikunci** — publik tidak bisa mengajukan booking.
  * **Eksklusif** — hanya satu agenda boleh ada di tanggal itu.
* **Kunci rentang tanggal**: mis. kunci 9–15 Maret 2027 selama libur Idul Fitri.
* Bila Kementerian Agama menetapkan tanggal Idul Fitri/Idul Adha berbeda, perbarui di sini lalu
  sesuaikan **akhir periode** di Pengaturan.

### 6. Audit Log
Riwayat lengkap: siapa mengajukan, menyetujui, menolak, mengubah jadwal, membatalkan, menghapus,
mengunci tanggal, mengubah pengaturan, serta login/percobaan PIN salah. Bisa dicari, difilter, dan
diunduh CSV.

### 7. Pengaturan
* Periode kalender (awal & akhir), jam operasional booking.
* Buka/tutup pengajuan booking sementara.
* Batas pengajuan pending per nomor WhatsApp.
* Pengumuman yang tampil di Dashboard.
* Status keamanan & notifikasi, serta tombol mengeluarkan semua sesi admin lain.
