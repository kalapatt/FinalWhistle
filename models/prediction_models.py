"""
FinalWhistle — 4-model prediction ensemble
Models: ELO · Poisson (Dixon-Coles) · XGBoost · Form/Momentum
"""
import math
import logging
import pickle
from typing import Optional

import numpy as np
from scipy.stats import poisson
import xgboost as xgb

from config import (
    MODEL_WEIGHTS, ELO_K_FACTOR, ELO_DEFAULT,
    POISSON_MAX_GOALS, DIXON_COLES_RHO,
    FORM_WINDOW, FORM_DECAY,
    XGB_MODEL_PATH, XGB_SCALER_PATH, XGB_FEATURES,
    CONFIDENCE_MIN, CONFIDENCE_MAX, STAGE_ENCODED,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════
# 1. ELO Model  (weight: 25%)
# ══════════════════════════════════════════════════════════════════════════
class EloModel:
    """Standard ELO win probability. World Cup = neutral venue (no home advantage)."""

    @staticmethod
    def expected_score(elo_a: float, elo_b: float) -> float:
        """P(A beats B) per ELO formula."""
        return 1.0 / (1.0 + 10 ** ((elo_b - elo_a) / 400.0))

    def predict(self, elo1: float, elo2: float) -> dict:
        win  = self.expected_score(elo1, elo2)
        loss = self.expected_score(elo2, elo1)
        draw = max(0, 1 - win - loss)
        # Normalise (in tournaments draw is less likely as stage increases)
        total = win + draw + loss
        return {
            "win":  win  / total,
            "draw": draw / total,
            "loss": loss / total,
            "elo1": elo1,
            "elo2": elo2,
        }

    def update(self, elo1: float, elo2: float, score1: int, score2: int) -> tuple[float, float]:
        """Return updated ELO ratings after a completed match."""
        expected1 = self.expected_score(elo1, elo2)
        if score1 > score2:
            actual1 = 1.0
        elif score1 == score2:
            actual1 = 0.5
        else:
            actual1 = 0.0
        actual2    = 1.0 - actual1
        expected2  = 1.0 - expected1
        new_elo1   = elo1 + ELO_K_FACTOR * (actual1 - expected1)
        new_elo2   = elo2 + ELO_K_FACTOR * (actual2 - expected2)
        return round(new_elo1, 1), round(new_elo2, 1)


# ══════════════════════════════════════════════════════════════════════════
# 2. Poisson / Dixon-Coles Model  (weight: 30%)
# ══════════════════════════════════════════════════════════════════════════
class PoissonModel:
    """
    Bivariate Poisson with Dixon-Coles low-score correction.
    Outputs full scoreline distribution and win/draw/loss probabilities.
    """

    @staticmethod
    def _dc_correction(x: int, y: int, mu1: float, mu2: float, rho: float = DIXON_COLES_RHO) -> float:
        """Dixon-Coles adjustment for scores involving 0 or 1 goals."""
        if x == 0 and y == 0:
            return 1 - mu1 * mu2 * rho
        if x == 0 and y == 1:
            return 1 + mu1 * rho
        if x == 1 and y == 0:
            return 1 + mu2 * rho
        if x == 1 and y == 1:
            return 1 - rho
        return 1.0

    def score_matrix(self, xg1: float, xg2: float, max_goals: int = POISSON_MAX_GOALS) -> np.ndarray:
        """Returns (max_goals+1 × max_goals+1) matrix of P(score1=i, score2=j)."""
        matrix = np.zeros((max_goals + 1, max_goals + 1))
        for i in range(max_goals + 1):
            for j in range(max_goals + 1):
                p = (
                    poisson.pmf(i, xg1)
                    * poisson.pmf(j, xg2)
                    * self._dc_correction(i, j, xg1, xg2)
                )
                matrix[i, j] = p
        # Normalise
        matrix /= matrix.sum()
        return matrix

    def predict(self, xg1: float, xg2: float) -> dict:
        mat  = self.score_matrix(xg1, xg2)
        win  = float(np.tril(mat, -1).sum())   # score1 > score2
        draw = float(np.trace(mat))
        loss = float(np.triu(mat, 1).sum())
        # Most likely scoreline
        idx  = np.unravel_index(mat.argmax(), mat.shape)
        return {
            "win":    win,
            "draw":   draw,
            "loss":   loss,
            "xg1":    round(xg1, 2),
            "xg2":    round(xg2, 2),
            "likely_score1": int(idx[0]),
            "likely_score2": int(idx[1]),
        }

    @staticmethod
    def estimate_xg(elo1: float, elo2: float, form1: float = 0.5, form2: float = 0.5) -> tuple[float, float]:
        """
        Simple xG estimate from ELO and form.
        Average WC goals/game ≈ 2.6 total; distribute based on relative strength.
        """
        total_xg    = 2.6
        elo_ratio   = elo1 / (elo1 + elo2) if (elo1 + elo2) > 0 else 0.5
        form_adj1   = 0.7 * elo_ratio + 0.3 * form1
        form_adj2   = 1 - form_adj1
        xg1         = round(total_xg * form_adj1, 2)
        xg2         = round(total_xg * form_adj2, 2)
        return xg1, xg2


# ══════════════════════════════════════════════════════════════════════════
# 3. XGBoost Model  (weight: 30%)
# ══════════════════════════════════════════════════════════════════════════
class XGBModel:
    def __init__(self):
        self.model  = None
        self.scaler = None
        self._load()

    def _load(self):
        try:
            self.model = xgb.XGBClassifier()
            self.model.load_model(XGB_MODEL_PATH)
            with open(XGB_SCALER_PATH, "rb") as f:
                self.scaler = pickle.load(f)
            logger.info("XGBoost model loaded")
        except FileNotFoundError:
            logger.warning("XGBoost model not found — run scripts/train_model.py first")

    def is_ready(self) -> bool:
        return self.model is not None and self.scaler is not None

    def build_features(
        self,
        elo1: float, elo2: float,
        avg_goals_for_1: float, avg_goals_against_1: float,
        avg_goals_for_2: float, avg_goals_against_2: float,
        avg_xg_for_1: float, avg_xg_against_1: float,
        avg_xg_for_2: float, avg_xg_against_2: float,
        form_score_1: float, form_score_2: float,
        rest_days_1: int, rest_days_2: int,
        confederation_same: bool,
        stage: str,
    ) -> np.ndarray:
        return np.array([[
            elo1 - elo2,
            avg_goals_for_1, avg_goals_against_1,
            avg_goals_for_2, avg_goals_against_2,
            avg_xg_for_1, avg_xg_against_1,
            avg_xg_for_2, avg_xg_against_2,
            form_score_1, form_score_2,
            rest_days_1, rest_days_2,
            int(confederation_same),
            STAGE_ENCODED.get(stage, 0),
        ]])

    def predict(self, features: np.ndarray) -> dict:
        if not self.is_ready():
            return {"win": 0.45, "draw": 0.25, "loss": 0.30}  # fallback
        X_scaled = self.scaler.transform(features)
        proba    = self.model.predict_proba(X_scaled)[0]
        # Classes: 0=loss, 1=draw, 2=win (trained with this encoding)
        return {
            "win":  float(proba[2]),
            "draw": float(proba[1]),
            "loss": float(proba[0]),
        }


# ══════════════════════════════════════════════════════════════════════════
# 4. Form / Momentum Model  (weight: 15%)
# ══════════════════════════════════════════════════════════════════════════
class FormModel:
    @staticmethod
    def score(form_rows: list[dict]) -> float:
        """
        Compute a 0–1 form score from recent matches.
        W=1, D=0.5, L=0 weighted by recency (FORM_DECAY).
        Also adjusts for xG (dominant performance vs lucky win).
        """
        if not form_rows:
            return 0.5
        total_weight = 0.0
        weighted_sum = 0.0
        for i, row in enumerate(form_rows[:FORM_WINDOW]):
            weight = FORM_DECAY ** i
            base   = {"W": 1.0, "D": 0.5, "L": 0.0}.get(row.get("result", "D"), 0.5)
            # xG adjustment: if xg_for > xg_against, slight boost even on loss
            xg_for     = row.get("xg_for", 0) or 0
            xg_against = row.get("xg_against", 0) or 0
            if xg_for + xg_against > 0:
                xg_adj = (xg_for / (xg_for + xg_against) - 0.5) * 0.15
            else:
                xg_adj = 0.0
            weighted_sum  += weight * min(1.0, max(0.0, base + xg_adj))
            total_weight  += weight
        return weighted_sum / total_weight if total_weight else 0.5

    def predict(self, form1: float, form2: float) -> dict:
        total = form1 + form2 if (form1 + form2) > 0 else 1.0
        win   = form1 / total
        loss  = form2 / total
        draw  = max(0, 1 - win - loss) * 0.4  # dampen draw prob from form model
        total2 = win + draw + loss
        return {
            "win":        win  / total2,
            "draw":       draw / total2,
            "loss":       loss / total2,
            "momentum1":  round(form1, 3),
            "momentum2":  round(form2, 3),
        }


# ══════════════════════════════════════════════════════════════════════════
# Ensemble
# ══════════════════════════════════════════════════════════════════════════
class PredictionEnsemble:
    def __init__(self):
        self.elo     = EloModel()
        self.poisson = PoissonModel()
        self.xgb     = XGBModel()
        self.form    = FormModel()

    def predict(
        self,
        fixture_id: int,
        team1: str, team2: str,
        elo1: float, elo2: float,
        form_rows_1: list[dict], form_rows_2: list[dict],
        stage: str = "qf",
        rest_days_1: int = 4, rest_days_2: int = 4,
        avg_stats_1: Optional[dict] = None,
        avg_stats_2: Optional[dict] = None,
    ) -> dict:
        """Run all 4 models and combine into a single prediction dict."""

        avg1 = avg_stats_1 or {}
        avg2 = avg_stats_2 or {}

        # 1. ELO
        elo_pred = self.elo.predict(elo1, elo2)

        # 2. Form scores
        form_score_1 = self.form.score(form_rows_1)
        form_score_2 = self.form.score(form_rows_2)
        form_pred    = self.form.predict(form_score_1, form_score_2)

        # 3. Poisson xG
        xg1, xg2 = self.poisson.estimate_xg(elo1, elo2, form_score_1, form_score_2)
        # Override with real avg xG if available
        if avg1.get("avg_xg_for"):
            xg1 = avg1["avg_xg_for"]
        if avg2.get("avg_xg_for"):
            xg2 = avg2["avg_xg_for"]
        poisson_pred = self.poisson.predict(xg1, xg2)

        # 4. XGBoost
        features = self.xgb.build_features(
            elo1=elo1, elo2=elo2,
            avg_goals_for_1=avg1.get("avg_goals_for", 1.3),
            avg_goals_against_1=avg1.get("avg_goals_against", 1.0),
            avg_goals_for_2=avg2.get("avg_goals_for", 1.3),
            avg_goals_against_2=avg2.get("avg_goals_against", 1.0),
            avg_xg_for_1=avg1.get("avg_xg_for", xg1),
            avg_xg_against_1=avg1.get("avg_xg_against", xg2),
            avg_xg_for_2=avg2.get("avg_xg_for", xg2),
            avg_xg_against_2=avg2.get("avg_xg_against", xg1),
            form_score_1=form_score_1,
            form_score_2=form_score_2,
            rest_days_1=rest_days_1,
            rest_days_2=rest_days_2,
            confederation_same=avg1.get("confederation") == avg2.get("confederation"),
            stage=stage,
        )
        xgb_pred = self.xgb.predict(features)

        # ── Weighted ensemble ──────────────────────────────────────────────
        w = MODEL_WEIGHTS
        win_prob  = (
            w["elo"]     * elo_pred["win"]
            + w["poisson"] * poisson_pred["win"]
            + w["xgb"]     * xgb_pred["win"]
            + w["form"]    * form_pred["win"]
        )
        draw_prob = (
            w["elo"]     * elo_pred["draw"]
            + w["poisson"] * poisson_pred["draw"]
            + w["xgb"]     * xgb_pred["draw"]
            + w["form"]    * form_pred["draw"]
        )
        loss_prob = (
            w["elo"]     * elo_pred["loss"]
            + w["poisson"] * poisson_pred["loss"]
            + w["xgb"]     * xgb_pred["loss"]
            + w["form"]    * form_pred["loss"]
        )
        # Normalise
        total     = win_prob + draw_prob + loss_prob
        win_prob  = win_prob  / total
        draw_prob = draw_prob / total
        loss_prob = loss_prob / total

        # ── Confidence = inverse inter-model variance ──────────────────────
        win_values = [elo_pred["win"], poisson_pred["win"], xgb_pred["win"], form_pred["win"]]
        std_dev    = float(np.std(win_values))
        raw_conf   = max(0, 1 - std_dev * 4)        # maps [0, 0.25] std → [1, 0] confidence
        confidence = int(CONFIDENCE_MIN + raw_conf * (CONFIDENCE_MAX - CONFIDENCE_MIN))

        return {
            "fixture_id":        fixture_id,
            "team1":             team1,
            "team2":             team2,
            "win_prob":          round(win_prob,  4),
            "draw_prob":         round(draw_prob, 4),
            "loss_prob":         round(loss_prob, 4),
            "predicted_score1":  poisson_pred["likely_score1"],
            "predicted_score2":  poisson_pred["likely_score2"],
            "xg1":               xg1,
            "xg2":               xg2,
            "confidence":        confidence,
            "model_breakdown": {
                "elo":     elo_pred,
                "poisson": poisson_pred,
                "xgb":     xgb_pred,
                "form":    form_pred,
            },
        }
