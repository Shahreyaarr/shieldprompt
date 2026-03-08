# 🔐 Google OAuth — ShieldPrompt Setup Guide
## Firebase Authentication (Recommended — Free & Easy)

---

## Step 1 — Firebase Project Banao (5 min)

1. **console.firebase.google.com** pe jao
2. **"Add project"** → Name: `ShieldPrompt`
3. Google Analytics: Optional → Continue
4. Project ban jayega ✅

---

## Step 2 — Authentication Enable Karo

1. Firebase Console → **Authentication** (left sidebar)
2. **"Get started"** button
3. **Sign-in method** tab → **Google** → Enable karo
4. Project support email: apna email dalo
5. **Save** ✅

---

## Step 3 — Web App Register Karo

1. Firebase Console → Project Overview → **"</>"** (Web icon)
2. App nickname: `ShieldPrompt Web`
3. **Register app**
4. **Firebase config copy karo** — kuch aisa dikhega:

```javascript
const firebaseConfig = {
  apiKey: "AIzaSy...",
  authDomain: "shieldprompt-xxxxx.firebaseapp.com",
  projectId: "shieldprompt-xxxxx",
  storageBucket: "shieldprompt-xxxxx.appspot.com",
  messagingSenderId: "123456789",
  appId: "1:123456789:web:abcdef"
};
```

5. Ye config apni `.env` mein dalo:

```bash
FIREBASE_API_KEY=AIzaSy...
FIREBASE_AUTH_DOMAIN=shieldprompt-xxxxx.firebaseapp.com
FIREBASE_PROJECT_ID=shieldprompt-xxxxx
```

---

## Step 4 — auth.html mein Google Button Add Karo

**`auth.html`** mein `<head>` ke andar ye add karo:

```html
<!-- Firebase SDK -->
<script src="https://www.gstatic.com/firebasejs/10.7.1/firebase-app-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/10.7.1/firebase-auth-compat.js"></script>
```

**Google button HTML** (already hai auth.html mein, bas enable karo):

```html
<button class="btn-google" onclick="signInWithGoogle()">
  <img src="https://developers.google.com/identity/images/g-logo.png" width="18">
  Continue with Google
</button>
```

**JavaScript** — auth.html ke `<script>` mein add karo:

```javascript
// Firebase config
const firebaseConfig = {
  apiKey:     "AIzaSy...",           // apna key
  authDomain: "shieldprompt-xxxxx.firebaseapp.com",
  projectId:  "shieldprompt-xxxxx",
};
firebase.initializeApp(firebaseConfig);

async function signInWithGoogle() {
  const provider = new firebase.auth.GoogleAuthProvider();
  try {
    const result = await firebase.auth().signInWithPopup(provider);
    const user   = result.user;
    const idToken = await user.getIdToken();

    // Send Google token to your Flask backend
    const res = await fetch('/api/v1/auth/google', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ id_token: idToken })
    });
    const data = await res.json();

    if (data.success) {
      localStorage.setItem('sp_token', data.access_token);
      localStorage.setItem('sp_user', JSON.stringify(data.user));
      window.location.href = data.redirect || '/dashboard';
    } else {
      alert('Error: ' + data.error);
    }
  } catch(err) {
    alert('Google sign-in failed: ' + err.message);
  }
}
```

---

## Step 5 — Flask Backend Route

**`auth.py`** mein ye function add karo:

```python
pip install firebase-admin
```

```python
import firebase_admin
from firebase_admin import credentials, auth as fb_auth

# Firebase Admin SDK initialize
# Service account key: Firebase Console → Project Settings → Service accounts
# → Generate new private key → download JSON
cred = credentials.Certificate("firebase-service-account.json")
firebase_admin.initialize_app(cred)

def google_auth(id_token: str) -> dict:
    """Verify Google token and login/register user."""
    try:
        decoded = fb_auth.verify_id_token(id_token)
    except Exception as e:
        return {"error": f"Invalid Google token: {str(e)}"}

    email   = decoded.get("email", "").lower()
    name    = decoded.get("name", email.split("@")[0].title())
    picture = decoded.get("picture", "")

    conn = _db()
    c    = conn.cursor()
    c.execute("SELECT id, name, plan, is_active FROM users WHERE email=?", (email,))
    user = c.fetchone()

    if not user:
        # First time — auto-register
        now = datetime.utcnow().isoformat()
        c.execute("""
            INSERT INTO users (name, email, password, plan, created_at)
            VALUES (?, ?, 'GOOGLE_OAUTH', 'free', ?)
        """, (name, email, now))
        conn.commit()
        uid  = c.lastrowid
        plan = "free"
        # Auto-create API key
        try:
            from api_keys import create_key
            create_key(name=name, email=email, tier="free")
        except Exception: pass
    else:
        uid  = user["id"]
        plan = user["plan"]
        if not user["is_active"]:
            conn.close()
            return {"error": "Account suspended. Contact support."}

    c.execute("UPDATE users SET last_login=? WHERE id=?",
              (datetime.utcnow().isoformat(), uid))
    conn.commit()
    conn.close()

    access  = _make_token(uid, email, plan, ACCESS_EXP)
    refresh = _make_token(uid, email, plan, REFRESH_EXP)

    return {
        "success":       True,
        "access_token":  access,
        "refresh_token": refresh,
        "user": {"id": uid, "name": name, "email": email, "plan": plan},
        "redirect": "/dashboard",
    }
```

**Route register karo** `register_auth_routes(app)` ke andar:

```python
@app.route('/api/v1/auth/google', methods=['POST'])
def api_google_auth():
    d = request.get_json() or {}
    result = google_auth(d.get('id_token', ''))
    if 'error' in result:
        return jsonify(result), 401
    return jsonify(result)
```

---

## Step 6 — Authorized Domains Add Karo

1. Firebase Console → Authentication → **Settings** tab
2. **Authorized domains** → **Add domain**
3. Add karo:
   - `localhost` (already hoga)
   - `shieldprompt.onrender.com` (apna Render domain)
   - `shieldprompt.in` (agar custom domain ho)

---

## Step 7 — Test Karo

```bash
# Flask start karo
cd app && python app.py

# Browser mein jao
http://localhost:5000/login

# "Continue with Google" click karo
# → Google popup aayega
# → Login hoga
# → /dashboard redirect
```

---

## ✅ Complete Checklist

- [ ] Firebase project created
- [ ] Google Auth enabled
- [ ] Web app registered, config copied
- [ ] `.env` mein Firebase keys added
- [ ] `firebase-admin` pip install kiya
- [ ] Service account JSON downloaded
- [ ] `auth.py` mein `google_auth()` function added
- [ ] `auth.html` mein Firebase SDK + `signInWithGoogle()` added
- [ ] Authorized domains mein apna URL added
- [ ] Test kiya localhost pe

---

## 💡 Pro Tips

**Deployment pe:**
```bash
# render.com pe environment variable add karo:
GOOGLE_CLIENT_ID = your_firebase_client_id
```

**Service account JSON** → `.gitignore` mein add karo:
```
firebase-service-account.json
```

**Firebase free tier** = 10,000 Google sign-ins/month — chhote project ke liye ekdum enough! 🎉