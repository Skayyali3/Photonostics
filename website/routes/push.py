from flask import Blueprint, request, jsonify, session
from pywebpush import webpush, WebPushException
from concurrent.futures import ThreadPoolExecutor
import os
import json
import logging

from db import get_cursor

logger = logging.getLogger(__name__)

push_bp = Blueprint("push", __name__)

VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY")
VAPID_PUBLIC_KEY  = os.getenv("VAPID_PUBLIC_KEY")
VAPID_CLAIMS = {"sub": os.getenv("VAPID_MAILTO", "youremail@gmail.com")}

def _send_push(subscription_info: dict, payload: dict) -> bool:
    try:
        webpush(
            subscription_info=subscription_info,
            data=json.dumps(payload),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims=VAPID_CLAIMS,
        )
        return True
    except WebPushException as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status in (404, 410):
            endpoint = subscription_info.get("endpoint")
            if endpoint:
                try:
                    with get_cursor() as cursor:
                        cursor.execute(
                            "DELETE FROM push_subscriptions WHERE endpoint = %s",
                            (endpoint,),
                        )
                except Exception:
                    pass
        logger.warning("WebPush failed (status=%s): %s", status, exc)
        return False
    except Exception as exc:
        logger.error("Unexpected push error: %s", exc)
        return False

def _get_device_subscriptions(device_id: str) -> list[dict]:
    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT ps.endpoint, ps.p256dh, ps.auth
            FROM push_subscriptions ps
            JOIN devices d ON d.user_id = ps.user_id
            WHERE d.device_id = %s
            """,
            (device_id,),
        )
        rows = cursor.fetchall()

    return [
        {
            "endpoint": r["endpoint"],
            "keys": {"p256dh": r["p256dh"], "auth": r["auth"]},
        }
        for r in rows
    ]

def _log_notification(device_id: str, alert_type: str, message: str) -> None:
    with get_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO push_notifications_log (device_id, alert_type, message)
            VALUES (%s, %s, %s)
            """,
            (device_id, alert_type, message),
        )

def _recently_alerted(device_id: str, alert_type: str, cooldown_seconds: int = 60) -> bool:
    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT 1 FROM push_notifications_log
            WHERE device_id   = %s
              AND alert_type  = %s
              AND sent_at > NOW() - (%s * INTERVAL '1 second')
            LIMIT 1
            """,
            (device_id, alert_type, cooldown_seconds),
        )
        return cursor.fetchone() is not None

ALERT_COOLDOWN = 60

def check_and_send_alerts(device_id: str, data: dict, prev: dict | None, baseline_power: float, baseline_light: float) -> None:
    if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
        return

    light = float(data.get("light") or 0)
    power = float(data.get("power") or 0)
    temp = float(data.get("temp") or 0)
    efficiency = float(data.get("efficiency") or 0)

    if prev is None:
        return

    prevLight = float(prev.get("light") or 0)
    prevPower = float(prev.get("power") or 0)

    if light < 150:
        return
    if power < 5:
        return

    lightChange = prevLight - light
    powerChange = prevPower - power

    subscriptions = _get_device_subscriptions(device_id)
    if not subscriptions:
        return

    def dispatch(alert_type: str, title: str, body: str) -> None:
        if _recently_alerted(device_id, alert_type, ALERT_COOLDOWN):
            return
        payload = {
            "title": title,
            "body": body,
            "tag": alert_type,
            "device_id": device_id,
        }

        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(lambda sub: _send_push(sub, payload), subscriptions))

        sent = sum(1 for success in results if success)
        
        if sent:
            _log_notification(device_id, alert_type, body)

    if temp >= 35 and efficiency < 90:
        dispatch(
            "overheat",
            "Panel Overheat Detected",
            f"{device_id}: Temperature is {temp:.1f} °C with efficiency at {efficiency:.1f} %.",
        )

    if baseline_light > 0 and light > baseline_light * 0.8 and efficiency < 75:
        dispatch(
            "dust",
            "Panel Soiling Detected - Please Clean your Panel",
            f"{device_id}: Possible dust or soiling – efficiency dropped to {efficiency:.1f} %.",
        )

    if lightChange > 200 and prevPower > 0 and powerChange > prevPower * 0.2:
        dispatch(
            "shading",
            "Sudden Shading Detected",
            f"{device_id}: Light dropped by {lightChange:.0f} a.u. and power by {powerChange:.1f} mW.",
        )

@push_bp.get("/api/push/vapid-public-key")
def vapid_public_key():
    if not VAPID_PUBLIC_KEY:
        return jsonify({"success": False, "error": "Push not configured"}), 503
    return jsonify({"success": True, "key": VAPID_PUBLIC_KEY})

@push_bp.post("/api/push/subscribe")
def subscribe():
    if "user_id" not in session:
        return jsonify({"success": False, "error": "Unauthorised"}), 401

    body = request.get_json(silent=True) or {}
    endpoint = body.get("endpoint")
    p256dh = (body.get("keys") or {}).get("p256dh")
    auth = (body.get("keys") or {}).get("auth")

    if not all([endpoint, p256dh, auth]):
        return jsonify({"success": False, "error": "Invalid subscription object"}), 400

    with get_cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (endpoint) DO UPDATE
                SET user_id  = EXCLUDED.user_id,
                    p256dh   = EXCLUDED.p256dh,
                    auth     = EXCLUDED.auth,
                    updated_at = NOW()
            """,
            (session["user_id"], endpoint, p256dh, auth),
        )

    return jsonify({"success": True})

@push_bp.delete("/api/push/subscribe")
def unsubscribe():
    if "user_id" not in session:
        return jsonify({"success": False, "error": "Unauthorised"}), 401

    body = request.get_json(silent=True) or {}
    endpoint = body.get("endpoint")

    if not endpoint:
        return jsonify({"success": False, "error": "Missing endpoint"}), 400

    with get_cursor() as cursor:
        cursor.execute(
            "DELETE FROM push_subscriptions WHERE endpoint = %s AND user_id = %s",
            (endpoint, session["user_id"]),
        )

    return jsonify({"success": True})

@push_bp.get("/api/push/status")
def push_status():
    if "user_id" not in session:
        return jsonify({"success": False, "error": "Unauthorised"}), 401

    endpoint = request.args.get("endpoint")
    if not endpoint:
        return jsonify({"success": False, "error": "Missing endpoint"}), 400

    with get_cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM push_subscriptions WHERE endpoint = %s AND user_id = %s",
            (endpoint, session["user_id"]),
        )
        exists = cursor.fetchone() is not None

    return jsonify({"success": True, "subscribed": exists})