from flask import Flask, request
from flask_wtf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta

from utils import limiter

from db import init_db, init_db_pool
from routes.api import api
from routes.web import web
from routes.auth import auth
from routes.push import push_bp
from routes.stats import stats_bp

PORT_NUMBER = int(os.getenv("PORT", 5000))

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

if not app.secret_key:
    raise ValueError("Set SECRET_KEY")

app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True, 
    SESSION_COOKIE_SECURE=True, 
    SESSION_COOKIE_SAMESITE="Lax", 
    SESSION_REFRESH_EACH_REQUEST=True,
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    RATELIMIT_DEFAULT="200 per day; 50 per hour"
)

limiter.init_app(app)

csrf = CSRFProtect(app)

@app.after_request
def add_security_headers(response):
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    if request.path == "/sitemap.xml":
        return response
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net 'sha256-HYVjnA6FBIzEZeRVREyAzD7iqVhwWjQFnQO06rIyMMk='; "
        "img-src 'self' data:; "
        "connect-src 'self' https://cdn.jsdelivr.net; "
        "font-src 'self' https://cdn.jsdelivr.net;"
    )
    return response

app.register_blueprint(api)
app.register_blueprint(web)
app.register_blueprint(auth)
app.register_blueprint(push_bp)
app.register_blueprint(stats_bp)

csrf.exempt(api)
csrf.exempt(push_bp)

@app.context_processor
def inject_year():
    return {"current_year": datetime.now().year}

if __name__ == "__main__":
    init_db_pool()
    init_db()
    port = PORT_NUMBER
    app.run(host="0.0.0.0", port=port)