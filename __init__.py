from flask import (
    Flask,
    redirect,
    url_for,
    render_template,
    request,
    session,
    jsonify,
    flash,
)
import os
import uuid
import random
from datetime import datetime, timedelta
import threading
import time

# Role distribution based on player count
ROLE_CONFIG = {
    5: {"resistance": 3, "spies": 2},
    6: {"resistance": 4, "spies": 2},
    7: {"resistance": 4, "spies": 3},
    8: {"resistance": 5, "spies": 3},
    9: {"resistance": 6, "spies": 3},
    10: {"resistance": 6, "spies": 4},
}

# Session expiration time (2 days)
SESSION_EXPIRATION_HOURS = 48

# In-memory session storage with timestamps
session_store = {}
session_lock = threading.Lock()


def cleanup_expired_sessions():
    """Remove sessions older than 2 days."""
    now = datetime.now()
    expiration_time = timedelta(hours=SESSION_EXPIRATION_HOURS)
    expired_sessions = []

    with session_lock:
        for session_id, data in list(session_store.items()):
            created_at = data.get("created_at")
            if created_at and (now - created_at) > expiration_time:
                expired_sessions.append(session_id)

        for session_id in expired_sessions:
            del session_store[session_id]

    if expired_sessions:
        print(f"Cleaned up {len(expired_sessions)} expired session(s)")


def get_valid_session(session_id):
    """Return session data if valid, or None. Caller must hold session_lock."""
    data = session_store.get(session_id)
    if data is None:
        return None
    created_at = data.get("created_at")
    if created_at and (datetime.now() - created_at) > timedelta(
        hours=SESSION_EXPIRATION_HOURS
    ):
        del session_store[session_id]
        return None
    return data


def get_role_info(current_data, user_id):
    """Return role visibility info for a user. Caller must hold session_lock."""
    user_role = None
    user_role_detail = None
    spy_names = []
    known_spies = []
    commander_info = []

    if "roles" not in current_data:
        return user_role, user_role_detail, spy_names, known_spies, commander_info

    user_role = current_data["roles"].get(user_id)
    role_details = current_data.get("role_details", {})
    user_role_detail = role_details.get(user_id)

    if user_role_detail == "commander":
        for uid, role in current_data["roles"].items():
            if role == "spy" and uid != user_id:
                detail = role_details.get(uid)
                if detail != "deep_cover":
                    name = current_data["names"].get(uid)
                    if name:
                        known_spies.append(name)

    elif user_role_detail == "bodyguard":
        for uid in current_data["roles"].keys():
            detail = role_details.get(uid)
            if detail in ("commander", "false_commander"):
                name = current_data["names"].get(uid)
                if name:
                    commander_info.append(name)

    elif user_role == "spy":
        if user_role_detail != "blind_spy":
            for uid, role in current_data["roles"].items():
                if role == "spy" and uid != user_id:
                    detail = role_details.get(uid)
                    if detail != "blind_spy":
                        name = current_data["names"].get(uid)
                        if name:
                            spy_names.append(name)

    return user_role, user_role_detail, spy_names, known_spies, commander_info


def start_cleanup_thread():
    """Start a background thread to periodically clean up expired sessions."""

    def cleanup_loop():
        while True:
            time.sleep(86400)
            cleanup_expired_sessions()

    thread = threading.Thread(target=cleanup_loop, daemon=True)
    thread.start()


def assign_roles(session_id):
    """Randomly assign roles to all users in a session. Caller must hold session_lock."""
    current_data = session_store[session_id]
    player_count = current_data["player_count"]
    users = list(current_data["names"].keys())
    special_roles = current_data.get("special_roles", {})

    config = ROLE_CONFIG[player_count]
    random.shuffle(users)

    role_assignment = {}
    role_details = {}
    user_index = 0

    resistance_count = config["resistance"]

    if special_roles.get("commander"):
        role_assignment[users[user_index]] = "resistance"
        role_details[users[user_index]] = "commander"
        user_index += 1
        resistance_count -= 1

    if special_roles.get("bodyguard"):
        role_assignment[users[user_index]] = "resistance"
        role_details[users[user_index]] = "bodyguard"
        user_index += 1
        resistance_count -= 1

    for _ in range(resistance_count):
        role_assignment[users[user_index]] = "resistance"
        user_index += 1

    spy_count = config["spies"]

    if special_roles.get("assassin"):
        role_assignment[users[user_index]] = "spy"
        role_details[users[user_index]] = "assassin"
        user_index += 1
        spy_count -= 1

    if special_roles.get("false_commander"):
        role_assignment[users[user_index]] = "spy"
        role_details[users[user_index]] = "false_commander"
        user_index += 1
        spy_count -= 1

    if special_roles.get("deep_cover"):
        role_assignment[users[user_index]] = "spy"
        role_details[users[user_index]] = "deep_cover"
        user_index += 1
        spy_count -= 1

    if special_roles.get("blind_spy"):
        role_assignment[users[user_index]] = "spy"
        role_details[users[user_index]] = "blind_spy"
        user_index += 1
        spy_count -= 1

    for _ in range(spy_count):
        role_assignment[users[user_index]] = "spy"
        user_index += 1

    current_data["roles"] = role_assignment
    current_data["role_details"] = role_details
    current_data["round"] = current_data.get("round", 0) + 1


def create_app(debug=False):
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY")

    start_cleanup_thread()

    @app.url_defaults
    def add_script_name(endpoint, values):
        pass

    @app.route("/")
    def home():
        special_roles = session.get("special_roles")
        return render_template("home.html", special_roles=special_roles)

    @app.route("/create_session", methods=["POST"])
    def create_session():
        player_count_str = request.form.get("player_count")

        if not player_count_str:
            flash("Player count is required. Please try again.", "error")
            return redirect(url_for("home"))

        try:
            player_count = int(player_count_str)
        except ValueError:
            flash("Invalid player count. Please try again.", "error")
            return redirect(url_for("home"))

        if player_count < 5 or player_count > 10:
            flash("Player count must be between 5 and 10. Please try again.", "error")
            return redirect(url_for("home"))

        special_roles = {
            "commander": bool(request.form.get("commander")),
            "bodyguard": bool(request.form.get("bodyguard")),
            "assassin": bool(request.form.get("assassin")),
            "false_commander": bool(request.form.get("false_commander")),
            "deep_cover": bool(request.form.get("deep_cover")),
            "blind_spy": bool(request.form.get("blind_spy")),
        }

        session["special_roles"] = special_roles
        if (
            (special_roles["assassin"] and not special_roles["commander"])
            or (special_roles["bodyguard"] and not special_roles["commander"])
            or (special_roles["false_commander"] and not special_roles["bodyguard"])
            or (special_roles["deep_cover"] and not special_roles["commander"])
        ):
            flash(
                "Invalid role selection. Assassin, Bodyguard, and Deep Cover require Commander. False Commander requires Bodyguard.",
                "error",
            )
            return redirect(url_for("home"))

        unique_id = uuid.uuid4().hex

        with session_lock:
            session_store[unique_id] = {
                "created_at": datetime.now(),
                "users": [],
                "player_count": player_count,
                "names": {},
                "special_roles": special_roles,
            }

        return redirect(url_for("view_session", session_id=unique_id))

    @app.route("/s/<session_id>")
    def view_session(session_id):
        if "user_id" not in session:
            session["user_id"] = uuid.uuid4().hex

        user_id = session["user_id"]

        with session_lock:
            current_data = get_valid_session(session_id)
            if current_data is None:
                return "404 - Session not found or expired", 404

            if user_id not in current_data["users"]:
                current_data["users"].append(user_id)

            counter = len(current_data["names"])

            user_role, user_role_detail, spy_names, known_spies, commander_info = (
                get_role_info(current_data, user_id)
            )

            template_data = {
                "session_id": session_id,
                "counter": counter,
                "player_count": current_data.get("player_count", 5),
                "round": current_data.get("round", 0),
                "user_id": user_id,
                "user_role": user_role,
                "user_role_detail": user_role_detail,
                "user_name": current_data["names"].get(user_id),
                "players": [
                    (uid, name) for uid, name in current_data["names"].items()
                ],
                "spy_names": spy_names,
                "known_spies": known_spies,
                "commander_info": commander_info,
                "special_roles": current_data.get("special_roles", {}),
            }

        return render_template("session.html", **template_data)

    @app.route("/s/<session_id>/set_name", methods=["POST"])
    def set_name(session_id):
        if "user_id" not in session:
            return redirect(url_for("view_session", session_id=session_id))

        user_id = session["user_id"]
        name = request.form.get("name", "").strip()

        if name and len(name) <= 50:
            with session_lock:
                current_data = get_valid_session(session_id)
                if current_data is None:
                    return "404 - Session not found or expired", 404

                if user_id not in current_data["names"]:
                    current_data["names"][user_id] = name

                    if len(current_data["names"]) >= current_data["player_count"]:
                        if "roles" not in current_data:
                            assign_roles(session_id)
                else:
                    current_data["names"][user_id] = name

        return redirect(url_for("view_session", session_id=session_id))

    @app.route("/s/<session_id>/kick", methods=["POST"])
    def kick_player(session_id):
        if "user_id" not in session:
            return redirect(url_for("view_session", session_id=session_id))

        user_id = session["user_id"]
        kick_user_id = request.form.get("kick_user_id", "").strip()

        if not kick_user_id or kick_user_id == user_id:
            return redirect(url_for("view_session", session_id=session_id))

        with session_lock:
            current_data = get_valid_session(session_id)
            if current_data is None:
                return "404 - Session not found or expired", 404

            if kick_user_id not in current_data["names"]:
                return redirect(url_for("view_session", session_id=session_id))

            del current_data["names"][kick_user_id]
            if kick_user_id in current_data["users"]:
                current_data["users"].remove(kick_user_id)

            if "roles" in current_data:
                del current_data["roles"]
            if "role_details" in current_data:
                del current_data["role_details"]

        return redirect(url_for("view_session", session_id=session_id))

    @app.route("/s/<session_id>/reset", methods=["POST"])
    def reset_session(session_id):
        if "user_id" not in session:
            return redirect(url_for("view_session", session_id=session_id))

        player_count_str = request.form.get("player_count")

        if not player_count_str:
            flash("Player count is required. Please try resetting again.", "error")
            return redirect(url_for("view_session", session_id=session_id))

        try:
            player_count = int(player_count_str)
        except ValueError:
            flash("Invalid player count. Please try resetting again.", "error")
            return redirect(url_for("view_session", session_id=session_id))

        if player_count < 5 or player_count > 10:
            flash(
                "Player count must be between 5 and 10. Please try resetting again.",
                "error",
            )
            return redirect(url_for("view_session", session_id=session_id))

        special_roles = {
            "commander": bool(request.form.get("commander")),
            "bodyguard": bool(request.form.get("bodyguard")),
            "assassin": bool(request.form.get("assassin")),
            "false_commander": bool(request.form.get("false_commander")),
            "deep_cover": bool(request.form.get("deep_cover")),
            "blind_spy": bool(request.form.get("blind_spy")),
        }

        if (
            (special_roles["assassin"] and not special_roles["commander"])
            or (special_roles["bodyguard"] and not special_roles["commander"])
            or (special_roles["false_commander"] and not special_roles["bodyguard"])
            or (special_roles["deep_cover"] and not special_roles["commander"])
        ):
            flash(
                "Invalid role selection. Assassin, Bodyguard, and Deep Cover require Commander. False Commander requires Bodyguard.",
                "error",
            )
            return redirect(url_for("view_session", session_id=session_id))

        with session_lock:
            current_data = get_valid_session(session_id)
            if current_data is None:
                return "404 - Session not found or expired", 404

            current_data["player_count"] = player_count
            current_data["special_roles"] = special_roles

            if "roles" in current_data:
                del current_data["roles"]
            if "role_details" in current_data:
                del current_data["role_details"]

            if len(current_data["names"]) == player_count:
                assign_roles(session_id)

        return redirect(url_for("view_session", session_id=session_id))

    @app.route("/api/s/<session_id>/status")
    def session_status(session_id):
        if "user_id" not in session:
            return jsonify({"error": "User not authenticated"}), 401

        user_id = session["user_id"]

        with session_lock:
            current_data = get_valid_session(session_id)
            if current_data is None:
                return jsonify({"error": "Session not found or expired"}), 404

            user_role, user_role_detail, spy_names, known_spies, commander_info = (
                get_role_info(current_data, user_id)
            )

            response_data = {
                "counter": len(current_data["names"]),
                "player_count": current_data["player_count"],
                "round": current_data.get("round", 0),
                "players": [
                    {"id": uid, "name": name}
                    for uid, name in current_data["names"].items()
                ],
                "kicked": user_id not in current_data["users"],
                "user_role": user_role,
                "user_role_detail": user_role_detail,
                "roles_assigned": "roles" in current_data,
                "spy_names": spy_names,
                "known_spies": known_spies,
                "commander_info": commander_info,
            }

        return jsonify(response_data)

    if debug:

        @app.route("/debug/fill/<session_id>", methods=["POST"])
        def debug_fill_session(session_id):
            fake_names = [
                "Alice", "Bob", "Charlie", "Diana", "Eve",
                "Frank", "Grace", "Hank", "Ivy", "Jack",
            ]
            with session_lock:
                current_data = get_valid_session(session_id)
                if current_data is None:
                    return "404 - Session not found or expired", 404

                spots_needed = current_data["player_count"] - len(current_data["names"])
                name_index = 0
                for _ in range(spots_needed):
                    fake_id = uuid.uuid4().hex
                    current_data["users"].append(fake_id)
                    current_data["names"][fake_id] = fake_names[name_index]
                    name_index += 1

                if len(current_data["names"]) >= current_data["player_count"]:
                    if "roles" not in current_data:
                        assign_roles(session_id)

            return redirect(url_for("view_session", session_id=session_id))

    return app
