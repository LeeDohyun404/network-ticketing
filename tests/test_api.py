from conftest import auth


# ---------- Autentikasi ----------
def test_akun_pertama_menjadi_admin(client):
    r = client.post("/auth/register", json={"nama": "A", "email": "a@contoh.com", "password": "rahasia123"})
    assert r.status_code == 201
    assert r.get_json()["role"] == "admin"


def test_registrasi_setelah_admin_perlu_token(client, admin_token):
    r = client.post("/auth/register", json={"nama": "B", "email": "b@contoh.com", "password": "rahasia123"})
    assert r.status_code == 401


def test_email_ganda_ditolak(client, admin_token):
    r = client.post("/auth/register", headers=auth(admin_token),
                    json={"nama": "X", "email": "admin@contoh.com", "password": "rahasia123"})
    assert r.status_code == 409


def test_password_pendek_ditolak(client):
    r = client.post("/auth/register", json={"nama": "A", "email": "a@contoh.com", "password": "123"})
    assert r.status_code == 400


def test_login_berhasil_dan_gagal(client, admin_token):
    assert client.post("/auth/login", json={"email": "admin@contoh.com", "password": "salah"}).status_code == 401
    assert client.post("/auth/login", json={"email": "admin@contoh.com", "password": "rahasia123"}).status_code == 200


def test_password_tersimpan_sebagai_hash(app, admin_token):
    from app.models import User
    user = User.query.filter_by(email="admin@contoh.com").first()
    assert user.password_hash != "rahasia123"
    assert user.check_password("rahasia123")


def test_tanpa_token_ditolak(client):
    assert client.get("/tickets").status_code == 401


# ---------- Tiket ----------
def test_buat_dan_ambil_tiket(client, admin_token, ticket_id):
    r = client.get(f"/tickets/{ticket_id}", headers=auth(admin_token))
    assert r.status_code == 200
    assert r.get_json()["status"] == "open"


def test_tiket_tanpa_judul_ditolak(client, admin_token):
    r = client.post("/tickets", headers=auth(admin_token), json={"pelanggan": "PT X"})
    assert r.status_code == 400


def test_teknisi_tidak_boleh_membuat_tiket(client, teknisi):
    _, token = teknisi
    r = client.post("/tickets", headers=auth(token), json={"judul": "x", "pelanggan": "y"})
    assert r.status_code == 403


def test_filter_prioritas_dan_urutan(client, admin_token):
    for judul, prio in (("rendah1", "rendah"), ("kritis1", "kritis"), ("sedang1", "sedang")):
        client.post("/tickets", headers=auth(admin_token), json={"judul": judul, "pelanggan": "P", "prioritas": prio})
    data = client.get("/tickets", headers=auth(admin_token)).get_json()["data"]
    assert [t["judul"] for t in data] == ["kritis1", "sedang1", "rendah1"]
    only = client.get("/tickets?prioritas=kritis", headers=auth(admin_token)).get_json()["data"]
    assert len(only) == 1 and only[0]["judul"] == "kritis1"


def test_tugaskan_hanya_ke_teknisi(client, admin_token, teknisi, ticket_id):
    tid, _ = teknisi
    r = client.put(f"/tickets/{ticket_id}/assign", headers=auth(admin_token), json={"teknisi_id": tid})
    assert r.status_code == 200 and r.get_json()["ditugaskan_ke"] == tid
    admin_id = client.get("/auth/me", headers=auth(admin_token)).get_json()["id"]
    r = client.put(f"/tickets/{ticket_id}/assign", headers=auth(admin_token), json={"teknisi_id": admin_id})
    assert r.status_code == 400


def test_teknisi_hanya_melihat_tiket_miliknya(client, admin_token, teknisi, ticket_id):
    _, token = teknisi
    assert client.get("/tickets", headers=auth(token)).get_json()["total"] == 0
    assert client.get(f"/tickets/{ticket_id}", headers=auth(token)).status_code == 404


def test_teknisi_lain_tidak_bisa_ubah_status(client, admin_token, teknisi, ticket_id):
    tid, token = teknisi
    client.put(f"/tickets/{ticket_id}/assign", headers=auth(admin_token), json={"teknisi_id": tid})
    r = client.post("/auth/register", headers=auth(admin_token),
                    json={"nama": "Sari", "email": "sari@contoh.com", "password": "rahasia123", "role": "teknisi"})
    assert r.status_code == 201
    other = client.post("/auth/login", json={"email": "sari@contoh.com", "password": "rahasia123"}).get_json()["access_token"]
    r = client.put(f"/tickets/{ticket_id}/status", headers=auth(other), json={"status": "in_progress"})
    assert r.status_code == 404


# ---------- Status, riwayat, SLA ----------
def test_alur_status_lengkap_dan_log(client, admin_token, teknisi, ticket_id):
    tid, token = teknisi
    client.put(f"/tickets/{ticket_id}/assign", headers=auth(admin_token), json={"teknisi_id": tid})

    r = client.put(f"/tickets/{ticket_id}/status", headers=auth(token), json={"status": "in_progress", "catatan": "Menuju lokasi"})
    assert r.status_code == 200 and r.get_json()["responded_at"] is not None

    r = client.put(f"/tickets/{ticket_id}/status", headers=auth(token), json={"status": "resolved", "catatan": "Kabel diganti"})
    body = r.get_json()
    assert body["resolved_at"] is not None
    assert body["sla"]["respons_menit"] is not None and body["sla"]["penyelesaian_menit"] is not None

    r = client.put(f"/tickets/{ticket_id}/status", headers=auth(admin_token), json={"status": "closed"})
    body = r.get_json()
    assert body["status"] == "closed"
    assert [(l["status_lama"], l["status_baru"]) for l in body["logs"]] == [
        ("open", "in_progress"), ("in_progress", "resolved"), ("resolved", "closed")]


def test_status_tidak_boleh_loncat(client, admin_token, teknisi, ticket_id):
    tid, token = teknisi
    client.put(f"/tickets/{ticket_id}/assign", headers=auth(admin_token), json={"teknisi_id": tid})
    r = client.put(f"/tickets/{ticket_id}/status", headers=auth(token), json={"status": "resolved"})
    assert r.status_code == 409


def test_tiket_belum_ditugaskan_tidak_bisa_diproses(client, admin_token, ticket_id):
    r = client.put(f"/tickets/{ticket_id}/status", headers=auth(admin_token), json={"status": "in_progress"})
    assert r.status_code == 409


def test_teknisi_tidak_boleh_menutup_tiket(client, admin_token, teknisi, ticket_id):
    tid, token = teknisi
    client.put(f"/tickets/{ticket_id}/assign", headers=auth(admin_token), json={"teknisi_id": tid})
    client.put(f"/tickets/{ticket_id}/status", headers=auth(token), json={"status": "in_progress"})
    client.put(f"/tickets/{ticket_id}/status", headers=auth(token), json={"status": "resolved"})
    r = client.put(f"/tickets/{ticket_id}/status", headers=auth(token), json={"status": "closed"})
    assert r.status_code == 403


def test_ringkasan(client, admin_token, teknisi, ticket_id):
    tid, token = teknisi
    client.put(f"/tickets/{ticket_id}/assign", headers=auth(admin_token), json={"teknisi_id": tid})
    client.put(f"/tickets/{ticket_id}/status", headers=auth(token), json={"status": "in_progress"})
    data = client.get("/tickets/summary", headers=auth(admin_token)).get_json()
    assert data["total"] == 1
    assert data["per_status"]["in_progress"] == 1
    assert data["rata_rata_respons_menit"] is not None


def test_hapus_hanya_tiket_open(client, admin_token, teknisi, ticket_id):
    tid, token = teknisi
    client.put(f"/tickets/{ticket_id}/assign", headers=auth(admin_token), json={"teknisi_id": tid})
    client.put(f"/tickets/{ticket_id}/status", headers=auth(token), json={"status": "in_progress"})
    assert client.delete(f"/tickets/{ticket_id}", headers=auth(admin_token)).status_code == 409


def test_halaman_ui_tersedia(client):
    r = client.get("/ui")
    assert r.status_code == 200
    assert b"Network Incident Ticketing" in r.data
    r.close()
