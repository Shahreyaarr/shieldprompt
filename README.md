# 🛡️ ShieldPrompt — India's AI Security Platform

> Protect your AI apps from prompt injection, jailbreaks & adversarial attacks in real time.
> **98% BERT accuracy · <50ms latency · ₹999/month Pro · Made in India 🇮🇳**

---

## 🚀 What is ShieldPrompt?

ShieldPrompt is an enterprise-grade API that detects and blocks prompt injection attacks before they reach your LLM. Built on fine-tuned DistilBERT trained on 41,308 real-world attack examples.

---

## 📁 Project Structure

```
shieldprompt/
├── app/
│   ├── app.py          ← Main Flask server (all routes)
│   ├── api_keys.py     ← API key system (3 tiers)
│   ├── auth.py         ← JWT login/register
│   ├── payments.py     ← Razorpay integration
│   └── admin.py        ← Super admin backend
├── templates/
│   ├── index.html      ← Landing page (light theme)
│   ├── auth.html       ← Login / Register
│   ├── dashboard.html  ← User dashboard
│   ├── pricing.html    ← Razorpay checkout
│   └── admin_panel.html← Super admin panel
├── model/
│   ├── shield_model.pkl
│   └── vectorizer.pkl
├── dataset/
├── .env.example
├── requirements.txt
├── render.yaml
└── README.md
```

---

## ⚡ Quick Start

```bash
# 1. Clone
git clone https://github.com/yourusername/shieldprompt.git
cd shieldprompt

# 2. Create virtual env
python -m venv venv
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Setup environment
cp .env.example .env
# Edit .env with your Razorpay keys & admin password

# 5. Run
cd app
python app.py
```

Open `http://localhost:5000` 🎉

---

## 🔌 API Usage

### Detect Prompt Injection

```python
import requests

response = requests.post(
    "https://api.shieldprompt.in/api/v1/check",
    headers={"X-API-Key": "sp_live_your_key_here"},
    json={"prompt": "Ignore all previous instructions..."}
)

data = response.json()
# {
#   "status": "MALICIOUS",
#   "is_malicious": true,
#   "confidence": 0.97,
#   "threat_level": "CRITICAL"
# }

if data["is_malicious"]:
    return "Request blocked 🛡️"
```

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/check` | Detect prompt injection |
| GET | `/api/v1/stats` | Usage statistics |
| GET | `/api/v1/logs` | Recent request logs |
| GET | `/api/v1/health` | Health check |
| POST | `/api/v1/auth/register` | Create account |
| POST | `/api/v1/auth/login` | Login |
| POST | `/api/v1/payments/create-order` | Start Razorpay payment |
| POST | `/api/v1/payments/verify` | Verify payment |

---

## 💰 Pricing

| Plan | Price | Requests/Day |
|------|-------|-------------|
| Free | ₹0/month | 100 |
| Pro | ₹999/month | 10,000 |
| Enterprise | Custom | Unlimited |

---

## 🧠 Model Performance

| Model | Accuracy |
|-------|----------|
| TF-IDF + Random Forest | 95.63% |
| TF-IDF + Ensemble | 96.60% |
| DistilBERT (fine-tuned) | **98.00%** |

Training data: 41,308 examples (19,617 safe + 21,691 malicious)

---

## 🌐 Deploy on Render.com

```bash
# 1. Push to GitHub
git init && git add . && git commit -m "Initial commit"
git push origin main

# 2. Go to render.com
# New → Web Service → Connect GitHub repo
# Build: pip install -r requirements.txt
# Start: cd app && gunicorn app:app --bind 0.0.0.0:$PORT

# 3. Add Environment Variables on Render:
# RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET
# ADMIN_EMAIL, ADMIN_PASSWORD
# FLASK_SECRET_KEY, JWT_SECRET
```

---

## 👨‍💼 Admin Panel

```
URL:      /admin
Email:    admin@shieldprompt.in
Password: (set in .env)
```

Features: User management, revenue dashboard, API key control, ban/unban users.

---

## 🔒 Security

- API keys stored as SHA-256 hashes (never plaintext)
- JWT tokens for user authentication
- Razorpay signature verification for payments
- DPDP Act 2023 compliant (Indian data residency)
- No prompt data stored (privacy-first)

---

## 👨‍💻 Built By

**Kamran Alam** · MSc Cyber Security · Amity University Rajasthan  
🇮🇳 Jaipur, India

---

## 📄 License

MIT License — Free to use, modify and distribute.