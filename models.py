# models.py
from datetime import datetime
from db import db # Import the db instance from your new db.py file
from werkzeug.security import generate_password_hash, check_password_hash

# Define your User model
class User(db.Model):
    __tablename__ = 'users' # Good practice to explicitly set table name
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    def __repr__(self):
        return f'<User {self.username}>'

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            # Do NOT include password_hash here for security
            # 'email': self.email # Include if you add an email field to User model
        }

# You would define other database models here as your application grows
# For example:
# class Post(db.Model):
#     __tablename__ = 'posts'
#     id = db.Column(db.Integer, primary_key=True)
#     title = db.Column(db.String(120), nullable=False)
#     content = db.Column(db.Text, nullable=False)
#     user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
#     author = db.relationship('User', backref='posts')

class CribbageGame(db.Model):
    """
    Model to store the final scores of Cribbage games.
    """
    __tablename__ = 'cribbage_games' # Explicitly set table name

    id = db.Column(db.Integer, primary_key=True)

    # Correlated with the logged-in user (the player who recorded the game)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    # Relationship to the User model (the player recording)
    # This allows you to access game.player_user to get the User object
    player_user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('recorded_games', lazy=True))

    # Optionally link to another registered user as an opponent
    opponent_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    # Relationship to the User model (the opponent, if registered)
    # This allows you to access game.opponent_registered_user to get the User object
    opponent_registered_user = db.relationship('User', foreign_keys=[opponent_user_id], backref=db.backref('opponent_games', lazy=True))

    # Allow for "guest" opponents if opponent_user_id is null
    guest_opponent_name = db.Column(db.String(100), nullable=True)

    # Each player's final score
    user_score = db.Column(db.Integer, nullable=False)
    opponent_score = db.Column(db.Integer, nullable=False)

    # Indicators for "skunk" or "Double skunk"
    is_skunk = db.Column(db.Boolean, default=False, nullable=False)
    is_double_skunk = db.Column(db.Boolean, default=False, nullable=False)

    # Timestamp for when the game was recorded
    game_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    notes = db.Column(db.Text, nullable=True)

    def __init__(self, user_id, user_score, opponent_score,
                 opponent_user_id=None, guest_opponent_name=None,
                 is_skunk=False, is_double_skunk=False, notes=''):
        self.user_id = user_id
        self.user_score = user_score
        self.opponent_score = opponent_score
        self.opponent_user_id = opponent_user_id
        self.guest_opponent_name = guest_opponent_name
        self.is_skunk = is_skunk
        self.is_double_skunk = is_double_skunk
        self.notes = notes
        # game_date defaults to utcnow, no need to set here unless custom date is needed

    def __repr__(self):
        opponent_info = ""
        if self.opponent_registered_user:
            opponent_info = f"vs. {self.opponent_registered_user.username}"
        elif self.guest_opponent_name:
            opponent_info = f"vs. Guest ({self.guest_opponent_name})"
        else:
            opponent_info = "vs. Unknown Opponent" # Should ideally not happen if logic is correct

        skunk_status = ""
        if self.is_double_skunk:
            skunk_status = " (DOUBLE SKUNK!)"
        elif self.is_skunk:
            skunk_status = " (SKUNK!)"

        return (f"<CribbageGame {self.id}: User {self.player_user.username} "
                f"{opponent_info} - Scores: {self.user_score}-{self.opponent_score}{skunk_status} - Notes: {self.notes}>")


    @property
    def winner(self):
        """Determines the winner of the game."""
        if self.user_score > self.opponent_score:
            return self.player_user.username
        elif self.opponent_score > self.user_score:
            # Return opponent's info based on whether they were a registered user or guest
            return self.opponent_registered_user.username if self.opponent_registered_user else self.guest_opponent_name
        else:
            return "Tie" # Cribbage rarely has ties in final score, but good to handle

    @property
    def is_game_valid(self):
        """Basic validation for cribbage scores (must reach 121)."""
        return self.user_score == 121 or self.opponent_score == 121
    
    def to_dict(self, current_user_id=None): # Added current_user_id for context
        # Determine opponent's display name for serialization
        opponent_display_name = ""
        if self.opponent_registered_user:
            opponent_display_name = self.opponent_registered_user.username
        elif self.guest_opponent_name:
            opponent_display_name = self.guest_opponent_name
        else:
            opponent_display_name = "Unknown Opponent"

        # Determine if the current viewer won this specific game
        viewer_won = False
        if current_user_id is not None:
            if self.user_id == current_user_id and self.user_score == 121:
                viewer_won = True
            elif self.opponent_user_id == current_user_id and self.opponent_score == 121:
                viewer_won = True

        return {
            'id': self.id,
            'user_id': self.user_id,
            'user_username': self.player_user.username if self.player_user else None,
            'user_score': self.user_score,
            'opponent_user_id': self.opponent_user_id,
            'opponent_username': opponent_display_name,
            'opponent_score': self.opponent_score,
            'is_skunk': self.is_skunk,
            'is_double_skunk': self.is_double_skunk,
            'game_date': self.game_date.isoformat(), # ISO format for easy parsing in JavaScript
            'notes': self.notes,
            'viewer_won': viewer_won # <--- NEW: Flag indicating if the current viewer won this game
        }

