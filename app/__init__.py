import os
from datetime import timedelta

from dotenv import load_dotenv
from flask import Flask, send_from_directory

from .extensions import db, migrate, jwt
from .utils import error


def create_app(test_config=None):
    load_dotenv()
    app = Flask(__name__)

    engine_options = {}
    if os.getenv("DB_HOST"):
        # Database bawaan Wasmer Edge (Postgres): Wasmer mengisi DB_HOST, DB_PORT, dst.
        import ssl
        from urllib.parse import quote_plus

        uri = "postgresql+pg8000://{u}:{p}@{h}:{port}/{n}".format(
            u=quote_plus(os.environ["DB_USERNAME"]),
            p=quote_plus(os.environ["DB_PASSWORD"]),
            h=os.environ["DB_HOST"],
            port=os.environ.get("DB_PORT", "5432"),
            n=os.environ["DB_NAME"],
        )
        # TLS wajib, sertifikat dari CA privat Wasmer: enkripsi tetap aktif, rantai tidak diverifikasi.
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        engine_options = {"connect_args": {"ssl_context": ctx}, "pool_pre_ping": True}
    else:
        uri = os.getenv("DATABASE_URL", "sqlite:///tickets.db")
        if uri.startswith("postgres://"):
            uri = uri.replace("postgres://", "postgresql://", 1)

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-ganti-di-produksi")
    app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "dev-jwt-secret-ganti-di-produksi-0123456789")
    app.config["SQLALCHEMY_DATABASE_URI"] = uri
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=8)
    if engine_options:
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = engine_options
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    from . import models  # noqa: F401  (agar model terdaftar)
    from .routes.auth import bp as auth_bp
    from .routes.tickets import bp as tickets_bp
    from .routes.customers import bp as customers_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(tickets_bp)
    app.register_blueprint(customers_bp)

    @app.get("/")
    def index():
        return {"nama": "Network Incident Ticketing API", "status": "ok"}

    @app.get("/ui")
    def ui():
        return send_from_directory(os.path.join(app.root_path, "static"), "ui.html")

    @app.errorhandler(404)
    def not_found(_e):
        return error("Data atau alamat tidak ditemukan", 404)

    @app.errorhandler(405)
    def not_allowed(_e):
        return error("Metode tidak diizinkan", 405)

    @jwt.unauthorized_loader
    def missing_token(_reason):
        return error("Token tidak ada, silakan login", 401)

    @jwt.invalid_token_loader
    def invalid_token(_reason):
        return error("Token tidak valid", 401)

    @jwt.expired_token_loader
    def expired_token(_header, _payload):
        return error("Token sudah kedaluwarsa, silakan login ulang", 401)

    with app.app_context():
        # Buat tabel yang belum ada
        db.create_all()

        # Pastikan kolom-kolom baru pada tabel lama (Postgres Wasmer) otomatis ditambahkan jika belum ada
        try:
            with db.engine.connect() as conn:
                # Kolom tickets: customer_id, device_id
                conn.execute(db.text("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS customer_id INTEGER REFERENCES customers(id);"))
                conn.execute(db.text("ALTER TABLE tickets ADD COLUMN IF NOT EXISTS device_id INTEGER REFERENCES devices(id);"))
                # Kolom ticket_logs: aksi, field_diubah, nilai_lama, nilai_baru
                conn.execute(db.text("ALTER TABLE ticket_logs ADD COLUMN IF NOT EXISTS aksi VARCHAR(50) DEFAULT 'status';"))
                conn.execute(db.text("ALTER TABLE ticket_logs ADD COLUMN IF NOT EXISTS field_diubah VARCHAR(50);"))
                conn.execute(db.text("ALTER TABLE ticket_logs ADD COLUMN IF NOT EXISTS nilai_lama TEXT;"))
                conn.execute(db.text("ALTER TABLE ticket_logs ADD COLUMN IF NOT EXISTS nilai_baru TEXT;"))
                # Kolom devices: customer_id nullable (untuk perangkat infrastruktur mandiri)
                conn.execute(db.text("ALTER TABLE devices ALTER COLUMN customer_id DROP NOT NULL;"))
                conn.commit()
        except Exception:
            pass

        from .models import SlaTarget
        SlaTarget.seed_defaults()

    return app
