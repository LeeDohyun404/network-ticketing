from tests.conftest import auth


def test_audit_penugasan_dan_filter(client, admin_token, teknisi, ticket_id):
    tid, tek_token = teknisi

    # 1. Tugaskan tiket ke teknisi
    r_assign = client.put(f"/tickets/{ticket_id}/assign", headers=auth(admin_token), json={
        "teknisi_id": tid,
    })
    assert r_assign.status_code == 200

    # 2. Ambil riwayat audit lewat GET /tickets/<id>/logs
    r_logs = client.get(f"/tickets/{ticket_id}/logs", headers=auth(admin_token))
    assert r_logs.status_code == 200
    logs = r_logs.get_json()["data"]
    assert len(logs) >= 1

    assign_log = [l for l in logs if l["aksi"] == "penugasan"][0]
    assert assign_log["field_diubah"] == "ditugaskan_ke"
    assert assign_log["nilai_lama"] == "Belum ditugaskan"
    assert assign_log["nilai_baru"] == "Budi"
    assert assign_log["nama_pengubah"] == "Admin"

    # 3. Filter riwayat berdasarkan aksi (?aksi=penugasan)
    r_filter = client.get(f"/tickets/{ticket_id}/logs?aksi=penugasan", headers=auth(admin_token))
    assert r_filter.status_code == 200
    filtered_logs = r_filter.get_json()["data"]
    assert len(filtered_logs) == 1
    assert filtered_logs[0]["aksi"] == "penugasan"

    # Filter aksi lain yang belum ada
    r_empty = client.get(f"/tickets/{ticket_id}/logs?aksi=edit", headers=auth(admin_token))
    assert len(r_empty.get_json()["data"]) == 0


def test_audit_perubahan_prioritas_dan_edit_data(client, admin_token, ticket_id):
    # Edit data dan prioritas sekaligus
    r_edit = client.put(f"/tickets/{ticket_id}", headers=auth(admin_token), json={
        "judul": "Internet mati total di Gedung B",
        "prioritas": "kritis",
        "lokasi": "Ruang NOC Lt. 1",
    })
    assert r_edit.status_code == 200

    r_logs = client.get(f"/tickets/{ticket_id}/logs", headers=auth(admin_token))
    assert r_logs.status_code == 200
    logs = r_logs.get_json()["data"]

    # Harus ada log prioritas
    prio_logs = [l for l in logs if l["aksi"] == "prioritas"]
    assert len(prio_logs) == 1
    assert prio_logs[0]["nilai_lama"] == "tinggi"
    assert prio_logs[0]["nilai_baru"] == "kritis"

    # Harus ada log edit (judul dan lokasi)
    edit_logs = [l for l in logs if l["aksi"] == "edit"]
    assert len(edit_logs) == 2
    fields_edited = {l["field_diubah"] for l in edit_logs}
    assert "judul" in fields_edited
    assert "lokasi" in fields_edited


def test_audit_alur_status_dan_filter_diubah_oleh(client, admin_token, teknisi, ticket_id):
    tid, tek_token = teknisi
    client.put(f"/tickets/{ticket_id}/assign", headers=auth(admin_token), json={"teknisi_id": tid})

    # Teknisi mengubah status
    client.put(f"/tickets/{ticket_id}/status", headers=auth(tek_token), json={
        "status": "in_progress",
        "catatan": "Sedang memeriksa kabel optik",
    })

    # Ambil logs
    r_logs = client.get(f"/tickets/{ticket_id}/logs", headers=auth(tek_token))
    assert r_logs.status_code == 200
    logs = r_logs.get_json()["data"]

    status_logs = [l for l in logs if l["aksi"] == "status"]
    assert len(status_logs) == 1
    assert status_logs[0]["status_lama"] == "open"
    assert status_logs[0]["status_baru"] == "in_progress"
    assert status_logs[0]["catatan"] == "Sedang memeriksa kabel optik"
    assert status_logs[0]["nama_pengubah"] == "Budi"

    # Filter berdasarkan diubah_oleh teknisi
    r_by_tek = client.get(f"/tickets/{ticket_id}/logs?diubah_oleh={tid}", headers=auth(admin_token))
    assert len(r_by_tek.get_json()["data"]) == 1
    assert r_by_tek.get_json()["data"][0]["diubah_oleh"] == tid

    # Validasi error filter non-angka
    r_bad = client.get(f"/tickets/{ticket_id}/logs?diubah_oleh=bukan_angka", headers=auth(admin_token))
    assert r_bad.status_code == 400


def test_pembatasan_hak_akses_audit(client, ticket_id, admin_token):
    # Buat teknisi 2 yang tidak ditugaskan ke tiket
    r_tek2 = client.post("/auth/register", headers=auth(admin_token), json={
        "nama": "Teknisi Lain", "email": "lain@contoh.com", "password": "rahasia123", "role": "teknisi"
    })
    r_login2 = client.post("/auth/login", json={"email": "lain@contoh.com", "password": "rahasia123"})
    token2 = r_login2.get_json()["access_token"]

    # Teknisi lain tidak boleh melihat log tiket yang bukan miliknya (404)
    r = client.get(f"/tickets/{ticket_id}/logs", headers=auth(token2))
    assert r.status_code == 404

    # Anonim ditolak (401)
    assert client.get(f"/tickets/{ticket_id}/logs").status_code == 401

