"""
ShieldPrompt — Razorpay Payment Integration
Handles subscription payments for Pro plan (₹999/month)
"""

import razorpay
import hmac
import hashlib
import json
from datetime import datetime, timedelta
from flask import request, jsonify, redirect
from api_keys import init_db, create_key
import sqlite3

# ── RAZORPAY CONFIG ────────────────────────────────────────────────
# Get these from https://dashboard.razorpay.com/app/keys
import os
RAZORPAY_KEY_ID     = os.getenv("RAZORPAY_KEY_ID", "rzp_test_demo")      # Replace with your key
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "demo_secret")             # Replace with your secret

client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

DB_PATH = "shieldprompt.db"

# ── PLAN PRICING ───────────────────────────────────────────────────
PLANS = {
    "pro": {
        "name":        "ShieldPrompt Pro",
        "amount":      99900,      # ₹999 in paise (Razorpay uses paise)
        "currency":    "INR",
        "description": "10,000 requests/day · Full dashboard · Priority support",
        "tier":        "pro",
    }
}

# ── DATABASE SETUP FOR PAYMENTS ────────────────────────────────────
def init_payments_db():
    """Add payments table to existing DB."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Users table
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            email        TEXT UNIQUE NOT NULL,
            password     TEXT NOT NULL,
            company      TEXT,
            plan         TEXT NOT NULL DEFAULT 'free',
            is_active    INTEGER NOT NULL DEFAULT 1,
            created_at   TEXT NOT NULL,
            api_key_hash TEXT
        )
    """)

    # Payments table
    c.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email          TEXT NOT NULL,
            razorpay_order_id   TEXT UNIQUE NOT NULL,
            razorpay_payment_id TEXT,
            razorpay_signature  TEXT,
            plan                TEXT NOT NULL,
            amount              INTEGER NOT NULL,
            currency            TEXT NOT NULL DEFAULT 'INR',
            status              TEXT NOT NULL DEFAULT 'created',
            created_at          TEXT NOT NULL,
            paid_at             TEXT,
            expires_at          TEXT
        )
    """)

    # Subscriptions table
    c.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email      TEXT UNIQUE NOT NULL,
            plan            TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'active',
            started_at      TEXT NOT NULL,
            expires_at      TEXT NOT NULL,
            payment_id      TEXT,
            auto_renew      INTEGER DEFAULT 1
        )
    """)

    conn.commit()
    conn.close()
    print("✅ Payments DB initialized!")


# ── CREATE ORDER ───────────────────────────────────────────────────
def create_order(email: str, plan: str) -> dict:
    """
    Create Razorpay order.
    Returns order details to pass to frontend checkout.
    """
    if plan not in PLANS:
        return {"error": f"Invalid plan: {plan}"}

    plan_data = PLANS[plan]
    now = datetime.utcnow().isoformat()

    try:
        # Create order on Razorpay
        order = client.order.create({
            "amount":   plan_data["amount"],
            "currency": plan_data["currency"],
            "receipt":  f"sp_{email}_{int(datetime.utcnow().timestamp())}",
            "notes": {
                "email": email,
                "plan":  plan,
            }
        })

        # Save order to DB
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            INSERT INTO payments (user_email, razorpay_order_id, plan, amount, currency, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'created', ?)
        """, (email, order["id"], plan, plan_data["amount"], plan_data["currency"], now))
        conn.commit()
        conn.close()

        return {
            "success":    True,
            "order_id":   order["id"],
            "amount":     plan_data["amount"],
            "currency":   plan_data["currency"],
            "plan":       plan,
            "plan_name":  plan_data["name"],
            "key_id":     RAZORPAY_KEY_ID,
        }

    except Exception as e:
        return {"error": str(e)}


# ── VERIFY PAYMENT ─────────────────────────────────────────────────
def verify_payment(order_id: str, payment_id: str, signature: str, email: str) -> dict:
    """
    Verify Razorpay payment signature.
    If valid → upgrade user plan → generate API key → activate subscription.
    """
    try:
        # Verify signature
        body        = f"{order_id}|{payment_id}"
        expected    = hmac.new(
            RAZORPAY_KEY_SECRET.encode(),
            body.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected, signature):
            return {"success": False, "error": "Invalid payment signature. Possible fraud attempt."}

        now        = datetime.utcnow()
        expires_at = (now + timedelta(days=30)).isoformat()
        now_str    = now.isoformat()

        conn = sqlite3.connect(DB_PATH)
        c    = conn.cursor()

        # Update payment record
        c.execute("""
            UPDATE payments
            SET razorpay_payment_id=?, razorpay_signature=?, status='paid', paid_at=?, expires_at=?
            WHERE razorpay_order_id=?
        """, (payment_id, signature, now_str, expires_at, order_id))

        # Upgrade user plan
        c.execute("UPDATE users SET plan='pro' WHERE email=?", (email,))

        # Create/update subscription
        c.execute("""
            INSERT INTO subscriptions (user_email, plan, status, started_at, expires_at, payment_id)
            VALUES (?, 'pro', 'active', ?, ?, ?)
            ON CONFLICT(user_email) DO UPDATE SET
                plan='pro', status='active', started_at=?, expires_at=?, payment_id=?
        """, (email, now_str, expires_at, payment_id, now_str, expires_at, payment_id))

        conn.commit()

        # Generate new Pro API key for user
        key_result = create_key(
            name=email,
            email=email,
            tier="pro"
        )

        # Save key hash to user record
        if "api_key" in key_result:
            import hashlib as hl
            key_hash = hl.sha256(key_result["api_key"].encode()).hexdigest()
            c2 = sqlite3.connect(DB_PATH)
            c2.execute("UPDATE users SET api_key_hash=? WHERE email=?", (key_hash, email))
            c2.commit()
            c2.close()

        conn.close()

        return {
            "success":    True,
            "message":    "Payment verified! Pro plan activated.",
            "plan":       "pro",
            "expires_at": expires_at,
            "api_key":    key_result.get("api_key"),   # Show ONCE
            "warning":    "Save your API key — it won't be shown again!"
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


# ── CHECK SUBSCRIPTION ─────────────────────────────────────────────
def get_subscription(email: str) -> dict:
    """Check user's current subscription status."""
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("""
        SELECT plan, status, started_at, expires_at, auto_renew
        FROM subscriptions WHERE user_email=?
    """, (email,))
    row = c.fetchone()
    conn.close()

    if not row:
        return {"plan": "free", "status": "active", "expires_at": None}

    plan, status, started, expires, auto_renew = row
    is_expired = datetime.utcnow() > datetime.fromisoformat(expires)

    return {
        "plan":       plan,
        "status":     "expired" if is_expired else status,
        "started_at": started,
        "expires_at": expires,
        "auto_renew": bool(auto_renew),
        "days_left":  max(0, (datetime.fromisoformat(expires) - datetime.utcnow()).days)
    }


# ── FLASK ROUTES ───────────────────────────────────────────────────
def register_payment_routes(app):
    """Call this in app.py: register_payment_routes(app)"""

    @app.route('/api/v1/payments/create-order', methods=['POST'])
    def create_payment_order():
        """Frontend calls this to start payment."""
        data  = request.get_json()
        email = data.get('email')
        plan  = data.get('plan', 'pro')
        if not email:
            return jsonify({"error": "Email required"}), 400
        result = create_order(email, plan)
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result)

    @app.route('/api/v1/payments/verify', methods=['POST'])
    def verify_payment_route():
        """Razorpay calls this after payment."""
        data = request.get_json()
        result = verify_payment(
            order_id=data.get('razorpay_order_id'),
            payment_id=data.get('razorpay_payment_id'),
            signature=data.get('razorpay_signature'),
            email=data.get('email')
        )
        if not result["success"]:
            return jsonify(result), 400
        return jsonify(result)

    @app.route('/api/v1/payments/subscription', methods=['GET'])
    def subscription_status():
        """Check subscription status."""
        email = request.args.get('email')
        if not email:
            return jsonify({"error": "Email required"}), 400
        return jsonify(get_subscription(email))

    @app.route('/payment')
    def payment_page():
        from flask import render_template
        plan = request.args.get('plan', 'pro')
        return render_template('pricing.html', plan=plan,
                               razorpay_key=RAZORPAY_KEY_ID)

    print("✅ Payment routes registered!")


# ── TEST ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "="*50)
    print("  ShieldPrompt — Payment System")
    print("="*50)
    init_payments_db()
    print("\n📌 Plan details:")
    for k, v in PLANS.items():
        print(f"   {k}: ₹{v['amount']//100}/month — {v['description']}")
    print("\n✅ Payment system ready!")
    print("\nTo integrate in app.py:")
    print("  from payments import init_payments_db, register_payment_routes")
    print("  init_payments_db()")
    print("  register_payment_routes(app)")
    print("="*50)