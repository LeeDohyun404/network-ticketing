from flask import Blueprint, jsonify, request

from ..extensions import db
from ..models import (PRIORITIES, PRIORITY_RANK, STATUSES, TICKET_TYPES, TRANSITIONS,
                      Customer, Device, Ticket, TicketLog, TicketComment, SlaTarget, User, minutes_between, utcnow)
from ..utils import current_user, error, roles_required

bp = Blueprint("tickets", __name__)


def can_view(user, ticket):
    if user is None:
        return False
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
            if key == "pelanggan" and data.get("customer_id"):
                pass
            else:
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

    if "customer_id" in data:
        cid = data["customer_id"]
        if cid is not None:
            if not isinstance(cid, int) or cid <= 0:
                return None, "customer_id harus berupa angka bulat positif"
            cust = db.session.get(Customer, cid)
            if not cust:
                return None, "Pelanggan tidak ditemukan"
            clean["customer_id"] = cust.id
            if not clean.get("pelanggan"):
                clean["pelanggan"] = cust.nama
        elif partial:
            clean["customer_id"] = None

    if "device_id" in data:
        did = data["device_id"]
        if did is not None:
            if not isinstance(did, int) or did <= 0:
                return None, "device_id harus berupa angka bulat positif"
            dev = db.session.get(Device, did)
            if not dev:
                return None, "Perangkat tidak ditemukan"
            if clean.get("customer_id") and dev.customer_id and dev.customer_id != clean["customer_id"]:
                return None, "Perangkat tidak terdaftar pada pelanggan ini"
            clean["device_id"] = dev.id
            if not clean.get("customer_id") and dev.customer_id:
                clean["customer_id"] = dev.customer_id
                if not clean.get("pelanggan") and dev.customer:
                    clean["pelanggan"] = dev.customer.nama
            if not clean.get("perangkat"):
                clean["perangkat"] = dev.nama
            if not clean.get("lokasi") and dev.lokasi:
                clean["lokasi"] = dev.lokasi
        elif partial:
            clean["device_id"] = None

    return clean, None


@bp.post("/tickets")
@roles_required("admin")
def create_ticket():
    data = request.get_json(silent=True) or {}
    clean, problem = validate(data)
    if problem:
        return error(problem)

    user = current_user()
    if user is None:
        return error("Pengguna tidak ditemukan", 401)

    ticket = Ticket(**clean, dibuat_oleh=user.id)
    db.session.add(ticket)
    db.session.commit()
    return jsonify(ticket.to_dict()), 201


@bp.get("/tickets")
@roles_required("admin", "teknisi")
def list_tickets():
    user = current_user()
    if user is None:
        return error("Pengguna tidak ditemukan", 401)
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

    cid = request.args.get("customer_id")
    if cid:
        try:
            query = query.filter(Ticket.customer_id == int(cid))
        except ValueError:
            return error("customer_id harus angka")

    did = request.args.get("device_id")
    if did:
        try:
            query = query.filter(Ticket.device_id == int(did))
        except ValueError:
            return error("device_id harus angka")

    # Urutan tampil: prioritas tertinggi dulu, lalu yang paling lama menunggu.
    rank = db.case(PRIORITY_RANK, value=Ticket.prioritas)
    query = query.order_by(rank.desc(), Ticket.created_at.asc())

    try:
        page = max(int(request.args.get("page", 1)), 1)
        per_page = min(max(int(request.args.get("per_page", 20)), 1), 100)
    except ValueError:
        return error("page dan per_page harus angka")

    targets_map = SlaTarget.get_targets_map()
    now = utcnow()
    melewati_sla_param = request.args.get("melewati_sla")

    if melewati_sla_param is not None:
        val = melewati_sla_param.strip().lower()
        if val in ("true", "1", "ya"):
            is_breached = True
        elif val in ("false", "0", "tidak"):
            is_breached = False
        else:
            return error("melewati_sla harus bernilai true atau false")

        all_items = query.all()
        filtered = [t for t in all_items if t.calculate_sla(targets_map, now)["melewati_sla"] is is_breached]
        total = len(filtered)
        start = (page - 1) * per_page
        end = start + per_page
        items = filtered[start:end]
        return jsonify({
            "data": [t.to_dict(targets_map=targets_map, now=now) for t in items],
            "page": page,
            "per_page": per_page,
            "total": total,
        })

    result = query.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        "data": [t.to_dict(targets_map=targets_map, now=now) for t in result.items],
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

    all_tickets = Ticket.query.all()
    targets_map = SlaTarget.get_targets_map()
    now = utcnow()

    respons, selesai = [], []
    jumlah_melewati_sla = 0
    pelanggaran_respons = 0
    pelanggaran_penyelesaian = 0

    for t in all_tickets:
        sla = t.calculate_sla(targets_map, now)
        if sla["respons_menit"] is not None:
            respons.append(sla["respons_menit"])
        if sla["penyelesaian_menit"] is not None:
            selesai.append(sla["penyelesaian_menit"])
        if sla["melewati_sla_respons"]:
            pelanggaran_respons += 1
        if sla["melewati_sla_penyelesaian"]:
            pelanggaran_penyelesaian += 1
        if sla["melewati_sla"]:
            jumlah_melewati_sla += 1

    total_tiket = sum(per_status.values())
    jumlah_memenuhi_sla = total_tiket - jumlah_melewati_sla
    persentase_memenuhi_sla = round((jumlah_memenuhi_sla / total_tiket * 100), 1) if total_tiket > 0 else 100.0

    def avg(values):
        return round(sum(values) / len(values), 1) if values else None

    return jsonify({
        "total": total_tiket,
        "per_status": per_status,
        "rata_rata_respons_menit": avg(respons),
        "rata_rata_penyelesaian_menit": avg(selesai),
        "jumlah_melewati_sla": jumlah_melewati_sla,
        "jumlah_memenuhi_sla": jumlah_memenuhi_sla,
        "persentase_memenuhi_sla": persentase_memenuhi_sla,
        "pelanggaran_respons": pelanggaran_respons,
        "pelanggaran_penyelesaian": pelanggaran_penyelesaian,
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

    user = current_user()
    now = utcnow()
    for key, value in clean.items():
        old_val = getattr(ticket, key)
        if old_val != value:
            setattr(ticket, key, value)
            if key == "prioritas":
                db.session.add(TicketLog(
                    ticket_id=ticket.id,
                    aksi="prioritas",
                    field_diubah="prioritas",
                    nilai_lama=old_val,
                    nilai_baru=value,
                    status_lama=ticket.status,
                    status_baru=ticket.status,
                    diubah_oleh=user.id if user else ticket.dibuat_oleh,
                    catatan=f"Prioritas diubah dari {old_val} ke {value}",
                    waktu=now,
                ))
            else:
                db.session.add(TicketLog(
                    ticket_id=ticket.id,
                    aksi="edit",
                    field_diubah=key,
                    nilai_lama=old_val,
                    nilai_baru=value,
                    status_lama=ticket.status,
                    status_baru=ticket.status,
                    diubah_oleh=user.id if user else ticket.dibuat_oleh,
                    catatan=f"Mengubah {key}",
                    waktu=now,
                ))

    db.session.commit()
    return jsonify(ticket.to_dict(with_logs=True))


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

    user = current_user()
    old_tek = db.session.get(User, ticket.ditugaskan_ke) if ticket.ditugaskan_ke else None
    old_name = old_tek.nama if old_tek else "Belum ditugaskan"

    ticket.ditugaskan_ke = teknisi.id
    db.session.add(TicketLog(
        ticket_id=ticket.id,
        aksi="penugasan",
        field_diubah="ditugaskan_ke",
        nilai_lama=old_name,
        nilai_baru=teknisi.nama,
        status_lama=ticket.status,
        status_baru=ticket.status,
        diubah_oleh=user.id if user else ticket.dibuat_oleh,
        catatan=f"Tiket ditugaskan kepada {teknisi.nama}",
        waktu=utcnow(),
    ))
    db.session.commit()
    return jsonify(ticket.to_dict(with_logs=True))


@bp.put("/tickets/<int:ticket_id>/status")
@roles_required("admin", "teknisi")
def change_status(ticket_id):
    user = current_user()
    if user is None:
        return error("Pengguna tidak ditemukan", 401)
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


@bp.get("/sla-targets")
@roles_required("admin", "teknisi")
def list_sla_targets():
    targets = SlaTarget.query.all()
    if not targets:
        SlaTarget.seed_defaults()
        targets = SlaTarget.query.all()
    return jsonify({"data": [t.to_dict() for t in targets]})


@bp.put("/sla-targets/<string:prioritas>")
@roles_required("admin")
def update_sla_target(prioritas):
    if prioritas not in PRIORITIES:
        return error("prioritas harus salah satu dari: " + ", ".join(PRIORITIES))

    data = request.get_json(silent=True) or {}
    resp = data.get("target_respons_menit")
    res = data.get("target_penyelesaian_menit")

    if not isinstance(resp, int) or resp <= 0:
        return error("target_respons_menit harus berupa angka bulat positif")
    if not isinstance(res, int) or res <= 0:
        return error("target_penyelesaian_menit harus berupa angka bulat positif")

    target = SlaTarget.query.filter_by(prioritas=prioritas).first()
    if not target:
        target = SlaTarget(prioritas=prioritas, target_respons_menit=resp, target_penyelesaian_menit=res)
        db.session.add(target)
    else:
        target.target_respons_menit = resp
        target.target_penyelesaian_menit = res

    db.session.commit()
    return jsonify(target.to_dict())


@bp.get("/tickets/<int:ticket_id>/logs")
@roles_required("admin", "teknisi")
def list_ticket_logs(ticket_id):
    user = current_user()
    if user is None:
        return error("Pengguna tidak ditemukan", 401)
    ticket = db.session.get(Ticket, ticket_id)
    if ticket is None or not can_view(user, ticket):
        return error("Tiket tidak ditemukan", 404)

    query = TicketLog.query.filter(TicketLog.ticket_id == ticket_id)
    aksi = request.args.get("aksi")
    if aksi:
        query = query.filter(TicketLog.aksi == aksi)

    diubah_oleh = request.args.get("diubah_oleh")
    if diubah_oleh:
        try:
            query = query.filter(TicketLog.diubah_oleh == int(diubah_oleh))
        except ValueError:
            return error("diubah_oleh harus berupa angka")

    logs = query.order_by(TicketLog.waktu.asc(), TicketLog.id.asc()).all()
    return jsonify({"data": [log.to_dict() for log in logs]})


@bp.post("/tickets/<int:ticket_id>/comments")
@roles_required("admin", "teknisi")
def add_ticket_comment(ticket_id):
    user = current_user()
    if user is None:
        return error("Pengguna tidak ditemukan", 401)
    ticket = db.session.get(Ticket, ticket_id)
    if ticket is None or not can_view(user, ticket):
        return error("Tiket tidak ditemukan", 404)

    data = request.get_json(silent=True) or {}
    pesan = data.get("pesan")
    if not isinstance(pesan, str) or not pesan.strip():
        return error("pesan komentar wajib diisi")
    pesan = pesan.strip()
    if len(pesan) > 2000:
        return error("pesan komentar maksimal 2000 karakter")

    komentar = TicketComment(ticket_id=ticket.id, dibuat_oleh=user.id, pesan=pesan)
    db.session.add(komentar)
    db.session.commit()
    return jsonify(komentar.to_dict()), 201


@bp.get("/tickets/<int:ticket_id>/comments")
@roles_required("admin", "teknisi")
def list_ticket_comments(ticket_id):
    user = current_user()
    if user is None:
        return error("Pengguna tidak ditemukan", 401)
    ticket = db.session.get(Ticket, ticket_id)
    if ticket is None or not can_view(user, ticket):
        return error("Tiket tidak ditemukan", 404)

    komentar_list = TicketComment.query.filter_by(ticket_id=ticket.id).order_by(TicketComment.created_at.asc(), TicketComment.id.asc()).all()
    return jsonify({"data": [c.to_dict() for c in komentar_list]})
