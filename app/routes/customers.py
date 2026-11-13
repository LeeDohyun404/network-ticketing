from flask import Blueprint, jsonify, request

from ..extensions import db
from ..models import Customer, Device, Ticket
from ..utils import error, roles_required

bp = Blueprint("customers", __name__)


def validate_customer_data(data, partial=False):
    clean = {}
    if "nama" in data:
        val = data["nama"]
        if not isinstance(val, str) or not val.strip():
            return None, "nama wajib diisi berupa teks"
        val = val.strip()
        if len(val) > 150:
            return None, "nama maksimal 150 karakter"
        clean["nama"] = val
    elif not partial:
        return None, "nama wajib diisi"

    for field, max_len in (("alamat", 500), ("kontak", 100)):
        if field in data:
            val = data[field]
            if val is not None and not isinstance(val, str):
                return None, f"{field} harus berupa teks"
            clean[field] = (val or "").strip()
            if len(clean[field]) > max_len:
                return None, f"{field} maksimal {max_len} karakter"
    return clean, None


def validate_device_data(data, partial=False):
    clean = {}
    if "nama" in data:
        val = data["nama"]
        if not isinstance(val, str) or not val.strip():
            return None, "nama wajib diisi berupa teks"
        val = val.strip()
        if len(val) > 150:
            return None, "nama maksimal 150 karakter"
        clean["nama"] = val
    elif not partial:
        return None, "nama wajib diisi"

    if "customer_id" in data:
        cid = data["customer_id"]
        if cid is not None and cid != "" and cid != 0:
            if not isinstance(cid, int) or cid <= 0:
                return None, "customer_id harus berupa angka bulat positif"
            if not db.session.get(Customer, cid):
                return None, "Pelanggan tidak ditemukan"
            clean["customer_id"] = cid
        else:
            clean["customer_id"] = None
    elif not partial:
        clean["customer_id"] = None

    for field, max_len in (("jenis", 50), ("lokasi", 200)):
        if field in data:
            val = data[field]
            if val is not None and not isinstance(val, str):
                return None, f"{field} harus berupa teks"
            clean[field] = (val or "").strip()
            if len(clean[field]) > max_len:
                return None, f"{field} maksimal {max_len} karakter"
    return clean, None


# ==========================================
# ENDPOINT PELANGGAN (CUSTOMERS)
# ==========================================

@bp.post("/customers")
@roles_required("admin")
def create_customer():
    data = request.get_json(silent=True) or {}
    clean, problem = validate_customer_data(data)
    if problem:
        return error(problem)

    customer = Customer(**clean)
    db.session.add(customer)
    db.session.commit()
    return jsonify(customer.to_dict()), 201


@bp.get("/customers")
@roles_required("admin", "teknisi")
def list_customers():
    query = Customer.query
    q = request.args.get("q")
    if q:
        q_clean = f"%{q.strip().lower()}%"
        query = query.filter(
            db.or_(
                db.func.lower(Customer.nama).like(q_clean),
                db.func.lower(Customer.alamat).like(q_clean),
                db.func.lower(Customer.kontak).like(q_clean),
            )
        )
    query = query.order_by(Customer.nama.asc())
    customers = query.all()
    return jsonify({"data": [c.to_dict() for c in customers]})


@bp.get("/customers/<int:customer_id>")
@roles_required("admin", "teknisi")
def get_customer(customer_id):
    customer = db.session.get(Customer, customer_id)
    if not customer:
        return error("Pelanggan tidak ditemukan", 404)
    return jsonify(customer.to_dict(with_devices=True))


@bp.put("/customers/<int:customer_id>")
@roles_required("admin")
def update_customer(customer_id):
    customer = db.session.get(Customer, customer_id)
    if not customer:
        return error("Pelanggan tidak ditemukan", 404)

    data = request.get_json(silent=True) or {}
    clean, problem = validate_customer_data(data, partial=True)
    if problem:
        return error(problem)

    for k, v in clean.items():
        setattr(customer, k, v)
    db.session.commit()
    return jsonify(customer.to_dict(with_devices=True))


@bp.delete("/customers/<int:customer_id>")
@roles_required("admin")
def delete_customer(customer_id):
    customer = db.session.get(Customer, customer_id)
    if not customer:
        return error("Pelanggan tidak ditemukan", 404)

    active_tickets = Ticket.query.filter(
        Ticket.customer_id == customer_id,
        Ticket.status.in_(["open", "in_progress"]),
    ).count()
    if active_tickets > 0:
        return error("Tidak dapat menghapus pelanggan yang masih memiliki tiket aktif", 409)

    db.session.delete(customer)
    db.session.commit()
    return jsonify({"pesan": "Pelanggan dihapus"})


# ==========================================
# ENDPOINT PERANGKAT (DEVICES)
# ==========================================

@bp.post("/devices")
@roles_required("admin")
def create_device():
    data = request.get_json(silent=True) or {}
    clean, problem = validate_device_data(data)
    if problem:
        return error(problem)

    device = Device(**clean)
    db.session.add(device)
    db.session.commit()
    return jsonify(device.to_dict()), 201


@bp.get("/devices")
@roles_required("admin", "teknisi")
def list_devices():
    query = Device.query
    cid = request.args.get("customer_id")
    if cid:
        try:
            cid_int = int(cid)
            query = query.filter(Device.customer_id == cid_int)
        except ValueError:
            return error("customer_id harus berupa angka")

    q = request.args.get("q")
    if q:
        q_clean = f"%{q.strip().lower()}%"
        query = query.filter(
            db.or_(
                db.func.lower(Device.nama).like(q_clean),
                db.func.lower(Device.jenis).like(q_clean),
                db.func.lower(Device.lokasi).like(q_clean),
            )
        )
    query = query.order_by(Device.nama.asc())
    devices = query.all()
    return jsonify({"data": [d.to_dict() for d in devices]})


@bp.get("/devices/<int:device_id>")
@roles_required("admin", "teknisi")
def get_device(device_id):
    device = db.session.get(Device, device_id)
    if not device:
        return error("Perangkat tidak ditemukan", 404)
    return jsonify(device.to_dict())


@bp.put("/devices/<int:device_id>")
@roles_required("admin")
def update_device(device_id):
    device = db.session.get(Device, device_id)
    if not device:
        return error("Perangkat tidak ditemukan", 404)

    data = request.get_json(silent=True) or {}
    clean, problem = validate_device_data(data, partial=True)
    if problem:
        return error(problem)

    for k, v in clean.items():
        setattr(device, k, v)
    db.session.commit()
    return jsonify(device.to_dict())


@bp.delete("/devices/<int:device_id>")
@roles_required("admin")
def delete_device(device_id):
    device = db.session.get(Device, device_id)
    if not device:
        return error("Perangkat tidak ditemukan", 404)

    active_tickets = Ticket.query.filter(
        Ticket.device_id == device_id,
        Ticket.status.in_(["open", "in_progress"]),
    ).count()
    if active_tickets > 0:
        return error("Tidak dapat menghapus perangkat yang sedang dalam penanganan tiket aktif", 409)

    db.session.delete(device)
    db.session.commit()
    return jsonify({"pesan": "Perangkat dihapus"})

