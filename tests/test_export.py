"""Tests Ekspor Data Tiket ke Excel dan Dokumen Word."""
from tests.conftest import auth


def test_ekspor_tiket_excel_butuh_auth(client):
    r = client.get("/tickets/export/excel")
    assert r.status_code == 401


def test_ekspor_tiket_excel_berhasil(client, admin_token, ticket_id):
    r = client.get("/tickets/export/excel", headers=auth(admin_token))
    assert r.status_code == 200
    assert r.mimetype == "text/csv"
    assert "attachment; filename=" in r.headers.get("Content-Disposition", "")
    
    content = r.data.decode("utf-8")
    assert "ID Tiket" in content
    assert "Judul" in content
    assert "Pelanggan" in content
    assert "Status SLA" in content
    assert str(ticket_id) in content


def test_ekspor_tiket_filter_teknisi(client, admin_token, teknisi, ticket_id):
    tid, tek_token = teknisi
    
    # Teknisi belum ditugaskan -> ekspor kosong / hanya header
    r_empty = client.get("/tickets/export/excel", headers=auth(tek_token))
    assert r_empty.status_code == 200
    content_empty = r_empty.data.decode("utf-8")
    assert str(ticket_id) not in content_empty
    
    # Tugaskan tiket ke teknisi
    client.put(f"/tickets/{ticket_id}/assign", headers=auth(admin_token), json={"teknisi_id": tid})
    
    # Sekarang teknisi bisa melihat tiketnya dalam ekspor
    r_assigned = client.get("/tickets/export/excel", headers=auth(tek_token))
    assert r_assigned.status_code == 200
    content_assigned = r_assigned.data.decode("utf-8")
    assert str(ticket_id) in content_assigned


def test_ui_halaman_memiliki_tombol_ekspor(client):
    r = client.get("/ui")
    assert r.status_code == 200
    text = r.data.decode("utf-8")
    assert "exportExcelBtn" in text
    assert "exportWordBtn" in text
    assert "exportTicketsToExcel" in text
    assert "exportTicketToPdf" in text
    assert "normalizeImageShape" in text



def test_favicon_tersedia(client):
    assert client.get("/favicon.ico").status_code == 200
    assert client.get("/static/favicon-192.png").status_code == 200
    assert "rel=\"icon\"" in client.get("/ui").data.decode("utf-8")