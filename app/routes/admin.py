from flask import Blueprint, jsonify, request

from ..extensions import db
from ..models import (Customer, Device, Invitation, MaintenanceSchedule,
                      Notification, Ticket, TicketAttachment, TicketComment,
                      TicketLog, User)
from ..utils import error, roles_required

bp = Blueprint("admin", __name__)

PILIHAN = ("tiket", "pelanggan", "perangkat", "maintenance", "teknisi")
KONFIRMASI = "KOSONGKAN"


def _reset_sequences(tables):
    """Di Postgres, nomor ID dimulai lagi dari 1 untuk tabel yang sudah kosong."""
    if db.engine.dialect.name != "postgresql":
        return
    for model in tables:
        name = model.__tablename__
        try:
            if db.session.query(model).count() == 0:
                db.session.execute(db.text(
                    "SELECT setval(pg_get_serial_sequence(:t, 'id'), 1, false)"), {"t": name})
        except Exception:
            db.session.rollback()
            return


@bp.post("/admin/reset-data")
@roles_required("admin")
def reset_data():
    """Kosongkan data terpilih. Akun admin tidak pernah dihapus."""
    data = request.get_json(silent=True) or {}
    if data.get("konfirmasi") != KONFIRMASI:
        return error(f"Ketik {KONFIRMASI} untuk konfirmasi", 400)

    pilih = {k: data.get(k) is True for k in PILIHAN}
    if not any(pilih.values()):
        return error("Pilih minimal satu data yang akan dikosongkan", 400)

    hasil = {}
    kosong = []
    q = db.session.query
    try:
        # 1. Jadwal maintenance
        if pilih["maintenance"]:
            hasil["maintenance"] = q(MaintenanceSchedule).delete(synchronize_session=False)
            kosong.append(MaintenanceSchedule)

        # 2. Tiket beserta turunannya
        if pilih["tiket"]:
            if not pilih["maintenance"]:
                q(MaintenanceSchedule).update({"last_ticket_id": None}, synchronize_session=False)
            q(Notification).filter(Notification.ticket_id.isnot(None)).delete(synchronize_session=False)
            q(TicketAttachment).delete(synchronize_session=False)
            q(TicketComment).delete(synchronize_session=False)
            q(TicketLog).delete(synchronize_session=False)
            hasil["tiket"] = q(Ticket).delete(synchronize_session=False)
            kosong += [TicketAttachment, TicketComment, TicketLog, Ticket]

        # 3. Pelanggan (tiket/jadwal/perangkat yang tersisa dilepas dari pelanggan)
        if pilih["pelanggan"]:
            q(Ticket).update({"customer_id": None}, synchronize_session=False)
            q(Device).update({"customer_id": None}, synchronize_session=False)
            q(MaintenanceSchedule).update({"customer_id": None}, synchronize_session=False)
            hasil["pelanggan"] = q(Customer).delete(synchronize_session=False)
            kosong.append(Customer)

        # 4. Perangkat
        if pilih["perangkat"]:
            q(Ticket).update({"device_id": None}, synchronize_session=False)
            q(MaintenanceSchedule).update({"device_id": None}, synchronize_session=False)
            hasil["perangkat"] = q(Device).delete(synchronize_session=False)
            kosong.append(Device)

        # 5. Teknisi (akun + undangan). Admin tidak disentuh.
        if pilih["teknisi"]:
            ids = [u.id for u in q(User.id).filter(User.role == "teknisi").all()]
            if ids:
                masih_dipakai = (
                    q(Ticket).filter(Ticket.dibuat_oleh.in_(ids)).first()
                    or q(TicketLog).filter(TicketLog.diubah_oleh.in_(ids)).first()
                    or q(TicketComment).filter(TicketComment.dibuat_oleh.in_(ids)).first()
                    or q(TicketAttachment).filter(TicketAttachment.diunggah_oleh.in_(ids)).first()
                    or q(MaintenanceSchedule).filter(MaintenanceSchedule.dibuat_oleh.in_(ids)).first()
                )
                if masih_dipakai:
                    db.session.rollback()
                    return error("Teknisi masih tercatat di tiket, log, komentar, atau lampiran. "
                                 "Centang juga \"Tiket\" agar riwayatnya ikut dikosongkan.", 409)
                q(Ticket).filter(Ticket.ditugaskan_ke.in_(ids)).update(
                    {"ditugaskan_ke": None}, synchronize_session=False)
                q(Notification).filter(Notification.user_id.in_(ids)).delete(synchronize_session=False)
                hasil["teknisi"] = q(User).filter(User.id.in_(ids)).delete(synchronize_session=False)
            else:
                hasil["teknisi"] = 0
            hasil["undangan"] = q(Invitation).delete(synchronize_session=False)

        db.session.commit()
        _reset_sequences(kosong)
        db.session.commit()
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        return error(f"Gagal mengosongkan data: {exc}", 500)

    return jsonify({"pesan": "Data terpilih berhasil dikosongkan", "dihapus": hasil})
