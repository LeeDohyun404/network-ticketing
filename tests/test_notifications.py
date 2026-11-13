"""Tests Fitur 7 — Eskalasi dan Notifikasi Tiket."""
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models import Ticket, utcnow
from tests.conftest import auth


def test_eskalasi_manual_berhasil(client, admin_token, teknisi, ticket_id):
    tid, tek_token = teknisi

    # Assign ticket ke teknisi
    client.put(f"/tickets/{ticket_id}/assign", headers=auth(admin_token), json={"teknisi_id": tid})

    # Teknisi melakukan eskalasi
    r = client.post(f"/tickets/{ticket_id}/escalate", headers=auth(tek_token), json={
        "alasan": "Kabel FO putus tertimpa pohon tumbang di area sulit dijangkau, butuh tim tambahan",
    })
    assert r.status_code == 200
    res = r.get_json()
    assert "Level 1" in res["pesan"]
    assert res["tiket"]["is_escalated"] is True
    assert res["tiket"]["escalation_level"] == 1
    assert "pohon tumbang" in res["tiket"]["escalation_reason"]

    # Cek notifikasi masuk ke akun admin
    r_notif = client.get("/notifications", headers=auth(admin_token))
    assert r_notif.status_code == 200
    notifs = r_notif.get_json()["data"]
    assert len(notifs) >= 1
    assert "ESKALASI" in notifs[0]["judul"]


def test_eskalasi_validasi_dan_hak_akses(client, admin_token, teknisi, ticket_id):
    tid, tek_token = teknisi

    # Teknisi yang tidak ditugaskan tidak boleh eskalasi (403)
    r_fail = client.post(f"/tickets/{ticket_id}/escalate", headers=auth(tek_token), json={
        "alasan": "Ingin eskalasi",
    })
    assert r_fail.status_code == 403

    # Alasan kosong ditolak (400)
    r_empty = client.post(f"/tickets/{ticket_id}/escalate", headers=auth(admin_token), json={
        "alasan": "",
    })
    assert r_empty.status_code == 400

    # Assign ke teknisi dan ubah status bertahap sampai closed
    client.put(f"/tickets/{ticket_id}/assign", headers=auth(admin_token), json={"teknisi_id": tid})
    client.put(f"/tickets/{ticket_id}/status", headers=auth(tek_token), json={"status": "in_progress"})
    client.put(f"/tickets/{ticket_id}/status", headers=auth(tek_token), json={"status": "resolved"})
    client.put(f"/tickets/{ticket_id}/status", headers=auth(admin_token), json={"status": "closed"})

    r_closed = client.post(f"/tickets/{ticket_id}/escalate", headers=auth(admin_token), json={
        "alasan": "Sudah ditutup tapi mau eskalasi",
    })
    assert r_closed.status_code == 400


def test_auto_eskalasi_sla_breach(client, admin_token, ticket_id):
    # Buat tiket yang tanggal created_at nya sudah lewat target SLA (misal 5 hari lalu)
    t = db.session.get(Ticket, ticket_id)
    t.created_at = utcnow() - timedelta(days=5)
    db.session.commit()

    # Jalankan auto-eskalasi
    r = client.post("/tickets/auto-escalate", headers=auth(admin_token))
    assert r.status_code == 200
    j = r.get_json()
    assert j["total"] >= 1

    # Verifikasi tiket sudah berstatus eskalasi
    t_after = db.session.get(Ticket, ticket_id)
    assert t_after.is_escalated is True
    assert t_after.escalation_level == 1
    assert "Pelanggaran SLA" in t_after.escalation_reason


def test_notifications_list_and_mark_read(client, admin_token, teknisi, ticket_id):
    tid, tek_token = teknisi

    # Assign & escalate untuk generate notifikasi
    client.put(f"/tickets/{ticket_id}/assign", headers=auth(admin_token), json={"teknisi_id": tid})
    client.post(f"/tickets/{ticket_id}/escalate", headers=auth(admin_token), json={
        "alasan": "Perangkat router rusak total perlu replacement unit",
    })

    # Cek notifikasi untuk teknisi
    r = client.get("/notifications", headers=auth(tek_token))
    assert r.status_code == 200
    data = r.get_json()
    assert data["unread_count"] >= 1
    nid = data["data"][0]["id"]

    # Tandai 1 dibaca
    r_read = client.put(f"/notifications/{nid}/read", headers=auth(tek_token))
    assert r_read.status_code == 200

    # Tandai semua dibaca
    r_all = client.put("/notifications/read-all", headers=auth(tek_token))
    assert r_all.status_code == 200

    r_check = client.get("/notifications?unread_only=true", headers=auth(tek_token))
    assert r_check.get_json()["unread_count"] == 0
    assert len(r_check.get_json()["data"]) == 0
