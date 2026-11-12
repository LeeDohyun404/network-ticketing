import hashlib
import os
import re
import secrets
from datetime import timedelta

from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, get_jwt, verify_jwt_in_request

from ..extensions import db
from ..mailer import send_activation
from ..models import ROLES, Invitation, Ticket, TicketLog, User, utcnow
from ..utils import current_user, error, roles_required

bp = Blueprint("auth", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@bp.post("/auth/register")
def register():
    """Akun pertama otomatis menjadi admin. Setelah itu hanya admin yang boleh membuat akun."""
    data = request.get_json(silent=True) or {}
    first_user = db.session.query(User.id).first() is None

    if first_user:
        role = "admin"
    else:
        verify_jwt_in_request()
        if get_jwt().get("role") != "admin":
            return error("Hanya admin yang boleh membuat akun", 403)
        role = data.get("role", "teknisi")
        if role not in ROLES:
            return error("Role harus salah satu dari: " + ", ".join(ROLES))

    nama = (data.get("nama") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not nama:
        return error("Nama wajib diisi")
    if not EMAIL_RE.match(email):
        return error("Format email tidak valid")
    if len(password) < 8:
        return error("Password minimal 8 karakter")
    if User.query.filter_by(email=email).first():
        return error("Email sudah terdaftar", 409)

    user = User(nama=nama, email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return jsonify(user.to_dict()), 201


@bp.post("/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    user = User.query.filter_by(email=email).first()
    if user is None or not user.check_password(password):
        return error("Email atau password salah", 401)

    token = create_access_token(identity=str(user.id), additional_claims={"role": user.role})
    return jsonify({"access_token": token, "user": user.to_dict()})


@bp.get("/auth/me")
@roles_required("admin", "teknisi")
def me():
    return jsonify(current_user().to_dict())


@bp.get("/users")
@roles_required("admin")
def list_users():
    role = request.args.get("role")
    query = User.query
    if role in ROLES:
        query = query.filter_by(role=role)
    return jsonify([u.to_dict() for u in query.order_by(User.id).all()])


# ---------- Undangan teknisi lewat email ----------
INVITE_HOURS = 48


def _hash(token):
    return hashlib.sha256((token or "").encode()).hexdigest()


def _valid_invite(token):
    inv = Invitation.query.filter_by(token_hash=_hash(token)).first()
    if inv is None or inv.used_at is not None or inv.expires_at < utcnow():
        return None
    return inv


@bp.post("/users/invite")
@roles_required("admin")
def invite():
    """Admin memasukkan nama dan email. Sistem mengirim tautan aktivasi ke email itu."""
    data = request.get_json(silent=True) or {}
    nama = (data.get("nama") or "").strip()
    email = (data.get("email") or "").strip().lower()
    if not nama:
        return error("Nama wajib diisi")
    if not EMAIL_RE.match(email):
        return error("Format email tidak valid")
    if User.query.filter_by(email=email).first():
        return error("Email sudah terdaftar", 409)

    Invitation.query.filter_by(email=email, used_at=None).delete()  # undang ulang = tautan lama hangus
    token = secrets.token_urlsafe(32)
    db.session.add(Invitation(nama=nama, email=email, token_hash=_hash(token),
                              expires_at=utcnow() + timedelta(hours=INVITE_HOURS)))
    db.session.commit()

    base = (os.getenv("APP_BASE_URL") or request.host_url).rstrip("/")
    link = f"{base}/ui?aktivasi={token}"
    sent, note = send_activation(email, nama, link, INVITE_HOURS)
    out = {"nama": nama, "email": email, "email_terkirim": sent, "berlaku_jam": INVITE_HOURS}
    if not sent:  # email belum diatur / gagal: admin bisa menyalin tautannya manual
        out["link_aktivasi"] = link
        out["catatan"] = note
    return jsonify(out), 201


@bp.get("/users/invitations")
@roles_required("admin")
def list_invitations():
    rows = Invitation.query.filter_by(used_at=None).order_by(Invitation.id.desc()).all()
    return jsonify([r.to_dict() for r in rows])


@bp.delete("/users/invitations/<int:inv_id>")
@roles_required("admin")
def cancel_invitation(inv_id):
    inv = db.session.get(Invitation, inv_id)
    if inv is None or inv.used_at is not None:
        return error("Undangan tidak ditemukan", 404)
    db.session.delete(inv)
    db.session.commit()
    return jsonify({"dihapus": inv_id})


@bp.get("/auth/invite/<token>")
def check_invite(token):
    inv = _valid_invite(token)
    if inv is None:
        return error("Tautan aktivasi tidak valid atau sudah kedaluwarsa", 404)
    return jsonify({"nama": inv.nama, "email": inv.email})


@bp.post("/auth/activate")
def activate():
    data = request.get_json(silent=True) or {}
    inv = _valid_invite(data.get("token"))
    if inv is None:
        return error("Tautan aktivasi tidak valid atau sudah kedaluwarsa", 404)
    password = data.get("password") or ""
    if len(password) < 8:
        return error("Password minimal 8 karakter")
    if User.query.filter_by(email=inv.email).first():
        return error("Email sudah terdaftar", 409)

    user = User(nama=inv.nama, email=inv.email, role="teknisi")
    user.set_password(password)
    inv.used_at = utcnow()
    db.session.add(user)
    db.session.commit()
    return jsonify(user.to_dict()), 201


@bp.delete("/users/<int:user_id>")
@roles_required("admin")
def delete_technician(user_id):
    """Admin menghapus teknisi. Admin tidak bisa dihapus lewat sini."""
    user = db.session.get(User, user_id)
    if user is None or user.role != "teknisi":
        return error("Teknisi tidak ditemukan", 404)
    if TicketLog.query.filter_by(diubah_oleh=user.id).first():
        return error("Teknisi ini sudah punya riwayat perubahan tiket, jadi tidak bisa dihapus "
                     "agar riwayat tetap utuh", 409)
    Ticket.query.filter_by(ditugaskan_ke=user.id).update({"ditugaskan_ke": None})
    db.session.delete(user)
    db.session.commit()
    return jsonify({"dihapus": user_id})
