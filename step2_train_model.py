# ============================================
# ShieldPrompt - UPGRADED MODEL TRAINING
# RF + Logistic Regression + XGBoost Ensemble
# Target: 98%+ Accuracy
# ============================================

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
from xgboost import XGBClassifier
import joblib

print("🚀 ShieldPrompt Upgraded Training shuru...")
print("=" * 50)

# ── 1. DATA LOAD ─────────────────────────────
df1 = pd.read_csv('dataset/MPDD.csv')
df1 = df1[['Prompt', 'isMalicious']].copy()
df1.columns = ['text', 'label']

df2 = pd.read_csv('dataset/jailbreak_prompts.csv', on_bad_lines='skip')
df2 = df2.iloc[:, 0].to_frame()
df2.columns = ['text']
df2['label'] = 1

df3 = pd.read_csv('dataset/malignant.csv', on_bad_lines='skip')
df3 = df3.iloc[:, 0].to_frame()
df3.columns = ['text']
df3['label'] = 1

df = pd.concat([df1, df2, df3], ignore_index=True)
df = df.dropna().drop_duplicates()
df['text'] = df['text'].astype(str)

print(f"📊 Total data: {len(df)} examples")
print(f"✅ Safe:      {len(df[df['label']==0])}")
print(f"🚨 Malicious: {len(df[df['label']==1])}")

# ── 2. TF-IDF UPGRADED ───────────────────────
# max_features: 10000 → 50000 (zyada words seekhega)
# ngram_range: (1,3) = single words + pairs + triplets
# sublinear_tf: common words ka weight kam karo
print("\n⚙️  TF-IDF vectorizing...")
vectorizer = TfidfVectorizer(
    max_features=50000,
    ngram_range=(1, 3),
    sublinear_tf=True,
    min_df=2
)
X = vectorizer.fit_transform(df['text'])
y = df['label']

# ── 3. TRAIN / TEST SPLIT ────────────────────
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)
print(f"📚 Training: {X_train.shape[0]} | 🧪 Testing: {X_test.shape[0]}")

# ── 4. TEEN MODELS ───────────────────────────

# Model 1: Random Forest — 300 trees ek saath vote karte hain
print("\n🌲 Model 1: Random Forest (300 trees)")
rf = RandomForestClassifier(
    n_estimators=300,
    random_state=42,
    n_jobs=-1
)

# Model 2: Logistic Regression — text ke liye bahut powerful
print("📈 Model 2: Logistic Regression")
lr = LogisticRegression(
    max_iter=1000,
    C=5.0,
    random_state=42
)

# Model 3: XGBoost — trees series mein seekhte hain
# Pehla tree galti karta hai → doosra tree us galti ko sudharta hai
# Isliye bahut zyada accurate!
print("⚡ Model 3: XGBoost (series learning)")
xgb = XGBClassifier(
    n_estimators=200,
    learning_rate=0.1,
    max_depth=6,
    random_state=42,
    eval_metric='logloss',
    n_jobs=-1
)

# ── 5. ENSEMBLE VOTING ───────────────────────
# Teeno models milke vote karte hain
# RF: MALICIOUS + LR: MALICIOUS + XGB: MALICIOUS = FINAL: MALICIOUS ✅
# 2 vs 1 majority se decide hota hai
print("\n🗳️  Ensemble Voting Classifier bana raha hai...")
ensemble = VotingClassifier(
    estimators=[
        ('random_forest', rf),
        ('logistic_regression', lr),
        ('xgboost', xgb),
    ],
    voting='soft'  # confidence scores se vote — zyada accurate
)

print("\n⏳ Training ho raha hai... (5-8 min, teeno models train honge)")
ensemble.fit(X_train, y_train)

# ── 6. ACCURACY ──────────────────────────────
y_pred = ensemble.predict(X_test)
accuracy = accuracy_score(y_test, y_pred)

print("\n" + "=" * 50)
print(f"🎯 FINAL ACCURACY: {accuracy*100:.2f}%")
print("=" * 50)
print(classification_report(y_test, y_pred, target_names=['Safe', 'Malicious']))

# ── 7. SAVE ──────────────────────────────────
joblib.dump(ensemble, 'model/shield_model.pkl')
joblib.dump(vectorizer, 'model/vectorizer.pkl')

print(f"✅ Upgraded model saved!")
print(f"📈 Improvement: 95.63% → {accuracy*100:.2f}%")
print("🎉 Training complete!")