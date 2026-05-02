from flask import Flask
from dotenv import load_dotenv
import os

from db import init_db, init_db_pool
from routes.api import api
from routes.web import web
from routes.auth import auth

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

if not app.secret_key:
    raise ValueError("Set SECRET_KEY")

app.register_blueprint(api)
app.register_blueprint(web)
app.register_blueprint(auth)

init_db_pool()
init_db()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)