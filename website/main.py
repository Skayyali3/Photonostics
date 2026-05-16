from flask import Flask
from flask_wtf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
import os
from utils import limiter

from db import init_db, init_db_pool
from routes.api import api
from routes.web import web
from routes.auth import auth
from routes.push import push_bp

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
    PERMANENT_SESSION_LIFETIME=3600, # in seconds
)

limiter.init_app(app)

csrf = CSRFProtect(app)

app.register_blueprint(api)
app.register_blueprint(web)
app.register_blueprint(auth)
app.register_blueprint(push_bp)

csrf.exempt(api)
csrf.exempt(push_bp)

init_db_pool()
init_db()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)