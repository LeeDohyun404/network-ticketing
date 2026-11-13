from tests.conftest import auth


def test_crud_customer_berhasil(client, admin_token, teknisi):
    tid, tek_token = teknisi

    # 1. Admin buat customer
    r = client.post("/customers", headers=auth(admin_token), json={
        "nama": "PT Telekomunikasi Maju",
        "alamat": "Jl. Gatot Subroto No. 12, Jakarta",
        "kontak": "08123456789 (Pak Budi)",
    })
    assert r.status_code == 201
    cust = r.get_json()
    cid = cust["id"]
    assert cust["nama"] == "PT Telekomunikasi Maju"
    assert "Jakarta" in cust["alamat"]

    # 2. Teknisi dan admin bisa melihat list customer
    r_list = client.get("/customers", headers=auth(tek_token))
    assert r_list.status_code == 200
    assert any(c["id"] == cid for c in r_list.get_json()["data"])

    # 3. Ambil detail customer (with devices)
    r_get = client.get(f"/customers/{cid}", headers=auth(admin_token))
    assert r_get.status_code == 200
    assert "devices" in r_get.get_json()

    # 4. Admin update customer
    r_put = client.put(f"/customers/{cid}", headers=auth(admin_token), json={
        "nama": "PT Telekomunikasi Maju Jaya",
    })
    assert r_put.status_code == 200
    assert r_put.get_json()["nama"] == "PT Telekomunikasi Maju Jaya"

    # 5. Admin hapus customer (tanpa tiket aktif)
    r_del = client.delete(f"/customers/{cid}", headers=auth(admin_token))
    assert r_del.status_code == 200
    assert r_del.get_json()["pesan"] == "Pelanggan dihapus"


def test_crud_device_berhasil(client, admin_token, teknisi):
    tid, tek_token = teknisi

    # Buat customer terlebih dahulu
    r_cust = client.post("/customers", headers=auth(admin_token), json={
        "nama": "PT Data Nusantara",
    })
    cid = r_cust.get_json()["id"]

    # 1. Admin buat device
    r_dev = client.post("/devices", headers=auth(admin_token), json={
        "nama": "Core Switch SW-01",
        "jenis": "switch",
        "lokasi": "Ruang Server Lt. 2",
        "customer_id": cid,
    })
    assert r_dev.status_code == 201
    dev = r_dev.get_json()
    did = dev["id"]
    assert dev["customer_id"] == cid
    assert dev["jenis"] == "switch"

    # 2. Teknisi & admin list devices (filter by customer_id)
    r_list = client.get(f"/devices?customer_id={cid}", headers=auth(tek_token))
    assert r_list.status_code == 200
    items = r_list.get_json()["data"]
    assert len(items) == 1
    assert items[0]["id"] == did

    # 3. Detail device
    r_get = client.get(f"/devices/{did}", headers=auth(tek_token))
    assert r_get.status_code == 200
    assert r_get.get_json()["nama"] == "Core Switch SW-01"

    # 4. Update device
    r_put = client.put(f"/devices/{did}", headers=auth(admin_token), json={
        "lokasi": "Ruang Server Lt. 3",
    })
    assert r_put.status_code == 200
    assert r_put.get_json()["lokasi"] == "Ruang Server Lt. 3"

    # 5. Hapus device
    r_del = client.delete(f"/devices/{did}", headers=auth(admin_token))
    assert r_del.status_code == 200
    assert r_del.get_json()["pesan"] == "Perangkat dihapus"


def test_buat_tiket_dengan_customer_dan_device(client, admin_token):
    # Buat customer dan 2 device
    c = client.post("/customers", headers=auth(admin_token), json={"nama": "Bank Sentral"}).get_json()
    cid = c["id"]

    d = client.post("/devices", headers=auth(admin_token), json={
        "nama": "Router Edge RE-01", "jenis": "router", "lokasi": "Gedung Utama Lt. 1", "customer_id": cid
    }).get_json()
    did = d["id"]

    # Buat tiket dengan menyertakan customer_id dan device_id
    r = client.post("/tickets", headers=auth(admin_token), json={
        "judul": "Interface GigabitEthernet0 Down",
        "customer_id": cid,
        "device_id": did,
        "prioritas": "tinggi",
    })
    assert r.status_code == 201
    ticket = r.get_json()
    assert ticket["customer_id"] == cid
    assert ticket["device_id"] == did
    # Pelanggan dan perangkat tersinkronisasi otomatis
    assert ticket["pelanggan"] == "Bank Sentral"
    assert ticket["perangkat"] == "Router Edge RE-01"
    assert ticket["lokasi"] == "Gedung Utama Lt. 1"

    # Filter daftar tiket berdasarkan customer_id dan device_id
    r_f1 = client.get(f"/tickets?customer_id={cid}", headers=auth(admin_token))
    assert len(r_f1.get_json()["data"]) >= 1

    r_f2 = client.get(f"/tickets?device_id={did}", headers=auth(admin_token))
    assert len(r_f2.get_json()["data"]) >= 1


def test_validasi_gagal_customer_dan_device(client, admin_token):
    # Customer tanpa nama
    assert client.post("/customers", headers=auth(admin_token), json={"alamat": "Jalan Raya"}).status_code == 400

    # Device tanpa nama ditolak
    assert client.post("/devices", headers=auth(admin_token), json={"customer_id": 1}).status_code == 400
    assert client.post("/devices", headers=auth(admin_token), json={"nama": ""}).status_code == 400

    # Customer tidak ditemukan
    assert client.post("/devices", headers=auth(admin_token), json={
        "nama": "Router", "customer_id": 99999
    }).status_code == 400

    # Device mandiri tanpa customer_id BERHASIL (perangkat jalan / infrastruktur umum)
    r_mandiri = client.post("/devices", headers=auth(admin_token), json={
        "nama": "Tiang FO P12 Songgom",
        "jenis": "tiang_fo",
        "lokasi": "Jl. Raya Songgom Km 3",
    })
    assert r_mandiri.status_code == 201
    dev_mandiri = r_mandiri.get_json()
    assert dev_mandiri["customer_id"] is None
    assert dev_mandiri["nama_pelanggan"] is None
    assert dev_mandiri["nama"] == "Tiang FO P12 Songgom"

    # Tiket dengan customer_id tidak valid
    assert client.post("/tickets", headers=auth(admin_token), json={
        "judul": "Gangguan link", "customer_id": 99999
    }).status_code == 400

    # Tiket dengan mismatch customer dan device
    c1 = client.post("/customers", headers=auth(admin_token), json={"nama": "Klien 1"}).get_json()["id"]
    c2 = client.post("/customers", headers=auth(admin_token), json={"nama": "Klien 2"}).get_json()["id"]
    d_c1 = client.post("/devices", headers=auth(admin_token), json={
        "nama": "Switch 1", "customer_id": c1
    }).get_json()["id"]

    # Tiket mengklaim milik c2 tapi devicenya milik c1
    r_mismatch = client.post("/tickets", headers=auth(admin_token), json={
        "judul": "Test Mismatch", "customer_id": c2, "device_id": d_c1
    })
    assert r_mismatch.status_code == 400
    assert "tidak terdaftar pada pelanggan ini" in r_mismatch.get_json()["error"]


def test_proteksi_hapus_customer_dan_device_berstatus_aktif(client, admin_token):
    # Buat customer, device, dan tiket open
    c = client.post("/customers", headers=auth(admin_token), json={"nama": "PT Aktif Selalu"}).get_json()
    cid = c["id"]

    d = client.post("/devices", headers=auth(admin_token), json={
        "nama": "OLT Huawei", "customer_id": cid
    }).get_json()
    did = d["id"]

    t = client.post("/tickets", headers=auth(admin_token), json={
        "judul": "PON Port LOS", "customer_id": cid, "device_id": did
    }).get_json()
    tid = t["id"]

    # Menghapus device yang masih ada tiket aktif harus ditolak 409
    r_del_d = client.delete(f"/devices/{did}", headers=auth(admin_token))
    assert r_del_d.status_code == 409
    assert "tiket aktif" in r_del_d.get_json()["error"]

    # Menghapus customer yang masih ada tiket aktif harus ditolak 409
    r_del_c = client.delete(f"/customers/{cid}", headers=auth(admin_token))
    assert r_del_c.status_code == 409
    assert "tiket aktif" in r_del_c.get_json()["error"]

    # Hapus tiket (berstatus open) terlebih dahulu
    client.delete(f"/tickets/{tid}", headers=auth(admin_token))

    # Sekarang device dan customer dapat dihapus
    assert client.delete(f"/devices/{did}", headers=auth(admin_token)).status_code == 200
    assert client.delete(f"/customers/{cid}", headers=auth(admin_token)).status_code == 200


def test_pembatasan_hak_akses_customer_dan_device(client, teknisi):
    tid, tek_token = teknisi

    # Teknisi dilarang membuat customer (403)
    assert client.post("/customers", headers=auth(tek_token), json={"nama": "Illegal"}).status_code == 403

    # Teknisi dilarang membuat device (403)
    assert client.post("/devices", headers=auth(tek_token), json={"nama": "Illegal", "customer_id": 1}).status_code == 403

    # Anonim dilarang (401)
    assert client.get("/customers").status_code == 401
    assert client.get("/devices").status_code == 401

