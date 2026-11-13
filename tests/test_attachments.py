"""Tests Fitur 6 — Lampiran Foto Tiket."""
import base64

from tests.conftest import auth


def _dummy_b64():
    """Buat gambar PNG 1x1 pixel sebagai base64."""
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return base64.b64encode(png_bytes).decode()


# ─── Test 1: Upload lampiran berhasil (admin) ────────────────────────────────
def test_upload_lampiran_berhasil(client, admin_token, ticket_id):
    r = client.post(f"/tickets/{ticket_id}/attachments", json={
        "nama_file": "foto_before.png",
        "mime_type": "image/png",
        "data": _dummy_b64(),
        "jenis": "before",
    }, headers=auth(admin_token))

    assert r.status_code == 201
    j = r.get_json()
    assert j["nama_file"] == "foto_before.png"
    assert j["jenis"] == "before"
    assert "data" not in j  # data tidak dikembalikan saat upload ringkas


# ─── Test 2: Upload gagal — format tidak didukung ────────────────────────────
def test_upload_format_tidak_didukung(client, admin_token, ticket_id):
    r = client.post(f"/tickets/{ticket_id}/attachments", json={
        "nama_file": "doc.pdf",
        "mime_type": "application/pdf",
        "data": base64.b64encode(b"dummy").decode(),
        "jenis": "umum",
    }, headers=auth(admin_token))

    assert r.status_code == 400
    assert "Format file" in r.get_json()["error"]


# ─── Test 3: Upload gagal — ukuran > 2MB ─────────────────────────────────────
def test_upload_ukuran_melebihi_batas(client, admin_token, ticket_id):
    big = base64.b64encode(b"X" * (2 * 1024 * 1024 + 1)).decode()
    r = client.post(f"/tickets/{ticket_id}/attachments", json={
        "nama_file": "besar.png",
        "mime_type": "image/png",
        "data": big,
        "jenis": "umum",
    }, headers=auth(admin_token))

    assert r.status_code == 400
    assert "melebihi batas" in r.get_json()["error"]


# ─── Test 4: Daftar & ambil lampiran, hapus oleh pengunggah ──────────────────
def test_list_get_delete_lampiran(client, admin_token, ticket_id):
    # Upload 1 lampiran
    up = client.post(f"/tickets/{ticket_id}/attachments", json={
        "nama_file": "shot.png",
        "mime_type": "image/png",
        "data": _dummy_b64(),
        "jenis": "after",
    }, headers=auth(admin_token))
    assert up.status_code == 201
    att_id = up.get_json()["id"]

    # List lampiran
    lst = client.get(f"/tickets/{ticket_id}/attachments", headers=auth(admin_token))
    assert lst.status_code == 200
    assert len(lst.get_json()["lampiran"]) == 1

    # Ambil dengan data
    get = client.get(f"/attachments/{att_id}", headers=auth(admin_token))
    assert get.status_code == 200
    assert "data" in get.get_json()

    # Hapus
    dl = client.delete(f"/attachments/{att_id}", headers=auth(admin_token))
    assert dl.status_code == 200

    # Sudah hilang
    lst2 = client.get(f"/tickets/{ticket_id}/attachments", headers=auth(admin_token))
    assert len(lst2.get_json()["lampiran"]) == 0


# ─── Test 5: Teknisi lain tidak bisa upload jika tidak ditugaskan ────────────
def test_teknisi_lain_tidak_bisa_upload(client, admin_token, teknisi, ticket_id):
    tid, tek_token = teknisi

    # Tiket tidak di-assign ke tek
    r = client.post(f"/tickets/{ticket_id}/attachments", json={
        "nama_file": "foto.png",
        "mime_type": "image/png",
        "data": _dummy_b64(),
        "jenis": "umum",
    }, headers=auth(tek_token))

    assert r.status_code == 403

    # Setelah ditugaskan ke teknisi, teknisi bisa upload
    client.put(f"/tickets/{ticket_id}/assign", headers=auth(admin_token), json={"teknisi_id": tid})
    r2 = client.post(f"/tickets/{ticket_id}/attachments", json={
        "nama_file": "foto.png",
        "mime_type": "image/png",
        "data": _dummy_b64(),
        "jenis": "after",
    }, headers=auth(tek_token))
    assert r2.status_code == 201
