import os
import sqlite3
import hashlib
import secrets
import logging

DB_PATH = "users.db"
logger = logging.getLogger(__name__)

def init_db():
    """Initializes the SQLite database with the users table."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL
    );
    """)
    conn.commit()
    conn.close()
    logger.info("Database initialized successfully.")

def hash_password(password: str) -> tuple[str, str]:
    """Generates a secure hash and salt for a password."""
    salt = secrets.token_hex(16)
    pwd_bytes = password.encode('utf-8')
    salt_bytes = salt.encode('utf-8')
    hashed = hashlib.pbkdf2_hmac('sha256', pwd_bytes, salt_bytes, 100000)
    return hashed.hex(), salt

def verify_password(password: str, password_hash: str, salt: str) -> bool:
    """Verifies a password against a stored hash and salt."""
    pwd_bytes = password.encode('utf-8')
    salt_bytes = salt.encode('utf-8')
    hashed = hashlib.pbkdf2_hmac('sha256', pwd_bytes, salt_bytes, 100000)
    return hashed.hex() == password_hash

class SessionManager:
    def __init__(self):
        self.sessions = {}  # token -> username

    def create_session(self, username: str) -> str:
        """Generates a secure session token for a user."""
        token = secrets.token_hex(32)
        self.sessions[token] = username
        return token

    def get_username(self, token: str) -> str | None:
        """Resolves a session token to a username."""
        return self.sessions.get(token)

    def remove_session(self, token: str):
        """Invalidates a session token."""
        if token in self.sessions:
            del self.sessions[token]

def register_user(username: str, password: str) -> bool:
    """Registers a new user in the database."""
    username = username.strip().lower()
    if not username or len(password) < 6:
        return False

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        # Check if username exists
        cursor.execute("SELECT 1 FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            return False

        p_hash, salt = hash_password(password)
        cursor.execute("INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
                       (username, p_hash, salt))
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error registering user '{username}': {e}")
        return False
    finally:
        conn.close()

def authenticate_user(username: str, password: str) -> bool:
    """Validates user credentials against stored database hashes."""
    username = username.strip().lower()
    if not username or not password:
        return False

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT password_hash, salt FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        if not row:
            return False
        p_hash, salt = row
        return verify_password(password, p_hash, salt)
    except Exception as e:
        logger.error(f"Error authenticating user '{username}': {e}")
        return False
    finally:
        conn.close()
