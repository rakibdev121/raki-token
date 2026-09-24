from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import time
import os

app = Flask(__name__)
CORS(app)

DB_NAME = "raki.db"

# =========================
# MINING SETTINGS
# =========================

# 1 Raki Token প্রতি মিনিটে
MINING_RATE_PER_MINUTE = 1.0

# Mining start bonus
START_BONUS = 10.0


# =========================
# DATABASE
# =========================

def db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            balance REAL DEFAULT 0,
            mining INTEGER DEFAULT 0,
            created_at INTEGER,
            mining_started_at INTEGER,
            last_mining_update INTEGER,
            start_bonus_received INTEGER DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            amount REAL,
            created_at INTEGER
        )
    """)

    # Existing database হলে missing column add করার চেষ্টা
    columns = [
        ("mining_started_at", "INTEGER"),
        ("last_mining_update", "INTEGER"),
        ("start_bonus_received", "INTEGER DEFAULT 0")
    ]

    existing = [
        row["name"]
        for row in conn.execute("PRAGMA table_info(users)").fetchall()
    ]

    for column, datatype in columns:
        if column not in existing:
            conn.execute(
                f"ALTER TABLE users ADD COLUMN {column} {datatype}"
            )

    conn.commit()
    conn.close()


# =========================
# MINING UPDATE
# =========================

def update_mining(user_id):

    conn = db()

    user = conn.execute(
        "SELECT * FROM users WHERE id=?",
        (user_id,)
    ).fetchone()

    if not user:
        conn.close()
        return None

    if user["mining"] != 1:
        conn.close()
        return user

    now = int(time.time())

    last_update = user["last_mining_update"]

    if last_update is None:
        last_update = now

    elapsed_seconds = now - last_update

    if elapsed_seconds <= 0:
        conn.close()
        return user

    # প্রতি মিনিটে 1 token
    earned = (elapsed_seconds / 60) * MINING_RATE_PER_MINUTE

    conn.execute("""
        UPDATE users
        SET balance = balance + ?,
            last_mining_update = ?
        WHERE id=?
    """, (
        earned,
        now,
        user_id
    ))

    conn.commit()

    user = conn.execute(
        "SELECT * FROM users WHERE id=?",
        (user_id,)
    ).fetchone()

    conn.close()

    return user


# =========================
# HOME
# =========================

@app.route("/")
def home():

    return jsonify({
        "app": "Raki Token API",
        "status": "online",
        "version": "3.0"
    })


# =========================
# GET USER
# =========================

@app.route("/api/user/<int:user_id>", methods=["GET"])
def get_user(user_id):

    user = update_mining(user_id)

    if not user:
        return jsonify({
            "error": "User not found"
        }), 404

    return jsonify({
        "id": user["id"],
        "username": user["username"],
        "balance": round(user["balance"], 6),
        "mining": user["mining"],
        "start_bonus_received": user["start_bonus_received"]
    })


# =========================
# CREATE USER
# =========================

@app.route("/api/user", methods=["POST"])
def create_user():

    data = request.get_json() or {}

    user_id = data.get("id")
    username = data.get("username", "")

    if not user_id:
        return jsonify({
            "error": "User ID required"
        }), 400

    conn = db()

    existing = conn.execute(
        "SELECT * FROM users WHERE id=?",
        (user_id,)
    ).fetchone()

    if existing:
        conn.close()

        return jsonify({
            "message": "User already exists",
            "user": {
                "id": existing["id"],
                "username": existing["username"],
                "balance": existing["balance"],
                "mining": existing["mining"]
            }
        })

    now = int(time.time())

    conn.execute("""
        INSERT INTO users (
            id,
            username,
            balance,
            mining,
            created_at,
            mining_started_at,
            last_mining_update,
            start_bonus_received
        )
        VALUES (?, ?, 0, 0, ?, NULL, NULL, 0)
    """, (
        user_id,
        username,
        now
    ))

    conn.commit()

    user = conn.execute(
        "SELECT * FROM users WHERE id=?",
        (user_id,)
    ).fetchone()

    conn.close()

    return jsonify({
        "message": "User created",
        "user": {
            "id": user["id"],
            "username": user["username"],
            "balance": user["balance"],
            "mining": user["mining"],
            "start_bonus_received": user["start_bonus_received"]
        }
    })


# =========================
# START MINING
# =========================

@app.route("/api/mining/start", methods=["POST"])
def start_mining():

    data = request.get_json() or {}

    user_id = data.get("user_id")

    if not user_id:
        return jsonify({
            "error": "User ID required"
        }), 400

    conn = db()

    user = conn.execute(
        "SELECT * FROM users WHERE id=?",
        (user_id,)
    ).fetchone()

    if not user:
        conn.close()

        return jsonify({
            "error": "User not found"
        }), 404

    # Already mining
    if user["mining"] == 1:

        conn.close()

        return jsonify({
            "message": "Mining already running",
            "success": True
        })

    now = int(time.time())

    bonus = 0

    # =========================
    # FIRST START BONUS
    # =========================

    if user["start_bonus_received"] == 0:

        bonus = START_BONUS

        conn.execute("""
            UPDATE users
            SET
                balance = balance + ?,
                mining = 1,
                mining_started_at = ?,
                last_mining_update = ?,
                start_bonus_received = 1
            WHERE id=?
        """, (
            bonus,
            now,
            now,
            user_id
        ))

        # Transaction record
        conn.execute("""
            INSERT INTO transactions (
                user_id,
                type,
                amount,
                created_at
            )
            VALUES (?, ?, ?, ?)
        """, (
            user_id,
            "start_bonus",
            START_BONUS,
            now
        ))

    else:

        conn.execute("""
            UPDATE users
            SET
                mining = 1,
                mining_started_at = ?,
                last_mining_update = ?
            WHERE id=?
        """, (
            now,
            now,
            user_id
        ))

    conn.commit()
    conn.close()

    return jsonify({
        "message": "Mining started",
        "success": True,
        "bonus": bonus,
        "mining_rate": "1 Raki Token / minute"
    })


# =========================
# STOP MINING
# =========================

@app.route("/api/mining/stop", methods=["POST"])
def stop_mining():

    data = request.get_json() or {}

    user_id = data.get("user_id")

    if not user_id:
        return jsonify({
            "error": "User ID required"
        }), 400

    # First calculate earned mining
    user = update_mining(user_id)

    if not user:
        return jsonify({
            "error": "User not found"
        }), 404

    conn = db()

    conn.execute("""
        UPDATE users
        SET
            mining = 0,
            mining_started_at = NULL,
            last_mining_update = NULL
        WHERE id=?
    """, (
        user_id,
    ))

    conn.commit()

    user = conn.execute(
        "SELECT * FROM users WHERE id=?",
        (user_id,)
    ).fetchone()

    conn.close()

    return jsonify({
        "message": "Mining stopped",
        "success": True,
        "balance": round(user["balance"], 6)
    })


# =========================
# TRANSACTIONS
# =========================

@app.route("/api/transactions/<int:user_id>", methods=["GET"])
def transactions(user_id):

    conn = db()

    rows = conn.execute("""
        SELECT *
        FROM transactions
        WHERE user_id=?
        ORDER BY id DESC
    """, (
        user_id,
    )).fetchall()

    conn.close()

    result = []

    for row in rows:
        result.append({
            "id": row["id"],
            "type": row["type"],
            "amount": row["amount"],
            "created_at": row["created_at"]
        })

    return jsonify(result)


# =========================
# START
# =========================

init_db()

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5050))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
