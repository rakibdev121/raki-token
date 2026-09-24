from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import time

app = Flask(__name__)
CORS(app)

DB = "raki.db"


def db():
    conn = sqlite3.connect(DB)
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
            created_at INTEGER
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

    conn.commit()
    conn.close()


@app.route("/")
def home():
    return jsonify({
        "status": "online",
        "app": "Raki Token API",
        "version": "1.0"
    })


@app.route("/api/user/<int:user_id>")
def get_user(user_id):

    conn = db()

    user = conn.execute(
        "SELECT * FROM users WHERE id=?",
        (user_id,)
    ).fetchone()

    conn.close()

    if not user:
        return jsonify({
            "error": "User not found"
        }), 404

    return jsonify(dict(user))


@app.route("/api/user", methods=["POST"])
def create_user():

    data = request.get_json() or {}

    user_id = data.get("id")
    username = data.get("username", "User")

    if not user_id:
        return jsonify({
            "error": "Telegram user ID required"
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
            "user": dict(existing)
        })

    conn.execute("""
        INSERT INTO users
        (id, username, balance, mining, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (
        user_id,
        username,
        0,
        0,
        int(time.time())
    ))

    conn.commit()

    user = conn.execute(
        "SELECT * FROM users WHERE id=?",
        (user_id,)
    ).fetchone()

    conn.close()

    return jsonify({
        "message": "User created",
        "user": dict(user)
    })


@app.route("/api/mining/start", methods=["POST"])
def start_mining():

    data = request.get_json() or {}
    user_id = data.get("user_id")

    if not user_id:
        return jsonify({
            "error": "user_id required"
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

    conn.execute(
        "UPDATE users SET mining=1 WHERE id=?",
        (user_id,)
    )

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "message": "Mining started"
    })


@app.route("/api/mining/stop", methods=["POST"])
def stop_mining():

    data = request.get_json() or {}
    user_id = data.get("user_id")

    conn = db()

    conn.execute(
        "UPDATE users SET mining=0 WHERE id=?",
        (user_id,)
    )

    conn.commit()
    conn.close()

    return jsonify({
        "success": True,
        "message": "Mining stopped"
    })


@app.route("/api/transactions/<int:user_id>")
def transactions(user_id):

    conn = db()

    rows = conn.execute("""
        SELECT *
        FROM transactions
        WHERE user_id=?
        ORDER BY id DESC
    """, (user_id,)).fetchall()

    conn.close()

    return jsonify([
        dict(row) for row in rows
    ])


if __name__ == "__main__":

    init_db()

    print("================================")
    print(" RAKI TOKEN BACKEND")
    print(" API: http://127.0.0.1:5000")
    print("================================")

    app.run(
        host="0.0.0.0",
        port=5050,
        debug=False
    )
