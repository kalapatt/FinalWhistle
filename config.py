"""
FinalWhistle — Central configuration
All constants, weights, and settings live here.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── API credentials ────────────────────────────────────────────────────────
SUPABASE_URL        = os.getenv("SUPABASE_URL", "https://mbtmimfhjepwhpyaztqn.supabase.co")
SUPABASE_ANON_KEY   = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")
ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY")
API_FOOTBALL_KEY    = os.getenv("API_FOOTBALL_KEY")

# ── API-Football ───────────────────────────────────────────────────────────
API_FOOTBALL_BASE   = "https://v3.football.api-sports.io"
WC_2026_LEAGUE_ID   = 1                  # FIFA World Cup league ID in API-Football
WC_2026_SEASON      = 2026
POLL_INTERVAL_SECS  = 300               # 5 minutes between live polls on match days

# ── Ensemble weights (must sum to 1.0) ────────────────────────────────────
MODEL_WEIGHTS = {
    "elo":     0.25,
    "poisson": 0.30,
    "xgb":     0.30,
    "form":    0.15,
}

# ── ELO settings ──────────────────────────────────────────────────────────
ELO_K_FACTOR        = 32               # Points exchanged per match
ELO_HOME_ADVANTAGE  = 0                # World Cup is neutral venue
ELO_DEFAULT         = 1500

# ── Poisson / Dixon-Coles ─────────────────────────────────────────────────
POISSON_MAX_GOALS   = 8                # Max goals to compute in distribution
DIXON_COLES_RHO     = -0.13            # Low-score correction parameter

# ── Form / momentum ───────────────────────────────────────────────────────
FORM_WINDOW         = 5                # Last N matches for form calculation
FORM_DECAY          = 0.85             # Recency weight decay per match back

# ── XGBoost ───────────────────────────────────────────────────────────────
XGB_MODEL_PATH      = "models/xgb_model.json"
XGB_SCALER_PATH     = "models/scaler.pkl"
XGB_FEATURES = [
    "elo_diff",
    "avg_goals_for_1", "avg_goals_against_1",
    "avg_goals_for_2", "avg_goals_against_2",
    "avg_xg_for_1", "avg_xg_against_1",
    "avg_xg_for_2", "avg_xg_against_2",
    "form_score_1", "form_score_2",
    "rest_days_1", "rest_days_2",
    "confederation_same",
    "stage_encoded",
]

# ── Confidence scoring ─────────────────────────────────────────────────────
# Confidence = 100 * (1 - normalised inter-model std dev)
CONFIDENCE_MIN      = 45
CONFIDENCE_MAX      = 92

# ── Reasoning (Claude) ────────────────────────────────────────────────────
REASONING_MODEL     = "claude-sonnet-4-6"
REASONING_MAX_TOKENS = 400

# ── Stages ────────────────────────────────────────────────────────────────
STAGE_ORDER = ["group", "r16", "qf", "sf", "final"]
STAGE_ENCODED = {s: i for i, s in enumerate(STAGE_ORDER)}
