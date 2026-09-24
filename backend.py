from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import time
import os

app = Flask(__name__)
CORS(app)

DB_NAME = "raki.db"

# =========================
# SETTINGS
# =========================

MINING_RATE_PER_MINUTE = 1.0
START_BONUS = 10.0

# Referral bonus
REFERRAL_BONUS = 5.0


# =========================
# DATABASE
# =========================

def db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():

    conn = db()

    # =========================
    # USERS
    # =========================

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            balance REAL DEFAULT 0,
            mining INTEGER DEFAULT 0,
            created_at INTEGER,
            mining_started_at INTEGER,
            last_mining_update INTEGER,
            start_bonus_received INTEGER DEFAULT 0,
            referrer_id INTEGER
        )
    """)

    # Existing database migration
    columns = [
        ("mining_started_at", "INTEGER"),
        ("last_mining_update", "INTEGER"),
        ("start_bonus_received", "INTEGER DEFAULT 0"),
        ("referrer_id", "INTEGER")
    ]

    existing = [
        row["name"]
        for row in conn.execute(
            "PRAGMA table_info(users)"
        ).fetchall()
    ]

    for column, datatype in columns:
        if column not in existing:
            conn.execute(
                f"ALTER TABLE users ADD COLUMN {column} {datatype}"
            )

    # =========================
    # TRANSACTIONS
    # =========================

    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            amount REAL,
            created_at INTEGER
        )
    """)

    # =========================
    # WITHDRAWALS
    # =========================

    conn.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            wallet_address TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at INTEGER
        )
    """)

    # =========================
    # REFERRALS
    # =========================

    conn.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER NOT NULL,
            referred_id INTEGER NOT NULL UNIQUE,
            bonus REAL DEFAULT 0,
            created_at INTEGER
        )
    """)

    # =========================
    # TASKS
    # =========================

    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            reward REAL DEFAULT 0,
            link TEXT,
            active INTEGER DEFAULT 1,
            created_at INTEGER
        )
    """)

    # =========================
    # USER TASKS
    # =========================

    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            task_id INTEGER,
            claimed_at INTEGER,
            UNIQUE(user_id, task_id)
        )
    """)

    # =========================
    # DEMO TASKS
    # =========================

    task_count = conn.execute(
        "SELECT COUNT(*) FROM tasks"
    ).fetchone()[0]

    if task_count == 0:

        now = int(time.time())

        demo_tasks = [
            (
                "Join Telegram Channel",
                "Join our official Telegram channel",
                5.0,
                "https://t.me/",
                1,
                now
            ),
            (
                "Watch YouTube Video",
                "Watch the Raki Token video",
                10.0,
                "https://youtube.com/",
                1,
                now
            ),
            (
                "Visit Website",
                "Visit Raki Token website",
                3.0,
                "https://rakibdev121.github.io/raki-token/",
                1,
                now
            )
        ]

        conn.executemany("""
            INSERT INTO tasks
            (title, description, reward, link, active, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, demo_tasks)

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

    earned = (
        elapsed_seconds / 60
    ) * MINING_RATE_PER_MINUTE

    conn.execute("""
        UPDATE users
        SET
            balance = balance + ?,
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
# TASK API
# =========================

@app.route("/api/tasks/<int:user_id>", methods=["GET"])
def get_tasks(user_id):

    conn = db()

    tasks = conn.execute("""
        SELECT
            tasks.id,
            tasks.title,
            tasks.description,
            tasks.reward,
            tasks.link,
            tasks.active,

            CASE
                WHEN user_tasks.id IS NOT NULL THEN 1
                ELSE 0
            END AS claimed

        FROM tasks

        LEFT JOIN user_tasks
        ON tasks.id = user_tasks.task_id
        AND user_tasks.user_id = ?

        WHERE tasks.active = 1

        ORDER BY tasks.id ASC
    """, (
        user_id,
    )).fetchall()

    conn.close()

    return jsonify({
        "success": True,
        "tasks": [dict(task) for task in tasks]
    })


# =========================
# CLAIM TASK
# =========================

@app.route("/api/tasks/claim", methods=["POST"])
def claim_task():

    data = request.get_json() or {}

    user_id = data.get("user_id")
    task_id = data.get("task_id")

    if not user_id or not task_id:

        return jsonify({
            "success": False,
            "error": "user_id and task_id required"
        }), 400

    conn = db()

    user = conn.execute(
        "SELECT * FROM users WHERE id=?",
        (user_id,)
    ).fetchone()

    if not user:

        conn.close()

        return jsonify({
            "success": False,
            "error": "User not found"
        }), 404

    task = conn.execute(
        "SELECT * FROM tasks WHERE id=? AND active=1",
        (task_id,)
    ).fetchone()

    if not task:

        conn.close()

        return jsonify({
            "success": False,
            "error": "Task not found"
        }), 404

    already_claimed = conn.execute("""
        SELECT id
        FROM user_tasks
        WHERE user_id=? AND task_id=?
    """, (
        user_id,
        task_id
    )).fetchone()

    if already_claimed:

        conn.close()

        return jsonify({
            "success": False,
            "error": "Task already claimed"
        }), 400

    now = int(time.time())

    # Add reward
    conn.execute("""
        UPDATE users
        SET balance = balance + ?
        WHERE id=?
    """, (
        task["reward"],
        user_id
    ))

    # Mark task completed
    conn.execute("""
        INSERT INTO user_tasks
        (user_id, task_id, claimed_at)
        VALUES (?, ?, ?)
    """, (
        user_id,
        task_id,
        now
    ))

    # Transaction
    conn.execute("""
        INSERT INTO transactions
        (user_id, type, amount, created_at)
        VALUES (?, ?, ?, ?)
    """, (
        user_id,
        "task_reward",
        task["reward"],
        now
    ))

    conn.commit()

    new_balance = conn.execute(
        "SELECT balance FROM users WHERE id=?",
        (user_id,)
    ).fetchone()["balance"]

    conn.close()

    return jsonify({
        "success": True,
        "message": "Task completed",
        "reward": task["reward"],
        "balance": new_balance
    })


# =========================
# WITHDRAW
# =========================

@app.route("/api/withdraw", methods=["POST"])
def create_withdraw():

    data = request.get_json() or {}

    user_id = data.get("user_id")
    amount = data.get("amount")
    wallet_address = str(
        data.get("wallet_address", "")
    ).strip()

    if not user_id:
        return jsonify({
            "success": False,
            "error": "User ID required"
        }), 400

    try:
        user_id = int(user_id)
        amount = float(amount)
    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "error": "Invalid user or amount"
        }), 400

    # Minimum withdrawal
    if amount < 1:
        return jsonify({
            "success": False,
            "error": "Minimum withdrawal is 1 RAKI"
        }), 400

    # Basic BSC/EVM address validation
    if not (
        len(wallet_address) == 42
        and wallet_address.startswith("0x")
    ):
        return jsonify({
            "success": False,
            "error": "Invalid BSC wallet address"
        }), 400

    try:
        int(wallet_address[2:], 16)
    except ValueError:
        return jsonify({
            "success": False,
            "error": "Invalid BSC wallet address"
        }), 400

    conn = db()

    try:

        # Lock database transaction
        conn.execute("BEGIN IMMEDIATE")

        user = conn.execute(
            """
            SELECT balance
            FROM users
            WHERE id=?
            """,
            (user_id,)
        ).fetchone()

        if not user:
            conn.rollback()
            conn.close()

            return jsonify({
                "success": False,
                "error": "User not found"
            }), 404

        balance = float(user["balance"] or 0)

        if amount > balance:
            conn.rollback()
            conn.close()

            return jsonify({
                "success": False,
                "error": "Insufficient balance",
                "balance": round(balance, 6)
            }), 400

        now = int(time.time())

        # Deduct balance
        conn.execute(
            """
            UPDATE users
            SET balance = balance - ?
            WHERE id=?
            """,
            (amount, user_id)
        )

        # Create pending withdrawal
        cursor = conn.execute(
            """
            INSERT INTO withdrawals
            (
                user_id,
                amount,
                wallet_address,
                status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                user_id,
                amount,
                wallet_address,
                "pending",
                now
            )
        )

        withdrawal_id = cursor.lastrowid

        # Transaction record
        conn.execute(
            """
            INSERT INTO transactions
            (
                user_id,
                type,
                amount,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                user_id,
                "withdraw_pending",
                -amount,
                now
            )
        )

        conn.commit()

        new_balance = conn.execute(
            """
            SELECT balance
            FROM users
            WHERE id=?
            """,
            (user_id,)
        ).fetchone()["balance"]

        conn.close()

        return jsonify({
            "success": True,
            "message": "Withdrawal request submitted",
            "withdrawal_id": withdrawal_id,
            "status": "pending",
            "amount": round(amount, 6),
            "balance": round(new_balance, 6)
        })

    except Exception as error:

        conn.rollback()
        conn.close()

        print("WITHDRAW ERROR:", error)

        return jsonify({
            "success": False,
            "error": "Withdrawal request failed"
        }), 500


# =========================
# HOME
# =========================

@app.route("/")
def home():

    return jsonify({
        "app": "Raki Token API",
        "status": "online",
        "version": "4.0"
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
        "start_bonus_received": user["start_bonus_received"],
        "referrer_id": user["referrer_id"]
    })


# =========================
# CREATE USER
# =========================

@app.route("/api/user", methods=["POST"])
def create_user():

    data = request.get_json() or {}

    user_id = data.get("id")
    username = data.get("username", "")

    # Referral ID
    referrer_id = data.get("referrer_id")

    if not user_id:

        return jsonify({
            "error": "User ID required"
        }), 400

    try:
        user_id = int(user_id)
    except:

        return jsonify({
            "error": "Invalid user ID"
        }), 400

    if referrer_id:

        try:
            referrer_id = int(referrer_id)
        except:

            referrer_id = None

    conn = db()

    # Check existing user
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
                "mining": existing["mining"],
                "referrer_id": existing["referrer_id"]
            }
        })

    # Prevent self referral
    if referrer_id == user_id:
        referrer_id = None

    # Check referrer exists
    if referrer_id:

        referrer = conn.execute(
            "SELECT id FROM users WHERE id=?",
            (referrer_id,)
        ).fetchone()

        if not referrer:
            referrer_id = None

    now = int(time.time())

    # Create user
    conn.execute("""
        INSERT INTO users (
            id,
            username,
            balance,
            mining,
            created_at,
            mining_started_at,
            last_mining_update,
            start_bonus_received,
            referrer_id
        )
        VALUES (?, ?, 0, 0, ?, NULL, NULL, 0, ?)
    """, (
        user_id,
        username,
        now,
        referrer_id
    ))

    # =========================
    # REFERRAL BONUS
    # =========================

    referral_bonus = 0

    if referrer_id:

        # Make sure referral does not already exist
        referral_exists = conn.execute("""
            SELECT id
            FROM referrals
            WHERE referred_id=?
        """, (
            user_id,
        )).fetchone()

        if not referral_exists:

            referral_bonus = REFERRAL_BONUS

            # Give bonus to referrer
            conn.execute("""
                UPDATE users
                SET balance = balance + ?
                WHERE id=?
            """, (
                referral_bonus,
                referrer_id
            ))

            # Referral record
            conn.execute("""
                INSERT INTO referrals (
                    referrer_id,
                    referred_id,
                    bonus,
                    created_at
                )
                VALUES (?, ?, ?, ?)
            """, (
                referrer_id,
                user_id,
                referral_bonus,
                now
            ))

            # Transaction for referrer
            conn.execute("""
                INSERT INTO transactions (
                    user_id,
                    type,
                    amount,
                    created_at
                )
                VALUES (?, ?, ?, ?)
            """, (
                referrer_id,
                "referral_bonus",
                referral_bonus,
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
        "referral_bonus": referral_bonus,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "balance": user["balance"],
            "mining": user["mining"],
            "start_bonus_received": user["start_bonus_received"],
            "referrer_id": user["referrer_id"]
        }
    })


# =========================
# REFERRAL INFO
# =========================

@app.route("/api/referral/<int:user_id>", methods=["GET"])
def referral_info(user_id):

    conn = db()

    user = conn.execute(
        "SELECT id FROM users WHERE id=?",
        (user_id,)
    ).fetchone()

    if not user:

        conn.close()

        return jsonify({
            "success": False,
            "error": "User not found"
        }), 404

    stats = conn.execute("""
        SELECT
            COUNT(*) AS total_referrals,
            COALESCE(SUM(bonus), 0) AS total_earned
        FROM referrals
        WHERE referrer_id=?
    """, (
        user_id,
    )).fetchone()

    referrals = conn.execute("""
        SELECT
            users.id,
            users.username,
            referrals.bonus,
            referrals.created_at
        FROM referrals

        JOIN users
        ON users.id = referrals.referred_id

        WHERE referrals.referrer_id=?

        ORDER BY referrals.id DESC
    """, (
        user_id,
    )).fetchall()

    conn.close()

    return jsonify({
        "success": True,
        "bonus_per_referral": REFERRAL_BONUS,
        "total_referrals": stats["total_referrals"],
        "total_earned": round(stats["total_earned"], 6),
        "referrals": [dict(row) for row in referrals]
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

    # First start bonus
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

    port = int(
        os.environ.get("PORT", 5050)
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
