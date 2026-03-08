"""
ShieldPrompt — Auth Backend (v2 — Production Ready)
JWT login, register, token refresh, password change
"""

import os
import sqlite3
import hashlib
import secrets
from datetime import datetime, timedelta
from functools import wraps

import jwt
from flask import request, jsonify, render_template
from dotenv import load_dotenv

load_dotenv()

# ── CONFIG ─────────────────────────────────────────────────────────
DB_PATH    = os.getenv("DB_PATH", "shieldprompt.db")
JWT_SECRET = os.getenv("JWT_SECRET", "shieldprompt_jwt_fallback_change_in_prod")
JWT_ALGO   = "HS256"
ACCESS_EXP = 7     # days — access token
REFRESH_EXP = 30   # days — refresh token

SALT = "shieldprompt_salt_v2"

# ── HELPERS ────────────────────────────────────────────────────────
def _hash(password: str) -> str:
    return hashlib.sha256(f"{SALT}:{password}".encode()).hexdigest()

def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _make_token(user_id, email, plan, expiry_days) -> str:
    return jwt.encode({
        "user_id": user_id,
        "email":   email,
        "plan":    plan,
        "exp":     datetime.utcnow() + timedelta(days=expiry_days),
        "iat":     datetime.utcnow(),
        "jti":     secrets.token_hex(8),   # unique token ID
    }, JWT_SECRET, algorithm=JWT_ALGO)

def _verify_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.ExpiredSignatureError:
        return {"error": "Session expired. Please log in again.", "code": "TOKEN_EXPIRED"}
    except jwt.InvalidTokenError as e:
        return {"error": f"Invalid session: {str(e)}", "code": "TOKEN_INVALID"}

def _token_from_request() -> str | None:
    hdr = request.headers.get("Authorization", "")
    if hdr.startswith("Bearer "):
        return hdr[7:]
    return request.cookies.get("sp_token") or request.headers.get("X-Auth-Token")

# ── REQUIRE AUTH DECORATOR ─────────────────────────────────────────
def require_auth(f):
    """Protect any Flask route with JWT auth."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _token_from_request()
        if not token:
            return jsonify({"error": "Authentication required.", "code": "NO_TOKEN"}), 401
        payload = _verify_token(token)
        if "error" in payload:
            return jsonify(payload), 401
        request.user = payload
        return f(*args, **kwargs)
    return decorated

# ── DB INIT ────────────────────────────────────────────────────────
def init_auth_db():
    """Create users table if not exists."""
    conn = _db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            email        TEXT UNIQUE NOT NULL,
            password     TEXT NOT NULL,
            company      TEXT DEFAULT '',
            plan         TEXT NOT NULL DEFAULT 'free',
            is_active    INTEGER NOT NULL DEFAULT 1,
            created_at   TEXT NOT NULL,
            last_login   TEXT,
            avatar_color TEXT DEFAULT '#1a56db'
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS refresh_tokens (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            token_hash TEXT UNIQUE NOT NULL,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    conn.commit()
    conn.close()
    print("✅ Auth DB initialized!")

# ── REGISTER ───────────────────────────────────────────────────────
def register_user(name, email, password, company="", plan="free") -> dict:
    # Validation
    name = name.strip()
    email = email.strip().lower()
    if not name:
        return {"error": "Name is required."}
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        return {"error": "Please enter a valid email address."}
    if len(password) < 8:
        return {"error": "Password must be at least 8 characters."}
    if not any(c.isupper() for c in password):
        return {"error": "Password must contain at least one uppercase letter."}
    if not any(c.isdigit() for c in password):
        return {"error": "Password must contain at least one number."}

    now = datetime.utcnow().isoformat()
    conn = _db()
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO users (name, email, password, company, plan, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, email, _hash(password), company.strip(), plan, now))
        conn.commit()
        uid = c.lastrowid

        # Auto-create free API key
        try:
            from api_keys import create_key
            key_result = create_key(name=name, email=email, tier=plan)
            api_key = key_result.get("api_key")
        except Exception:
            api_key = None

        access  = _make_token(uid, email, plan, ACCESS_EXP)
        refresh = _make_token(uid, email, plan, REFRESH_EXP)
        _store_refresh_token(conn, uid, refresh)
        conn.close()

        return {
            "success":       True,
            "access_token":  access,
            "refresh_token": refresh,
            "expires_in":    ACCESS_EXP * 86400,
            "api_key":       api_key,
            "api_key_note":  "Save this key — it won't be shown again!" if api_key else None,
            "user": {
                "id":      uid,
                "name":    name,
                "email":   email,
                "plan":    plan,
                "company": company,
            },
            "message": "Account created! Welcome to ShieldPrompt 🛡️",
            "redirect": "/payment?plan=pro" if plan == "pro" else "/dashboard",
        }
    except sqlite3.IntegrityError:
        conn.close()
        return {"error": "An account with this email already exists. Please log in."}

# ── LOGIN ──────────────────────────────────────────────────────────
def login_user(email, password) -> dict:
    email = email.strip().lower()
    if not email or not password:
        return {"error": "Email and password are required."}

    conn = _db()
    c = conn.cursor()
    c.execute("""
        SELECT id, name, email, plan, company, is_active
        FROM users WHERE email=? AND password=?
    """, (email, _hash(password)))
    user = c.fetchone()

    if not user:
        conn.close()
        return {"error": "Incorrect email or password. Please try again."}
    if not user["is_active"]:
        conn.close()
        return {"error": "Your account has been suspended. Contact support@shieldprompt.in"}

    # Update last_login
    c.execute("UPDATE users SET last_login=? WHERE id=?",
              (datetime.utcnow().isoformat(), user["id"]))
    conn.commit()

    access  = _make_token(user["id"], user["email"], user["plan"], ACCESS_EXP)
    refresh = _make_token(user["id"], user["email"], user["plan"], REFRESH_EXP)
    _store_refresh_token(conn, user["id"], refresh)
    conn.close()

    return {
        "success":       True,
        "access_token":  access,
        "refresh_token": refresh,
        "expires_in":    ACCESS_EXP * 86400,
        "user": {
            "id":      user["id"],
            "name":    user["name"],
            "email":   user["email"],
            "plan":    user["plan"],
            "company": user["company"],
        },
        "redirect": "/dashboard",
    }

# ── REFRESH TOKEN ──────────────────────────────────────────────────
def refresh_access_token(refresh_token: str) -> dict:
    payload = _verify_token(refresh_token)
    if "error" in payload:
        return payload

    token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
    conn = _db()
    c = conn.cursor()
    c.execute("SELECT * FROM refresh_tokens WHERE token_hash=?", (token_hash,))
    row = c.fetchone()
    if not row or datetime.fromisoformat(row["expires_at"]) < datetime.utcnow():
        conn.close()
        return {"error": "Refresh token expired. Please log in again.", "code": "REFRESH_EXPIRED"}

    new_access = _make_token(payload["user_id"], payload["email"], payload["plan"], ACCESS_EXP)
    conn.close()
    return {"success": True, "access_token": new_access, "expires_in": ACCESS_EXP * 86400}

# ── GET PROFILE ────────────────────────────────────────────────────
def get_profile(email: str) -> dict:
    conn = _db()
    c = conn.cursor()
    c.execute("SELECT id,name,email,company,plan,created_at,last_login FROM users WHERE email=?", (email,))
    user = c.fetchone()
    if not user:
        conn.close()
        return {"error": "User not found."}

    c.execute("SELECT key_prefix,tier,is_active,created_at,last_used FROM api_keys WHERE email=? AND is_active=1", (email,))
    keys = [dict(k) for k in c.fetchall()]

    today = datetime.utcnow().date().isoformat()
    c.execute("""
        SELECT SUM(ul.count) FROM usage_log ul
        JOIN api_keys ak ON ul.key_hash = ak.key_hash
        WHERE ak.email=? AND ul.date=?
    """, (email, today))
    usage_today = c.fetchone()[0] or 0

    # Daily limit based on plan
    limits = {"free": 100, "pro": 10000, "enterprise": 999999}
    plan = user["plan"]
    conn.close()
    return {
        "user": dict(user),
        "api_keys": keys,
        "usage_today": usage_today,
        "daily_limit": limits.get(plan, 100),
        "usage_pct": round(usage_today / limits.get(plan, 100) * 100, 1),
    }

# ── CHANGE PASSWORD ────────────────────────────────────────────────
def change_password(email: str, old_pass: str, new_pass: str) -> dict:
    if len(new_pass) < 8:
        return {"error": "New password must be at least 8 characters."}
    conn = _db()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE email=? AND password=?", (email, _hash(old_pass)))
    if not c.fetchone():
        conn.close()
        return {"error": "Current password is incorrect."}
    c.execute("UPDATE users SET password=? WHERE email=?", (_hash(new_pass), email))
    # Invalidate all refresh tokens (force re-login)
    c.execute("DELETE FROM refresh_tokens WHERE user_id=(SELECT id FROM users WHERE email=?)", (email,))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Password updated. Please log in again."}

# ── LOGOUT ─────────────────────────────────────────────────────────
def logout_user(email: str, refresh_token: str = None) -> dict:
    conn = _db()
    c = conn.cursor()
    if refresh_token:
        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        c.execute("DELETE FROM refresh_tokens WHERE token_hash=?", (token_hash,))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Logged out successfully."}

# ── INTERNAL HELPER ────────────────────────────────────────────────
def _store_refresh_token(conn, user_id: int, token: str):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires_at = (datetime.utcnow() + timedelta(days=REFRESH_EXP)).isoformat()
    conn.execute("""
        INSERT OR REPLACE INTO refresh_tokens (user_id, token_hash, expires_at, created_at)
        VALUES (?, ?, ?, ?)
    """, (user_id, token_hash, expires_at, datetime.utcnow().isoformat()))

# ── FLASK ROUTES ───────────────────────────────────────────────────
def register_auth_routes(app):

    @app.route('/login')
    @app.route('/register')
    def auth_page():
        return render_template('auth.html')

    @app.route('/api/v1/auth/register', methods=['POST'])
    def api_register():
        d = request.get_json() or {}
        # Support "name" or "first_name + last_name"
        name = d.get('name') or f"{d.get('first_name','')} {d.get('last_name','')}".strip()
        result = register_user(
            name=name,
            email=d.get('email', ''),
            password=d.get('password', ''),
            company=d.get('company', ''),
            plan=d.get('plan', 'free'),
        )
        if 'error' in result:
            return jsonify(result), 400
        return jsonify(result), 201

    @app.route('/api/v1/auth/login', methods=['POST'])
    def api_login():
        d = request.get_json() or {}
        result = login_user(d.get('email', ''), d.get('password', ''))
        if 'error' in result:
            return jsonify(result), 401
        return jsonify(result)

    @app.route('/api/v1/auth/refresh', methods=['POST'])
    def api_refresh():
        d = request.get_json() or {}
        rt = d.get('refresh_token') or _token_from_request()
        if not rt:
            return jsonify({"error": "Refresh token required."}), 400
        return jsonify(refresh_access_token(rt))

    @app.route('/api/v1/auth/profile', methods=['GET'])
    @require_auth
    def api_profile():
        return jsonify(get_profile(request.user['email']))

    @app.route('/api/v1/auth/verify', methods=['GET'])
    @require_auth
    def api_verify():
        return jsonify({"valid": True, "user": request.user})

    @app.route('/api/v1/auth/change-password', methods=['POST'])
    @require_auth
    def api_change_password():
        d = request.get_json() or {}
        return jsonify(change_password(
            request.user['email'],
            d.get('old_password', ''),
            d.get('new_password', ''),
        ))

    @app.route('/api/v1/auth/logout', methods=['POST'])
    @require_auth
    def api_logout():
        d = request.get_json() or {}
        return jsonify(logout_user(request.user['email'], d.get('refresh_token')))

    print("✅ Auth routes registered!")

if __name__ == "__main__":
    init_auth_db()
    print("\n--- Testing Register ---")
    r = register_user("Kamran Alam", "kamran@shieldprompt.in", "Test@1234", "Amity University", "free")
    print("Register:", r.get('message') or r.get('error'))

    print("\n--- Testing Login ---")
    l = login_user("kamran@shieldprompt.in", "Test@1234")
    print("Login:", "✅ Success" if l.get('success') else l.get('error'))

    print("\n--- Testing Token Verify ---")
    p = _verify_token(l.get('access_token',''))
    print("Token:", "✅ Valid for", p.get('email') if 'email' in p else p.get('error'))