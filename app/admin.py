"""
ShieldPrompt — Super Admin Backend
Full control: users, revenue, API keys, system stats
"""

import sqlite3
import hashlib
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, render_template, session

DB_PATH = "shieldprompt.db"

# ── ADMIN CREDENTIALS ──────────────────────────────────────────────
# Change these before deployment!
import os
ADMIN_EMAIL    = os.getenv("ADMIN_EMAIL", "admin@shieldprompt.in")
raw_pass = os.getenv("ADMIN_PASSWORD", "ShieldAdmin@2026")
ADMIN_PASSWORD = hashlib.sha256(raw_pass.encode()).hexdigest()
ADMIN_SECRET   = os.getenv("ADMIN_SECRET_TOKEN", "sp_admin_super_secret_2026")   # For API access

# ── ADMIN AUTH DECORATOR ───────────────────────────────────────────
def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("X-Admin-Token") or session.get("admin_token")
        if token != ADMIN_SECRET:
            return jsonify({"error": "Unauthorized. Admin access required."}), 403
        return f(*args, **kwargs)
    return decorated

# ── HELPERS ────────────────────────────────────────────────────────
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def fmt(val): return val or "—"

# ── DASHBOARD STATS ────────────────────────────────────────────────
def get_dashboard_stats():
    conn = db()
    c    = conn.cursor()
    today = datetime.utcnow().date().isoformat()
    month = datetime.utcnow().strftime("%Y-%m")

    # Users
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE created_at LIKE ?", (f"{today}%",))
    new_today = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE plan='pro'")
    pro_users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM users WHERE plan='enterprise'")
    ent_users = c.fetchone()[0]

    # Revenue
    c.execute("SELECT COUNT(*), SUM(amount) FROM payments WHERE status='paid'")
    row = c.fetchone()
    total_payments = row[0] or 0
    total_revenue  = (row[1] or 0) // 100   # paise → rupees

    c.execute("SELECT COUNT(*), SUM(amount) FROM payments WHERE status='paid' AND paid_at LIKE ?", (f"{month}%",))
    row2 = c.fetchone()
    monthly_payments = row2[0] or 0
    monthly_revenue  = (row2[1] or 0) // 100

    # API Keys
    c.execute("SELECT COUNT(*) FROM api_keys WHERE is_active=1")
    active_keys = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM api_keys WHERE is_active=0")
    revoked_keys = c.fetchone()[0]

    # Requests today
    c.execute("SELECT SUM(count) FROM usage_log WHERE date=?", (today,))
    row3 = c.fetchone()
    requests_today = row3[0] or 0

    # Threats detected total
    c.execute("SELECT COUNT(*) FROM request_log WHERE is_malicious=1")
    threats_total = c.fetchone()[0]

    conn.close()
    return {
        "users": {
            "total": total_users, "new_today": new_today,
            "pro": pro_users, "enterprise": ent_users,
            "free": total_users - pro_users - ent_users
        },
        "revenue": {
            "total": total_revenue, "monthly": monthly_revenue,
            "total_payments": total_payments, "monthly_payments": monthly_payments
        },
        "api_keys": { "active": active_keys, "revoked": revoked_keys },
        "usage": { "requests_today": requests_today, "threats_total": threats_total }
    }

# ── ALL USERS ──────────────────────────────────────────────────────
def get_all_users(page=1, per_page=20, search="", plan_filter=""):
    conn = db()
    c    = conn.cursor()
    offset = (page - 1) * per_page

    query  = "SELECT id,name,email,company,plan,is_active,created_at FROM users WHERE 1=1"
    params = []
    if search:
        query  += " AND (name LIKE ? OR email LIKE ? OR company LIKE ?)"
        params += [f"%{search}%", f"%{search}%", f"%{search}%"]
    if plan_filter:
        query  += " AND plan=?"
        params.append(plan_filter)

    c.execute(query + " ORDER BY created_at DESC LIMIT ? OFFSET ?", params + [per_page, offset])
    users = [dict(row) for row in c.fetchall()]

    c.execute("SELECT COUNT(*) FROM users WHERE 1=1" +
              (" AND (name LIKE ? OR email LIKE ? OR company LIKE ?)" if search else "") +
              (" AND plan=?" if plan_filter else ""),
              params)
    total = c.fetchone()[0]
    conn.close()
    return {"users": users, "total": total, "pages": (total + per_page - 1) // per_page}

# ── USER DETAIL ────────────────────────────────────────────────────
def get_user_detail(user_id):
    conn = db()
    c    = conn.cursor()
    c.execute("SELECT * FROM users WHERE id=?", (user_id,))
    user = dict(c.fetchone() or {})
    if not user:
        conn.close()
        return {"error": "User not found"}

    # Their API keys
    c.execute("SELECT key_prefix,tier,is_active,created_at,last_used FROM api_keys WHERE email=?", (user["email"],))
    keys = [dict(r) for r in c.fetchall()]

    # Their payments
    c.execute("SELECT razorpay_order_id,plan,amount,status,created_at,paid_at FROM payments WHERE user_email=? ORDER BY created_at DESC", (user["email"],))
    payments = [dict(r) for r in c.fetchall()]

    # Usage today
    today = datetime.utcnow().date().isoformat()
    c.execute("SELECT SUM(count) FROM usage_log WHERE key_hash IN (SELECT key_hash FROM api_keys WHERE email=?) AND date=?", (user["email"], today))
    usage_today = c.fetchone()[0] or 0

    conn.close()
    user.pop("password", None)   # Never expose password
    return {"user": user, "api_keys": keys, "payments": payments, "usage_today": usage_today}

# ── UPGRADE / DOWNGRADE USER ───────────────────────────────────────
def update_user_plan(user_id, new_plan):
    valid = ["free", "pro", "enterprise"]
    if new_plan not in valid:
        return {"error": f"Invalid plan. Choose: {valid}"}
    conn = db()
    c    = conn.cursor()
    c.execute("UPDATE users SET plan=? WHERE id=?", (new_plan, user_id))

    # Update their API key tier
    c.execute("SELECT email FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    if row:
        c.execute("UPDATE api_keys SET tier=? WHERE email=?", (new_plan, row["email"]))

    conn.commit()
    conn.close()
    return {"success": True, "message": f"User plan updated to {new_plan}"}

# ── BAN / UNBAN USER ───────────────────────────────────────────────
def toggle_user_status(user_id, active: bool):
    conn = db()
    c    = conn.cursor()
    c.execute("UPDATE users SET is_active=? WHERE id=?", (int(active), user_id))
    c.execute("SELECT email FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    if row:
        # Also disable/enable all their API keys
        c.execute("UPDATE api_keys SET is_active=? WHERE email=?", (int(active), row["email"]))
    conn.commit()
    conn.close()
    return {"success": True, "message": "User " + ("activated" if active else "banned")}

# ── ALL PAYMENTS ───────────────────────────────────────────────────
def get_all_payments(page=1, per_page=20):
    conn = db()
    c    = conn.cursor()
    offset = (page - 1) * per_page
    c.execute("""
        SELECT p.id, p.user_email, p.razorpay_order_id, p.razorpay_payment_id,
               p.plan, p.amount, p.status, p.created_at, p.paid_at,
               u.name as user_name
        FROM payments p
        LEFT JOIN users u ON p.user_email = u.email
        ORDER BY p.created_at DESC LIMIT ? OFFSET ?
    """, (per_page, offset))
    payments = [dict(r) for r in c.fetchall()]
    c.execute("SELECT COUNT(*) FROM payments")
    total = c.fetchone()[0]
    conn.close()
    return {"payments": payments, "total": total, "pages": (total + per_page - 1) // per_page}

# ── SYSTEM STATS ───────────────────────────────────────────────────
def get_system_stats():
    conn = db()
    c    = conn.cursor()

    # Daily requests last 7 days
    daily = []
    for i in range(6, -1, -1):
        d = (datetime.utcnow() - timedelta(days=i)).date().isoformat()
        c.execute("SELECT SUM(count) FROM usage_log WHERE date=?", (d,))
        cnt = c.fetchone()[0] or 0
        daily.append({"date": d, "requests": cnt})

    # Top users by usage
    c.execute("""
        SELECT u.name, u.email, u.plan, SUM(ul.count) as total_reqs
        FROM usage_log ul
        JOIN api_keys ak ON ul.key_hash = ak.key_hash
        JOIN users u ON ak.email = u.email
        GROUP BY u.email ORDER BY total_reqs DESC LIMIT 5
    """)
    top_users = [dict(r) for r in c.fetchall()]

    # Revenue by month (last 6 months)
    monthly_rev = []
    for i in range(5, -1, -1):
        d = datetime.utcnow() - timedelta(days=i*30)
        m = d.strftime("%Y-%m")
        c.execute("SELECT SUM(amount) FROM payments WHERE status='paid' AND paid_at LIKE ?", (f"{m}%",))
        rev = (c.fetchone()[0] or 0) // 100
        monthly_rev.append({"month": d.strftime("%b"), "revenue": rev})

    conn.close()
    return {"daily_requests": daily, "top_users": top_users, "monthly_revenue": monthly_rev}

# ── REVOKE API KEY ─────────────────────────────────────────────────
def admin_revoke_key(key_prefix):
    conn = db()
    c    = conn.cursor()
    c.execute("UPDATE api_keys SET is_active=0 WHERE key_prefix LIKE ?", (f"{key_prefix}%",))
    conn.commit()
    conn.close()
    return {"success": True, "message": "API key revoked."}

# ── FLASK ROUTES ───────────────────────────────────────────────────
def register_admin_routes(app):

    @app.route('/admin')
    @app.route('/admin/')
    def admin_panel():
        return render_template('admin_panel.html')

    @app.route('/api/admin/login', methods=['POST'])
    def admin_login():
        data = request.get_json()
        pw   = hashlib.sha256(data.get('password','').encode()).hexdigest()
        if data.get('email') == ADMIN_EMAIL and pw == ADMIN_PASSWORD:
            session['admin_token'] = ADMIN_SECRET
            return jsonify({"success": True, "token": ADMIN_SECRET})
        return jsonify({"error": "Invalid admin credentials."}), 401

    @app.route('/api/admin/stats')
    @require_admin
    def admin_stats():
        return jsonify(get_dashboard_stats())

    @app.route('/api/admin/users')
    @require_admin
    def admin_users():
        page   = int(request.args.get('page', 1))
        search = request.args.get('search', '')
        plan   = request.args.get('plan', '')
        return jsonify(get_all_users(page, search=search, plan_filter=plan))

    @app.route('/api/admin/users/<int:uid>')
    @require_admin
    def admin_user_detail(uid):
        return jsonify(get_user_detail(uid))

    @app.route('/api/admin/users/<int:uid>/plan', methods=['PUT'])
    @require_admin
    def admin_update_plan(uid):
        data = request.get_json()
        return jsonify(update_user_plan(uid, data.get('plan','')))

    @app.route('/api/admin/users/<int:uid>/status', methods=['PUT'])
    @require_admin
    def admin_toggle_status(uid):
        data = request.get_json()
        return jsonify(toggle_user_status(uid, data.get('active', True)))

    @app.route('/api/admin/payments')
    @require_admin
    def admin_payments():
        page = int(request.args.get('page', 1))
        return jsonify(get_all_payments(page))

    @app.route('/api/admin/system')
    @require_admin
    def admin_system():
        return jsonify(get_system_stats())

    @app.route('/api/admin/keys/<prefix>/revoke', methods=['POST'])
    @require_admin
    def admin_revoke(prefix):
        return jsonify(admin_revoke_key(prefix))

    print("✅ Admin routes registered! Panel at /admin")