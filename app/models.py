from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db

ROLES = ("admin", "teknisi")
TICKET_TYPES = ("gangguan", "pemeliharaan")
PRIORITIES = ("rendah", "sedang", "tinggi", "kritis")
PRIORITY_RANK = {name: i for i, name in enumerate(PRIORITIES)}
STATUSES = ("open", "in_progress", "resolved", "closed")

# Urutan status yang boleh. Status tidak boleh loncat.
TRANSITIONS = {
    "open": ("in_progress",),
    "in_progress": ("resolved",),
    "resolved": ("closed", "in_progress"),  # in_progress = dibuka lagi karena belum tuntas
    "closed": (),
}


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def minutes_between(start, end):
    if start is None or end is None:
        return None
    return int((end - start).total_seconds() // 60)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    nama = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="teknisi")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {"id": self.id, "nama": self.nama, "email": self.email, "role": self.role}


class Ticket(db.Model):
    __tablename__ = "tickets"

    id = db.Column(db.Integer, primary_key=True)
    judul = db.Column(db.String(150), nullable=False)
    deskripsi = db.Column(db.Text, default="")
    pelanggan = db.Column(db.String(150), nullable=False)
    jenis = db.Column(db.String(20), nullable=False, default="gangguan")
    perangkat = db.Column(db.String(150), default="")
    lokasi = db.Column(db.String(200), default="")
    prioritas = db.Column(db.String(20), nullable=False, default="sedang")
    status = db.Column(db.String(20), nullable=False, default="open", index=True)
    dibuat_oleh = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    ditugaskan_ke = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    responded_at = db.Column(db.DateTime, nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)

    logs = db.relationship("TicketLog", backref="ticket", order_by="TicketLog.id", cascade="all, delete-orphan")

    def to_dict(self, with_logs=False):
        data = {
            "id": self.id,
            "judul": self.judul,
            "deskripsi": self.deskripsi,
            "pelanggan": self.pelanggan,
            "jenis": self.jenis,
            "perangkat": self.perangkat,
            "lokasi": self.lokasi,
            "prioritas": self.prioritas,
            "status": self.status,
            "dibuat_oleh": self.dibuat_oleh,
            "ditugaskan_ke": self.ditugaskan_ke,
            "created_at": self.created_at.isoformat(),
            "responded_at": self.responded_at.isoformat() if self.responded_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "sla": {
                "respons_menit": minutes_between(self.created_at, self.responded_at),
                "penyelesaian_menit": minutes_between(self.created_at, self.resolved_at),
            },
        }
        if with_logs:
            data["logs"] = [log.to_dict() for log in self.logs]
        return data


class TicketLog(db.Model):
    __tablename__ = "ticket_logs"

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("tickets.id"), nullable=False, index=True)
    status_lama = db.Column(db.String(20), nullable=False)
    status_baru = db.Column(db.String(20), nullable=False)
    diubah_oleh = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    catatan = db.Column(db.Text, default="")
    waktu = db.Column(db.DateTime, nullable=False, default=utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "ticket_id": self.ticket_id,
            "status_lama": self.status_lama,
            "status_baru": self.status_baru,
            "diubah_oleh": self.diubah_oleh,
            "catatan": self.catatan,
            "waktu": self.waktu.isoformat(),
        }


class Invitation(db.Model):
    """Undangan aktivasi teknisi. Token asli hanya ada di email; di database disimpan hash-nya."""
    __tablename__ = "invitations"

    id = db.Column(db.Integer, primary_key=True)
    nama = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False, index=True)
    token_hash = db.Column(db.String(64), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    def to_dict(self):
        return {"id": self.id, "nama": self.nama, "email": self.email,
                "expires_at": self.expires_at.isoformat(), "kedaluwarsa": self.expires_at < utcnow()}
