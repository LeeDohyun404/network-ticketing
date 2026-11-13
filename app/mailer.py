import os
import smtplib
import ssl
from email.message import EmailMessage

from flask import current_app


def _ssl_context():
    """Pakai daftar sertifikat dari certifi (server Wasmer tidak punya bawaan)."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def send_activation(to, nama, link, hours):
    """Kirim email aktivasi. Mengembalikan (terkirim, catatan)."""
    host = os.getenv("MAIL_SERVER")
    api_key = os.getenv("BREVO_API_KEY")
    script_url = os.getenv("APPS_SCRIPT_URL")
    if current_app.config.get("TESTING") or not (host or api_key or script_url):
        print(f"[EMAIL tidak dikirim] tautan aktivasi untuk {to}: {link}")
        return False, "Email belum diatur (MAIL_SERVER kosong). Salin tautan ini dan kirim manual."

    if script_url and not current_app.config.get("TESTING"):
        return _send_apps_script(script_url, to, nama, link, hours)
    if api_key and not current_app.config.get("TESTING"):
        return _send_brevo(api_key, to, nama, link, hours)

    msg = EmailMessage()
    msg["Subject"] = "Aktifkan akun teknisi Anda"
    msg["From"] = os.getenv("MAIL_FROM") or os.getenv("MAIL_USERNAME", "")
    msg["To"] = to
    msg.set_content(
        f"Halo {nama},\n\nAdmin mengundang Anda sebagai teknisi di Network Incident Ticketing.\n"
        f"Buka tautan berikut untuk membuat password dan mengaktifkan akun:\n\n{link}\n\n"
        f"Tautan berlaku {hours} jam dan hanya bisa dipakai sekali.\n"
        "Jika Anda tidak merasa diundang, abaikan email ini.\n")
    try:
        port = int(os.getenv("MAIL_PORT", "587"))
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=15, context=_ssl_context())
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            server.starttls(context=_ssl_context())
        with server:
            if os.getenv("MAIL_USERNAME"):
                server.login(os.getenv("MAIL_USERNAME"), os.getenv("MAIL_PASSWORD", ""))
            server.send_message(msg)
        return True, ""
    except Exception as e:  # noqa: BLE001
        return False, f"Gagal mengirim email ({e}). Salin tautan ini dan kirim manual."



def _send_brevo(api_key, to, nama, link, hours):
    """Kirim lewat HTTPS (API Brevo). Cocok untuk hosting yang memblokir SMTP."""
    import json
    import urllib.error
    import urllib.request

    sender = os.getenv("MAIL_FROM") or os.getenv("MAIL_USERNAME", "")
    text = (
        f"Halo {nama},\n\nAdmin mengundang Anda sebagai teknisi di Network Incident Ticketing.\n"
        f"Buka tautan berikut untuk membuat password dan mengaktifkan akun:\n\n{link}\n\n"
        f"Tautan berlaku {hours} jam dan hanya bisa dipakai sekali.\n"
        "Jika Anda tidak merasa diundang, abaikan email ini.\n")
    payload = {
        "sender": {"name": "Network Incident Ticketing", "email": sender},
        "to": [{"email": to, "name": nama}],
        "subject": "Aktifkan akun teknisi Anda",
        "textContent": text,
    }
    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=json.dumps(payload).encode(),
        headers={"api-key": api_key, "content-type": "application/json", "accept": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15, context=_ssl_context()):
            return True, ""
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:200]
        return False, f"Gagal mengirim email (Brevo {e.code}: {detail}). Salin tautan ini dan kirim manual."
    except Exception as e:  # noqa: BLE001
        return False, f"Gagal mengirim email ({e}). Salin tautan ini dan kirim manual."



def _send_apps_script(url, to, nama, link, hours):
    """Kirim lewat Google Apps Script (web app di akun Gmail sendiri) via HTTPS."""
    import json
    import urllib.request

    body = (
        f"Halo {nama},\n\nAdmin mengundang Anda sebagai teknisi di Network Incident Ticketing.\n"
        f"Buka tautan berikut untuk membuat password dan mengaktifkan akun:\n\n{link}\n\n"
        f"Tautan berlaku {hours} jam dan hanya bisa dipakai sekali.\n"
        "Jika Anda tidak merasa diundang, abaikan email ini.\n")
    payload = {"token": os.getenv("APPS_SCRIPT_TOKEN", ""), "to": to,
               "subject": "Aktifkan akun teknisi Anda", "body": body}
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"content-type": "text/plain;charset=utf-8"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20, context=_ssl_context()) as r:
            reply = r.read().decode(errors="replace").strip()
        if reply == "ok":
            return True, ""
        return False, f"Gagal mengirim email (balasan skrip: {reply[:120]}). Salin tautan ini dan kirim manual."
    except Exception as e:  # noqa: BLE001
        return False, f"Gagal mengirim email ({e}). Salin tautan ini dan kirim manual."


def send_ticket_notification(to, nama, subjek, isi_pesan, ticket_info=None):
    """Kirim email notifikasi tiket/eskalasi ke teknisi atau admin. Mengembalikan (terkirim, catatan)."""
    host = os.getenv("MAIL_SERVER")
    api_key = os.getenv("BREVO_API_KEY")
    script_url = os.getenv("APPS_SCRIPT_URL")

    detail = ""
    if ticket_info:
        detail = (
            f"\nDetail Tiket:\n"
            f"- ID Tiket: #{ticket_info.get('id')}\n"
            f"- Judul: {ticket_info.get('judul')}\n"
            f"- Pelanggan: {ticket_info.get('pelanggan')}\n"
            f"- Perangkat: {ticket_info.get('perangkat') or '-'}\n"
            f"- Prioritas: {ticket_info.get('prioritas')}\n"
            f"- Status: {ticket_info.get('status')}\n"
        )

    body_text = (
        f"Halo {nama},\n\n"
        f"{isi_pesan}\n"
        f"{detail}\n"
        f"Silakan buka portal ICRM+ untuk melakukan penanganan lebih lanjut:\n"
        f"https://ticketing-api.wasmer.app/ui\n\n"
        f"--\nPLN Icon Plus - ICRM+ Incident Ticketing"
    )

    if current_app.config.get("TESTING") or not (host or api_key or script_url):
        print(f"[EMAIL NOTIFIKASI] Ke: {to} | Subjek: {subjek} | Pesan: {isi_pesan}")
        return False, "Email belum diatur (MAIL_SERVER kosong)."

    if api_key and not current_app.config.get("TESTING"):
        import json
        import urllib.request
        sender = os.getenv("MAIL_FROM") or os.getenv("MAIL_USERNAME", "")
        payload = {
            "sender": {"name": "ICRM+ PLN Icon Plus", "email": sender},
            "to": [{"email": to, "name": nama}],
            "subject": subjek,
            "textContent": body_text,
        }
        req = urllib.request.Request(
            "https://api.brevo.com/v3/smtp/email",
            data=json.dumps(payload).encode(),
            headers={"api-key": api_key, "content-type": "application/json", "accept": "application/json"},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15, context=_ssl_context()):
                return True, ""
        except Exception as e:
            return False, f"Gagal mengirim email ({e})"

    msg = EmailMessage()
    msg["Subject"] = subjek
    msg["From"] = os.getenv("MAIL_FROM") or os.getenv("MAIL_USERNAME", "")
    msg["To"] = to
    msg.set_content(body_text)

    try:
        port = int(os.getenv("MAIL_PORT", "587"))
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=15, context=_ssl_context())
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            server.starttls(context=_ssl_context())
        with server:
            if os.getenv("MAIL_USERNAME"):
                server.login(os.getenv("MAIL_USERNAME"), os.getenv("MAIL_PASSWORD", ""))
            server.send_message(msg)
        return True, ""
    except Exception as e:
        return False, f"Gagal mengirim email ({e})"

