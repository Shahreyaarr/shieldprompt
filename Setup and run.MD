# 🛡️ ShieldPrompt — Aaj Hi Chalao (Step by Step)

## Teri project folder structure EXACTLY aisi honi chahiye:

```
prompt-injection-project/          ← ROOT folder
│
├── .env                           ← Secret keys (already banaya)
│
├── app/                           ← Python files
│   ├── app.py
│   ├── api_keys.py
│   ├── auth.py
│   ├── payments.py
│   └── admin.py
│
├── templates/                     ← HTML files
│   ├── index.html
│   ├── auth.html
│   ├── dashboard.html
│   ├── pricing.html
│   └── admin_panel.html
│
├── model/                         ← Already hai
│   ├── shield_model.pkl
│   └── vectorizer.pkl
│
└── requirements.txt
```

---

## STEP 1 — Files sahi jagah rakho

Terminal kholo aur ye commands chalo:

```bash
# Root folder pe jao
cd ~/Desktop/prompt-injection-project

# Folders banao agar nahi hain
mkdir -p app templates static

# Python files → app/ folder mein
# HTML files → templates/ folder mein
```

---

## STEP 2 — .env file root mein rakho

```
prompt-injection-project/
└── .env    ← YAHAN, app/ ke bahar
```

---

## STEP 3 — Dependencies install karo

```bash
cd ~/Desktop/prompt-injection-project
pip install flask flask-cors PyJWT python-dotenv razorpay joblib scikit-learn --break-system-packages
```

---

## STEP 4 — App chalao

```bash
cd ~/Desktop/prompt-injection-project/app
python app.py
```

### Ye dikhega:
```
🛡️  ShieldPrompt API Server v4.0
===============================
🌐 Landing:    http://localhost:5000/
🔐 Auth:       http://localhost:5000/login
📊 Dashboard:  http://localhost:5000/dashboard
💳 Payment:    http://localhost:5000/payment
👨‍💼 Admin:      http://localhost:5000/admin
```

---

## STEP 5 — Browser mein kholo

```
http://localhost:5000/
```

---

## Agar koi error aaye:

### "ModuleNotFoundError: No module named 'flask'"
```bash
pip install flask flask-cors PyJWT python-dotenv --break-system-packages
```

### "ModuleNotFoundError: No module named 'jwt'"
```bash
pip install PyJWT --break-system-packages
```

### "Template not found"
- Check karo: HTML files `templates/` folder mein hain?
- `app.py` `app/` folder mein hai?

### Port already in use
```bash
# Mac/Linux
kill $(lsof -ti:5000)
# Phir dobara chalao
python app.py
```

---

## Test karo — Sign Up karo:

1. `http://localhost:5000/login` pe jao
2. "Create account" tab click karo
3. Name, email, password bhar do
4. Submit karo
5. Dashboard pe automatically redirect hoga ✅