# ============================================
# ShieldPrompt - BERT MODEL TRAINING
# Google ka BERT model use karke 98-99% target
# ============================================

import pandas as pd
import torch
from torch.utils.data import Dataset, DataLoader
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from torch.optim import AdamW
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
import numpy as np
import joblib
import os

print("🚀 ShieldPrompt BERT Training shuru...")
print("=" * 55)

# ── DEVICE CHECK ─────────────────────────────
# Mac M-chip pe MPS (Metal) use hoga — bahut fast!
if torch.backends.mps.is_available():
    device = torch.device("mps")
    print("⚡ Mac M-chip detected! MPS acceleration ON")
elif torch.cuda.is_available():
    device = torch.device("cuda")
    print("⚡ GPU detected!")
else:
    device = torch.device("cpu")
    print("💻 CPU mode")

print(f"🖥️  Device: {device}")

# ── 1. DATA LOAD ─────────────────────────────
print("\n📂 Data load ho raha hai...")
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

print(f"📊 Total: {len(df)} | ✅ Safe: {len(df[df['label']==0])} | 🚨 Malicious: {len(df[df['label']==1])}")

# ── 2. TRAIN / TEST SPLIT ────────────────────
X_train, X_test, y_train, y_test = train_test_split(
    df['text'].tolist(),
    df['label'].tolist(),
    test_size=0.2,
    random_state=42,
    stratify=df['label']
)
print(f"📚 Train: {len(X_train)} | 🧪 Test: {len(X_test)}")

# ── 3. TOKENIZER ─────────────────────────────
# BERT ke liye text ko tokens mein todna padta hai
# DistilBERT = BERT ka chhota version — same accuracy, faster!
print("\n🔤 Tokenizer load ho raha hai (pehli baar download hoga ~250MB)...")
MODEL_NAME = "distilbert-base-uncased"
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
print("✅ Tokenizer ready!")

# ── 4. DATASET CLASS ─────────────────────────
class PromptDataset(Dataset):
    def __init__(self, texts, labels, tokenizer, max_len=128):
        self.encodings = tokenizer(
            texts,
            truncation=True,
            padding=True,
            max_length=max_len,
            return_tensors='pt'
        )
        self.labels = torch.tensor(labels, dtype=torch.long)

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        return {
            'input_ids':      self.encodings['input_ids'][idx],
            'attention_mask': self.encodings['attention_mask'][idx],
            'labels':         self.labels[idx]
        }

print("\n⚙️  Dataset prepare ho raha hai...")
train_dataset = PromptDataset(X_train, y_train, tokenizer)
test_dataset  = PromptDataset(X_test,  y_test,  tokenizer)

train_loader = DataLoader(train_dataset, batch_size=32, shuffle=True)
test_loader  = DataLoader(test_dataset,  batch_size=64)

# ── 5. MODEL LOAD ────────────────────────────
print("\n🧠 DistilBERT model load ho raha hai...")
model = AutoModelForSequenceClassification.from_pretrained(
    MODEL_NAME,
    num_labels=2
)
model = model.to(device)
print("✅ Model ready!")

# ── 6. TRAINING ──────────────────────────────
optimizer = AdamW(model.parameters(), lr=2e-5)
EPOCHS = 3

print(f"\n⏳ Training shuru... ({EPOCHS} epochs)")
print("Har epoch mein accuracy dikhega\n")

for epoch in range(EPOCHS):
    model.train()
    total_loss = 0
    for i, batch in enumerate(train_loader):
        input_ids      = batch['input_ids'].to(device)
        attention_mask = batch['attention_mask'].to(device)
        labels         = batch['labels'].to(device)

        optimizer.zero_grad()
        outputs = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
        loss    = outputs.loss
        loss.backward()
        optimizer.step()

        total_loss += loss.item()
        if (i + 1) % 50 == 0:
            print(f"  Epoch {epoch+1} | Batch {i+1}/{len(train_loader)} | Loss: {total_loss/(i+1):.4f}")

    # Epoch ke baad accuracy check
    model.eval()
    all_preds, all_labels = [], []
    with torch.no_grad():
        for batch in test_loader:
            input_ids      = batch['input_ids'].to(device)
            attention_mask = batch['attention_mask'].to(device)
            labels         = batch['labels'].to(device)
            outputs        = model(input_ids=input_ids, attention_mask=attention_mask)
            preds          = torch.argmax(outputs.logits, dim=1)
            all_preds.extend(preds.cpu().numpy())
            all_labels.extend(labels.cpu().numpy())

    acc = accuracy_score(all_labels, all_preds)
    print(f"\n🎯 Epoch {epoch+1} Accuracy: {acc*100:.2f}%\n")

# ── 7. FINAL REPORT ──────────────────────────
print("=" * 55)
print(f"🏆 FINAL BERT ACCURACY: {acc*100:.2f}%")
print("=" * 55)
print(classification_report(all_labels, all_preds, target_names=['Safe', 'Malicious']))

# ── 8. SAVE ──────────────────────────────────
os.makedirs('model/bert', exist_ok=True)
model.save_pretrained('model/bert')
tokenizer.save_pretrained('model/bert')
print("✅ BERT Model saved in model/bert/")
print("🎉 BERT Training complete!")