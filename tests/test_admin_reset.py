from conftest import auth

from app.extensions import db
from app.models import Customer, Device, MaintenanceSchedule, Ticket, User


def seed(client, tok):
    c = client.post("/customers", headers=auth(tok), json={"nama": "SMA 1"}).get_json()
    d = client.post("/devices", headers=auth(tok), json={"nama": "ONT 1", "customer_id": c["id"]}).get_json()
    client.post("/tickets", headers=auth(tok), json={
        "judul": "Putus", "pelanggan": "SMA 1", "jenis": "gangguan",
        "customer_id": c["id"], "device_id": d["id"]})
    client.post("/maintenance-schedules", headers=auth(tok), json={
        "judul": "Cek ODP", "tanggal_rencana": "2030-01-01T08:00", "customer_id": c["id"]})


def reset(client, tok, **kw):
    body = {"konfirmasi": "KOSONGKAN"}
    body.update(kw)
    return client.post("/admin/reset-data", headers=auth(tok), json=body)


def test_butuh_konfirmasi_dan_pilihan(client, admin_token):
    assert client.post("/admin/reset-data", headers=auth(admin_token), json={"tiket": True}).status_code == 400
    assert reset(client, admin_token).status_code == 400


def test_teknisi_tidak_boleh(client, teknisi):
    assert reset(client, teknisi[1], tiket=True).status_code == 403


def test_kosongkan_semua(client, admin_token, teknisi):
    seed(client, admin_token)
    r = reset(client, admin_token, tiket=True, pelanggan=True, perangkat=True, maintenance=True, teknisi=True)
    assert r.status_code == 200, r.get_json()
    assert Ticket.query.count() == 0 and Customer.query.count() == 0
    assert Device.query.count() == 0 and MaintenanceSchedule.query.count() == 0
    assert [u.role for u in User.query.all()] == ["admin"]


def test_pelanggan_saja(client, admin_token):
    seed(client, admin_token)
    assert reset(client, admin_token, pelanggan=True).status_code == 200
    assert Customer.query.count() == 0 and Ticket.query.count() == 1 and Device.query.count() == 1
    assert Ticket.query.first().customer_id is None


def test_tiket_saja_dengan_maintenance_tersisa(client, admin_token):
    seed(client, admin_token)
    assert reset(client, admin_token, tiket=True).status_code == 200
    assert Ticket.query.count() == 0 and MaintenanceSchedule.query.count() == 1


def test_teknisi_masih_dipakai_ditolak(client, admin_token, teknisi, ticket_id):
    tid, ttok = teknisi
    client.put(f"/tickets/{ticket_id}/assign", headers=auth(admin_token), json={"teknisi_id": tid})
    client.put(f"/tickets/{ticket_id}/status", headers=auth(ttok), json={"status": "in_progress"})
    assert reset(client, admin_token, teknisi=True).status_code == 409
    assert User.query.count() == 2
    assert reset(client, admin_token, tiket=True, teknisi=True).status_code == 200
    assert User.query.count() == 1


def test_teknisi_melihat_nama_teknisi_di_tiket(client, admin_token, teknisi, ticket_id):
    tid, ttok = teknisi
    client.put(f"/tickets/{ticket_id}/assign", headers=auth(admin_token), json={"teknisi_id": tid})
    d = client.get(f"/tickets/{ticket_id}", headers=auth(ttok)).get_json()
    assert d["nama_teknisi"] == "Budi" and d["nama_pembuat"] == "Admin"
    lst = client.get("/tickets", headers=auth(ttok)).get_json()["data"]
    assert lst[0]["nama_teknisi"] == "Budi"