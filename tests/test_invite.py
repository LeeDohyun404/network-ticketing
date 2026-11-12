from datetime import timedelta

from app.extensions import db
from app.models import Invitation, utcnow
from conftest import auth


def _invite(client, admin_token, email="sari@contoh.com"):
    r = client.post("/users/invite", headers=auth(admin_token), json={"nama": "Sari", "email": email})
    return r, r.get_json().get("link_aktivasi", "").split("aktivasi=")[-1]


def test_undangan_lalu_aktivasi_dan_login(client, admin_token):
    r, token = _invite(client, admin_token)
    assert r.status_code == 201 and token
    assert client.get(f"/auth/invite/{token}").get_json()["email"] == "sari@contoh.com"
    r = client.post("/auth/activate", json={"token": token, "password": "passbaru123"})
    assert r.status_code == 201 and r.get_json()["role"] == "teknisi"
    r = client.post("/auth/login", json={"email": "sari@contoh.com", "password": "passbaru123"})
    assert r.status_code == 200


def test_tautan_hanya_sekali_pakai(client, admin_token):
    _, token = _invite(client, admin_token)
    client.post("/auth/activate", json={"token": token, "password": "passbaru123"})
    assert client.post("/auth/activate", json={"token": token, "password": "passbaru123"}).status_code == 404


def test_tautan_kedaluwarsa(client, app, admin_token):
    _, token = _invite(client, admin_token)
    inv = Invitation.query.first()
    inv.expires_at = utcnow() - timedelta(minutes=1)
    db.session.commit()
    assert client.get(f"/auth/invite/{token}").status_code == 404


def test_password_pendek_ditolak(client, admin_token):
    _, token = _invite(client, admin_token)
    assert client.post("/auth/activate", json={"token": token, "password": "123"}).status_code == 400


def test_teknisi_tidak_boleh_mengundang(client, teknisi):
    _, tok = teknisi
    r = client.post("/users/invite", headers=auth(tok), json={"nama": "X", "email": "x@contoh.com"})
    assert r.status_code == 403


def test_undang_ulang_mematikan_tautan_lama(client, admin_token):
    _, lama = _invite(client, admin_token)
    _, baru = _invite(client, admin_token)
    assert client.get(f"/auth/invite/{lama}").status_code == 404
    assert client.get(f"/auth/invite/{baru}").status_code == 200


def test_admin_hapus_teknisi_dan_tiketnya_dilepas(client, admin_token, teknisi, ticket_id):
    tid, _ = teknisi
    client.put(f"/tickets/{ticket_id}/assign", headers=auth(admin_token), json={"teknisi_id": tid})
    assert client.delete(f"/users/{tid}", headers=auth(admin_token)).status_code == 200
    assert client.get(f"/tickets/{ticket_id}", headers=auth(admin_token)).get_json()["ditugaskan_ke"] is None
    assert client.post("/auth/login", json={"email": "budi@contoh.com", "password": "rahasia123"}).status_code == 401


def test_teknisi_dengan_riwayat_tidak_bisa_dihapus(client, admin_token, teknisi, ticket_id):
    tid, tok = teknisi
    client.put(f"/tickets/{ticket_id}/assign", headers=auth(admin_token), json={"teknisi_id": tid})
    client.put(f"/tickets/{ticket_id}/status", headers=auth(tok), json={"status": "in_progress"})
    assert client.delete(f"/users/{tid}", headers=auth(admin_token)).status_code == 409


def test_admin_tidak_bisa_dihapus_dan_teknisi_tidak_boleh_menghapus(client, admin_token, teknisi):
    tid, tok = teknisi
    assert client.delete("/users/1", headers=auth(admin_token)).status_code == 404
    assert client.delete(f"/users/{tid}", headers=auth(tok)).status_code == 403
