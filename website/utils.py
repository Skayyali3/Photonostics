import re
from db import get_cursor
from email.mime.text import MIMEText
from dotenv import load_dotenv
import os
import smtplib
from flask import request, has_request_context
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

def limiter_key():
    if request.is_json and has_request_context:
        data = request.get_json(silent=True) or {}
        return data.get("device_id") or get_remote_address()
    return get_remote_address()

limiter = Limiter(key_func=limiter_key, default_limits=["200 per day", "50 per hour"])

load_dotenv()

MAIL_HOST = os.getenv("MAIL_HOST", "smtp.gmail.com")
MAIL_PORT = int(os.getenv("MAIL_PORT", 587))
MAIL_USERNAME = os.getenv("MAIL_USERNAME")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
MAIL_FROM = os.getenv("MAIL_FROM", MAIL_USERNAME)

def validate_device_id(device_id):
    return bool(re.fullmatch(r"PVH_[A-F0-9]{12}", device_id))
    
def get_user_devices(user_id):
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT device_id, nickname, max_power, baseline_power, baseline_light
            FROM devices WHERE user_id = %s
        """, (user_id,))
        rows = cursor.fetchall()
    
    return [{"device_id": r['device_id'], "nickname": r['nickname'], "max_power": r['max_power'], "baseline_power": r['baseline_power'], "baseline_light": r['baseline_light']} for r in rows]

def send_reset_email(receiverAddress, resetLink):
    body = f"""Hi,

You requested a password reset for your PhotonVHealth account.

Click the link below to reset your password (valid for 1 hour):
{resetLink}

If you didn't request this, you can safely ignore this email.

— PhotonVHealth
"""
    msg = MIMEText(body)
    msg["Subject"] = "PhotonVHealth — Password Reset"
    msg["From"] = MAIL_FROM
    msg["To"] = receiverAddress

    with smtplib.SMTP(MAIL_HOST, MAIL_PORT) as server:
        server.starttls()
        server.login(MAIL_USERNAME, MAIL_PASSWORD)
        server.sendmail(MAIL_FROM, [receiverAddress], msg.as_string())