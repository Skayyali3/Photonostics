import os
import re
import logging
import json
import urllib.request
import urllib.error
from dotenv import load_dotenv
from flask import request, has_request_context, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from db import get_cursor

logger = logging.getLogger(__name__)

MAXIMUM_VOLTAGE = 1000
MAXIMUM_POWER_WATTS =  500
MAXIMUM_POWER_MILLIWATTS = MAXIMUM_POWER_WATTS * 1000
MAXIMUM_CURRENT_AMPS = 30  
MAXIMUM_CURRENT_MILLIAMPS = MAXIMUM_CURRENT_AMPS * 1000
MAXIMUM_PERCENTAGE = 100
MAXIMUM_TEMPERATURE = 125
MINIMUM_TEMPERATURE = -45
MAXIMUM_LIGHT_AU = 100000

def limiter_key():
    if request.is_json and has_request_context():
        data = request.get_json(silent=True) or {}
        if data.get("device_id"):
            return f"device:{data.get('device_id')}"

    if has_request_context():
        if session.get("user_id"):
            return f"user:{session["user_id"]}"
        
        email = request.form.get("email") or request.form.get("username")
        if email:
            return f"email:{email.strip().lower()}"

    return get_remote_address()

limiter = Limiter(
    key_func=limiter_key, 
    default_limits=["200 per day", "50 per hour"],
    storage_uri=os.getenv("RATELIMIT_STORAGE_URI", "memory://"),
    strategy="moving-window"
)

load_dotenv()

BREVO_API_KEY = os.getenv("BREVO_API_KEY")
MAIL_FROM_EMAIL = os.getenv("MAIL_FROM_EMAIL", "photonvhealth@gmail.com")
MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME", "PhotonVHealth")

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
    if not BREVO_API_KEY:
        raise RuntimeError("BREVO_API_KEY is not set")

    body = f"""Hi,

You requested a password reset for your PhotonVHealth account.

Click the link below to reset your password (valid for 1 hour):
{resetLink}

If you didn't request this, you can safely ignore this email.

— PhotonVHealth
"""
    payload = json.dumps({
        "sender": {"name": MAIL_FROM_NAME, "email": MAIL_FROM_EMAIL},
        "to": [{"email": receiverAddress}],
        "subject": "PhotonVHealth — Password Reset",
        "textContent": body,
    }).encode()

    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=payload,
        headers={
            "api-key": BREVO_API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status not in (200, 201):
                raise RuntimeError(f"Brevo returned HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        error_body = e.read().decode(errors="replace")
        raise RuntimeError(f"Brevo error {e.code}: {error_body}") from e