# app.py
import os
from dotenv import load_dotenv
from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
from flask_jwt_extended import (
    create_access_token, JWTManager, get_jwt_identity, jwt_required
)
from werkzeug.security import generate_password_hash, check_password_hash

# --- NEW IMPORTS ---
from db import db        # Import the db instance
from models import User, CribbageGame  # Import your User model (and any other models)
from flask_migrate import Migrate

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# --- JWT Configuration ---
app.config["JWT_SECRET_KEY"] = os.environ.get("JWT_SECRET_KEY", "a-default-secret-key-for-dev")
app.config["JWT_TOKEN_LOCATION"] = ["headers"]
app.config["JWT_COOKIE_CSRF_PROTECT"] = False
jwt = JWTManager(app)

frontend_cors_origin = os.environ.get("FRONTEND_CORS_ORIGIN", "http://localhost:3000")

# --- CORS Configuration ---
CORS(app, resources={r"/api/*": {"origins": frontend_cors_origin}}, supports_credentials=True)

# --- PostgreSQL Database Configuration for Local Docker (from .env) ---
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
if not app.config["SQLALCHEMY_DATABASE_URI"]:
    raise ValueError("DATABASE_URL environment variable is not set! Please check your .env file or system environment.")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# --- Initialize SQLAlchemy with the app ---
# This is the key step for segmentation: Associate the db instance with the Flask app
db.init_app(app)
migrate = Migrate(app, db)


# --- All your endpoints (login, register, get_data, get_post_data) ---
# These remain mostly the same, but now they use the User model imported from models.py

@app.route("/")
def index():
    users = User.query.all()
  
    return render_template('index.html', users=users)

@app.post("/api/login")
def login():
    username = request.json.get('username', None)
    password = request.json.get('password', None)

    user = User.query.filter_by(username=username).first() # User comes from models.py

    if not user or not user.check_password(password):
        return jsonify({"msg": "Bad username or password"}), 401

    access_token = create_access_token(identity=str(user.id))
    return jsonify({"msg": "Login successful", "access_token": access_token}), 200

# --- User Registration Endpoint ---
@app.post("/api/register")
def register():
    username = request.json.get('username', None)
    password = request.json.get('password', None)

    if not username or not password:
        return jsonify({"msg": "Missing username or password"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"msg": "Username already exists"}), 409

    hashed_password = generate_password_hash(password)
    new_user = User(username=username, password_hash=hashed_password)

    try:
        db.session.add(new_user)
        db.session.commit()
        return jsonify({"msg": "User created successfully"}), 201
    except Exception as e:
        db.session.rollback()
        print(f"Error during registration: {e}")
        return jsonify({"msg": "An error occurred during registration"}), 500


# --- Protected GET Endpoint ---
@app.get("/api/data")
@jwt_required()
def get_data():
    current_user_id = get_jwt_identity()
    user = User.query.get(current_user_id) # User comes from models.py
    if not user:
        return jsonify({"msg": "User not found"}), 404
    return jsonify({"message": f"Hello, {user.username}! Your ID is {current_user_id}"})


# --- Protected POST Endpoint ---
@app.post("/api/data")
@jwt_required()
def get_post_data():
   print("post request received")
   current_user_id = get_jwt_identity()
   user = User.query.get(current_user_id) # User comes from models.py
   if not user:
       return jsonify({"msg": "User not found"}), 404

   data_from_client = request.json
   print(f"User {user.username} submitted data: {data_from_client}")

   return jsonify({"message": f"Data received from {user.username}", "data": data_from_client})


@app.get("/api/users")
@jwt_required() # Protect this route
def get_users_for_opponent_selection():
    current_user_id = get_jwt_identity() # Get the ID of the currently authenticated user

    # Fetch all users EXCEPT the current logged-in user
    # This ensures a user cannot select themselves as an opponent from the dropdown
    users = User.query.filter(User.id != current_user_id).all()

    # Return a list of user dictionaries using the to_dict method
    # The frontend expects a direct array, not nested under "users" key
    return jsonify([user.to_dict() for user in users]), 200

# --- Protected POST Endpoint for Logging Cribbage Scores ---
@app.post("/api/score")
@jwt_required() # Protect this route
def log_cribbage_score():
    try:
        current_user_id = get_jwt_identity() # Get the ID of the currently authenticated user from the JWT
        data = request.get_json() # Get the JSON payload from the frontend

        # --- Server-Side Validation ---
        required_fields = ['user_score', 'opponent_score', 'is_skunk', 'is_double_skunk']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400

        try:
            user_score = int(data['user_score'])
            opponent_score = int(data['opponent_score'])
            if not (0 <= user_score <= 121 and 0 <= opponent_score <= 121):
                return jsonify({"error": "Scores must be between 0 and 121"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "Scores must be valid numbers"}), 400

        opponent_user_id = data.get('opponent_user_id')
        guest_opponent_name = data.get('guest_opponent_name')

        # Ensure that either opponent_user_id OR guest_opponent_name is provided, but not both
        if opponent_user_id is None and guest_opponent_name is None:
            return jsonify({"error": "Either opponent_user_id or guest_opponent_name must be provided"}), 400
        if opponent_user_id is not None and guest_opponent_name is not None:
             # This case means both were sent. Prioritize opponent_user_id as it's for registered users.
             guest_opponent_name = None # Clear guest name if registered user ID is present
        elif opponent_user_id is not None:
            # Verify opponent_user_id refers to an actual existing user
            if not User.query.get(opponent_user_id):
                return jsonify({"error": "Referenced opponent_user_id does not exist"}), 400
        elif guest_opponent_name is not None and not isinstance(guest_opponent_name, str):
            return jsonify({"error": "guest_opponent_name must be a string"}), 400


        # Create a new CribbageGame instance
        new_game = CribbageGame(
            user_id=current_user_id, # <--- CRUCIAL: Use user ID from JWT, NOT from frontend payload
            user_score=user_score,
            opponent_score=opponent_score,
            opponent_user_id=opponent_user_id,
            guest_opponent_name=guest_opponent_name,
            is_skunk=bool(data.get('is_skunk', False)),
            is_double_skunk=bool(data.get('is_double_skunk', False)),
            notes=data.get('notes') # 'notes' field is now in the model
        )

        db.session.add(new_game)
        db.session.commit()

        # Return a success response
        return jsonify({
            "message": "Cribbage game logged successfully!",
            "game_id": new_game.id,
            "user_id": new_game.user_id, # Can return this for confirmation
            "user_score": new_game.user_score,
            "opponent_score": new_game.opponent_score
        }), 201 # 201 Created

    except Exception as e:
        db.session.rollback() # Rollback the session in case of an error
        print(f"Error logging cribbage game: {e}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


# --- Protected GET Endpoint for Dashboard Stats ---
@app.get("/api/dashboard-stats")
@jwt_required()
def get_dashboard_stats():
    current_user_id = get_jwt_identity() # Get the ID of the currently authenticated user

    # Fetch the current user object
    current_user = User.query.get(current_user_id)
    if not current_user:
        return jsonify({"error": "User not found"}), 404

    # Get all games where the current user was either the recorder or the opponent
    all_relevant_games = CribbageGame.query.filter(
        (CribbageGame.user_id == current_user_id) |
        (CribbageGame.opponent_user_id == current_user_id)
    ).order_by(CribbageGame.game_date.desc()).all() # Order by date descending for streak calculation

    total_games = len(all_relevant_games)
    total_wins = 0
    total_losses = 0
    consecutive_wins = 0
    
    # Calculate wins, losses, and consecutive wins
    for game in all_relevant_games:
        print(game.user_id)
        print(game.user_score)
        print(game.opponent_score)
        print(current_user_id)
        print(current_user.id)
        print(current_user.id == game.user_id)
        print(current_user_id == game.user_id)
        # Determine if the current_user_id won this specific game
        current_user_won_this_game = False
        if game.user_id == current_user.id and game.user_score == 121:
            current_user_won_this_game = True
        elif game.opponent_user_id == current_user.id and game.opponent_score == 121:
            current_user_won_this_game = True

        # Update total wins/losses
        if current_user_won_this_game:
            total_wins += 1
        else:
            # A game is a loss if the other player reached 121, or if the current user reached 121
            # but the other player also reached 121 (unlikely in cribbage, but covers all cases)
            if (game.user_id == current_user.id and game.opponent_score == 121) or \
               (game.opponent_user_id == current_user.id and game.user_score == 121):
                total_losses += 1

        # Calculate consecutive wins (only if the game was a win for the current user)
        if current_user_won_this_game:
            consecutive_wins += 1
        else:
            # Streak is broken if the current game was not a win for the current user
            # Since games are ordered by date descending, the first non-win breaks the streak
            break

    # Get recent games (e.g., last 10, or all if less than 10)
    # Use the to_dict method, passing the current_user_id so it can calculate 'viewer_won'
    recent_games_limit = 10
    recent_games_data = [game.to_dict(current_user_id=current_user.id) for game in all_relevant_games[:recent_games_limit]]

    return jsonify({
        "username": current_user.username,
        "total_games": total_games,
        "total_wins": total_wins,
        "total_losses": total_losses,
        "consecutive_wins": consecutive_wins,
        "recent_games": recent_games_data
    }), 200



@app.get("/api/message")
def get_message():
    return jsonify("message")






if __name__ == "__main__":
    with app.app_context():
        db.create_all() # This will create tables in your database
    # app.run(debug=True, ssl_context=('cert.pem', 'key.pem')) # Adjust SSL context as needed
    app.run(debug=True, ssl_context='adhoc')

