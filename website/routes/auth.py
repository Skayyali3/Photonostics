from flask import render_template, request, session, redirect, Blueprint
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, UTC
import secrets
import os
import psycopg2
import hashlib

from utils import send_reset_email, limiter
from db import get_cursor

APP_BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:5000/")

auth = Blueprint("auth", __name__)

@auth.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login():
    if request.method == "GET":
        return render_template("login.html", logged_in=False)
 
    account = request.form.get("username", "").strip()
    password = request.form.get("password").strip()
    
    if not account or not password:
        return render_template("login.html", logged_in=False, error="Username/email and password required")
 
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT id, username, password_hashed FROM users WHERE username = %s OR email = %s",
            (account.lower(), account.lower())
        )
    
        user = cursor.fetchone()
 
    if user and check_password_hash(user['password_hashed'], password):
        session["user_id"] = user['id']
        session["username"] = user['username']
        return redirect("/dashboard")
 
    return render_template("login.html", logged_in=False, error="Invalid username/email or password")
 
@auth.route("/signup", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def signup():
    if request.method == "GET":
        return render_template("signup.html", logged_in=False)
 
    username = request.form.get("username").lower()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password").strip()
    
    if not username or not password or not email:
        return render_template("signup.html", logged_in=False, error="Username, email and password required")
    
    if len(password) < 8:
        return render_template("signup.html", logged_in=False, error="Password needs to be 8 or more characters long.")
 
    hashed = generate_password_hash(password)
 
    with get_cursor() as cursor:
        try:
            cursor.execute(
                "INSERT INTO users (username, password_hashed, email) VALUES (%s, %s, %s)",
                (username, hashed, email)
            )
        except psycopg2.IntegrityError:
            return render_template("signup.html", logged_in=False, error="Username or email already exists")

    return redirect("/login")

@auth.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("5 per hour")
def forgot_password():
    if request.method == "GET":
        return render_template("forgot_password.html", logged_in=False)
 
    email = request.form.get("email", "").strip().lower()
    if not email:
        return render_template("forgot_password.html", logged_in=False, error="Email is required.")
 
    with get_cursor() as cursor:
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
 
        if user:
            token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            expires_at = datetime.now(UTC) + timedelta(hours=1)
            cursor.execute(
                "INSERT INTO password_reset_tokens (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
                (token_hash, user['id'], expires_at)
            )
            resetLink = f"{APP_BASE_URL}/reset-password/{token}"
            try:
                send_reset_email(email, resetLink)
            except Exception as e:
                auth.logger.error(f"Failed to send reset email: {e}")

    return render_template("forgot_password.html", logged_in=False, success=True)
 
@auth.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT user_id FROM password_reset_tokens
            WHERE token_hash = %s AND used = FALSE AND expires_at > %s
        """, (token_hash, datetime.now(UTC)))
        row = cursor.fetchone()
 
        if not row:
            return render_template("reset_password.html", logged_in=False, invalid=True, token=token)
 
        if request.method == "GET":
            return render_template("reset_password.html", logged_in=False, invalid=False, token=token)
 
        password = request.form.get("password", "").strip()
        confirm = request.form.get("confirm_password", "")
 
        if not password or len(password) < 8:
            return render_template("reset_password.html", logged_in=False, invalid=False, token=token, error="Password must be at least 8 characters.")
 
        if password != confirm:
            return render_template("reset_password.html", logged_in=False, invalid=False, token=token, error="Passwords do not match.")
 
        hashed = generate_password_hash(password)
        cursor.execute("UPDATE users SET password_hashed = %s WHERE id = %s", (hashed, row['user_id']))
        cursor.execute("UPDATE password_reset_tokens SET used = TRUE WHERE token = %s", (token_hash,))
        
    session.clear()
    return redirect("/login?reset=1")

@auth.route("/logout")
def logout():
    session.clear()
    return redirect("/")