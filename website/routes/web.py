from flask import render_template, request, session, redirect, Blueprint, jsonify, send_from_directory, Response, current_app
from datetime import datetime
import os

from utils import get_user_devices, MAXIMUM_POWER_MILLIWATTS
from db import get_cursor

web = Blueprint("web", __name__)

@web.route("/")
def homepage():
    if "user_id" in session:
        return redirect("/dashboard")
    return redirect("/login")

@web.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect("/")
    devices = get_user_devices(session["user_id"])
    return render_template("dashboard.html", logged_in=True, devices=devices)

@web.route("/devices", methods=["GET", "POST"])
def devices():
    if "user_id" not in session:
        return redirect("/")

    if request.method == "GET":
        return render_template(
            "devices.html",
            logged_in=True,
            devices=get_user_devices(session["user_id"])
        )

    deviceID = request.form.get("device_id", "").strip()
    nickname = request.form.get("nickname", "").strip()
    maxPower = request.form.get("max_power", "").strip()
    isAJAX = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    
    try:
        maxPowerInt = int(maxPower)
        if not (0 <= maxPowerInt <= MAXIMUM_POWER_MILLIWATTS):
            raise ValueError()
    except (ValueError, TypeError):
        msg = "Max Power must be a positive integer within valid operating constraints."
        if isAJAX:
            return jsonify(success=False, error=msg), 400
        return render_template("devices.html", logged_in=True, devices=get_user_devices(session["user_id"]), error=msg)

    if not deviceID or not nickname or not maxPower:
        msg = "All fields are required."
        if isAJAX:
            return jsonify(success=False, error=msg), 400
        return render_template("devices.html", logged_in=True, devices=get_user_devices(session["user_id"]), error=msg)

    with get_cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM devices WHERE device_id = %s AND user_id = %s",
            (deviceID, session["user_id"])
        )
        
        addedAlready = cursor.fetchone()

        if addedAlready:
            msg = "You already added this device."
            if isAJAX:
                return jsonify(success=False, error=msg), 409
            return render_template(
                "devices.html",
                logged_in=True,
                devices=get_user_devices(session["user_id"]),
                error=msg
            )

        cursor.execute(
            "SELECT 1 FROM devices WHERE device_id = %s AND user_id IS NOT NULL",
            (deviceID,)
        )
        
        ownedByOther = cursor.fetchone()

        if ownedByOther:
            msg = "A user already owns this device."

            if isAJAX:
                return jsonify(success=False, error=msg), 409

            return render_template(
                "devices.html",
                logged_in=True,
                devices=get_user_devices(session["user_id"]),
                error=msg
            )
            
        cursor.execute("""
           SELECT 1 FROM devices WHERE device_id = %s 
        """, (deviceID,))
        
        if not cursor.fetchone():
            msg = "Device ID not found. Ensure your physical hardware monitor is powered on and connected to Wi-Fi first."
            if isAJAX: return jsonify(success=False, error=msg), 404
            return render_template("devices.html", logged_in=True, devices=get_user_devices(session["user_id"]), error=msg)
            
        else:
            cursor.execute("""
                UPDATE devices SET user_id = %s, nickname = %s, max_power = %s
                WHERE device_id = %s
            """, (session["user_id"], nickname, maxPowerInt, deviceID))

    if isAJAX:
        return jsonify(success=True, device={
            "device_id": deviceID,
            "nickname": nickname,
            "max_power": maxPower
        })

    return redirect("/devices")

@web.route("/devices/<device_id>", methods=["DELETE"])
def delete_device(device_id):
    if "user_id" not in session:
        return jsonify(success=False, error="Unauthorized"), 401
 
    with get_cursor() as cursor:
        cursor.execute(
            "UPDATE devices SET user_id = NULL, nickname = 'Unclaimed Device', max_power = 0 "
            "WHERE device_id = %s AND user_id = %s",
            (device_id, session["user_id"])
        )
        deleted = cursor.rowcount
 
    if deleted:
        return jsonify(success=True)
    return jsonify(success=False, error="Device not found"), 404

@web.route("/devices/<device_id>/renew", methods=["POST"])
def renew_device_baseline(device_id):
    if "user_id" not in session:
        return jsonify(success=False), 401

    with get_cursor() as cursor:
        cursor.execute("""
            UPDATE devices
            SET renew_baseline = TRUE
            WHERE device_id = %s AND user_id = %s
        """, (device_id, session["user_id"]))

    return jsonify(success=True)

@web.route('/robots.txt')
def robots_txt():
    return send_from_directory(os.getcwd(), 'robots.txt')

@web.route('/sitemap.xml')
def sitemap():
    urls = [{'loc': 'https://photonvhealth.onrender.com', 'lastmod': datetime.now().date().isoformat()}]
    return Response(render_template('sitemap.xml', urls=urls), mimetype='application/xml')

@web.route("/health")
def health():
    return "OK", 200

@web.route('/sw.js')
def service_worker():
    response = send_from_directory(os.path.join(current_app.root_path, 'static'),'sw.js', mimetype='application/javascript')
    response.headers['Service-Worker-Allowed'] = '/'
    response.headers['Cache-Control'] = 'no-cache'
    return response