# db.py
from flask_sqlalchemy import SQLAlchemy

# Initialize SQLAlchemy without passing the app directly.
# This allows 'db' to be imported by models.py without circular imports.
db = SQLAlchemy()
