# FinalWhistle — Setup Guide

## Repo structure

```
FinalWhistle/
├── config.py                    ← All settings and constants
├── data_layer.py                ← API-Football + Supabase client
├── live_updater.py              ← Scheduler (run this on your server)
├── reasoning_engine.py          ← Claude reasoning layer
├── requirements.txt
├── .env.example                 ← Copy to .env and fill keys
├── models/
│   └── prediction_models.py    ← ELO + Poisson + XGBoost + Form
├── scripts/
│   ├── train_model.py          ← Train XGBoost
│   └── load_kaggle_data.py     ← Prepare historical training data
├── frontend/
│   └── world-cup-predictor.jsx ← React UI
└── database/
    └── supabase_schema.sql     ← Already run against Supabase
```

---

## Step 1 — Push to GitHub

```bash
cd /path/to/FinalWhistle

git init
git remote add origin https://github.com/faisalkalapatt/projects/FinalWhistle.git
git add .
git commit -m "Initial commit — FinalWhistle WC 2026 prediction engine"
git branch -M main
git push -u origin main
```

---

## Step 2 — Add API keys

```bash
cp .env.example .env
```

Edit `.env`:

```
SUPABASE_URL=https://mbtmimfhjepwhpyaztqn.supabase.co
SUPABASE_ANON_KEY=sb_publishable_WxKmGpwc8oPq7HOuLN0eLw_h0SSn9CM
SUPABASE_SECRET_KEY=<your_supabase_secret_key>
ANTHROPIC_API_KEY=<your key from console.anthropic.com>
API_FOOTBALL_KEY=<your key from api-football.com>
```

---

## Step 3 — Install Python dependencies

```bash
pip install -r requirements.txt
```

---

## Step 4 — Download Kaggle training data

**Option A — Kaggle CLI (fastest):**
```bash
pip install kaggle
# Place your kaggle.json in ~/.kaggle/
python scripts/load_kaggle_data.py --kaggle
```

**Option B — Manual download:**
1. Go to https://www.kaggle.com/datasets/abecklas/fifa-world-cup
2. Download and unzip into `data/kaggle/`
3. Run: `python scripts/load_kaggle_data.py`

This outputs `data/wc_matches.csv` (~850 historical WC matches, 1930–2022).

---

## Step 5 — Train XGBoost model

```bash
python scripts/train_model.py
# Outputs: models/xgb_model.json + models/scaler.pkl
```

Expected CV accuracy: ~62–67% (WC knockout matches are hard to predict).

---

## Step 6 — Run the live updater (local test)

```bash
python live_updater.py
```

On startup it syncs all WC 2026 fixtures from API-Football, then polls every 5 minutes.

---

## Step 7 — Deploy live_updater.py

### Option A — Railway (recommended, ~$5/month)

```bash
npm install -g @railway/cli
railway login
railway init
railway up
```

Add environment variables in the Railway dashboard (copy from .env).

### Option B — Fly.io (free tier)

```bash
brew install flyctl
fly auth login
fly launch
fly secrets set SUPABASE_URL=... ANTHROPIC_API_KEY=... API_FOOTBALL_KEY=...
fly deploy
```

### Option C — VPS (Hetzner CX11, ~€4/month)

```bash
ssh root@your-server-ip
git clone https://github.com/faisalkalapatt/projects/FinalWhistle
cd FinalWhistle
pip install -r requirements.txt
cp .env.example .env && nano .env
# Install model artifacts
python scripts/load_kaggle_data.py --kaggle
python scripts/train_model.py
# Run with screen or systemd
screen -S finalwhistle
python live_updater.py
```

---

## Step 8 — Deploy the React UI

### Vercel (free)

```bash
cd frontend
npm create vite@latest . -- --template react
# Replace src/App.jsx with world-cup-predictor.jsx contents
npm install
vercel deploy
```

### Netlify (free)

Same as Vercel — push to GitHub and connect via netlify.com.

---

## Step 9 — Wire real WC 2026 fixture IDs

Once `live_updater.py` has run once, the `matches` table will be populated with real `fixture_id`s from API-Football. 

Update `DEMO_FIXTURES` in `frontend/world-cup-predictor.jsx` with the real fixture IDs from your Supabase `matches` table:

```sql
-- Run in Supabase SQL editor to see your fixture IDs
select fixture_id, team1, team2, stage, date
from matches
where stage in ('qf', 'sf', 'final')
order by date;
```

Then replace the hardcoded `fixture_id: 9001` etc. with the real values.

---

## Architecture recap

```
API-Football (poll every 5 min on match days)
    ↓
live_updater.py
    ├── Pre-match:  lineups + injuries → update ELO/Poisson/Form → new prediction
    ├── Post-match: xG + stats → update ELO + Form in Supabase
    └── Always:     predictions written to Supabase
                        ↓
              React UI reads Supabase (auto-refresh every 2 min)
```

## Model weights

| Model     | Weight | What it captures                            |
|-----------|--------|---------------------------------------------|
| ELO       | 25%    | Long-term team quality                      |
| Poisson   | 30%    | Scoreline distribution (Dixon-Coles)        |
| XGBoost   | 30%    | Non-linear features (rest days, xG, lineup) |
| Form      | 15%    | Recency-weighted momentum                   |

**Confidence** = inverse of inter-model variance (high agreement → high confidence).
