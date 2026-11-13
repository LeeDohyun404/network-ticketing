from datetime import datetime, timedelta, timezone
from tests.conftest import auth


def test_crud_maintenance_schedule_berhasil(client, admin_token, teknisi):
    tid, tek_token = teknisi

    # 1. Buat customer & device
    c = client.post("/customers", headers=auth(admin_token), json={"nama": "RS Harapan Sehat"}).get_json()
    d = client.post("/devices", headers=auth(admin_token), json={
        "nama": "Switch Core RS", "jenis": "switch", "customer_id": c["id"], "lokasi": "Gedung A Lt. 1"
    }).get_json()

    # 2. Admin membuat jadwal maintenance
    rencana = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%dT10:00:00")
    r_create = client.post("/maintenance-schedules", headers=auth(admin_token), json={
        "judul": "Pembersihan Rak & Backup Konfigurasi Switch",
        "deskripsi": "Lakukan backup konfigurasi vlan dan bersihkan dust filter",
        "customer_id": c["id"],
        "device_id": d["id"],
        "prioritas": "tinggi",
        "tanggal_rencana": rencana,
        "pengulangan": "mingguan",
    })
    assert r_create.status_code == 201
    sched = r_create.get_json()
    sid = sched["id"]
    assert sched["judul"] == "Pembersihan Rak & Backup Konfigurasi Switch"
    assert sched["prioritas"] == "tinggi"
    assert sched["pelanggan"] == "RS Harapan Sehat"
    assert sched["perangkat"] == "Switch Core RS"
    assert sched["lokasi"] == "Gedung A Lt. 1"
    assert sched["pengulangan"] == "mingguan"
    assert sched["status"] == "terjadwal"
    assert sched["jatuh_tempo"] is False

    # 3. Teknisi dan admin bisa list dan get detail
    r_list = client.get("/maintenance-schedules", headers=auth(tek_token))
    assert r_list.status_code == 200
    assert any(s["id"] == sid for s in r_list.get_json()["data"])

    r_get = client.get(f"/maintenance-schedules/{sid}", headers=auth(tek_token))
    assert r_get.status_code == 200
    assert r_get.get_json()["id"] == sid

    # 4. Admin update jadwal
    r_put = client.post if False else client.put
    r_up = r_put(f"/maintenance-schedules/{sid}", headers=auth(admin_token), json={
        "prioritas": "kritis",
        "deskripsi": "Backup konfigurasi dan uji failover link redundant",
    })
    assert r_up.status_code == 200
    assert r_up.get_json()["prioritas"] == "kritis"
    assert "failover" in r_up.get_json()["deskripsi"]

    # 5. Admin delete jadwal
    r_del = client.delete(f"/maintenance-schedules/{sid}", headers=auth(admin_token))
    assert r_del.status_code == 200
    assert r_del.get_json()["pesan"] == "Jadwal maintenance dihapus"

    # Verifikasi sudah terhapus
    assert client.get(f"/maintenance-schedules/{sid}", headers=auth(admin_token)).status_code == 404


def test_hak_akses_teknisi_maintenance(client, admin_token, teknisi):
    tid, tek_token = teknisi

    # Admin buat 1 jadwal
    rencana = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%dT14:00:00")
    sched = client.post("/maintenance-schedules", headers=auth(admin_token), json={
        "judul": "Inspeksi ODP Fiber Songgom",
        "tanggal_rencana": rencana,
    }).get_json()
    sid = sched["id"]

    # Teknisi coba buat -> 403
    assert client.post("/maintenance-schedules", headers=auth(tek_token), json={
        "judul": "Tes teknisi buat", "tanggal_rencana": rencana
    }).status_code == 403

    # Teknisi coba update -> 403
    assert client.put(f"/maintenance-schedules/{sid}", headers=auth(tek_token), json={
        "status": "dibatalkan"
    }).status_code == 403

    # Teknisi coba generate ticket -> 403
    assert client.post(f"/maintenance-schedules/{sid}/generate-ticket", headers=auth(tek_token)).status_code == 403

    # Teknisi coba delete -> 403
    assert client.delete(f"/maintenance-schedules/{sid}", headers=auth(tek_token)).status_code == 403

    # Teknisi BISA baca
    assert client.get("/maintenance-schedules", headers=auth(tek_token)).status_code == 200
    assert client.get(f"/maintenance-schedules/{sid}", headers=auth(tek_token)).status_code == 200


def test_validasi_maintenance_gagal(client, admin_token):
    rencana = "2026-12-01T08:00:00"

    # Judul kosong / tidak ada
    assert client.post("/maintenance-schedules", headers=auth(admin_token), json={
        "tanggal_rencana": rencana
    }).status_code == 400
    assert client.post("/maintenance-schedules", headers=auth(admin_token), json={
        "judul": "   ", "tanggal_rencana": rencana
    }).status_code == 400

    # Tanggal rencana tidak ada atau format salah
    assert client.post("/maintenance-schedules", headers=auth(admin_token), json={
        "judul": "Tes validasi"
    }).status_code == 400
    assert client.post("/maintenance-schedules", headers=auth(admin_token), json={
        "judul": "Tes validasi", "tanggal_rencana": "tanggal-ngawur"
    }).status_code == 400

    # Prioritas tidak valid
    assert client.post("/maintenance-schedules", headers=auth(admin_token), json={
        "judul": "Tes validasi", "tanggal_rencana": rencana, "prioritas": "urgent"
    }).status_code == 400

    # Pengulangan tidak valid
    assert client.post("/maintenance-schedules", headers=auth(admin_token), json={
        "judul": "Tes validasi", "tanggal_rencana": rencana, "pengulangan": "tahunan"
    }).status_code == 400

    # Customer tidak ditemukan
    assert client.post("/maintenance-schedules", headers=auth(admin_token), json={
        "judul": "Tes validasi", "tanggal_rencana": rencana, "customer_id": 99999
    }).status_code == 400

    # Device tidak ditemukan
    assert client.post("/maintenance-schedules", headers=auth(admin_token), json={
        "judul": "Tes validasi", "tanggal_rencana": rencana, "device_id": 99999
    }).status_code == 400


def test_generate_ticket_dari_schedule_non_recurring(client, admin_token):
    rencana = "2026-11-20T09:00:00"
    r = client.post("/maintenance-schedules", headers=auth(admin_token), json={
        "judul": "Peremajaan Kabel Patchcord Ruang Server",
        "deskripsi": "Ganti kabel patchcord kuning single mode yang tertekuk",
        "pelanggan": "Kantor Pusat",
        "perangkat": "Patch Panel ODF-01",
        "lokasi": "R. Server Lt. Dasar",
        "prioritas": "sedang",
        "tanggal_rencana": rencana,
        "pengulangan": "tidak_ada",
    })
    sid = r.get_json()["id"]

    # Generate ticket
    r_gen = client.post(f"/maintenance-schedules/{sid}/generate-ticket", headers=auth(admin_token))
    assert r_gen.status_code == 201
    body = r_gen.get_json()
    assert "tiket" in body
    assert "jadwal" in body

    ticket = body["tiket"]
    assert ticket["judul"] == "Peremajaan Kabel Patchcord Ruang Server"
    assert ticket["jenis"] == "pemeliharaan"
    assert ticket["pelanggan"] == "Kantor Pusat"
    assert ticket["perangkat"] == "Patch Panel ODF-01"
    assert ticket["lokasi"] == "R. Server Lt. Dasar"
    assert ticket["status"] == "open"
    assert "[Pemeliharaan Terjadwal]" in ticket["deskripsi"]

    jadwal = body["jadwal"]
    assert jadwal["status"] == "selesai"  # Karena non-recurring, otomatis selesai
    assert jadwal["last_ticket_id"] == ticket["id"]


def test_generate_ticket_dari_schedule_recurring_mingguan(client, admin_token):
    # Buat jadwal berulang mingguan
    t0 = datetime(2026, 11, 20, 10, 0, 0)
    r = client.post("/maintenance-schedules", headers=auth(admin_token), json={
        "judul": "Inspeksi Rutin OLT Mingguan",
        "tanggal_rencana": t0.strftime("%Y-%m-%dT%H:%M:%S"),
        "pengulangan": "mingguan",
    })
    sid = r.get_json()["id"]

    # Generate ticket pertama
    r_gen = client.post(f"/maintenance-schedules/{sid}/generate-ticket", headers=auth(admin_token))
    assert r_gen.status_code == 201
    jadwal = r_gen.get_json()["jadwal"]

    # Karena recurring, status tetap 'terjadwal' dan tanggal maju 7 hari
    assert jadwal["status"] == "terjadwal"
    t1 = datetime.fromisoformat(jadwal["tanggal_rencana"])
    assert (t1 - t0).days == 7


def test_filter_jatuh_tempo_dan_status(client, admin_token):
    # 1. Jadwal masa lampau (overdue)
    lampau = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%dT08:00:00")
    client.post("/maintenance-schedules", headers=auth(admin_token), json={
        "judul": "Jadwal Terlambat 1", "tanggal_rencana": lampau, "status": "terjadwal"
    })

    # 2. Jadwal masa depan (belum overdue)
    depan = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%dT08:00:00")
    client.post("/maintenance-schedules", headers=auth(admin_token), json={
        "judul": "Jadwal Masa Depan 2", "tanggal_rencana": depan, "status": "terjadwal"
    })

    # Filter jatuh tempo
    r_due = client.get("/maintenance-schedules?jatuh_tempo=true", headers=auth(admin_token))
    assert r_due.status_code == 200
    items = r_due.get_json()["data"]
    assert any("Jadwal Terlambat 1" in s["judul"] for s in items)
    assert not any("Jadwal Masa Depan 2" in s["judul"] for s in items)

