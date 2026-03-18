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
# Structure: { 'session_id': { 'created_at': datetime, 'counter': ..., 'users': [], ... } }
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


def session_exists_and_valid(session_id):
    """Check if a session exists and is not expired."""
    with session_lock:
        if session_id not in session_store:
            return False

        data = session_store[session_id]
        created_at = data.get("created_at")
        if created_at:
            age = datetime.now() - created_at
            if age > timedelta(hours=SESSION_EXPIRATION_HOURS):
                del session_store[session_id]
                return False

        return True


def start_cleanup_thread():
    """Start a background thread to periodically clean up expired sessions."""

    def cleanup_loop():
        while True:
            time.sleep(86400)  # Run once per day
            cleanup_expired_sessions()

    thread = threading.Thread(target=cleanup_loop, daemon=True)
    thread.start()


def assign_roles(session_id):
    """Randomly assign roles to all users in a session."""
    current_data = session_store[session_id]
    player_count = current_data["player_count"]
    # Only assign roles to players who have entered a name
    users = list(current_data["names"].keys())
    special_roles = current_data.get("special_roles", {})

    # Get role distribution for this player count
    config = ROLE_CONFIG[player_count]

    # Shuffle users for random assignment
    random.shuffle(users)

    # Track which users get which role
    role_assignment = {}
    role_details = {}  # Stores special role name
    user_index = 0

    # Assign Resistance roles
    resistance_count = config["resistance"]

    # Assign Commander if selected
    if special_roles.get("commander"):
        role_assignment[users[user_index]] = "resistance"
        role_details[users[user_index]] = "commander"
        user_index += 1
        resistance_count -= 1

    # Assign Bodyguard if selected
    if special_roles.get("bodyguard"):
        role_assignment[users[user_index]] = "resistance"
        role_details[users[user_index]] = "bodyguard"
        user_index += 1
        resistance_count -= 1

    # Assign remaining regular resistance
    for _ in range(resistance_count):
        role_assignment[users[user_index]] = "resistance"
        user_index += 1

    # Assign Spy roles
    spy_count = config["spies"]

    # Assign Assassin if selected
    if special_roles.get("assassin"):
        role_assignment[users[user_index]] = "spy"
        role_details[users[user_index]] = "assassin"
        user_index += 1
        spy_count -= 1

    # Assign False Commander if selected
    if special_roles.get("false_commander"):
        role_assignment[users[user_index]] = "spy"
        role_details[users[user_index]] = "false_commander"
        user_index += 1
        spy_count -= 1

    # Assign Deep Cover if selected
    if special_roles.get("deep_cover"):
        role_assignment[users[user_index]] = "spy"
        role_details[users[user_index]] = "deep_cover"
        user_index += 1
        spy_count -= 1

    # Assign Blind Spy if selected
    if special_roles.get("blind_spy"):
        role_assignment[users[user_index]] = "spy"
        role_details[users[user_index]] = "blind_spy"
        user_index += 1
        spy_count -= 1

    # Assign remaining regular spies
    for _ in range(spy_count):
        role_assignment[users[user_index]] = "spy"
        user_index += 1

    # Store in session data
    session_store[session_id]["roles"] = role_assignment
    session_store[session_id]["role_details"] = role_details


def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get("SECRET_KEY")

    # Start background cleanup thread
    start_cleanup_thread()

    # Support for being mounted at a sub-path
    @app.url_defaults
    def add_script_name(endpoint, values):
        """Add SCRIPT_NAME to all generated URLs"""
        pass  # Flask will automatically use SCRIPT_NAME from environ

    @app.route("/")
    def home():
        special_roles = session.get("special_roles")
        """The landing page with a button to start a new session."""
        return render_template("home.html", special_roles=special_roles)

    @app.route("/create_session", methods=["POST"])
    def create_session():
        """Generates a unique ID and redirects to the specific session URL."""
        # 1. Get player count from form
        player_count_str = request.form.get("player_count")

        if not player_count_str:
            flash("Player count is required. Please try again.", "error")
            return redirect(url_for("home"))

        player_count = int(player_count_str)

        # Validate player count is between 5-10
        if player_count < 5 or player_count > 10:
            flash("Player count must be between 5 and 10. Please try again.", "error")
            return redirect(url_for("home"))

        # 2. Get special roles selection
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

        # 3. Generate a unique identifier
        unique_id = uuid.uuid4().hex

        # 4. Initialize the state for this session in our mock DB
        with session_lock:
            session_store[unique_id] = {
                "created_at": datetime.now(),
                "counter": 0,
                "users": [],
                "player_count": player_count,
                "names": {},  # Maps user_id to name
                "special_roles": special_roles,
            }

        # 5. Redirect the user to the dynamic route
        return redirect(url_for("view_session", session_id=unique_id))

    @app.route("/s/<session_id>")
    def view_session(session_id):
        """
        The Dynamic Route.
        Flask captures whatever follows '/s/' and passes it as 'session_id'.
        """
        # 4. Check if this session actually exists and is not expired
        if not session_exists_and_valid(session_id):
            return "404 - Session not found or expired", 404

        # Get or create a unique user ID for this visitor
        if "user_id" not in session:
            session["user_id"] = uuid.uuid4().hex

        user_id = session["user_id"]

        with session_lock:
            current_data = session_store.get(session_id)
            if current_data is None:
                return "404 - Session not found or expired", 404

            # Track that this user has visited (for users list)
            if user_id not in current_data["users"]:
                current_data["users"].append(user_id)

            # Counter now represents players with names
            current_data["counter"] = len(current_data["names"])

            # Get the user's role if roles have been assigned
            user_role = None
            user_role_detail = None
            spy_names = []
            commander_info = []
            known_spies = []

            if "roles" in current_data:
                user_role = current_data["roles"].get(user_id)
                role_details = current_data.get("role_details", {})
                user_role_detail = role_details.get(user_id)

                # Handle special role information
                if user_role_detail == "commander":
                    # Commander knows all spies except Deep Cover
                    for uid, role in current_data["roles"].items():
                        if role == "spy" and uid != user_id:
                            detail = role_details.get(uid)
                            if detail != "deep_cover":  # Deep Cover is hidden
                                spy_name = current_data["names"].get(uid)
                                if spy_name:
                                    known_spies.append(spy_name)

                elif user_role_detail == "bodyguard":
                    # Bodyguard sees Commander and False Commander
                    for uid in current_data["roles"].keys():
                        detail = role_details.get(uid)
                        if detail == "commander" or detail == "false_commander":
                            commander_name = current_data["names"].get(uid)
                            if commander_name:
                                commander_info.append(commander_name)

                elif user_role == "spy":
                    # Regular spy logic - depends on role detail
                    if user_role_detail == "blind_spy":
                        # Blind Spy sees no one
                        spy_names = []
                    else:
                        # Normal spies and special spies see other spies (except Blind Spy)
                        for uid, role in current_data["roles"].items():
                            if role == "spy" and uid != user_id:
                                detail = role_details.get(uid)
                                if detail != "blind_spy":  # Blind Spy is not visible
                                    spy_name = current_data["names"].get(uid)
                                    if spy_name:
                                        spy_names.append(spy_name)

            template_data = {
                "session_id": session_id,
                "counter": current_data["counter"],
                "player_count": current_data.get("player_count", 5),
                "user_id": user_id,
                "user_role": user_role,
                "user_role_detail": user_role_detail,
                "user_name": current_data["names"].get(user_id),
                "player_names": list(current_data["names"].values()),
                "spy_names": spy_names,
                "known_spies": known_spies,
                "commander_info": commander_info,
                "special_roles": current_data.get("special_roles", {}),
            }

        return render_template("session.html", **template_data)

    @app.route("/s/<session_id>/set_name", methods=["POST"])
    def set_name(session_id):
        """Allow a user to set their name for the session."""
        if not session_exists_and_valid(session_id):
            return "404 - Session not found or expired", 404

        if "user_id" not in session:
            return redirect(url_for("view_session", session_id=session_id))

        user_id = session["user_id"]
        name = request.form.get("name", "").strip()

        if name and len(name) <= 50:  # Validate name
            with session_lock:
                current_data = session_store.get(session_id)
                if current_data is None:
                    return "404 - Session not found or expired", 404

                # Add name only if not already set (prevent race condition overwrites)
                if user_id not in current_data["names"]:
                    current_data["names"][user_id] = name
                    # Update counter to reflect named players
                    current_data["counter"] = len(current_data["names"])

                    # Check if we now have enough players to assign roles
                    if current_data["counter"] >= current_data["player_count"]:
                        if "roles" not in current_data:
                            assign_roles(session_id)
                else:
                    # Name already exists, just update it
                    current_data["names"][user_id] = name

        return redirect(url_for("view_session", session_id=session_id))

    @app.route("/s/<session_id>/reset", methods=["POST"])
    def reset_session(session_id):
        """Reset the session to allow reconfiguration while keeping all players."""
        if not session_exists_and_valid(session_id):
            return "404 - Session not found or expired", 404

        if "user_id" not in session:
            return redirect(url_for("view_session", session_id=session_id))

        # Get new configuration
        player_count_str = request.form.get("player_count")

        if not player_count_str:
            flash("Player count is required. Please try resetting again.", "error")
            return redirect(url_for("view_session", session_id=session_id))

        player_count = int(player_count_str)
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

        # Validate role combinations
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

        # Reset roles but keep users and names
        with session_lock:
            current_data = session_store.get(session_id)
            if current_data is None:
                return "404 - Session not found or expired", 404

            current_data["player_count"] = player_count
            current_data["special_roles"] = special_roles

            # Remove role assignments to start fresh
            if "roles" in current_data:
                del current_data["roles"]
            if "role_details" in current_data:
                del current_data["role_details"]

            # Check if we have enough named players to assign roles now
            if len(current_data["names"]) == player_count:
                assign_roles(session_id)

        return redirect(url_for("view_session", session_id=session_id))

    @app.route("/api/s/<session_id>/status")
    def session_status(session_id):
        """API endpoint to get current session status for polling."""
        if not session_exists_and_valid(session_id):
            return jsonify({"error": "Session not found or expired"}), 404

        if "user_id" not in session:
            return jsonify({"error": "User not authenticated"}), 401

        user_id = session["user_id"]

        with session_lock:
            current_data = session_store.get(session_id)
            if current_data is None:
                return jsonify({"error": "Session not found or expired"}), 404

            # Check if user has a role assigned
            user_role = None
            user_role_detail = None
            spy_names = []
            known_spies = []
            commander_info = []

            if "roles" in current_data:
                user_role = current_data["roles"].get(user_id)
                role_details = current_data.get("role_details", {})
                user_role_detail = role_details.get(user_id)

                # Handle special role information (same logic as view_session)
                if user_role_detail == "commander":
                    for uid, role in current_data["roles"].items():
                        if role == "spy" and uid != user_id:
                            detail = role_details.get(uid)
                            if detail != "deep_cover":
                                spy_name = current_data["names"].get(uid)
                                if spy_name:
                                    known_spies.append(spy_name)

                elif user_role_detail == "bodyguard":
                    for uid in current_data["roles"].keys():
                        detail = role_details.get(uid)
                        if detail == "commander" or detail == "false_commander":
                            commander_name = current_data["names"].get(uid)
                            if commander_name:
                                commander_info.append(commander_name)

                elif user_role == "spy":
                    if user_role_detail == "blind_spy":
                        spy_names = []
                    else:
                        for uid, role in current_data["roles"].items():
                            if role == "spy" and uid != user_id:
                                detail = role_details.get(uid)
                                if detail != "blind_spy":
                                    spy_name = current_data["names"].get(uid)
                                    if spy_name:
                                        spy_names.append(spy_name)

            response_data = {
                "counter": current_data["counter"],
                "player_count": current_data["player_count"],
                "player_names": list(current_data["names"].values()),
                "user_role": user_role,
                "user_role_detail": user_role_detail,
                "roles_assigned": "roles" in current_data,
                "spy_names": spy_names,
                "known_spies": known_spies,
                "commander_info": commander_info,
            }

        return jsonify(response_data)

    return app
