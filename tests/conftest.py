import pytest

from app import create_app
from app.extensions import db


@pytest.fixture()
def app():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "JWT_SECRET_KEY": "kunci-uji-yang-cukup-panjang-0123456789",
    })
    with app.app_context():
        db.drop_all()
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def admin_token(client):
    client.post("/auth/register", json={"nama": "Admin", "email": "admin@contoh.com", "password": "rahasia123"})
    r = client.post("/auth/login", json={"email": "admin@contoh.com", "password": "rahasia123"})
    return r.get_json()["access_token"]


@pytest.fixture()
def teknisi(client, admin_token):
    """Kembalikan (id, token) seorang teknisi."""
    r = client.post("/auth/register", headers=auth(admin_token),
                    json={"nama": "Budi", "email": "budi@contoh.com", "password": "rahasia123", "role": "teknisi"})
    tid = r.get_json()["id"]
    r = client.post("/auth/login", json={"email": "budi@contoh.com", "password": "rahasia123"})
    return tid, r.get_json()["access_token"]


@pytest.fixture()
def ticket_id(client, admin_token):
    r = client.post("/tickets", headers=auth(admin_token), json={
        "judul": "Internet mati di Kantor X", "pelanggan": "PT Maju Jaya",
        "jenis": "gangguan", "perangkat": "Router Purwokerto-03",
        "lokasi": "Purwokerto", "prioritas": "tinggi"})
    return r.get_json()["id"]
