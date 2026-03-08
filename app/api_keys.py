"""
ShieldPrompt — API Key Management System
Enterprise-grade: SQLite + Rate Limiting + Tiers
"""

import sqlite3
import secrets
import hashlib
from datetime import datetime, date
from functools import wraps
from flask import request, jsonify

DB_PATH = "shieldprompt.db"

# ── TIERS ─────────────────────────────────────────────────────────
TIERS = {
    "free":       { "daily_limit": 100,    "label": "Free",       "price": "₹0/month" },
    "pro":        { "daily_limit": 10000,  "label": "Pro",        "price": "₹999/month" },
    "enterprise": { "daily_limit": None,   "label": "Enterprise", "price": "Custom" },
}

# ── DATABASE SETUP ─────────────────────────────────────────────────
def init_db():
    """Initialize SQLite database with all tables."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # API Keys table
    c.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            key_hash    TEXT UNIQUE NOT NULL,
            key_prefix  TEXT NOT NULL,
            name        TEXT NOT NULL,
            email       TEXT NOT NULL,
            tier        TEXT NOT NULL DEFAULT 'free',
            is_active   INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT NOT NULL,
            last_used   TEXT
        )
    """)

    # Usage tracking table
    c.execute("""
        CREATE TABLE IF NOT EXISTS usage_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            key_hash    TEXT NOT NULL,
            date        TEXT NOT NULL,
            count       INTEGER NOT NULL DEFAULT 0,
            UNIQUE(key_hash, date)
        )
    """)

    # Request log table
    c.execute("""
        CREATE TABLE IF NOT EXISTS request_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            key_hash        TEXT NOT NULL,
            timestamp       TEXT NOT NULL,
            prompt_preview  TEXT,
            is_malicious    INTEGER,
            confidence      REAL,
            response_ms     REAL
        )
    """)

    conn.commit()
    conn.close()
    print("✅ Database initialized: shieldprompt.db")


# ── KEY GENERATION ─────────────────────────────────────────────────
def generate_api_key():
    """Generate a secure API key: sp_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"""
    raw = secrets.token_hex(32)
    key = f"sp_live_{raw}"
    return key

def hash_key(key: str) -> str:
    """Hash the API key for secure storage."""
    return hashlib.sha256(key.encode()).hexdigest()

def get_prefix(key: str) -> str:
    """Get first 12 chars for display: sp_live_xxxx..."""
    return key[:16] + "..."


# ── KEY OPERATIONS ─────────────────────────────────────────────────
def create_key(name: str, email: str, tier: str = "free") -> dict:
    """Create a new API key. Returns key (shown ONCE only)."""
    if tier not in TIERS:
        return {"error": f"Invalid tier. Choose: {list(TIERS.keys())}"}

    key = generate_api_key()
    key_hash = hash_key(key)
    prefix = get_prefix(key)
    now = datetime.utcnow().isoformat()

    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            INSERT INTO api_keys (key_hash, key_prefix, name, email, tier, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (key_hash, prefix, name, email, tier, now))
        conn.commit()
        conn.close()

        return {
            "success": True,
            "api_key": key,           # Show ONCE — never stored in plaintext
            "key_prefix": prefix,
            "name": name,
            "email": email,
            "tier": tier,
            "tier_label": TIERS[tier]["label"],
            "daily_limit": TIERS[tier]["daily_limit"],
            "price": TIERS[tier]["price"],
            "created_at": now,
            "warning": "⚠️  Save this key now — it will NOT be shown again!"
        }
    except sqlite3.IntegrityError:
        return {"error": "Key conflict. Please try again."}


def validate_key(key: str) -> dict:
    """Validate API key and check rate limits. Returns status dict."""
    if not key or not key.startswith("sp_live_"):
        return {"valid": False, "error": "Invalid API key format.", "code": 401}

    key_hash = hash_key(key)
    today = date.today().isoformat()

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Fetch key info
    c.execute("""
        SELECT key_hash, name, email, tier, is_active, key_prefix
        FROM api_keys WHERE key_hash = ?
    """, (key_hash,))
    row = c.fetchone()

    if not row:
        conn.close()
        return {"valid": False, "error": "API key not found.", "code": 401}

    key_hash_db, name, email, tier, is_active, prefix = row

    if not is_active:
        conn.close()
        return {"valid": False, "error": "API key is disabled.", "code": 403}

    # Rate limit check
    daily_limit = TIERS[tier]["daily_limit"]

    if daily_limit is not None:
        c.execute("""
            SELECT count FROM usage_log WHERE key_hash = ? AND date = ?
        """, (key_hash, today))
        usage_row = c.fetchone()
        current_usage = usage_row[0] if usage_row else 0

        if current_usage >= daily_limit:
            conn.close()
            return {
                "valid": False,
                "error": f"Daily rate limit exceeded ({daily_limit} req/day). Upgrade your plan.",
                "code": 429,
                "usage": current_usage,
                "limit": daily_limit,
                "tier": tier,
                "upgrade_url": "https://shieldprompt.in/pricing"
            }
    else:
        current_usage = None  # Enterprise = unlimited

    conn.close()
    return {
        "valid": True,
        "key_hash": key_hash,
        "name": name,
        "email": email,
        "tier": tier,
        "tier_label": TIERS[tier]["label"],
        "daily_limit": daily_limit,
        "usage_today": current_usage,
        "prefix": prefix
    }


def increment_usage(key_hash: str):
    """Increment daily usage counter for a key."""
    today = date.today().isoformat()
    now = datetime.utcnow().isoformat()

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Upsert usage count
    c.execute("""
        INSERT INTO usage_log (key_hash, date, count)
        VALUES (?, ?, 1)
        ON CONFLICT(key_hash, date) DO UPDATE SET count = count + 1
    """, (key_hash, today))

    # Update last_used
    c.execute("""
        UPDATE api_keys SET last_used = ? WHERE key_hash = ?
    """, (now, key_hash))

    conn.commit()
    conn.close()


def log_request(key_hash: str, prompt_preview: str, is_malicious: bool,
                confidence: float, response_ms: float):
    """Log individual request for analytics."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO request_log (key_hash, timestamp, prompt_preview, is_malicious, confidence, response_ms)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (key_hash, datetime.utcnow().isoformat(),
          prompt_preview[:80],  # 80 char max — privacy first
          int(is_malicious), confidence, response_ms))
    conn.commit()
    conn.close()


def get_key_stats(key: str) -> dict:
    """Get usage statistics for a key."""
    key_hash = hash_key(key)
    today = date.today().isoformat()

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT name, email, tier, created_at, last_used, key_prefix FROM api_keys WHERE key_hash = ?", (key_hash,))
    row = c.fetchone()
    if not row:
        conn.close()
        return {"error": "Key not found."}

    name, email, tier, created_at, last_used, prefix = row

    # Today's usage
    c.execute("SELECT count FROM usage_log WHERE key_hash = ? AND date = ?", (key_hash, today))
    today_row = c.fetchone()
    today_usage = today_row[0] if today_row else 0

    # Total usage
    c.execute("SELECT SUM(count) FROM usage_log WHERE key_hash = ?", (key_hash,))
    total_row = c.fetchone()
    total_usage = total_row[0] if total_row[0] else 0

    # Threats detected
    c.execute("SELECT COUNT(*) FROM request_log WHERE key_hash = ? AND is_malicious = 1", (key_hash,))
    threats = c.fetchone()[0]

    conn.close()

    daily_limit = TIERS[tier]["daily_limit"]
    return {
        "key_prefix": prefix,
        "name": name,
        "email": email,
        "tier": tier,
        "tier_label": TIERS[tier]["label"],
        "price": TIERS[tier]["price"],
        "daily_limit": daily_limit if daily_limit else "Unlimited",
        "usage_today": today_usage,
        "remaining_today": (daily_limit - today_usage) if daily_limit else "Unlimited",
        "total_requests": total_usage,
        "threats_detected": threats,
        "created_at": created_at,
        "last_used": last_used,
    }


def revoke_key(key: str) -> dict:
    """Deactivate an API key."""
    key_hash = hash_key(key)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE api_keys SET is_active = 0 WHERE key_hash = ?", (key_hash,))
    affected = c.rowcount
    conn.commit()
    conn.close()
    if affected:
        return {"success": True, "message": "API key revoked successfully."}
    return {"error": "Key not found."}


def list_all_keys() -> list:
    """Admin: list all keys (hashed, no plaintext)."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT key_prefix, name, email, tier, is_active, created_at, last_used
        FROM api_keys ORDER BY created_at DESC
    """)
    rows = c.fetchall()
    conn.close()
    return [
        {
            "key_prefix": r[0], "name": r[1], "email": r[2],
            "tier": r[3], "is_active": bool(r[4]),
            "created_at": r[5], "last_used": r[6]
        } for r in rows
    ]


# ── FLASK DECORATOR ────────────────────────────────────────────────
def require_api_key(f):
    """
    Flask decorator — add to any route to protect it.

    Usage:
        @app.route('/api/v1/check', methods=['POST'])
        @require_api_key
        def check_prompt():
            ...
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # Accept key from header OR query param
        key = request.headers.get("X-API-Key") or request.args.get("api_key")

        if not key:
            return jsonify({
                "error": "API key required.",
                "hint": "Pass key in header: X-API-Key: sp_live_...",
                "get_key": "https://shieldprompt.in/api-keys"
            }), 401

        result = validate_key(key)

        if not result["valid"]:
            return jsonify({
                "error": result["error"],
                "code": result.get("code", 401),
                "usage": result.get("usage"),
                "limit": result.get("limit"),
                "upgrade": result.get("upgrade_url")
            }), result.get("code", 401)

        # Attach key info to request context
        request.key_info = result
        return f(*args, **kwargs)

    return decorated


# ── FLASK ROUTES (add to app.py) ───────────────────────────────────
def register_key_routes(app):
    """Call this in app.py: register_key_routes(app)"""

    @app.route('/api/v1/keys/create', methods=['POST'])
    def create_api_key():
        """Create new API key."""
        data = request.get_json()
        if not data or not data.get('name') or not data.get('email'):
            return jsonify({"error": "name and email required."}), 400
        tier = data.get('tier', 'free')
        result = create_key(data['name'], data['email'], tier)
        if 'error' in result:
            return jsonify(result), 400
        return jsonify(result), 201

    @app.route('/api/v1/keys/stats', methods=['GET'])
    def key_stats():
        """Get usage stats for a key."""
        key = request.headers.get("X-API-Key") or request.args.get("api_key")
        if not key:
            return jsonify({"error": "API key required."}), 401
        return jsonify(get_key_stats(key))

    @app.route('/api/v1/keys/revoke', methods=['POST'])
    def revoke_api_key():
        """Revoke an API key."""
        key = request.headers.get("X-API-Key") or request.args.get("api_key")
        if not key:
            return jsonify({"error": "API key required."}), 401
        return jsonify(revoke_key(key))

    @app.route('/api/v1/admin/keys', methods=['GET'])
    def admin_list_keys():
        """Admin: list all keys."""
        admin_token = request.headers.get("X-Admin-Token")
        if admin_token != "shieldprompt_admin_2026":  # Change this!
            return jsonify({"error": "Unauthorized."}), 403
        return jsonify(list_all_keys())

    print("✅ API Key routes registered!")


# ── QUICK TEST ─────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "="*50)
    print("  ShieldPrompt — API Key System Test")
    print("="*50)

    init_db()

    # Create test keys
    print("\n📌 Creating Free tier key...")
    free = create_key("Test User", "test@example.com", "free")
    print(f"   Key: {free['api_key']}")
    print(f"   Tier: {free['tier_label']} | Limit: {free['daily_limit']} req/day")

    print("\n📌 Creating Pro tier key...")
    pro = create_key("Pro User", "pro@startup.com", "pro")
    print(f"   Key: {pro['api_key']}")
    print(f"   Tier: {pro['tier_label']} | Limit: {pro['daily_limit']} req/day | Price: {pro['price']}")

    print("\n📌 Creating Enterprise key...")
    ent = create_key("BigCorp India", "cto@bigcorp.in", "enterprise")
    print(f"   Key: {ent['api_key']}")
    print(f"   Tier: {ent['tier_label']} | Limit: Unlimited | Price: {ent['price']}")

    # Validate
    print("\n🔍 Validating free key...")
    v = validate_key(free['api_key'])
    print(f"   Valid: {v['valid']} | Tier: {v['tier']} | Name: {v['name']}")

    # Increment usage
    increment_usage(v['key_hash'])
    increment_usage(v['key_hash'])
    increment_usage(v['key_hash'])

    # Stats
    print("\n📊 Key stats:")
    stats = get_key_stats(free['api_key'])
    print(f"   Usage today: {stats['usage_today']}/{stats['daily_limit']}")
    print(f"   Remaining: {stats['remaining_today']}")

    print("\n✅ All tests passed!")
    print("="*50)
    print("\nTo integrate in app.py:")
    print("  from api_keys import init_db, register_key_routes, require_api_key")
    print("  init_db()")
    print("  register_key_routes(app)")
    print("  Then add @require_api_key to protected routes!")
    print("="*50 + "\n")