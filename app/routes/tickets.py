from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt

from ..extensions import db
from ..models import (PRIORITIES, PRIORITY_RANK, STATUSES, TICKET_TYPES, TRANSITIONS,
                      Ticket, TicketLog, User, minutes_between, utcnow)
from ..utils import current_user, error, roles_required

bp = Blueprint("tickets", __name__)


def can_view(user, ticket):
    return user.role == "admin" or ticket.ditugaskan_ke == user.id


def validate(data, partial=False):
    """Kembalikan (field_bersih, pesan_error)."""
    clean = {}

    def text(key, max_len, required=False):
        if key in data:
            value = data[key]
            if not isinstance(value, str):
                return f"{key} harus berupa teks"
            value = value.strip()
            if required and not value:
                return f"{key} wajib diisi"
            if len(value) > max_len:
                return f"{key} maksimal {max_len} karakter"
            clean[key] = value
        elif required and not partial:
            return f"{key} wajib diisi"
        return None

    for key, max_len, required in (("judul", 150, True), ("pelanggan", 150, True),
                                   ("deskripsi", 5000, False), ("perangkat", 150, False),
                                   ("lokasi", 200, False)):
        problem = text(key, max_len, required)
        if problem:
            return None, problem

    if "jenis" in data:
        if data["jenis"] not in TICKET_TYPES:
            return None, "jenis harus salah satu dari: " + ", ".join(TICKET_TYPES)
        clean["jenis"] = data["jenis"]
    if "prioritas" in data:
        if data["prioritas"] not in PRIORITIES:
            return None, "prioritas harus salah satu dari: " + ", ".join(PRIORITIES)
        clean["prioritas"] = data["prioritas"]
    return clean, None


@bp.post("/tickets")
@roles_required("admin")
def create_ticket():
    data = request.get_json(silent=True) or {}
    clean, problem = validate(data)
    if problem:
        return error(problem)

    ticket = Ticket(**clean, dibuat_oleh=current_user().id)
    db.session.add(ticket)
    db.session.commit()
    return jsonify(ticket.to_dict()), 201


@bp.get("/tickets")
@roles_required("admin", "teknisi")
def list_tickets():
    user = current_user()
    query = Ticket.query
    if user.role == "teknisi":
        query = query.filter(Ticket.ditugaskan_ke == user.id)

    status = request.args.get("status")
    prioritas = request.args.get("prioritas")
    jenis = request.args.get("jenis")
    if status:
        if status not in STATUSES:
            return error("status tidak dikenal")
        query = query.filter(Ticket.status == status)
    if prioritas:
        if prioritas not in PRIORITIES:
            return error("prioritas tidak dikenal")
        query = query.filter(Ticket.prioritas == prioritas)
    if jenis:
        if jenis not in TICKET_TYPES:
            return error("jenis tidak dikenal")
        query = query.filter(Ticket.jenis == jenis)

    # Urutan tampil: prioritas tertinggi dulu, lalu yang paling lama menunggu.
    rank = db.case(PRIORITY_RANK, value=Ticket.prioritas)
    query = query.order_by(rank.desc(), Ticket.created_at.asc())

    try:
        page = max(int(request.args.get("page", 1)), 1)
        per_page = min(max(int(request.args.get("per_page", 20)), 1), 100)
    except ValueError:
        return error("page dan per_page harus angka")
    result = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "data": [t.to_dict() for t in result.items],
        "page": result.page,
        "per_page": per_page,
        "total": result.total,
    })


@bp.get("/tickets/summary")
@roles_required("admin")
def summary():
    per_status = {s: 0 for s in STATUSES}
    for status, count in db.session.query(Ticket.status, db.func.count(Ticket.id)).group_by(Ticket.status):
        per_status[status] = count

    respons, selesai = [], []
    for t in Ticket.query.all():
        r = minutes_between(t.created_at, t.responded_at)
        s = minutes_between(t.created_at, t.resolved_at)
        if r is not None:
            respons.append(r)
        if s is not None:
            selesai.append(s)

    def avg(values):
        return round(sum(values) / len(values), 1) if values else None

    return jsonify({
        "total": sum(per_status.values()),
        "per_status": per_status,
        "rata_rata_respons_menit": avg(respons),
        "rata_rata_penyelesaian_menit": avg(selesai),
    })


@bp.get("/tickets/<int:ticket_id>")
@roles_required("admin", "teknisi")
def get_ticket(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if ticket is None or not can_view(current_user(), ticket):
        return error("Tiket tidak ditemukan", 404)
    return jsonify(ticket.to_dict(with_logs=True))


@bp.put("/tickets/<int:ticket_id>")
@roles_required("admin")
def update_ticket(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if ticket is None:
        return error("Tiket tidak ditemukan", 404)
    data = request.get_json(silent=True) or {}
    clean, problem = validate(data, partial=True)
    if problem:
        return error(problem)
    for key, value in clean.items():
        setattr(ticket, key, value)
    db.session.commit()
    return jsonify(ticket.to_dict())


@bp.delete("/tickets/<int:ticket_id>")
@roles_required("admin")
def delete_ticket(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if ticket is None:
        return error("Tiket tidak ditemukan", 404)
    if ticket.status != "open":
        return error("Hanya tiket berstatus open yang boleh dihapus", 409)
    db.session.delete(ticket)
    db.session.commit()
    return jsonify({"pesan": "Tiket dihapus"})


@bp.put("/tickets/<int:ticket_id>/assign")
@roles_required("admin")
def assign_ticket(ticket_id):
    ticket = db.session.get(Ticket, ticket_id)
    if ticket is None:
        return error("Tiket tidak ditemukan", 404)
    if ticket.status in ("resolved", "closed"):
        return error("Tiket yang sudah selesai tidak bisa ditugaskan ulang", 409)

    data = request.get_json(silent=True) or {}
    teknisi_id = data.get("teknisi_id")
    teknisi = db.session.get(User, teknisi_id) if isinstance(teknisi_id, int) else None
    if teknisi is None or teknisi.role != "teknisi":
        return error("teknisi_id harus berupa id user dengan role teknisi")

    ticket.ditugaskan_ke = teknisi.id
    db.session.commit()
    return jsonify(ticket.to_dict())


@bp.put("/tickets/<int:ticket_id>/status")
@roles_required("admin", "teknisi")
def change_status(ticket_id):
    user = current_user()
    ticket = db.session.get(Ticket, ticket_id)
    if ticket is None or not can_view(user, ticket):
        return error("Tiket tidak ditemukan", 404)

    data = request.get_json(silent=True) or {}
    new_status = data.get("status")
    catatan = (data.get("catatan") or "").strip()
    if new_status not in STATUSES:
        return error("status harus salah satu dari: " + ", ".join(STATUSES))
    if new_status not in TRANSITIONS[ticket.status]:
        allowed = ", ".join(TRANSITIONS[ticket.status]) or "tidak ada"
        return error(f"Dari {ticket.status} hanya boleh ke: {allowed}", 409)
    if new_status == "closed" and user.role != "admin":
        return error("Hanya admin yang boleh menutup tiket", 403)
    if new_status == "in_progress" and ticket.ditugaskan_ke is None:
        return error("Tugaskan tiket ke teknisi sebelum diproses", 409)

    now = utcnow()
    old_status = ticket.status
    ticket.status = new_status
    if new_status == "in_progress":
        if ticket.responded_at is None:
            ticket.responded_at = now
        ticket.resolved_at = None  # dibuka lagi
    elif new_status == "resolved":
        ticket.resolved_at = now

    db.session.add(TicketLog(ticket_id=ticket.id, status_lama=old_status, status_baru=new_status,
                             diubah_oleh=user.id, catatan=catatan, waktu=now))
    db.session.commit()
    return jsonify(ticket.to_dict(with_logs=True))
