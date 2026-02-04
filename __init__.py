from flask import Flask, redirect, url_for, render_template, request, session, jsonify
import os
import uuid
import random

# Role distribution based on player count
ROLE_CONFIG = {
    5: {"resistance": 3, "spies": 2},
    6: {"resistance": 4, "spies": 2},
    7: {"resistance": 4, "spies": 3},
    8: {"resistance": 5, "spies": 3},
    9: {"resistance": 6, "spies": 3},
    10: {"resistance": 6, "spies": 4},
}

# In a real app, use SQLite, PostgreSQL, Redis, etc.
# Structure: { 'session_id': { 'created_at': ..., 'data': ... } }
session_store = {}


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

    # Support for being mounted at a sub-path
    @app.url_defaults
    def add_script_name(endpoint, values):
        """Add SCRIPT_NAME to all generated URLs"""
        pass  # Flask will automatically use SCRIPT_NAME from environ

    @app.route("/")
    def home():
        """The landing page with a button to start a new session."""
        return render_template("home.html")

    @app.route("/create_session", methods=["POST"])
    def create_session():
        """Generates a unique ID and redirects to the specific session URL."""
        # 1. Get player count from form
        player_count = int(request.form.get("player_count", 5))

        # Validate player count is between 5-10
        if player_count < 5 or player_count > 10:
            player_count = 5

        # 2. Get special roles selection
        special_roles = {
            "commander": bool(request.form.get("commander")),
            "bodyguard": bool(request.form.get("bodyguard")),
            "assassin": bool(request.form.get("assassin")),
            "false_commander": bool(request.form.get("false_commander")),
            "deep_cover": bool(request.form.get("deep_cover")),
            "blind_spy": bool(request.form.get("blind_spy")),
        }

        # 3. Generate a unique identifier
        unique_id = uuid.uuid4().hex

        # 4. Initialize the state for this session in our mock DB
        session_store[unique_id] = {
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
        # 4. Check if this session actually exists
        if session_id not in session_store:
            return "404 - Session not found or expired", 404

        # Get or create a unique user ID for this visitor
        if "user_id" not in session:
            session["user_id"] = uuid.uuid4().hex

        user_id = session["user_id"]
        current_data = session_store[session_id]

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
                for uid, detail in role_details.items():
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

        return render_template(
            "session.html",
            session_id=session_id,
            counter=current_data["counter"],
            player_count=current_data.get("player_count", 5),
            user_id=user_id,
            user_role=user_role,
            user_role_detail=user_role_detail,
            user_name=current_data["names"].get(user_id),
            player_names=list(current_data["names"].values()),
            spy_names=spy_names,
            known_spies=known_spies,
            commander_info=commander_info,
            special_roles=current_data.get("special_roles", {}),
        )

    @app.route("/s/<session_id>/set_name", methods=["POST"])
    def set_name(session_id):
        """Allow a user to set their name for the session."""
        if session_id not in session_store:
            return "404 - Session not found", 404

        if "user_id" not in session:
            return redirect(url_for("view_session", session_id=session_id))

        user_id = session["user_id"]
        name = request.form.get("name", "").strip()

        if name and len(name) <= 50:  # Validate name
            current_data = session_store[session_id]

            # Add name only if not already set (prevent race condition overwrites)
            if user_id not in current_data["names"]:
                current_data["names"][user_id] = name
                # Update counter to reflect named players
                current_data["counter"] = len(current_data["names"])

                # Check if we now have enough players to assign roles
                # Use double-check to prevent race condition
                if current_data["counter"] >= current_data["player_count"]:
                    if "roles" not in current_data:
                        # Set a flag immediately to prevent concurrent assignment
                        current_data["roles"] = {}  # Placeholder
                        assign_roles(session_id)
            else:
                # Name already exists, just update it
                current_data["names"][user_id] = name

        return redirect(url_for("view_session", session_id=session_id))

    @app.route("/s/<session_id>/reset", methods=["POST"])
    def reset_session(session_id):
        """Reset the session to allow reconfiguration while keeping all players."""
        if session_id not in session_store:
            return "404 - Session not found", 404

        if "user_id" not in session:
            return redirect(url_for("view_session", session_id=session_id))

        # Get new configuration
        player_count = int(request.form.get("player_count", 5))
        if player_count < 5 or player_count > 10:
            player_count = 5

        special_roles = {
            "commander": bool(request.form.get("commander")),
            "bodyguard": bool(request.form.get("bodyguard")),
            "assassin": bool(request.form.get("assassin")),
            "false_commander": bool(request.form.get("false_commander")),
            "deep_cover": bool(request.form.get("deep_cover")),
            "blind_spy": bool(request.form.get("blind_spy")),
        }

        # Reset roles but keep users and names
        current_data = session_store[session_id]
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
        if session_id not in session_store:
            return jsonify({"error": "Session not found"}), 404

        if "user_id" not in session:
            return jsonify({"error": "User not authenticated"}), 401

        user_id = session["user_id"]
        current_data = session_store[session_id]

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
                for uid, detail in role_details.items():
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

        return jsonify(
            {
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
        )

    return app
