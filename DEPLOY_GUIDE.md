# 🚀 ShieldPrompt — Render.com Deploy Guide
## Step-by-Step — Pehli baar bhi kar sakta hai!

---

## Pre-requisites (pehle ye sab ready kar)

- [ ] GitHub account
- [ ] Render.com account (free)
- [ ] Razorpay keys (dashboard.razorpay.com)
- [ ] Project sab files ready

---

## Step 1 — Project Structure Sahi Kar (Local)

```
shieldprompt/                  ← Root folder
├── app/
│   ├── app.py                 ✅
│   ├── api_keys.py            ✅
│   ├── auth.py                ✅
│   ├── payments.py            ✅
│   └── admin.py               ✅
├── templates/
│   ├── index.html             ✅
│   ├── auth.html              ✅
│   ├── dashboard.html         ✅
│   ├── pricing.html           ✅
│   └── admin_panel.html       ✅
├── static/
│   └── (CSS, JS, images)
├── model/
│   ├── shield_model.pkl       ✅
│   └── vectorizer.pkl         ✅
├── Assests/
│   └── video/
│       └── heroVideo.mp4      ✅
├── .env                       ✅ (local only — gitignore mein)
├── .env.example               ✅ (GitHub pe jayega)
├── .gitignore                 ✅
├── requirements.txt           ✅
├── render.yaml                ✅
└── README.md                  ✅
```

---

## Step 2 — requirements.txt Check Karo

```
flask==3.0.0
flask-cors==4.0.0
gunicorn==21.2.0
python-dotenv==1.0.0
PyJWT==2.8.0
razorpay==1.4.1
scikit-learn==1.3.2
transformers==4.35.0
torch==2.1.0
joblib==1.3.2
numpy==1.26.2
```

---

## Step 3 — GitHub pe Push Karo

```bash
# Terminal mein project folder mein jao
cd /path/to/shieldprompt

# Git initialize
git init

# Sab files add karo (.env NAHI jayega — gitignore handles it)
git add .

# Check kar — .env toh nahi gaya?
git status
# ✅ .env should NOT be listed

# First commit
git commit -m "ShieldPrompt v1.0 — Initial Deploy"

# GitHub pe new repo banao: github.com/new
# Name: shieldprompt
# Public ya Private — apni choice

# GitHub repo se connect karo
git remote add origin https://github.com/TERA_USERNAME/shieldprompt.git
git branch -M main
git push -u origin main
```

✅ GitHub pe code gaya!

---

## Step 4 — Render.com Pe Deploy

### 4.1 — Render Account
1. **render.com** → Sign Up (GitHub se login karo — easier)

### 4.2 — New Web Service
1. Dashboard → **"New +"** → **"Web Service"**
2. **"Connect a repository"** → GitHub auth → apna `shieldprompt` repo select karo

### 4.3 — Service Configure Karo

| Setting | Value |
|---------|-------|
| **Name** | `shieldprompt-api` |
| **Region** | `Singapore` (India ke closest) |
| **Branch** | `main` |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `cd app && gunicorn app:app --workers 2 --bind 0.0.0.0:$PORT --timeout 120` |
| **Plan** | `Free` (start ke liye) |

### 4.4 — ⚠️ IMPORTANT: Environment Variables

Render Dashboard → **"Environment"** tab → Add karo:

```
FLASK_SECRET_KEY    =  (generate button press karo — auto fill)
JWT_SECRET          =  (generate button press karo — auto fill)
FLASK_ENV           =  production
RAZORPAY_KEY_ID     =  rzp_live_xxxxx     ← apna live key
RAZORPAY_KEY_SECRET =  xxxxx              ← apna live secret
ADMIN_EMAIL         =  admin@shieldprompt.in
ADMIN_PASSWORD      =  (strong password dalo)
ADMIN_SECRET_TOKEN  =  (generate button press karo)
DB_PATH             =  shieldprompt.db
PORT                =  10000
```

**"Save Changes"** → **"Deploy"** button!

---

## Step 5 — Deploy Complete! (5-10 min wait)

Render logs mein ye dikhega:
```
==> Build successful 🎉
==> Deploying...
✅ ShieldPrompt API Server v3.0
🌐 Running on https://shieldprompt-api.onrender.com
```

---

## Step 6 — Test Karo

```bash
# API health check
curl https://shieldprompt-api.onrender.com/api/v1/health

# Expected response:
# {"status":"healthy","model":"loaded","version":"3.0.0"}

# Landing page
# Browser: https://shieldprompt-api.onrender.com
```

---

## Step 7 — Custom Domain (Optional — ₹500-1000/year)

### Domain kharido:
- **GoDaddy India**: godaddy.com/in
- **BigRock**: bigrock.in
- **Namecheap**: namecheap.com

### Render pe add karo:
1. Render Dashboard → Settings → **Custom Domain**
2. Domain add karo: `shieldprompt.in`
3. DNS settings milegi — DNS provider pe add karo:
   ```
   Type: CNAME
   Name: @
   Value: shieldprompt-api.onrender.com
   ```
4. SSL certificate auto-generate ho jayega (free!) ✅

---

## ⚠️ Important: ML Model Issue on Render

**Problem:** `shield_model.pkl` aur `vectorizer.pkl` large files hain — GitHub mein nahi jayenge (100MB limit).

**Solution — Git LFS:**
```bash
# Git LFS install karo
git lfs install

# Model files LFS pe bhejo
git lfs track "model/*.pkl"
git add .gitattributes
git add model/
git commit -m "Add ML models via LFS"
git push
```

**Ya alternative — Hugging Face Hub:**
```python
# Model cloud pe store karo, load karo startup pe
from huggingface_hub import hf_hub_download
```

---

## 🔄 Future Updates Deploy Kaise Karein

```bash
# Code update karo locally
# Phir:
git add .
git commit -m "Update: dashboard improvements"
git push origin main

# Render auto-deploy karega! 🎉
# (Auto-deploy by default ON hota hai)
```

---

## 📊 Render Free Tier Limits

| Resource | Free Tier |
|----------|-----------|
| RAM | 512 MB |
| CPU | Shared |
| Sleep | 15 min inactivity pe sleep |
| Bandwidth | 100 GB/month |
| Build mins | 500/month |

**Pro tip:** Free tier pe server 15 min baad so jaata hai — pehli request slow hoti hai.
Upgrade to **Starter ($7/month)** for always-on.

---

## ✅ Final Checklist

- [ ] GitHub pe code push kiya
- [ ] Render pe Web Service banaya
- [ ] Sab environment variables set kiye
- [ ] Deploy successful
- [ ] API health check kiya
- [ ] Admin panel test kiya (/admin)
- [ ] Razorpay live keys dali
- [ ] Custom domain add kiya (optional)

---

## 🆘 Common Errors & Fixes

| Error | Fix |
|-------|-----|
| `ModuleNotFoundError` | `requirements.txt` mein add karo |
| `Port already in use` | `$PORT` use karo hardcoded 5000 ki jagah |
| `Model file not found` | Git LFS check karo |
| `DB not found` | `DB_PATH` env var check karo |
| Build timeout | Torch install slow hai — wait karo |
| 500 on /admin | `ADMIN_SECRET_TOKEN` env var set hai? |

---

**Teri site live hogi:** `https://shieldprompt-api.onrender.com` 🎉