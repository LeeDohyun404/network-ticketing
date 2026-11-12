# Network Incident Ticketing API

REST API manajemen tiket gangguan jaringan, terinspirasi alur tiket ICRM+ yang saya gunakan saat magang di PT PLN Icon Plus. API ini mencatat tiket gangguan atau pemeliharaan beserta prioritas dan statusnya, membedakan hak akses admin dan teknisi, serta menghitung waktu respons dan waktu penyelesaian (SLA) tiap tiket.

Stack: Python, Flask, Flask-SQLAlchemy, Flask-JWT-Extended, SQLite (bisa diganti lewat `DATABASE_URL`), pytest.

## Cara menjalankan (Windows PowerShell)

```
py -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # lalu ganti isi SECRET_KEY dan JWT_SECRET_KEY
flask --app run run
```

Server berjalan di `http://127.0.0.1:5000`. Jalankan tes dengan `pytest`.

## Tabel database

**users**: id, nama, email (unik), password_hash, role (`admin` atau `teknisi`)

**tickets**: id, judul, deskripsi, pelanggan, jenis (`gangguan` atau `pemeliharaan`), perangkat, lokasi, prioritas (`rendah`, `sedang`, `tinggi`, `kritis`), status, dibuat_oleh (id user), ditugaskan_ke (id user), created_at, responded_at, resolved_at

**ticket_logs**: id, ticket_id, status_lama, status_baru, diubah_oleh (id user), catatan, waktu

`ticket_logs` dipisah dari `tickets` karena satu tiket bisa berubah status berkali-kali, dan tiap perubahan butuh satu baris catatan sendiri.

## Aturan

- Akun pertama yang didaftarkan otomatis menjadi admin. Setelah itu hanya admin yang bisa membuat akun.
- Alur status: `open` → `in_progress` → `resolved` → `closed`. Status tidak boleh loncat. Tiket `resolved` boleh dibuka lagi ke `in_progress` kalau belum tuntas.
- Admin: membuat, mengubah, menghapus (hanya tiket `open`), dan menugaskan tiket; menutup tiket; melihat ringkasan; membuat akun.
- Teknisi: hanya melihat tiket yang ditugaskan kepadanya, dan mengubah status `open` → `in_progress` → `resolved` beserta catatan.
- SLA: waktu respons = `responded_at` dikurangi `created_at`; waktu penyelesaian = `resolved_at` dikurangi `created_at` (dalam menit).
- Daftar tiket diurutkan dari prioritas tertinggi, lalu yang paling lama menunggu.

## Daftar endpoint

| Metode | Alamat | Akses | Fungsi |
|---|---|---|---|
| POST | /auth/register | akun pertama bebas, setelahnya admin | Buat akun |
| POST | /auth/login | bebas | Login, dapat token JWT |
| GET | /auth/me | login | Data akun sendiri |
| GET | /users | admin | Daftar user (`?role=teknisi`) |
| POST | /tickets | admin | Buat tiket |
| GET | /tickets | login | Daftar tiket (`?status=`, `?prioritas=`, `?jenis=`, `?page=`) |
| GET | /tickets/summary | admin | Jumlah per status dan rata-rata SLA |
| GET | /tickets/<id> | admin atau teknisi yang ditugaskan | Detail beserta riwayat |
| PUT | /tickets/<id> | admin | Ubah data tiket |
| DELETE | /tickets/<id> | admin | Hapus tiket berstatus open |
| PUT | /tickets/<id>/assign | admin | Tugaskan ke teknisi (`{"teknisi_id": 2}`) |
| PUT | /tickets/<id>/status | admin atau teknisi yang ditugaskan | Ubah status (`{"status": "...", "catatan": "..."}`) |

Header untuk endpoint terlindungi: `Authorization: Bearer <token>`.

## Deploy ke Render

Build command: `pip install -r requirements.txt`. Start command: `gunicorn run:app`. Isi `SECRET_KEY`, `JWT_SECRET_KEY`, dan `DATABASE_URL` di bagian Environment. File SQLite di layanan gratis tidak bertahan permanen, jadi untuk demo jangka panjang gunakan database yang disediakan Render dan isi alamatnya di `DATABASE_URL`.

## Pengembangan lanjutan

Unggah foto perangkat (sebelum dan sesudah penanganan), dokumentasi Swagger, dan migrasi database dengan Flask-Migrate.
