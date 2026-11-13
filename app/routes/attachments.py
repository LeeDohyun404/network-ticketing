import base64

from flask import Blueprint, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required

from ..extensions import db
from ..models import (
    ALLOWED_MIME, ATTACHMENT_TYPES, MAX_ATTACHMENT_BYTES,
    MAX_ATTACHMENTS_PER_TICKET, Ticket, TicketAttachment,
)
from ..utils import error

bp = Blueprint("attachments", __name__)


@bp.post("/tickets/<int:ticket_id>/attachments")
@jwt_required()
def upload_attachment(ticket_id):
    """Upload foto lampiran tiket (admin & teknisi yang ditugaskan)."""
    claims = get_jwt()
    uid = int(get_jwt_identity())

    ticket = db.session.get(Ticket, ticket_id)
    if ticket is None:
        return error("Tiket tidak ditemukan", 404)

    # Hak akses: admin atau teknisi yang ditugaskan
    if claims.get("role") != "admin" and ticket.ditugaskan_ke != uid:
        return error("Hanya admin atau teknisi yang ditugaskan yang dapat mengunggah lampiran", 403)

    # Cek batas jumlah lampiran
    total = TicketAttachment.query.filter_by(ticket_id=ticket_id).count()
    if total >= MAX_ATTACHMENTS_PER_TICKET:
        return error(f"Maksimal {MAX_ATTACHMENTS_PER_TICKET} lampiran per tiket", 400)

    data = request.get_json(silent=True) or {}

    nama_file = (data.get("nama_file") or "").strip()
    mime_type = (data.get("mime_type") or "").strip().lower()
    b64_data = (data.get("data") or "").strip()
    jenis = (data.get("jenis") or "umum").strip().lower()

    if not nama_file:
        return error("nama_file wajib diisi", 400)
    if mime_type not in ALLOWED_MIME:
        return error("Format file tidak didukung. Gunakan JPEG, PNG, WebP, atau GIF", 400)
    if jenis not in ATTACHMENT_TYPES:
        return error(f"Jenis lampiran harus salah satu dari: {', '.join(ATTACHMENT_TYPES)}", 400)
    if not b64_data:
        return error("Data gambar (base64) wajib diisi", 400)

    # Validasi ukuran
    try:
        raw = base64.b64decode(b64_data, validate=True)
    except Exception:
        return error("Data gambar tidak valid (bukan base64)", 400)

    if len(raw) > MAX_ATTACHMENT_BYTES:
        mb = MAX_ATTACHMENT_BYTES // (1024 * 1024)
        return error(f"Ukuran file melebihi batas {mb} MB", 400)

    att = TicketAttachment(
        ticket_id=ticket_id,
        nama_file=nama_file,
        mime_type=mime_type,
        data=b64_data,
        jenis=jenis,
        diunggah_oleh=uid,
    )
    db.session.add(att)
    db.session.commit()
    return att.to_dict(), 201


@bp.get("/tickets/<int:ticket_id>/attachments")
@jwt_required()
def list_attachments(ticket_id):
    """Daftar lampiran tiket (tanpa data gambar, hanya metadata)."""
    ticket = db.session.get(Ticket, ticket_id)
    if ticket is None:
        return error("Tiket tidak ditemukan", 404)

    items = TicketAttachment.query.filter_by(ticket_id=ticket_id).order_by(TicketAttachment.id).all()
    return {"lampiran": [a.to_dict() for a in items]}


@bp.get("/attachments/<int:att_id>")
@jwt_required()
def get_attachment(att_id):
    """Ambil 1 lampiran beserta data base64-nya."""
    att = db.session.get(TicketAttachment, att_id)
    if att is None:
        return error("Lampiran tidak ditemukan", 404)
    return att.to_dict(with_data=True)


@bp.delete("/attachments/<int:att_id>")
@jwt_required()
def delete_attachment(att_id):
    """Hapus lampiran (admin atau pengunggah)."""
    claims = get_jwt()
    uid = int(get_jwt_identity())

    att = db.session.get(TicketAttachment, att_id)
    if att is None:
        return error("Lampiran tidak ditemukan", 404)

    if claims.get("role") != "admin" and att.diunggah_oleh != uid:
        return error("Hanya admin atau pengunggah yang dapat menghapus lampiran ini", 403)

    db.session.delete(att)
    db.session.commit()
    return {"pesan": "Lampiran berhasil dihapus"}

