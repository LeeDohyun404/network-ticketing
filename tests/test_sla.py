from datetime import timedelta

from app.extensions import db
from app.models import Ticket, utcnow
from tests.conftest import auth


def test_sla_target_dan_sisa_waktu_tiket_baru(client, admin_token):
    # Buat tiket prioritas kritis
    r = client.post("/tickets", headers=auth(admin_token), json={
        "judul": "Core switch mati",
        "pelanggan": "PT Telko Prima",
        "prioritas": "kritis",
    })
    assert r.status_code == 201
    data = r.get_json()
    sla = data["sla"]

    # Target kritis: respons 60 menit, penyelesaian 240 menit
    assert sla["target_respons_menit"] == 60
    assert sla["target_penyelesaian_menit"] == 240
    assert sla["melewati_sla_respons"] is False
    assert sla["melewati_sla_penyelesaian"] is False
    assert sla["melewati_sla"] is False
    assert sla["sisa_respons_menit"] <= 60
    assert sla["sisa_penyelesaian_menit"] <= 240


def test_deteksi_pelanggaran_sla_respons_dan_penyelesaian(client, admin_token, app):
    # Buat tiket dengan prioritas kritis (target 60 & 240 menit)
    r = client.post("/tickets", headers=auth(admin_token), json={
        "judul": "BGP flapping",
        "pelanggan": "PT Internet Cepat",
        "prioritas": "kritis",
    })
    tid = r.get_json()["id"]

    # Simulasikan tiket dibuat 70 menit yang lalu (melewati respons 60 menit)
    with app.app_context():
        ticket = db.session.get(Ticket, tid)
        ticket.created_at = utcnow() - timedelta(minutes=70)
        db.session.commit()

    r = client.get(f"/tickets/{tid}", headers=auth(admin_token))
    sla = r.get_json()["sla"]
    assert sla["melewati_sla_respons"] is True
    assert sla["melewati_sla_penyelesaian"] is False
    assert sla["melewati_sla"] is True
    assert sla["sisa_respons_menit"] < 0

    # Simulasikan tiket dibuat 300 menit yang lalu (melewati penyelesaian 240 menit)
    with app.app_context():
        ticket = db.session.get(Ticket, tid)
        ticket.created_at = utcnow() - timedelta(minutes=300)
        db.session.commit()

    r = client.get(f"/tickets/{tid}", headers=auth(admin_token))
    sla = r.get_json()["sla"]
    assert sla["melewati_sla_respons"] is True
    assert sla["melewati_sla_penyelesaian"] is True
    assert sla["melewati_sla"] is True


def test_filter_melewati_sla(client, admin_token, app):
    # Buat 2 tiket
    r1 = client.post("/tickets", headers=auth(admin_token), json={
        "judul": "Tiket Tepat Waktu", "pelanggan": "Pelanggan A", "prioritas": "sedang",
    })
    t1_id = r1.get_json()["id"]

    r2 = client.post("/tickets", headers=auth(admin_token), json={
        "judul": "Tiket Terlambat", "pelanggan": "Pelanggan B", "prioritas": "kritis",
    })
    t2_id = r2.get_json()["id"]

    # Mundurkan waktu tiket 2 agar melewati SLA
    with app.app_context():
        ticket2 = db.session.get(Ticket, t2_id)
        ticket2.created_at = utcnow() - timedelta(minutes=100)
        db.session.commit()

    # Filter ?melewati_sla=true
    r = client.get("/tickets?melewati_sla=true", headers=auth(admin_token))
    assert r.status_code == 200
    ids_breached = [t["id"] for t in r.get_json()["data"]]
    assert t2_id in ids_breached
    assert t1_id not in ids_breached

    # Filter ?melewati_sla=false
    r = client.get("/tickets?melewati_sla=false", headers=auth(admin_token))
    assert r.status_code == 200
    ids_ok = [t["id"] for t in r.get_json()["data"]]
    assert t1_id in ids_ok
    assert t2_id not in ids_ok

    # Filter dengan nilai invalid
    r_bad = client.get("/tickets?melewati_sla=ngawur", headers=auth(admin_token))
    assert r_bad.status_code == 400
    assert "melewati_sla harus bernilai true atau false" in r_bad.get_json()["error"]


def test_ringkasan_sla(client, admin_token, app):
    # Buat tiket normal dan tiket melanggar
    r1 = client.post("/tickets", headers=auth(admin_token), json={
        "judul": "Tiket OK", "pelanggan": "Pelanggan A", "prioritas": "rendah",
    })
    r2 = client.post("/tickets", headers=auth(admin_token), json={
        "judul": "Tiket Telat", "pelanggan": "Pelanggan B", "prioritas": "kritis",
    })
    t2_id = r2.get_json()["id"]

    with app.app_context():
        ticket2 = db.session.get(Ticket, t2_id)
        ticket2.created_at = utcnow() - timedelta(minutes=120)
        db.session.commit()

    r = client.get("/tickets/summary", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.get_json()
    assert data["total"] == 2
    assert data["jumlah_melewati_sla"] == 1
    assert data["jumlah_memenuhi_sla"] == 1
    assert data["persentase_memenuhi_sla"] == 50.0
    assert data["pelanggaran_respons"] >= 1


def test_crud_sla_targets_dan_hak_akses(client, admin_token, teknisi):
    tid, tek_token = teknisi

    # Teknisi dan admin bisa melihat SLA targets
    r_tek = client.get("/sla-targets", headers=auth(tek_token))
    assert r_tek.status_code == 200
    assert len(r_tek.get_json()["data"]) == 4

    # Teknisi dilarang mengubah target SLA (403)
    r_put_tek = client.put("/sla-targets/kritis", headers=auth(tek_token), json={
        "target_respons_menit": 30,
        "target_penyelesaian_menit": 180,
    })
    assert r_put_tek.status_code == 403

    # Anonim dilarang (401)
    r_anon = client.get("/sla-targets")
    assert r_anon.status_code == 401

    # Admin sukses mengubah target SLA kritis
    r_put_adm = client.put("/sla-targets/kritis", headers=auth(admin_token), json={
        "target_respons_menit": 30,
        "target_penyelesaian_menit": 180,
    })
    assert r_put_adm.status_code == 200
    updated = r_put_adm.get_json()
    assert updated["target_respons_menit"] == 30
    assert updated["target_penyelesaian_menit"] == 180

    # Validasi input gagal
    r_fail = client.put("/sla-targets/kritis", headers=auth(admin_token), json={
        "target_respons_menit": -10,
        "target_penyelesaian_menit": 180,
    })
    assert r_fail.status_code == 400

    r_fail_prio = client.put("/sla-targets/superkritis", headers=auth(admin_token), json={
        "target_respons_menit": 15,
        "target_penyelesaian_menit": 60,
    })
    assert r_fail_prio.status_code == 400

