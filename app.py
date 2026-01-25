from flask import Flask
from routes import register_routes
import secrets


def create_app():
    app = Flask(__name__)
    app.secret_key = secrets.token_hex(16)
    register_routes(app)
    return app
