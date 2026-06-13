"""
FinalWhistle — XGBoost training script
Usage: python scripts/train_model.py [--data data/wc_matches.csv]

Trains on historical World Cup data and saves:
  models/xgb_model.json
  models/scaler.pkl
"""
import argparse
import logging
import os
import pickle
import sys

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report

# Add parent dir so we can import config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import XGB_MODEL_PATH, XGB_SCALER_PATH, XGB_FEATURES, STAGE_ENCODED

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Label encoding: 0=loss, 1=draw, 2=win (from team1 perspective) ────────
def encode_outcome(row) -> int:
    if row["goals1"] > row["goals2"]:   return 2  # win
    if row["goals1"] == row["goals2"]:  return 1  # draw
    return 0                                       # loss


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Construct the XGB_FEATURES vector for each match row.
    Expects columns: elo1, elo2, avg_goals_for_1, avg_goals_against_1, etc.
    See config.XGB_FEATURES for the full list.
    """
    df = df.copy()

    # ELO diff
    df["elo_diff"] = df["elo1"] - df["elo2"]

    # Stage encoding
    df["stage_encoded"] = df["stage"].map(STAGE_ENCODED).fillna(0).astype(int)

    # Confederation same
    df["confederation_same"] = (df["confederation1"] == df["confederation2"]).astype(int)

    # Fill missing xG with goal proxies
    for side in ["1", "2"]:
        if f"avg_xg_for_{side}" not in df.columns:
            df[f"avg_xg_for_{side}"]     = df.get(f"avg_goals_for_{side}", 1.2)
            df[f"avg_xg_against_{side}"] = df.get(f"avg_goals_against_{side}", 1.0)

        if f"form_score_{side}" not in df.columns:
            df[f"form_score_{side}"] = 0.5

        if f"rest_days_{side}" not in df.columns:
            df[f"rest_days_{side}"] = 4

    return df[XGB_FEATURES]


def train(data_path: str):
    logger.info(f"Loading training data from {data_path}")
    df = pd.read_csv(data_path)
    logger.info(f"Loaded {len(df)} matches")

    # Drop rows with missing goals (pre-tournament matches without results)
    df = df.dropna(subset=["goals1", "goals2"])
    logger.info(f"After dropping nulls: {len(df)} matches")

    # Encode outcome
    df["outcome"] = df.apply(encode_outcome, axis=1)

    X = build_features(df)
    y = df["outcome"].values

    logger.info(f"Feature matrix: {X.shape} | Classes: {np.bincount(y)}")

    # Scale
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # XGBoost
    model = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="mlogloss",
        objective="multi:softprob",
        num_class=3,
        random_state=42,
    )

    # Cross-validation
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    scores = cross_val_score(model, X_scaled, y, cv=cv, scoring="accuracy")
    logger.info(f"CV accuracy: {scores.mean():.3f} ± {scores.std():.3f}")

    # Full fit
    model.fit(X_scaled, y)
    y_pred = model.predict(X_scaled)
    logger.info("\n" + classification_report(y, y_pred, target_names=["Loss", "Draw", "Win"]))

    # Save
    os.makedirs("models", exist_ok=True)
    model.save_model(XGB_MODEL_PATH)
    with open(XGB_SCALER_PATH, "wb") as f:
        pickle.dump(scaler, f)
    logger.info(f"Model saved → {XGB_MODEL_PATH}")
    logger.info(f"Scaler saved → {XGB_SCALER_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train FinalWhistle XGBoost model")
    parser.add_argument("--data", default="data/wc_matches.csv", help="Path to training CSV")
    args = parser.parse_args()

    if not os.path.exists(args.data):
        logger.error(f"Training data not found: {args.data}")
        logger.error("Run: python scripts/load_kaggle_data.py  to prepare the data first.")
        sys.exit(1)

    train(args.data)
