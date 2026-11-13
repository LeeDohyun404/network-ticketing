from datetime import datetime
from flask import Blueprint, jsonify, request

from ..extensions import db
from ..models import (
    Customer,
    Device,
    MaintenanceSchedule,
    PRIORITIES,
    RECURRENCE_TYPES,
    SCHEDULE_STATUSES,
    Ticket,
    utcnow,
)
from ..utils import current_user, error, roles_required

bp = Blueprint("maintenance", __name__, url_prefix="/maintenance-schedules")


def parse_datetime(dt_str):
    if not isinstance(dt_str, str):
        return None
    dt_str = dt_str.strip()
    # Support format ISO: YYYY-MM-DDTHH:MM:SS or YYYY-MM-DDTHH:MM or YYYY-MM-DD HH:MM:SS or YYYY-MM-DD
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(dt_str.replace("Z", ""), fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(dt_str.replace("Z", ""))
    except Exception:
        return None


def validate_schedule_data(data, partial=False):
    clean = {}

    if "judul" in data:
        val = data["judul"]
        if not isinstance(val, str) or not val.strip():
            return None, "judul wajib diisi berupa teks"
        val = val.strip()
        if len(val) > 150:
            return None, "judul maksimal 150 karakter"
        clean["judul"] = val
    elif not partial:
        return None, "judul wajib diisi"

    for field, max_len in (("deskripsi", 5000), ("pelanggan", 150), ("perangkat", 150), ("lokasi", 200)):
        if field in data:
            val = data[field]
            if val is not None and not isinstance(val, str):
                return None, f"{field} harus berupa teks"
            clean[field] = (val or "").strip()
            if len(clean[field]) > max_len:
                return None, f"{field} maksimal {max_len} karakter"

    if "prioritas" in data:
        prio = data["prioritas"]
        if prio not in PRIORITIES:
            return None, "prioritas harus salah satu dari: " + ", ".join(PRIORITIES)
        clean["prioritas"] = prio
    elif not partial:
        clean["prioritas"] = "sedang"

    if "pengulangan" in data:
        peng = data["pengulangan"]
        if peng not in RECURRENCE_TYPES:
            return None, "pengulangan harus salah satu dari: " + ", ".join(RECURRENCE_TYPES)
        clean["pengulangan"] = peng
    elif not partial:
        clean["pengulangan"] = "tidak_ada"

    if "status" in data:
        st = data["status"]
        if st not in SCHEDULE_STATUSES:
            return None, "status harus salah satu dari: " + ", ".join(SCHEDULE_STATUSES)
        clean["status"] = st
    elif not partial:
        clean["status"] = "terjadwal"

    if "tanggal_rencana" in data:
        dt = parse_datetime(data["tanggal_rencana"])
        if dt is None:
            return None, "tanggal_rencana format tanggal tidak valid"
        clean["tanggal_rencana"] = dt
    elif not partial:
        return None, "tanggal_rencana wajib diisi"

    if "customer_id" in data:
        cid = data["customer_id"]
        if cid is not None and cid != "" and cid != 0:
            if not isinstance(cid, int) or cid <= 0:
                return None, "customer_id harus berupa angka bulat positif"
            cust = db.session.get(Customer, cid)
            if not cust:
                return None, "Pelanggan tidak ditemukan"
            clean["customer_id"] = cid
            if not clean.get("pelanggan"):
                clean["pelanggan"] = cust.nama
        else:
            clean["customer_id"] = None
    elif not partial:
        clean["customer_id"] = None

    if "device_id" in data:
        did = data["device_id"]
        if did is not None and did != "" and did != 0:
            if not isinstance(did, int) or did <= 0:
                return None, "device_id harus berupa angka bulat positif"
            dev = db.session.get(Device, did)
            if not dev:
                return None, "Perangkat tidak ditemukan"
            clean["device_id"] = did
            if not clean.get("perangkat"):
                clean["perangkat"] = dev.nama
            if not clean.get("lokasi") and dev.lokasi:
                clean["lokasi"] = dev.lokasi
            if clean.get("customer_id") is None and dev.customer_id:
                clean["customer_id"] = dev.customer_id
                if not clean.get("pelanggan") and dev.customer:
                    clean["pelanggan"] = dev.customer.nama
        else:
            clean["device_id"] = None
    elif not partial:
        clean["device_id"] = None

    return clean, None


@bp.post("")
@roles_required("admin")
def create_schedule():
    data = request.get_json(silent=True) or {}
    clean, problem = validate_schedule_data(data)
    if problem:
        return error(problem)

    user = current_user()
    if not user:
        return error("Pengguna tidak ditemukan", 401)

    schedule = MaintenanceSchedule(**clean, dibuat_oleh=user.id)
    db.session.add(schedule)
    db.session.commit()
    return jsonify(schedule.to_dict()), 201


@bp.get("")
@roles_required("admin", "teknisi")
def list_schedules():
    query = MaintenanceSchedule.query

    status_filter = request.args.get("status")
    if status_filter:
        query = query.filter(MaintenanceSchedule.status == status_filter.strip())

    jatuh_tempo = request.args.get("jatuh_tempo")
    if jatuh_tempo and jatuh_tempo.lower() in ("true", "1", "ya"):
        query = query.filter(
            MaintenanceSchedule.status == "terjadwal",
            MaintenanceSchedule.tanggal_rencana < utcnow(),
        )

    q = request.args.get("q")
    if q:
        q_clean = f"%{q.strip().lower()}%"
        query = query.filter(
            db.or_(
                db.func.lower(MaintenanceSchedule.judul).like(q_clean),
                db.func.lower(MaintenanceSchedule.pelanggan).like(q_clean),
                db.func.lower(MaintenanceSchedule.perangkat).like(q_clean),
                db.func.lower(MaintenanceSchedule.lokasi).like(q_clean),
            )
        )

    query = query.order_by(MaintenanceSchedule.tanggal_rencana.asc())
    schedules = query.all()
    return jsonify({"data": [s.to_dict() for s in schedules]})


@bp.get("/<int:schedule_id>")
@roles_required("admin", "teknisi")
def get_schedule(schedule_id):
    schedule = db.session.get(MaintenanceSchedule, schedule_id)
    if not schedule:
        return error("Jadwal maintenance tidak ditemukan", 404)
    return jsonify(schedule.to_dict())


@bp.put("/<int:schedule_id>")
@roles_required("admin")
def update_schedule(schedule_id):
    schedule = db.session.get(MaintenanceSchedule, schedule_id)
    if not schedule:
        return error("Jadwal maintenance tidak ditemukan", 404)

    data = request.get_json(silent=True) or {}
    clean, problem = validate_schedule_data(data, partial=True)
    if problem:
        return error(problem)

    for field, val in clean.items():
        setattr(schedule, field, val)

    db.session.commit()
    return jsonify(schedule.to_dict())


@bp.post("/<int:schedule_id>/generate-ticket")
@roles_required("admin")
def generate_ticket_from_schedule(schedule_id):
    schedule = db.session.get(MaintenanceSchedule, schedule_id)
    if not schedule:
        return error("Jadwal maintenance tidak ditemukan", 404)

    if schedule.status == "dibatalkan":
        return error("Tidak dapat membuat tiket dari jadwal yang dibatalkan")

    user = current_user()
    if not user:
        return error("Pengguna tidak ditemukan", 401)

    pelanggan = schedule.pelanggan or (schedule.customer.nama if schedule.customer else "Publik / Lapangan")
    perangkat = schedule.perangkat or (schedule.device.nama if schedule.device else "")
    lokasi = schedule.lokasi or (schedule.device.lokasi if schedule.device else "")

    ticket = Ticket(
        judul=schedule.judul,
        deskripsi=f"[Pemeliharaan Terjadwal] {schedule.deskripsi}".strip() if schedule.deskripsi else "[Pemeliharaan Terjadwal]",
        pelanggan=pelanggan,
        customer_id=schedule.customer_id,
        jenis="pemeliharaan",
        perangkat=perangkat,
        device_id=schedule.device_id,
        lokasi=lokasi,
        prioritas=schedule.prioritas,
        status="open",
        dibuat_oleh=user.id,
    )
    db.session.add(ticket)
    db.session.flush()

    schedule.last_ticket_id = ticket.id
    schedule.advance_recurrence()

    db.session.commit()
    return jsonify({
        "pesan": "Tiket pemeliharaan berhasil dibuat",
        "tiket": ticket.to_dict(),
        "jadwal": schedule.to_dict(),
    }), 201


@bp.delete("/<int:schedule_id>")
@roles_required("admin")
def delete_schedule(schedule_id):
    schedule = db.session.get(MaintenanceSchedule, schedule_id)
    if not schedule:
        return error("Jadwal maintenance tidak ditemukan", 404)

    db.session.delete(schedule)
    db.session.commit()
    return jsonify({"pesan": "Jadwal maintenance dihapus"})

