import pandas as pd

# Dataset load karo
df = pd.read_csv('dataset/MPDD.csv')

# Kya hai andar dekhte hain
print("📊 Dataset ka size:", df.shape)
print("\n📋 Columns:")
print(df.columns.tolist())
print("\n🔍 Pehli 5 rows:")
print(df.head())
print("\n✅ Labels (safe/malicious):")
print(df['isMalicious'].value_counts())