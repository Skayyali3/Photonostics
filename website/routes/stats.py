import matplotlib
import base64
import io
from datetime import date, timedelta

matplotlib.use("agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from flask import Blueprint, render_template, request, session, redirect
from db import get_cursor
from utils import get_user_devices

stats_bp = Blueprint("stats", __name__)

TIME_Y_AXES = [
    ("power", "Power (mW)"),
    ("voltage", "Voltage (V)"),
    ("efficiency", "Efficiency (%)"),
    ("health", "Health (%)"),
    ("temp", "Temperature (°C)"),
    ("light", "Light (a.u.)"),
    ("current", "Current (mA)"),
]

SCATTER_AXES = [
    ("power_vs_light", "Power vs Light Intensity", "light", "Light (a.u.)", "power", "Power (mW)"),
    ("efficiency_vs_light", "Efficiency vs Light", "light", "Light (a.u.)", "efficiency", "Efficiency (%)"),
    ("power_vs_temp", "Power vs Temperature", "temp", "Temperature (°C)", "power", "Power (mW)"),
    ("efficiency_vs_temp", "Efficiency vs Temperature", "temp", "Temperature (°C)", "efficiency", "Efficiency (%)"),
    ("health_vs_temp", "Health vs Temperature", "temp", "Temperature (°C)", "health", "Health (%)"),
]

SCATTER_IDS = {s[0]: s for s in SCATTER_AXES}

TIME_RANGES = [
    ("yesterday", "Yesterday"),
    ("3months", "Last 3 Months"),
    ("6months", "Last 6 Months"),
    ("9months", "Last 9 Months"),
    ("1year", "Last Year"),
]

def _apply_theme(fig, ax):
    fig.patch.set_facecolor("#152220")
    ax.set_facecolor("#1E2F2C")
    ax.tick_params(colors="#C8D8D6", labelsize=9)
    ax.xaxis.label.set_color("#8AADA8")
    ax.yaxis.label.set_color("#8AADA8")
    ax.title.set_color("#C8D8D6")
    for spine in ax.spines.values():
        spine.set_edgecolor("#2A4540")
    ax.grid(True, color="#2A4540", linewidth=0.6, linestyle="--", alpha=0.7)

def _fetch_time_series(device_id: str, y_col: str, time_range: str):
    today = date.today()

    if time_range == "yesterday":
        table    = "sensor_data_hourly_agg"
        time_col = "log_time"
        target   = today - timedelta(days=1)
        where    = "DATE(log_time) = %s"
        params   = (device_id, target)
        x_label  = f"Hour ({target.strftime('%d %b %Y')})"
    else:
        table    = "sensor_data_daily_agg"
        time_col = "log_date"
        days     = {"3months": 90, "6months": 180, "9months": 270, "1year": 365}[time_range]
        cutoff   = today - timedelta(days=days)
        where    = f"{time_col} >= %s"
        params   = (device_id, cutoff)
        x_label  = "Date"

    col_map = {
        "power": "power", "voltage": "voltage", "efficiency": "efficiency",
        "health": "health", "temp": "temp", "light": "light",
        "current": "current",
    }
    db_col = col_map.get(y_col, y_col)
    y_label = dict(TIME_Y_AXES).get(y_col, y_col)

    with get_cursor() as cursor:
        cursor.execute(
            f"SELECT {time_col}, {db_col} FROM {table} "
            f"WHERE device_id = %s AND {where} "
            f"ORDER BY {time_col} ASC",
            params,
        )
        rows = cursor.fetchall()

    xs = [r[time_col] for r in rows]
    ys = [r[db_col]   for r in rows]
    return xs, ys, x_label, y_label


def _fetch_scatter(device_id: str, scatter_id: str, time_range: str):
    _, _, x_col, x_label, y_col, y_label = SCATTER_IDS[scatter_id]
    today = date.today()

    if time_range == "yesterday":
        table    = "sensor_data_hourly_agg"
        time_col = "log_time"
        target   = today - timedelta(days=1)
        where    = "DATE(log_time) = %s"
        params   = (device_id, target)
    else:
        table    = "sensor_data_daily_agg"
        time_col = "log_date"
        days     = {"3months": 90, "6months": 180, "9months": 270, "1year": 365}[time_range]
        cutoff   = today - timedelta(days=days)
        where    = f"{time_col} >= %s"
        params   = (device_id, cutoff)

    with get_cursor() as cursor:
        cursor.execute(
            f"SELECT {x_col}, {y_col} FROM {table} "
            f"WHERE device_id = %s AND {where} "
            f"AND {x_col} IS NOT NULL AND {y_col} IS NOT NULL",
            params,
        )
        rows = cursor.fetchall()

    xs = [r[x_col] for r in rows]
    ys = [r[y_col] for r in rows]
    return xs, ys, x_label, y_label

def _chart_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=130, facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


def _render_time_chart(xs, ys, x_label, y_label, title, time_range) -> str:
    fig, ax = plt.subplots(figsize=(9, 4))
    _apply_theme(fig, ax)

    if not xs:
        ax.text(0.5, 0.5, "No data available for this period",
                ha="center", va="center", color="#8AADA8", transform=ax.transAxes)
    else:
        ax.plot(xs, ys, color="#FFD340", linewidth=1.8, marker="o",
                markersize=3, markerfacecolor="#FFD340")
        ax.fill_between(xs, ys, alpha=0.12, color="#FFD340")

        if time_range == "yesterday":
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=2))
        elif time_range == "3months":
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
            ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
        else:
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
            ax.xaxis.set_major_locator(mdates.MonthLocator())

        fig.autofmt_xdate(rotation=35, ha="right")

    ax.set_xlabel(x_label, fontsize=9)
    ax.set_ylabel(y_label, fontsize=9)
    ax.set_title(title, fontsize=11, pad=10)
    fig.tight_layout()
    return _chart_to_b64(fig)

def _render_scatter_chart(xs, ys, x_label, y_label, title) -> str:
    fig, ax = plt.subplots(figsize=(9, 4))
    _apply_theme(fig, ax)

    if not xs:
        ax.text(0.5, 0.5, "No data available for this period",
                ha="center", va="center", color="#8AADA8", transform=ax.transAxes)
    else:
        ax.scatter(xs, ys, color="#FFD340", alpha=0.65, s=22, edgecolors="none")

    ax.set_xlabel(x_label, fontsize=9)
    ax.set_ylabel(y_label, fontsize=9)
    ax.set_title(title, fontsize=11, pad=10)
    fig.tight_layout()
    return _chart_to_b64(fig)

VALID_TIME_RANGES  = {t[0] for t in TIME_RANGES}
VALID_Y_AXES       = {a[0] for a in TIME_Y_AXES}
VALID_SCATTER_IDS  = set(SCATTER_IDS)

@stats_bp.route("/stats")
def stats():
    if "user_id" not in session:
        return redirect("/")

    devices = get_user_devices(session["user_id"])

    device_id = request.args.get("device_id", "").strip().upper()
    if not devices:
        return render_template("stats.html", logged_in=True, devices=[], chart_b64=None, time_ranges=TIME_RANGES, time_y_axes=TIME_Y_AXES, scatter_axes=SCATTER_AXES, selected={})

    valid_ids = {d["device_id"] for d in devices}
    if device_id not in valid_ids:
        device_id = devices[0]["device_id"]

    time_range  = request.args.get("time_range",  "yesterday")
    plot_type   = request.args.get("plot_type",   "time")
    y_axis      = request.args.get("y_axis",      "power")
    scatter_id  = request.args.get("scatter_id",  "power_vs_light")

    if time_range  not in VALID_TIME_RANGES: time_range  = "yesterday"
    if y_axis      not in VALID_Y_AXES:      y_axis      = "power"
    if scatter_id  not in VALID_SCATTER_IDS: scatter_id  = "power_vs_light"
    if plot_type   not in ("time", "scatter"): plot_type  = "time"

    nickname = next((d["nickname"] for d in devices if d["device_id"] == device_id), device_id)

    if plot_type == "scatter":
        meta  = SCATTER_IDS[scatter_id]
        title = f"{meta[1]} — {nickname}"
        xs, ys, x_label, y_label = _fetch_scatter(device_id, scatter_id, time_range)
        chart_b64 = _render_scatter_chart(xs, ys, x_label, y_label, title)
    else:
        xs, ys, x_label, y_label = _fetch_time_series(device_id, y_axis, time_range)
        range_label = dict(TIME_RANGES)[time_range]
        title = f"{y_label} over time — {nickname} ({range_label})"
        chart_b64 = _render_time_chart(xs, ys, x_label, y_label, title, time_range)

    selected = dict(
        device_id=device_id,
        time_range=time_range,
        plot_type=plot_type,
        y_axis=y_axis,
        scatter_id=scatter_id,
    )

    return render_template("stats.html", logged_in=True,
        devices=devices,
        chart_b64=chart_b64,
        time_ranges=TIME_RANGES,
        time_y_axes=TIME_Y_AXES,
        scatter_axes=SCATTER_AXES,
        selected=selected,
    )