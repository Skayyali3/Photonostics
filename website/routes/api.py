import threading
from flask import Blueprint, jsonify, request, session
from secrets import token_hex
from hashlib import sha256

from db import get_cursor
from utils import validate_device_id, limiter, MAXIMUM_VOLTAGE, MINIMUM_TEMPERATURE, MAXIMUM_TEMPERATURE, MAXIMUM_POWER_MILLIWATTS, MAXIMUM_CURRENT_MILLIAMPS, MAXIMUM_PERCENTAGE, MAXIMUM_LIGHT_AU
from routes.push import check_and_send_alerts

api = Blueprint("api", __name__, url_prefix="/api")

def _post_data_alert_hook(device_id: str, current_data: dict) -> None:
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT power, light
            FROM sensor_data
            WHERE device_id = %s
            ORDER BY recorded_at DESC
            OFFSET 1 LIMIT 1
            """,(device_id,))
        prevRow = cursor.fetchone()
 
    prev = dict(prevRow) if prevRow else None
    try:
        check_and_send_alerts(device_id, current_data, prev)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("Alert check failed: %s", exc)

@api.route("/register_device", methods=["POST"])
@limiter.limit("10 per minute")
def register_device():
    data = request.get_json(silent=True)
    api_key = token_hex(32)
    hashed_api_key = sha256(api_key.encode()).hexdigest()

    if not data:
        return jsonify(success=False, error="Expected JSON"), 400

    device_id = (data.get("device_id") or "").strip().upper()

    if not device_id:
        return jsonify(success=False, error="device_id required"), 400
    
    if not validate_device_id(device_id):
        return jsonify(success=False, error="Invalid device ID"), 400

    with get_cursor() as cursor:
        cursor.execute(
            "SELECT api_key FROM devices WHERE device_id = %s",
            (device_id,)
        )
        
        existing = cursor.fetchone()
        
        if existing:
            return jsonify(success=False, error="Device ID already registered."), 409

        cursor.execute("""
            INSERT INTO devices (user_id, device_id, api_key, nickname, max_power)
            VALUES (NULL, %s, %s, %s, %s)
        """, (device_id, hashed_api_key, "Unclaimed Device", 0))

    return jsonify(success=True, message="Device registered", apiKey=api_key)

@api.route("/data", methods=["POST"])
@limiter.limit("60 per minute")
def api_data():
    data = request.get_json(silent=True)
    if not data:
        return jsonify(success=False, error="Expected JSON"), 400
 
    device_id = (data.get("device_id") or "").strip().upper()
    api_key = (data.get("api_key") or "").strip()
    hashed_api_key = sha256(api_key.encode()).hexdigest()
    
    if not device_id:
        return jsonify(success=False, error="device_id required"), 400
    
    if not validate_device_id(device_id):
        return jsonify(success=False, error="Invalid device ID"), 400
 
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT max_power, baseline_power, baseline_light
            FROM devices WHERE device_id = %s and api_key = %s
        """, (device_id, hashed_api_key))
        row = cursor.fetchone()
    
        if not row:
            return jsonify(success=False, error="Unknown device"), 404
    
        maxPower = row['max_power']
        baselinePower = row['baseline_power']
        baselineLight = row['baseline_light']
    
        try:
            power = min(max(float(data.get("power", 0)), 0.0), MAXIMUM_POWER_MILLIWATTS)
            voltage = min(max(float(data.get("voltage", 0)), 0.0), MAXIMUM_VOLTAGE)
            light = min(max(float(data.get("light", 0)), 0.0), MAXIMUM_LIGHT_AU)
            lightIntensity = min(max(float(data.get("percentage", 0)), 0.0), MAXIMUM_PERCENTAGE)
            temp = min(max(float(data.get("temp", 0)), MINIMUM_TEMPERATURE), MAXIMUM_TEMPERATURE)
            efficiency = min(max(float(data.get("efficiency", 0)), 0.0), MAXIMUM_PERCENTAGE)
            current = min(max(float(data.get("current", 0)), 0.0), MAXIMUM_CURRENT_MILLIAMPS)
            
        except (ValueError, TypeError):
            return jsonify(success=False, error="Invalid parameters"), 400
            
        health = 0.0
        if maxPower and maxPower > 0 and baselinePower and baselinePower > 0:
            health = min((baselinePower / maxPower) * 100.0, 100.0)

        if power > (baselinePower or 1) * 1.1 and light > 2400 and temp < 35:
            cursor.execute("""
                UPDATE devices SET baseline_power = %s, baseline_light = %s
                WHERE device_id = %s
            """, (power, light, device_id))
    
        cursor.execute("""
            INSERT INTO sensor_data (device_id, power, voltage, current, light, light_percentage, temp, efficiency, health)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (device_id, power, voltage, current, light, lightIntensity, temp, efficiency, health))
        
        threading.Thread(target=_post_data_alert_hook, args=(device_id, {
            "power": power, "current":current,
            "light": light, "temp": temp, 
            "efficiency": efficiency, "baseline_power": baselinePower, "baseline_light": baselineLight
        },)).start()
 
    return jsonify(success=True, health=round(health, 1))
 
@api.route("/latest/<device_id>")
@limiter.exempt
def api_latest(device_id):
    if "user_id" not in session:
        return jsonify(success=False, error="Unauthorized"), 401
 
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT nickname FROM devices WHERE device_id = %s AND user_id = %s",
            (device_id, session["user_id"])
        )
        device = cursor.fetchone()
        if not device:
            return jsonify(success=False, error="Not found"), 404
    
        cursor.execute("""
            SELECT power, voltage, light_percentage, temp, efficiency, health, recorded_at
            FROM sensor_data WHERE device_id = %s
            ORDER BY recorded_at DESC LIMIT 1
        """, (device_id,))
        row = cursor.fetchone()
    
    if not row:
        return jsonify(success=True, data=None)
 
    return jsonify(success=True, data={
        "power":      row['power'],
        "voltage":    row["voltage"],
        "light":      row['light_percentage'],
        "temp":       row['temp'],
        "efficiency": row['efficiency'],
        "health":     row['health'],
        "recorded_at": row['recorded_at'].isoformat() if row['recorded_at'] else None,
    })
 
@api.route("/commands/<device_id>")
def api_commands(device_id):
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT baseline_power, baseline_light, renew_baseline
            FROM devices
            WHERE device_id = %s
        """, (device_id,))

        row = cursor.fetchone()

        if not row:
            return jsonify(success=False), 404

        renew = bool(row['renew_baseline'])

        if renew:
            cursor.execute("""
                UPDATE devices SET renew_baseline = FALSE
                WHERE device_id = %s
            """, (device_id,))

    return jsonify(
        success=True,
        renew_baseline=renew,
        baseline_power=row['baseline_power'] or 0,
        baseline_light=row['baseline_light'] or 0
    )