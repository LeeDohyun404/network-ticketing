from datetime import datetime, timezone, timedelta

from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db

ROLES = ("admin", "teknisi")
ATTACHMENT_TYPES = ("before", "after", "umum")
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_ATTACHMENT_BYTES = 2 * 1024 * 1024   # 2 MB
MAX_ATTACHMENTS_PER_TICKET = 5
TICKET_TYPES = ("gangguan", "pemeliharaan")
PRIORITIES = ("rendah", "sedang", "tinggi", "kritis")
PRIORITY_RANK = {name: i for i, name in enumerate(PRIORITIES)}
STATUSES = ("open", "in_progress", "resolved", "closed")
RECURRENCE_TYPES = ("tidak_ada", "harian", "mingguan", "bulanan")
SCHEDULE_STATUSES = ("terjadwal", "selesai", "dibatalkan")

DEFAULT_SLA_TARGETS = {
    "kritis": {"respons_menit": 60, "penyelesaian_menit": 240},
    "tinggi": {"respons_menit": 120, "penyelesaian_menit": 480},
    "sedang": {"respons_menit": 240, "penyelesaian_menit": 1440},
    "rendah": {"respons_menit": 480, "penyelesaian_menit": 4320},
}

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

    def __init__(self, nama="", email="", password_hash="", role="teknisi", **kwargs):
        super().__init__(**kwargs)
        self.nama = nama
        self.email = email
        self.password_hash = password_hash
        self.role = role

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {"id": self.id, "nama": self.nama, "email": self.email, "role": self.role}


class Customer(db.Model):
    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True)
    nama = db.Column(db.String(150), nullable=False)
    alamat = db.Column(db.Text, default="")
    kontak = db.Column(db.String(100), default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    devices = db.relationship("Device", backref="customer", cascade="all, delete-orphan", order_by="Device.id")
    tickets = db.relationship("Ticket", backref="customer_ref", lazy="dynamic")

    def __init__(self, nama="", alamat="", kontak="", created_at=None, **kwargs):
        super().__init__(**kwargs)
        self.nama = nama
        self.alamat = alamat
        self.kontak = kontak
        if created_at is not None:
            self.created_at = created_at

    def to_dict(self, with_devices=False):
        data = {
            "id": self.id,
            "nama": self.nama,
            "alamat": self.alamat or "",
            "kontak": self.kontak or "",
            "created_at": self.created_at.isoformat(),
        }
        if with_devices:
            data["devices"] = [d.to_dict() for d in self.devices]
        return data


class Device(db.Model):
    __tablename__ = "devices"

    id = db.Column(db.Integer, primary_key=True)
    nama = db.Column(db.String(150), nullable=False)
    jenis = db.Column(db.String(50), nullable=False, default="router")
    lokasi = db.Column(db.String(200), default="")
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    tickets = db.relationship("Ticket", backref="device_ref", lazy="dynamic")

    def __init__(self, nama="", jenis="router", lokasi="", customer_id=None, created_at=None, **kwargs):
        super().__init__(**kwargs)
        self.nama = nama
        self.jenis = jenis
        self.lokasi = lokasi
        self.customer_id = customer_id
        if created_at is not None:
            self.created_at = created_at

    def to_dict(self):
        return {
            "id": self.id,
            "nama": self.nama,
            "jenis": self.jenis,
            "lokasi": self.lokasi or "",
            "customer_id": self.customer_id,
            "nama_pelanggan": self.customer.nama if self.customer else None,
            "created_at": self.created_at.isoformat(),
        }


class Ticket(db.Model):
    __tablename__ = "tickets"

    id = db.Column(db.Integer, primary_key=True)
    judul = db.Column(db.String(150), nullable=False)
    deskripsi = db.Column(db.Text, default="")
    pelanggan = db.Column(db.String(150), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=True, index=True)
    jenis = db.Column(db.String(20), nullable=False, default="gangguan")
    perangkat = db.Column(db.String(150), default="")
    device_id = db.Column(db.Integer, db.ForeignKey("devices.id"), nullable=True, index=True)
    lokasi = db.Column(db.String(200), default="")
    prioritas = db.Column(db.String(20), nullable=False, default="sedang")
    status = db.Column(db.String(20), nullable=False, default="open", index=True)
    dibuat_oleh = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    ditugaskan_ke = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    responded_at = db.Column(db.DateTime, nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)

    logs = db.relationship("TicketLog", backref="ticket", order_by="TicketLog.id", cascade="all, delete-orphan")
    comments = db.relationship("TicketComment", backref="ticket", order_by="TicketComment.id.asc()", cascade="all, delete-orphan")
    attachments = db.relationship("TicketAttachment", backref="ticket", order_by="TicketAttachment.id", cascade="all, delete-orphan")

    def __init__(self, judul="", deskripsi="", pelanggan="", jenis="gangguan", perangkat="",
                 lokasi="", prioritas="sedang", status="open", dibuat_oleh=None, ditugaskan_ke=None,
                 customer_id=None, device_id=None, **kwargs):
        super().__init__(**kwargs)
        self.judul = judul
        self.deskripsi = deskripsi
        self.pelanggan = pelanggan
        self.jenis = jenis
        self.perangkat = perangkat
        self.lokasi = lokasi
        self.prioritas = prioritas
        self.status = status
        if dibuat_oleh is not None:
            self.dibuat_oleh = dibuat_oleh
        if ditugaskan_ke is not None:
            self.ditugaskan_ke = ditugaskan_ke
        if customer_id is not None:
            self.customer_id = customer_id
        if device_id is not None:
            self.device_id = device_id

    def calculate_sla(self, targets_map=None, now=None):
        if targets_map is None:
            targets_map = SlaTarget.get_targets_map()
        if now is None:
            now = utcnow()

        target = targets_map.get(
            self.prioritas,
            DEFAULT_SLA_TARGETS.get(self.prioritas, {"respons_menit": 240, "penyelesaian_menit": 1440}),
        )
        target_resp = target["respons_menit"]
        target_res = target["penyelesaian_menit"]

        durasi_respons = minutes_between(self.created_at, self.responded_at)
        if self.responded_at is not None:
            sisa_resp = 0
            melewati_resp = durasi_respons > target_resp
        else:
            berjalan_resp = minutes_between(self.created_at, now) or 0
            sisa_resp = target_resp - berjalan_resp
            melewati_resp = sisa_resp < 0

        durasi_selesai = minutes_between(self.created_at, self.resolved_at)
        if self.resolved_at is not None:
            sisa_res = 0
            melewati_res = durasi_selesai > target_res
        else:
            berjalan_res = minutes_between(self.created_at, now) or 0
            sisa_res = target_res - berjalan_res
            melewati_res = sisa_res < 0

        return {
            "respons_menit": durasi_respons,
            "penyelesaian_menit": durasi_selesai,
            "target_respons_menit": target_resp,
            "target_penyelesaian_menit": target_res,
            "sisa_respons_menit": sisa_resp,
            "sisa_penyelesaian_menit": sisa_res,
            "melewati_sla_respons": melewati_resp,
            "melewati_sla_penyelesaian": melewati_res,
            "melewati_sla": melewati_resp or melewati_res,
        }

    def to_dict(self, with_logs=False, with_comments=False, targets_map=None, now=None):
        data = {
            "id": self.id,
            "judul": self.judul,
            "deskripsi": self.deskripsi,
            "pelanggan": self.pelanggan,
            "customer_id": self.customer_id,
            "jenis": self.jenis,
            "perangkat": self.perangkat,
            "device_id": self.device_id,
            "lokasi": self.lokasi,
            "prioritas": self.prioritas,
            "status": self.status,
            "dibuat_oleh": self.dibuat_oleh,
            "ditugaskan_ke": self.ditugaskan_ke,
            "created_at": self.created_at.isoformat(),
            "responded_at": self.responded_at.isoformat() if self.responded_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "sla": self.calculate_sla(targets_map=targets_map, now=now),
        }
        if with_logs:
            data["logs"] = [log.to_dict() for log in self.logs if log.aksi == "status"]
        if with_comments or with_logs:
            data["komentar"] = [c.to_dict() for c in self.comments]
        return data


class TicketLog(db.Model):
    __tablename__ = "ticket_logs"

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("tickets.id"), nullable=False, index=True)
    aksi = db.Column(db.String(50), nullable=False, default="status")
    field_diubah = db.Column(db.String(50), nullable=True)
    nilai_lama = db.Column(db.Text, nullable=True)
    nilai_baru = db.Column(db.Text, nullable=True)
    status_lama = db.Column(db.String(20), nullable=True, default="")
    status_baru = db.Column(db.String(20), nullable=True, default="")
    diubah_oleh = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    catatan = db.Column(db.Text, default="")
    waktu = db.Column(db.DateTime, nullable=False, default=utcnow)

    user = db.relationship("User", backref="ticket_logs")

    def __init__(self, ticket_id=None, status_lama="", status_baru="", diubah_oleh=None,
                 catatan="", waktu=None, aksi="status", field_diubah=None, nilai_lama=None,
                 nilai_baru=None, **kwargs):
        super().__init__(**kwargs)
        if ticket_id is not None:
            self.ticket_id = ticket_id
        self.aksi = aksi or "status"
        self.field_diubah = field_diubah or ("status" if self.aksi == "status" else None)
        self.status_lama = status_lama or ""
        self.status_baru = status_baru or ""
        self.nilai_lama = str(nilai_lama) if nilai_lama is not None else (self.status_lama if self.aksi == "status" else None)
        self.nilai_baru = str(nilai_baru) if nilai_baru is not None else (self.status_baru if self.aksi == "status" else None)
        if diubah_oleh is not None:
            self.diubah_oleh = diubah_oleh
        self.catatan = catatan or ""
        if waktu is not None:
            self.waktu = waktu

    def to_dict(self):
        return {
            "id": self.id,
            "ticket_id": self.ticket_id,
            "aksi": self.aksi,
            "field_diubah": self.field_diubah,
            "nilai_lama": self.nilai_lama,
            "nilai_baru": self.nilai_baru,
            "status_lama": self.status_lama,
            "status_baru": self.status_baru,
            "diubah_oleh": self.diubah_oleh,
            "nama_pengubah": self.user.nama if self.user else None,
            "catatan": self.catatan,
            "waktu": self.waktu.isoformat(),
        }


class TicketComment(db.Model):
    __tablename__ = "ticket_comments"

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("tickets.id"), nullable=False, index=True)
    dibuat_oleh = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    pesan = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    user = db.relationship("User", backref="ticket_comments")

    def __init__(self, ticket_id=None, dibuat_oleh=None, pesan="", created_at=None, **kwargs):
        super().__init__(**kwargs)
        if ticket_id is not None:
            self.ticket_id = ticket_id
        if dibuat_oleh is not None:
            self.dibuat_oleh = dibuat_oleh
        self.pesan = pesan
        if created_at is not None:
            self.created_at = created_at

    def to_dict(self):
        return {
            "id": self.id,
            "ticket_id": self.ticket_id,
            "dibuat_oleh": self.dibuat_oleh,
            "nama_penulis": self.user.nama if self.user else None,
            "role_penulis": self.user.role if self.user else None,
            "pesan": self.pesan,
            "created_at": self.created_at.isoformat(),
        }


class TicketAttachment(db.Model):
    __tablename__ = "ticket_attachments"

    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey("tickets.id"), nullable=False, index=True)
    nama_file = db.Column(db.String(200), nullable=False)
    mime_type = db.Column(db.String(50), nullable=False)
    data = db.Column(db.Text, nullable=False)          # base64-encoded
    jenis = db.Column(db.String(20), nullable=False, default="umum")   # before/after/umum
    diunggah_oleh = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    uploader = db.relationship("User", backref="attachments")

    def __init__(self, ticket_id=None, nama_file="", mime_type="", data="",
                 jenis="umum", diunggah_oleh=None, created_at=None, **kwargs):
        super().__init__(**kwargs)
        if ticket_id is not None:
            self.ticket_id = ticket_id
        self.nama_file = nama_file
        self.mime_type = mime_type
        self.data = data
        self.jenis = jenis
        if diunggah_oleh is not None:
            self.diunggah_oleh = diunggah_oleh
        if created_at is not None:
            self.created_at = created_at

    def to_dict(self, with_data=False):
        d = {
            "id": self.id,
            "ticket_id": self.ticket_id,
            "nama_file": self.nama_file,
            "mime_type": self.mime_type,
            "jenis": self.jenis,
            "diunggah_oleh": self.diunggah_oleh,
            "nama_pengunggah": self.uploader.nama if self.uploader else None,
            "created_at": self.created_at.isoformat(),
        }
        if with_data:
            d["data"] = self.data
        return d


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

    def __init__(self, nama="", email="", token_hash="", expires_at=None, used_at=None, **kwargs):
        super().__init__(**kwargs)
        self.nama = nama
        self.email = email
        self.token_hash = token_hash
        if expires_at is not None:
            self.expires_at = expires_at
        if used_at is not None:
            self.used_at = used_at

    def to_dict(self):
        return {"id": self.id, "nama": self.nama, "email": self.email,
                "expires_at": self.expires_at.isoformat(), "kedaluwarsa": self.expires_at < utcnow()}


class SlaTarget(db.Model):
    __tablename__ = "sla_targets"

    id = db.Column(db.Integer, primary_key=True)
    prioritas = db.Column(db.String(20), unique=True, nullable=False)
    target_respons_menit = db.Column(db.Integer, nullable=False)
    target_penyelesaian_menit = db.Column(db.Integer, nullable=False)

    def __init__(self, prioritas="", target_respons_menit=0, target_penyelesaian_menit=0, **kwargs):
        super().__init__(**kwargs)
        self.prioritas = prioritas
        self.target_respons_menit = target_respons_menit
        self.target_penyelesaian_menit = target_penyelesaian_menit

    def to_dict(self):
        return {
            "id": self.id,
            "prioritas": self.prioritas,
            "target_respons_menit": self.target_respons_menit,
            "target_penyelesaian_menit": self.target_penyelesaian_menit,
        }

    @classmethod
    def get_targets_map(cls):
        targets = {k: dict(v) for k, v in DEFAULT_SLA_TARGETS.items()}
        try:
            for item in cls.query.all():
                targets[item.prioritas] = {
                    "respons_menit": item.target_respons_menit,
                    "penyelesaian_menit": item.target_penyelesaian_menit,
                }
        except Exception:
            pass
        return targets

    @classmethod
    def seed_defaults(cls):
        try:
            if cls.query.count() == 0:
                for prio, vals in DEFAULT_SLA_TARGETS.items():
                    db.session.add(cls(
                        prioritas=prio,
                        target_respons_menit=vals["respons_menit"],
                        target_penyelesaian_menit=vals["penyelesaian_menit"],
                    ))
                db.session.commit()
        except Exception:
            db.session.rollback()


class MaintenanceSchedule(db.Model):
    __tablename__ = "maintenance_schedules"

    id = db.Column(db.Integer, primary_key=True)
    judul = db.Column(db.String(150), nullable=False)
    deskripsi = db.Column(db.Text, default="")
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=True, index=True)
    pelanggan = db.Column(db.String(150), default="")
    device_id = db.Column(db.Integer, db.ForeignKey("devices.id"), nullable=True, index=True)
    perangkat = db.Column(db.String(150), default="")
    lokasi = db.Column(db.String(200), default="")
    prioritas = db.Column(db.String(20), nullable=False, default="sedang")
    tanggal_rencana = db.Column(db.DateTime, nullable=False)
    pengulangan = db.Column(db.String(20), nullable=False, default="tidak_ada")
    status = db.Column(db.String(20), nullable=False, default="terjadwal", index=True)
    last_ticket_id = db.Column(db.Integer, db.ForeignKey("tickets.id"), nullable=True)
    dibuat_oleh = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    # Relationship
    customer = db.relationship("Customer", backref="maintenance_schedules")
    device = db.relationship("Device", backref="maintenance_schedules")
    creator = db.relationship("User", foreign_keys=[dibuat_oleh], backref="maintenance_schedules")
    last_ticket = db.relationship("Ticket", foreign_keys=[last_ticket_id])

    def __init__(self, judul="", deskripsi="", customer_id=None, pelanggan="", device_id=None,
                 perangkat="", lokasi="", prioritas="sedang", tanggal_rencana=None,
                 pengulangan="tidak_ada", status="terjadwal", last_ticket_id=None,
                 dibuat_oleh=None, created_at=None, **kwargs):
        super().__init__(**kwargs)
        self.judul = judul
        self.deskripsi = deskripsi
        self.customer_id = customer_id
        self.pelanggan = pelanggan
        self.device_id = device_id
        self.perangkat = perangkat
        self.lokasi = lokasi
        self.prioritas = prioritas
        self.tanggal_rencana = tanggal_rencana or utcnow()
        self.pengulangan = pengulangan
        self.status = status
        self.last_ticket_id = last_ticket_id
        if dibuat_oleh is not None:
            self.dibuat_oleh = dibuat_oleh
        if created_at is not None:
            self.created_at = created_at

    def is_overdue(self):
        if self.status != "terjadwal" or self.tanggal_rencana is None:
            return False
        return self.tanggal_rencana < utcnow()

    def advance_recurrence(self):
        """Memajukan tanggal_rencana jika berulang, atau menandai selesai jika tidak berulang."""
        if self.pengulangan == "harian":
            self.tanggal_rencana += timedelta(days=1)
        elif self.pengulangan == "mingguan":
            self.tanggal_rencana += timedelta(weeks=1)
        elif self.pengulangan == "bulanan":
            self.tanggal_rencana += timedelta(days=30)
        else:
            self.status = "selesai"

    def to_dict(self):
        return {
            "id": self.id,
            "judul": self.judul,
            "deskripsi": self.deskripsi or "",
            "customer_id": self.customer_id,
            "pelanggan": self.pelanggan or (self.customer.nama if self.customer else ""),
            "device_id": self.device_id,
            "perangkat": self.perangkat or (self.device.nama if self.device else ""),
            "lokasi": self.lokasi or "",
            "prioritas": self.prioritas,
            "tanggal_rencana": self.tanggal_rencana.isoformat() if self.tanggal_rencana else None,
            "pengulangan": self.pengulangan,
            "status": self.status,
            "jatuh_tempo": self.is_overdue(),
            "last_ticket_id": self.last_ticket_id,
            "dibuat_oleh": self.dibuat_oleh,
            "nama_pembuat": self.creator.nama if self.creator else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
