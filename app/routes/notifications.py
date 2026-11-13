from flask import Blueprint, jsonify, request
from flask_jwt_extended import current_user, get_jwt, get_jwt_identity, jwt_required

from ..extensions import db
from ..mailer import send_ticket_notification
from ..models import Notification, Ticket, TicketLog, User, utcnow
from ..utils import error

bp = Blueprint("notifications", __name__)


def _notify_and_email(user, ticket, subjek, pesan, tipe="eskalasi"):
    """Buat in-app notification dan kirim email ke user."""
    notif = Notification(
        user_id=user.id,
        ticket_id=ticket.id if ticket else None,
        judul=subjek,
        pesan=pesan,
        tipe=tipe,
    )
    db.session.add(notif)
    # Kirim email ke alamat asli user
    if user.email:
        send_ticket_notification(
            to=user.email,
            nama=user.nama,
            subjek=subjek,
            isi_pesan=pesan,
            ticket_info=ticket.to_dict() if ticket else None,
        )


@bp.post("/tickets/<int:ticket_id>/escalate")
@jwt_required()
def escalate_ticket(ticket_id):
    """Eskalasi tiket secara manual oleh admin atau teknisi terkait."""
    claims = get_jwt()
    uid = int(get_jwt_identity())
    caller_role = claims.get("role")

    ticket = db.session.get(Ticket, ticket_id)
    if ticket is None:
        return error("Tiket tidak ditemukan", 404)

    # Hanya admin atau teknisi yang ditugaskan yang boleh eskalasi
    if caller_role != "admin" and ticket.ditugaskan_ke != uid:
        return error("Hanya admin atau teknisi yang ditugaskan yang dapat melakukan eskalasi", 403)

    if ticket.status in ("resolved", "closed"):
        return error("Tiket yang sudah selesai atau ditutup tidak dapat dieskalasi", 400)

    data = request.get_json(silent=True) or {}
    alasan = (data.get("alasan") or "").strip()
    if not alasan:
        return error("Alasan eskalasi wajib diisi", 400)

    old_level = ticket.escalation_level or 0
    level = data.get("level")
    if level is not None:
        try:
            level = int(level)
            if level <= 0:
                level = old_level + 1
        except ValueError:
            level = old_level + 1
    else:
        level = old_level + 1

    ticket.is_escalated = True
    ticket.escalation_level = level
    ticket.escalated_at = utcnow()
    ticket.escalation_reason = alasan

    # Jika prioritas masih rendah atau sedang, naikkan ke kritis / tinggi
    if ticket.prioritas in ("rendah", "sedang"):
        ticket.prioritas = "tinggi" if level == 1 else "kritis"

    log = TicketLog(
        ticket_id=ticket.id,
        aksi="eskalasi",
        field_diubah="eskalasi",
        nilai_lama=f"Level {old_level}",
        nilai_baru=f"Level {level}",
        diubah_oleh=uid,
        catatan=alasan,
    )
    db.session.add(log)

    # Kirim notifikasi & email ke teknisi jika ada
    subjek_email = f"⚠️ [ESKALASI LEVEL {level}] Tiket #{ticket.id} - {ticket.judul}"
    pesan_email = (
        f"Tiket #{ticket.id} ({ticket.judul}) telah dieskalasi ke Level {level}.\n"
        f"Alasan eskalasi: {alasan}\n"
        f"Pelanggan: {ticket.pelanggan} | Lokasi: {ticket.lokasi or '-'}"
    )

    if ticket.ditugaskan_ke:
        tech = db.session.get(User, ticket.ditugaskan_ke)
        if tech and tech.id != uid:
            _notify_and_email(tech, ticket, subjek_email, pesan_email, tipe="eskalasi")

    # Kirim notifikasi & email ke semua admin
    admins = User.query.filter_by(role="admin").all()
    for adm in admins:
        if adm.id != uid:
            _notify_and_email(adm, ticket, subjek_email, pesan_email, tipe="eskalasi")

    db.session.commit()
    return jsonify({
        "pesan": f"Tiket berhasil dieskalasi ke Level {level}",
        "tiket": ticket.to_dict(with_logs=True),
    })


@bp.post("/tickets/auto-escalate")
@jwt_required()
def auto_escalate():
    """Pengecekan massal untuk auto-eskalasi tiket yang melanggar SLA."""
    claims = get_jwt()
    if claims.get("role") != "admin":
        return error("Hanya admin yang boleh menjalankan auto-eskalasi", 403)

    active_tickets = Ticket.query.filter(Ticket.status.in_(["open", "in_progress"])).all()
    escalated_count = 0
    now = utcnow()

    for t in active_tickets:
        sla_info = t.calculate_sla(now=now)
        if sla_info.get("melewati_sla") and not t.is_escalated:
            t.is_escalated = True
            t.escalation_level = 1
            t.escalated_at = now
            t.escalation_reason = "Pelanggaran SLA target waktu (Otomatis oleh sistem)"
            if t.prioritas in ("rendah", "sedang"):
                t.prioritas = "kritis"

            log = TicketLog(
                ticket_id=t.id,
                aksi="eskalasi",
                field_diubah="eskalasi",
                nilai_lama="Level 0",
                nilai_baru="Level 1",
                diubah_oleh=int(get_jwt_identity()),
                catatan=t.escalation_reason,
            )
            db.session.add(log)

            subjek = f"🚨 [AUTO-ESKALASI SLA] Tiket #{t.id} - {t.judul}"
            pesan = f"Tiket #{t.id} melanggar target batas SLA dan otomatis dieskalasi ke Level 1."
            if t.ditugaskan_ke:
                tech = db.session.get(User, t.ditugaskan_ke)
                if tech:
                    _notify_and_email(tech, t, subjek, pesan, tipe="sla_breach")

            escalated_count += 1

    db.session.commit()
    return jsonify({"pesan": f"{escalated_count} tiket berhasil dieskalasi otomatis", "total": escalated_count})


@bp.get("/notifications")
@jwt_required()
def list_notifications():
    """Ambil daftar notifikasi untuk user saat ini."""
    uid = int(get_jwt_identity())
    unread_only = request.args.get("unread_only", "").lower() == "true"

    query = Notification.query.filter_by(user_id=uid)
    if unread_only:
        query = query.filter_by(dibaca=False)

    items = query.order_by(Notification.created_at.desc()).limit(50).all()
    unread_count = Notification.query.filter_by(user_id=uid, dibaca=False).count()

    return jsonify({
        "data": [n.to_dict() for n in items],
        "unread_count": unread_count,
    })


@bp.put("/notifications/<int:notif_id>/read")
@jwt_required()
def mark_read(notif_id):
    """Tandai 1 notifikasi telah dibaca."""
    uid = int(get_jwt_identity())
    notif = db.session.get(Notification, notif_id)
    if notif is None or notif.user_id != uid:
        return error("Notifikasi tidak ditemukan", 404)

    notif.dibaca = True
    db.session.commit()
    return jsonify({"pesan": "Notifikasi ditandai telah dibaca"})


@bp.put("/notifications/read-all")
@jwt_required()
def mark_all_read():
    """Tandai semua notifikasi user telah dibaca."""
    uid = int(get_jwt_identity())
    Notification.query.filter_by(user_id=uid, dibaca=False).update({"dibaca": True})
    db.session.commit()
    return jsonify({"pesan": "Semua notifikasi ditandai telah dibaca"})

