def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_tambah_komentar_admin_dan_teknisi_berhasil(client, admin_token, teknisi, ticket_id):
    tek_id, tek_token = teknisi
    # Tugaskan tiket ke teknisi
    client.put(f"/tickets/{ticket_id}/assign", headers=auth(admin_token), json={"teknisi_id": tek_id})

    # Admin menambah komentar
    r = client.post(f"/tickets/{ticket_id}/comments", headers=auth(admin_token), json={"pesan": "Mohon segera ditindaklanjuti ke lokasi."})
    assert r.status_code == 201
    body = r.get_json()
    assert body["pesan"] == "Mohon segera ditindaklanjuti ke lokasi."
    assert body["nama_penulis"] == "Admin"
    assert body["role_penulis"] == "admin"
    assert body["ticket_id"] == ticket_id

    # Teknisi yang ditugaskan menambah komentar
    r2 = client.post(f"/tickets/{ticket_id}/comments", headers=auth(tek_token), json={"pesan": "Siap, sedang dalam perjalanan membawa kabel cadangan."})
    assert r2.status_code == 201
    body2 = r2.get_json()
    assert body2["pesan"] == "Siap, sedang dalam perjalanan membawa kabel cadangan."
    assert body2["role_penulis"] == "teknisi"

    # Ambil list komentar
    r_list = client.get(f"/tickets/{ticket_id}/comments", headers=auth(tek_token))
    assert r_list.status_code == 200
    data = r_list.get_json()["data"]
    assert len(data) == 2
    assert data[0]["pesan"] == "Mohon segera ditindaklanjuti ke lokasi."
    assert data[1]["pesan"] == "Siap, sedang dalam perjalanan membawa kabel cadangan."

    # Periksa di detail tiket (GET /tickets/<id>)
    r_detail = client.get(f"/tickets/{ticket_id}", headers=auth(admin_token))
    assert r_detail.status_code == 200
    detail_body = r_detail.get_json()
    assert "komentar" in detail_body
    assert len(detail_body["komentar"]) == 2


def test_validasi_komentar_gagal(client, admin_token, ticket_id):
    # Pesan kosong
    r = client.post(f"/tickets/{ticket_id}/comments", headers=auth(admin_token), json={"pesan": ""})
    assert r.status_code == 400
    assert "wajib diisi" in r.get_json()["error"]

    # Pesan hanya spasi
    r = client.post(f"/tickets/{ticket_id}/comments", headers=auth(admin_token), json={"pesan": "   "})
    assert r.status_code == 400

    # Pesan bukan string
    r = client.post(f"/tickets/{ticket_id}/comments", headers=auth(admin_token), json={"pesan": 12345})
    assert r.status_code == 400

    # Pesan melebihi 2000 karakter
    r = client.post(f"/tickets/{ticket_id}/comments", headers=auth(admin_token), json={"pesan": "A" * 2001})
    assert r.status_code == 400
    assert "maksimal 2000" in r.get_json()["error"]


def test_pembatasan_hak_akses_komentar(client, admin_token, ticket_id):
    # Buat teknisi 1 dan teknisi 2
    r_inv1 = client.post("/users/invite", headers=auth(admin_token), json={"nama": "Teknisi Satu", "email": "tek1@contoh.com"})
    token1 = r_inv1.get_json()["link_aktivasi"].split("aktivasi=")[1]
    client.post("/auth/activate", json={"token": token1, "password": "password123"})
    token_tek1 = client.post("/auth/login", json={"email": "tek1@contoh.com", "password": "password123"}).get_json()["access_token"]
    user_tek1_id = client.get("/auth/me", headers=auth(token_tek1)).get_json()["id"]

    r_inv2 = client.post("/users/invite", headers=auth(admin_token), json={"nama": "Teknisi Dua", "email": "tek2@contoh.com"})
    token2 = r_inv2.get_json()["link_aktivasi"].split("aktivasi=")[1]
    client.post("/auth/activate", json={"token": token2, "password": "password123"})
    token_tek2 = client.post("/auth/login", json={"email": "tek2@contoh.com", "password": "password123"}).get_json()["access_token"]

    # Tugaskan tiket ke Teknisi Satu
    client.put(f"/tickets/{ticket_id}/assign", headers=auth(admin_token), json={"teknisi_id": user_tek1_id})

    # Teknisi Dua tidak boleh melihat atau memberi komentar pada tiket Teknisi Satu
    r_view = client.get(f"/tickets/{ticket_id}/comments", headers=auth(token_tek2))
    assert r_view.status_code == 404

    r_post = client.post(f"/tickets/{ticket_id}/comments", headers=auth(token_tek2), json={"pesan": "Komentar teknisi tak berhak"})
    assert r_post.status_code == 404
