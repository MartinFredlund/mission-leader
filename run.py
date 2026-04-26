import os

from dotenv import load_dotenv

load_dotenv()

from __init__ import create_app

debug = os.environ.get("FLASK_DEBUG", "false").lower() in ("true", "1")
flask_app = create_app(debug=debug)

if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", debug=debug)
