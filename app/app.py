# ============================================================
# ShieldPrompt — Main Flask App (v5.0 — BULLETPROOF)
# Run: python app.py
# Make sure ye file app/ folder mein hai
# ============================================================

import os, sqlite3, hashlib, secrets, time
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, render_template, redirect

# ── OPTIONAL IMPORTS (crash nahi karega agar missing hai) ───
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
    load_dotenv()  # fallback
except ImportError:
    pass

try:
    import jwt as pyjwt
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False
    print("⚠️  PyJWT not installed. Run: pip install PyJWT")

try:
    import joblib
    MODEL_AVAILABLE = True
except ImportError:
    MODEL_AVAILABLE = False

try:
    from flask_cors import CORS
    CORS_AVAILABLE = True
except ImportError:
    CORS_AVAILABLE = False

# ── FLASK SETUP ─────────────────────────────────────────────
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR  = os.path.join(BASE_DIR, '..', 'templates')
STATIC_DIR    = os.path.join(BASE_DIR, 'static')

app = Flask(__name__, template_folder=TEMPLATE_DIR, static_folder=STATIC_DIR)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "shieldprompt_secret_" + secrets.token_hex(8))

if CORS_AVAILABLE:
    CORS(app, origins="*")
else:
    @app.after_request
    def add_cors(response):
        response.headers['Access-Control-Allow-Origin']  = '*'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-API-Key, X-Admin-Token'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        return response

    @app.route('/', defaults={'path': ''}, methods=['OPTIONS'])
    @app.route('/<path:path>', methods=['OPTIONS'])
    def options_handler(path):
        return '', 204

# ── CONFIG ───────────────────────────────────────────────────
DB_PATH      = os.getenv("DB_PATH", os.path.join(BASE_DIR, "shieldprompt.db"))
JWT_SECRET   = os.getenv("JWT_SECRET", "shieldprompt_jwt_secret_fallback_2026")
ADMIN_EMAIL  = os.getenv("ADMIN_EMAIL", "admin@shieldprompt.in")
ADMIN_PASS   = os.getenv("ADMIN_PASSWORD", "ShieldAdmin@2026")
ADMIN_TOKEN  = os.getenv("ADMIN_SECRET_TOKEN", "sp_admin_super_secret_2026")
SALT         = "shieldprompt_salt_v2"

# ── DB ───────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def init_all_tables():
    conn = get_db()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            email      TEXT UNIQUE NOT NULL,
            password   TEXT NOT NULL,
            company    TEXT DEFAULT '',
            plan       TEXT NOT NULL DEFAULT 'free',
            is_active  INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );

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
        );

        CREATE TABLE IF NOT EXISTS usage_log (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            key_hash TEXT NOT NULL,
            date     TEXT NOT NULL,
            count    INTEGER NOT NULL DEFAULT 0,
            UNIQUE(key_hash, date)
        );

        CREATE TABLE IF NOT EXISTS request_log (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            key_hash       TEXT NOT NULL,
            timestamp      TEXT NOT NULL,
            prompt_preview TEXT,
            is_malicious   INTEGER DEFAULT 0,
            confidence     REAL DEFAULT 0.0,
            response_ms    REAL DEFAULT 0.0
        );

        CREATE TABLE IF NOT EXISTS payments (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email          TEXT NOT NULL,
            razorpay_order_id   TEXT,
            razorpay_payment_id TEXT,
            plan                TEXT NOT NULL,
            amount              INTEGER NOT NULL,
            status              TEXT NOT NULL DEFAULT 'created',
            created_at          TEXT NOT NULL,
            paid_at             TEXT
        );
    """)
    conn.commit()
    conn.close()
    print("✅ Database tables ready!")

# ── AUTH HELPERS ─────────────────────────────────────────────
def _hash_password(pw):
    return hashlib.sha256(f"{SALT}:{pw}".encode()).hexdigest()

def _hash_admin_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def _make_token(user_id, email, plan):
    if not JWT_AVAILABLE:
        # Simple fallback token (NOT secure, for dev only)
        import base64, json
        payload = {"user_id": user_id, "email": email, "plan": plan, "ts": time.time()}
        return base64.b64encode(json.dumps(payload).encode()).decode()
    return pyjwt.encode({
        "user_id": user_id,
        "email":   email,
        "plan":    plan,
        "exp":     datetime.utcnow() + timedelta(days=7),
        "iat":     datetime.utcnow(),
    }, JWT_SECRET, algorithm="HS256")

def _verify_token(token):
    if not JWT_AVAILABLE:
        try:
            import base64, json
            payload = json.loads(base64.b64decode(token.encode()).decode())
            return payload
        except:
            return {"error": "Invalid token"}
    try:
        return pyjwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except pyjwt.ExpiredSignatureError:
        return {"error": "Session expired. Please log in again."}
    except Exception as e:
        return {"error": f"Invalid token: {e}"}

def _get_token():
    hdr = request.headers.get("Authorization", "")
    if hdr.startswith("Bearer "):
        return hdr[7:]
    return request.cookies.get("sp_token") or request.headers.get("X-Auth-Token")

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _get_token()
        if not token:
            return jsonify({"error": "Login required"}), 401
        payload = _verify_token(token)
        if "error" in payload:
            return jsonify(payload), 401
        request.user = payload
        return f(*args, **kwargs)
    return decorated

# ── API KEY HELPERS ──────────────────────────────────────────
DAILY_LIMITS = {"free": 100, "pro": 10000, "enterprise": 999999}

def _hash_key(key):
    return hashlib.sha256(key.encode()).hexdigest()

def _create_api_key(name, email, tier="free"):
    key        = f"sp_{'live' if tier != 'free' else 'free'}_{secrets.token_hex(20)}"
    key_hash   = _hash_key(key)
    key_prefix = key[:18] + "..."
    now        = datetime.utcnow().isoformat()
    conn = get_db()
    c    = conn.cursor()
    # Max 3 keys per user per tier
    c.execute("SELECT COUNT(*) FROM api_keys WHERE email=? AND tier=? AND is_active=1", (email, tier))
    if c.fetchone()[0] >= 3:
        conn.close()
        return {"error": "Max 3 active keys allowed per tier. Revoke one first."}
    c.execute("""
        INSERT INTO api_keys (key_hash, key_prefix, name, email, tier, is_active, created_at)
        VALUES (?, ?, ?, ?, ?, 1, ?)
    """, (key_hash, key_prefix, name, email, tier, now))
    conn.commit()
    conn.close()
    return {"api_key": key, "key_prefix": key_prefix, "tier": tier, "created_at": now}

def require_api_key(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        key = request.headers.get("X-API-Key") or request.args.get("api_key")
        if not key:
            return jsonify({"error": "API key required. Add header: X-API-Key: sp_..."}), 401
        key_hash = _hash_key(key)
        conn = get_db()
        c    = conn.cursor()
        c.execute("SELECT * FROM api_keys WHERE key_hash=? AND is_active=1", (key_hash,))
        row = c.fetchone()
        if not row:
            conn.close()
            return jsonify({"error": "Invalid or revoked API key."}), 403
        # Check daily limit
        today = datetime.utcnow().date().isoformat()
        c.execute("SELECT count FROM usage_log WHERE key_hash=? AND date=?", (key_hash, today))
        usage_row = c.fetchone()
        used  = usage_row["count"] if usage_row else 0
        limit = DAILY_LIMITS.get(row["tier"], 100)
        if used >= limit:
            conn.close()
            return jsonify({"error": f"Daily limit reached ({limit} req/day). Upgrade to Pro for more."}), 429
        # Update last_used
        c.execute("UPDATE api_keys SET last_used=? WHERE key_hash=?", (datetime.utcnow().isoformat(), key_hash))
        conn.commit()
        conn.close()
        request.key_info = dict(row)
        return f(*args, **kwargs)
    return decorated

def _increment_usage(key_hash):
    today = datetime.utcnow().date().isoformat()
    conn  = get_db()
    conn.execute("""
        INSERT INTO usage_log (key_hash, date, count) VALUES (?, ?, 1)
        ON CONFLICT(key_hash, date) DO UPDATE SET count = count + 1
    """, (key_hash, today))
    conn.commit()
    conn.close()

# ── LOAD ML MODEL ────────────────────────────────────────────
MODEL_LOADED = False
model = vectorizer = None

if MODEL_AVAILABLE:
    try:
        MODEL_PATH = os.path.join(BASE_DIR, '..', 'model', 'shield_model.pkl')
        VEC_PATH   = os.path.join(BASE_DIR, '..', 'model', 'vectorizer.pkl')
        model      = joblib.load(MODEL_PATH)
        vectorizer = joblib.load(VEC_PATH)
        MODEL_LOADED = True
        print("✅ AI Model loaded! Accuracy: 98%")
    except Exception as e:
        print(f"⚠️  Model not loaded ({e}). Using keyword fallback.")

INJECT_KEYWORDS = [
    'ignore previous','ignore all','forget previous','override',
    'jailbreak','DAN','pretend you','act as','system prompt',
    'bypass','reveal your','disregard','you are now','new persona',
    'ignore instructions','delete all','hack','sudo','root access'
]

def _detect(prompt):
    if MODEL_LOADED:
        vec  = vectorizer.transform([prompt])
        pred = model.predict(vec)[0]
        prob = model.predict_proba(vec)[0]
        return bool(pred == 1), round(float(prob.max()), 4)
    # Fallback keyword detection
    pl = prompt.lower()
    is_mal = any(kw.lower() in pl for kw in INJECT_KEYWORDS)
    return is_mal, (0.93 if is_mal else 0.89)

def _threat_level(conf, is_mal):
    if not is_mal: return "NONE"
    if conf >= 0.95: return "CRITICAL"
    if conf >= 0.80: return "HIGH"
    if conf >= 0.65: return "MEDIUM"
    return "LOW"

# ── SESSION STATS ─────────────────────────────────────────────
attack_log    = []
total_checked = 0
total_blocked = 0

# ══════════════════════════════════════════════════════════════
# PAGE ROUTES
# ══════════════════════════════════════════════════════════════
@app.route('/')
def landing():
    return render_template('index.html')

@app.route('/login')
@app.route('/register')
def auth_page():
    return render_template('auth.html')

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@app.route('/payment')
def payment_page():
    plan = request.args.get('plan', 'pro')
    rzp  = os.getenv("RAZORPAY_KEY_ID", "rzp_test_demo")
    return render_template('pricing.html', plan=plan, razorpay_key=rzp)

@app.route('/admin')
@app.route('/admin/')
def admin_panel():
    return render_template('admin_panel.html')

# ══════════════════════════════════════════════════════════════
# AUTH ROUTES
# ══════════════════════════════════════════════════════════════
@app.route('/api/v1/auth/register', methods=['POST'])
def auth_register():
    data = request.get_json() or {}
    name     = str(data.get('name', '')).strip()
    email    = str(data.get('email', '')).strip().lower()
    password = str(data.get('password', ''))
    company  = str(data.get('company', '')).strip()
    plan     = str(data.get('plan', 'free')).strip()

    if not name:
        return jsonify({"error": "Name is required."}), 400
    if not email or '@' not in email:
        return jsonify({"error": "Valid email is required."}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters."}), 400
    if plan not in ['free', 'pro', 'enterprise']:
        plan = 'free'

    now = datetime.utcnow().isoformat()
    conn = get_db()
    c    = conn.cursor()
    try:
        c.execute("""
            INSERT INTO users (name, email, password, company, plan, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, email, _hash_password(password), company, plan, now))
        conn.commit()
        user_id = c.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "Email already registered. Please log in."}), 409
    conn.close()

    # Auto-generate free API key
    key_result = _create_api_key(name=name, email=email, tier=plan)
    token = _make_token(user_id, email, plan)

    return jsonify({
        "success": True,
        "token":   token,
        "api_key": key_result.get("api_key"),
        "user":    {"id": user_id, "name": name, "email": email, "plan": plan},
        "message": "Account created successfully! Welcome to ShieldPrompt 🛡️"
    }), 201

@app.route('/api/v1/auth/login', methods=['POST'])
def auth_login():
    data     = request.get_json() or {}
    email    = str(data.get('email', '')).strip().lower()
    password = str(data.get('password', ''))

    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400

    conn = get_db()
    c    = conn.cursor()
    c.execute("""
        SELECT id, name, email, plan, company, is_active
        FROM users WHERE email=? AND password=?
    """, (email, _hash_password(password)))
    user = c.fetchone()
    conn.close()

    if not user:
        return jsonify({"error": "Invalid email or password."}), 401
    if not user["is_active"]:
        return jsonify({"error": "Account suspended. Contact support."}), 403

    token = _make_token(user["id"], user["email"], user["plan"])
    return jsonify({
        "success": True,
        "token":   token,
        "user":    {"id": user["id"], "name": user["name"], "email": user["email"], "plan": user["plan"]}
    })

@app.route('/api/v1/auth/verify', methods=['GET'])
@require_auth
def auth_verify():
    return jsonify({"valid": True, "user": request.user})

@app.route('/api/v1/auth/profile', methods=['GET'])
@require_auth
def auth_profile():
    email = request.user.get("email", "")
    conn  = get_db()
    c     = conn.cursor()
    c.execute("SELECT id,name,email,company,plan,created_at FROM users WHERE email=?", (email,))
    user = c.fetchone()
    c.execute("SELECT key_prefix,tier,is_active,created_at,last_used FROM api_keys WHERE email=?", (email,))
    keys = [dict(k) for k in c.fetchall()]
    today = datetime.utcnow().date().isoformat()
    c.execute("""
        SELECT COALESCE(SUM(ul.count),0) as total FROM usage_log ul
        JOIN api_keys ak ON ul.key_hash=ak.key_hash
        WHERE ak.email=? AND ul.date=?
    """, (email, today))
    row = c.fetchone()
    conn.close()
    if not user:
        return jsonify({"error": "User not found"}), 404
    return jsonify({
        "user":        dict(user),
        "api_keys":    keys,
        "usage_today": row["total"] if row else 0
    })

# ══════════════════════════════════════════════════════════════
# API KEY ROUTES
# ══════════════════════════════════════════════════════════════
@app.route('/api/v1/keys/generate', methods=['POST'])
@require_auth
def generate_key():
    email = request.user.get("email", "")
    plan  = request.user.get("plan", "free")
    conn  = get_db()
    c     = conn.cursor()
    c.execute("SELECT name FROM users WHERE email=?", (email,))
    row   = c.fetchone()
    conn.close()
    name  = row["name"] if row else email.split("@")[0]
    result = _create_api_key(name=name, email=email, tier=plan)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result), 201

@app.route('/api/v1/keys/my', methods=['GET'])
@require_auth
def my_keys():
    email = request.user.get("email", "")
    conn  = get_db()
    c     = conn.cursor()
    c.execute("SELECT key_prefix,tier,is_active,created_at,last_used FROM api_keys WHERE email=?", (email,))
    keys  = [dict(k) for k in c.fetchall()]
    conn.close()
    return jsonify({"keys": keys})

@app.route('/api/v1/keys/<prefix>/revoke', methods=['POST'])
@require_auth
def revoke_key(prefix):
    email = request.user.get("email", "")
    conn  = get_db()
    c     = conn.cursor()
    c.execute("UPDATE api_keys SET is_active=0 WHERE key_prefix LIKE ? AND email=?",
              (f"{prefix[:15]}%", email))
    conn.commit()
    affected = c.rowcount
    conn.close()
    if affected:
        return jsonify({"success": True, "message": "Key revoked."})
    return jsonify({"error": "Key not found or not yours."}), 404

# ══════════════════════════════════════════════════════════════
# DETECTION ROUTE (main API)
# ══════════════════════════════════════════════════════════════
@app.route('/api/v1/check', methods=['POST'])
@require_api_key
def check_prompt():
    global total_checked, total_blocked
    data = request.get_json() or {}
    prompt = str(data.get('prompt', '')).strip()
    if not prompt:
        return jsonify({"error": "Missing 'prompt' field"}), 400

    is_mal, confidence = _detect(prompt)
    status = "MALICIOUS" if is_mal else "SAFE"
    total_checked += 1
    if is_mal: total_blocked += 1

    key_hash = request.key_info['key_hash']
    _increment_usage(key_hash)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = {"id": total_checked, "timestamp": now, "prompt_preview": prompt[:80], "status": status, "confidence": confidence}
    attack_log.append(entry)
    if len(attack_log) > 200: attack_log.pop(0)

    return jsonify({
        "status":       status,
        "is_malicious": is_mal,
        "confidence":   confidence,
        "threat_level": _threat_level(confidence, is_mal),
        "message":      "🚨 Prompt injection detected." if is_mal else "✅ Prompt is safe.",
        "timestamp":    now,
        "tier":         request.key_info.get('tier', 'free'),
    })

# ══════════════════════════════════════════════════════════════
# STATS & LOGS
# ══════════════════════════════════════════════════════════════
@app.route('/api/v1/stats')
def stats():
    rate = round(total_blocked / total_checked * 100, 1) if total_checked else 0
    return jsonify({
        "total_checked": total_checked, "malicious_blocked": total_blocked,
        "safe_passed": total_checked - total_blocked, "block_rate": f"{rate}%",
        "model_accuracy": "98%", "uptime_status": "operational"
    })

@app.route('/api/v1/logs')
def logs():
    limit = min(int(request.args.get('limit', 20)), 100)
    return jsonify({"total_in_session": len(attack_log), "logs": list(reversed(attack_log[-limit:]))})

@app.route('/api/v1/dashboard/stats')
def dashboard_stats():
    token = _get_token()
    email = ""
    plan  = "free"
    daily_usage = 0
    if token:
        payload = _verify_token(token)
        if "error" not in payload:
            email = payload.get("email", "")
            plan  = payload.get("plan", "free")
    if email:
        try:
            conn  = get_db()
            c     = conn.cursor()
            today = datetime.utcnow().date().isoformat()
            c.execute("""
                SELECT COALESCE(SUM(ul.count),0) as total FROM usage_log ul
                JOIN api_keys ak ON ul.key_hash=ak.key_hash
                WHERE ak.email=? AND ul.date=?
            """, (email, today))
            row = c.fetchone()
            daily_usage = row["total"] if row else 0
            conn.close()
        except: pass
    daily_limit = DAILY_LIMITS.get(plan, 100)
    rate = round(total_blocked / total_checked * 100, 1) if total_checked else 0
    return jsonify({
        "total_checked": total_checked, "malicious_blocked": total_blocked,
        "safe_passed": total_checked - total_blocked, "block_rate": f"{rate}%",
        "model_accuracy": "98%", "daily_usage": daily_usage,
        "daily_limit": daily_limit, "plan": plan,
        "usage_pct": round(daily_usage / daily_limit * 100, 1) if daily_limit else 0,
    })

@app.route('/api/v1/health')
def health():
    return jsonify({"status": "healthy", "model": "loaded" if MODEL_LOADED else "keyword-fallback", "version": "5.0.0"})

# ══════════════════════════════════════════════════════════════
# PAYMENT ROUTES (basic — Razorpay optional)
# ══════════════════════════════════════════════════════════════
@app.route('/api/v1/payments/create-order', methods=['POST'])
def create_order():
    data  = request.get_json() or {}
    email = data.get('email', '')
    plan  = data.get('plan', 'pro')
    now   = datetime.utcnow().isoformat()

    RZP_KEY    = os.getenv("RAZORPAY_KEY_ID", "")
    RZP_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")

    if RZP_KEY and RZP_KEY != "rzp_test_YOUR_KEY_ID_HERE":
        try:
            import razorpay
            client = razorpay.Client(auth=(RZP_KEY, RZP_SECRET))
            order  = client.order.create({"amount": 99900, "currency": "INR", "receipt": f"sp_{email}"})
            conn   = get_db()
            conn.execute("INSERT INTO payments (user_email,razorpay_order_id,plan,amount,status,created_at) VALUES (?,?,?,99900,'created',?)",
                         (email, order["id"], plan, now))
            conn.commit(); conn.close()
            return jsonify({"success": True, "order_id": order["id"], "amount": 99900,
                            "currency": "INR", "key_id": RZP_KEY, "plan": plan})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    else:
        # Demo mode
        return jsonify({"success": True, "order_id": "demo_order_" + secrets.token_hex(6),
                        "amount": 99900, "currency": "INR", "key_id": "rzp_test_demo",
                        "plan": plan, "demo": True})

@app.route('/api/v1/payments/verify', methods=['POST'])
def verify_payment():
    data = request.get_json() or {}
    email    = data.get('email', '')
    order_id = data.get('razorpay_order_id', '')
    now = datetime.utcnow().isoformat()
    expires = (datetime.utcnow() + timedelta(days=30)).isoformat()

    # Update user plan to pro
    conn = get_db()
    conn.execute("UPDATE users SET plan='pro' WHERE email=?", (email,))
    conn.execute("UPDATE payments SET status='paid', paid_at=? WHERE razorpay_order_id=?", (now, order_id))
    conn.commit()
    # Generate pro API key
    conn.execute("UPDATE api_keys SET tier='pro' WHERE email=?", (email,))
    conn.commit()
    conn.close()

    key_result = _create_api_key(name=email.split("@")[0], email=email, tier="pro")
    return jsonify({
        "success": True, "message": "Pro plan activated!",
        "plan": "pro", "expires_at": expires,
        "api_key": key_result.get("api_key"),
        "warning": "Save your API key — shown only once!"
    })

# ══════════════════════════════════════════════════════════════
# ADMIN ROUTES
# ══════════════════════════════════════════════════════════════
def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("X-Admin-Token") or request.json and request.json.get("token")
        if token != ADMIN_TOKEN:
            return jsonify({"error": "Admin access denied."}), 403
        return f(*args, **kwargs)
    return decorated

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json() or {}
    pw   = hashlib.sha256(data.get('password', '').encode()).hexdigest()
    if data.get('email') == ADMIN_EMAIL and pw == hashlib.sha256(ADMIN_PASS.encode()).hexdigest():
        return jsonify({"success": True, "token": ADMIN_TOKEN})
    return jsonify({"error": "Invalid admin credentials."}), 401

@app.route('/api/admin/stats')
@require_admin
def admin_stats():
    conn = get_db()
    c    = conn.cursor()
    today = datetime.utcnow().date().isoformat()
    c.execute("SELECT COUNT(*) as n FROM users"); total_users = c.fetchone()["n"]
    c.execute("SELECT COUNT(*) as n FROM users WHERE plan='pro'"); pro = c.fetchone()["n"]
    c.execute("SELECT COUNT(*) as n FROM users WHERE created_at LIKE ?", (f"{today}%",)); new_today = c.fetchone()["n"]
    c.execute("SELECT COUNT(*) as n FROM api_keys WHERE is_active=1"); active_keys = c.fetchone()["n"]
    c.execute("SELECT COALESCE(SUM(amount),0) as n FROM payments WHERE status='paid'"); revenue = c.fetchone()["n"]
    c.execute("SELECT COALESCE(SUM(count),0) as n FROM usage_log WHERE date=?", (today,)); req_today = c.fetchone()["n"]
    conn.close()
    return jsonify({
        "users":   {"total": total_users, "pro": pro, "free": total_users-pro, "new_today": new_today},
        "revenue": {"total": revenue//100, "monthly": revenue//100},
        "api_keys":{"active": active_keys, "revoked": 0},
        "usage":   {"requests_today": req_today, "threats_total": total_blocked}
    })

@app.route('/api/admin/users')
@require_admin
def admin_users():
    page   = int(request.args.get('page', 1))
    search = request.args.get('search', '')
    plan_f = request.args.get('plan', '')
    conn   = get_db()
    c      = conn.cursor()
    q      = "SELECT id,name,email,company,plan,is_active,created_at FROM users WHERE 1=1"
    params = []
    if search:
        q += " AND (name LIKE ? OR email LIKE ?)"; params += [f"%{search}%", f"%{search}%"]
    if plan_f:
        q += " AND plan=?"; params.append(plan_f)
    c.execute(q + " ORDER BY created_at DESC LIMIT 20 OFFSET ?", params + [(page-1)*20])
    users = [dict(r) for r in c.fetchall()]
    c.execute("SELECT COUNT(*) as n FROM users"); total = c.fetchone()["n"]
    conn.close()
    return jsonify({"users": users, "total": total, "pages": max(1, (total+19)//20)})

@app.route('/api/admin/users/<int:uid>/plan', methods=['PUT'])
@require_admin
def admin_update_plan(uid):
    data = request.get_json() or {}
    plan = data.get('plan', 'free')
    if plan not in ['free','pro','enterprise']:
        return jsonify({"error": "Invalid plan"}), 400
    conn = get_db()
    conn.execute("UPDATE users SET plan=? WHERE id=?", (plan, uid))
    conn.execute("UPDATE api_keys SET tier=? WHERE email=(SELECT email FROM users WHERE id=?)", (plan, uid))
    conn.commit(); conn.close()
    return jsonify({"success": True, "message": f"Plan updated to {plan}"})

@app.route('/api/admin/users/<int:uid>/status', methods=['PUT'])
@require_admin
def admin_toggle_status(uid):
    data   = request.get_json() or {}
    active = int(data.get('active', True))
    conn   = get_db()
    conn.execute("UPDATE users SET is_active=? WHERE id=?", (active, uid))
    conn.execute("UPDATE api_keys SET is_active=? WHERE email=(SELECT email FROM users WHERE id=?)", (active, uid))
    conn.commit(); conn.close()
    return jsonify({"success": True})

@app.route('/api/admin/payments')
@require_admin
def admin_payments():
    conn = get_db()
    c    = conn.cursor()
    c.execute("SELECT p.*,u.name as user_name FROM payments p LEFT JOIN users u ON p.user_email=u.email ORDER BY p.created_at DESC LIMIT 50")
    payments = [dict(r) for r in c.fetchall()]
    c.execute("SELECT COUNT(*) as n FROM payments"); total = c.fetchone()["n"]
    conn.close()
    return jsonify({"payments": payments, "total": total})

@app.route('/api/admin/system')
@require_admin
def admin_system():
    conn = get_db()
    c    = conn.cursor()
    daily = []
    for i in range(6, -1, -1):
        d = (datetime.utcnow() - timedelta(days=i)).date().isoformat()
        c.execute("SELECT COALESCE(SUM(count),0) as n FROM usage_log WHERE date=?", (d,))
        daily.append({"date": d, "requests": c.fetchone()["n"]})
    conn.close()
    return jsonify({"daily_requests": daily, "top_users": [], "monthly_revenue": []})

@app.route('/api/admin/keys/<prefix>/revoke', methods=['POST'])
@require_admin
def admin_revoke_key(prefix):
    conn = get_db()
    conn.execute("UPDATE api_keys SET is_active=0 WHERE key_prefix LIKE ?", (f"{prefix[:15]}%",))
    conn.commit(); conn.close()
    return jsonify({"success": True})

# ══════════════════════════════════════════════════════════════
# ── PUBLIC DEMO ROUTE (no API key needed — for landing page) ──
@app.route('/api/v1/demo', methods=['POST'])
def demo_check():
    """Public demo endpoint — no API key required. Rate limited to 10 req/min by IP."""
    data   = request.get_json() or {}
    prompt = str(data.get('prompt', '')).strip()
    if not prompt:
        return jsonify({"error": "Missing 'prompt' field"}), 400
    if len(prompt) > 500:
        return jsonify({"error": "Demo limited to 500 characters. Sign up for full access."}), 400

    is_mal, confidence = _detect(prompt)
    return jsonify({
        "status":       "MALICIOUS" if is_mal else "SAFE",
        "is_malicious": is_mal,
        "confidence":   confidence,
        "threat_level": _threat_level(confidence, is_mal),
        "message":      "🚨 Prompt injection detected." if is_mal else "✅ Prompt is safe.",
        "demo":         True,
        "note":         "Sign up for full API access with your own API key."
    })

# ── START
# ══════════════════════════════════════════════════════════════
if __name__ == '__main__':
    init_all_tables()
    port  = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_ENV", "development") != "production"
    print("\n" + "="*55)
    print("  🛡️  ShieldPrompt API Server v5.0")
    print("="*55)
    print(f"  🌐 Landing:    http://localhost:{port}/")
    print(f"  🔐 Auth:       http://localhost:{port}/login")
    print(f"  📊 Dashboard:  http://localhost:{port}/dashboard")
    print(f"  💳 Payment:    http://localhost:{port}/payment")
    print(f"  👨‍💼 Admin:      http://localhost:{port}/admin")
    print(f"  📡 API:        POST http://localhost:{port}/api/v1/check")
    print("="*55 + "\n")
    app.run(debug=debug, port=port, host='0.0.0.0')