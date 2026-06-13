"""
FinalWhistle — Kaggle World Cup data loader
Downloads and prepares the historical WC dataset for XGBoost training.

Kaggle dataset: "FIFA World Cup" by abecklas
URL: https://www.kaggle.com/datasets/abecklas/fifa-world-cup

Usage:
  1. Download from Kaggle and place CSVs in data/kaggle/
     OR run with --kaggle flag if you have kaggle CLI configured:
     python scripts/load_kaggle_data.py --kaggle

  2. Script outputs: data/wc_matches.csv  (ready for train_model.py)

Expected Kaggle files (place in data/kaggle/):
  - WorldCups.csv
  - WorldCupMatches.csv
  - WorldCupPlayers.csv
"""
import argparse
import logging
import os
import sys

import pandas as pd
import numpy as np

# Add parent dir
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── ELO ratings for each WC team, calibrated to modern ratings ────────────
# Used to backfill the feature columns for historical matches
HISTORICAL_ELO = {
    "Brazil":       1985, "Germany":      1870, "Italy":        1830,
    "Argentina":    2090, "France":       2005, "Spain":        1920,
    "England":      1930, "Netherlands":  1885, "Uruguay":      1720,
    "Sweden":       1680, "Yugoslavia":   1640, "Czechoslovakia": 1600,
    "Hungary":      1620, "Portugal":     1900, "Croatia":      1810,
    "Belgium":      1840, "Mexico":       1740, "USA":          1755,
    "Poland":       1680, "Russia":       1700, "Soviet Union": 1720,
    "Denmark":      1750, "Morocco":      1780, "South Korea":  1700,
    "Japan":        1720, "Colombia":     1710, "Senegal":      1730,
    "Switzerland":  1760, "Austria":      1640, "Scotland":     1630,
    "Chile":        1700, "Cameroon":     1570, "Nigeria":      1600,
    "Romania":      1610, "Bulgaria":     1590, "Norway":       1620,
    "Paraguay":     1660, "Turkey":       1650, "Ecuador":      1680,
    "Australia":    1640, "Iran":         1630, "Costa Rica":   1650,
    "Ghana":        1580, "Serbia":       1620, "Algeria":      1560,
    "Ivory Coast":  1590, "Tunisia":      1560, "Honduras":     1520,
    "Slovakia":     1550, "Slovenia":     1540, "New Zealand":  1500,
    "Greece":       1550, "Ukraine":      1580, "Togo":         1500,
    "Angola":       1500, "Saudi Arabia": 1590, "Qatar":        1500,
    "Canada":       1650, "Egypt":        1610, "Panama":       1520,
    "Peru":         1660, "Iceland":      1580, "Wales":        1600,
    "IR Iran":      1630,  # alias
    "Korea Republic": 1700,  # alias
    "Korea DPR":    1510,
    "West Germany": 1870,  # map to Germany ELO
    "East Germany": 1640,
    "Zaire":        1480,
    "Haiti":        1480,
    "North Korea":  1510,
    "El Salvador":  1480,
    "Cuba":         1480,
    "Bolivia":      1520,
    "Iraq":         1500,
    "United Arab Emirates": 1500,
    "China PR":     1540,
    "Senegal":      1730,
    "Trinidad and Tobago": 1500,
    "Cape Verde":   1500,
    "Bosnia and Herzegovina": 1570,
    "CRO": 1810,  # fallback
}

CONFEDERATION_MAP = {
    "Brazil": "CONMEBOL", "Argentina": "CONMEBOL", "Uruguay": "CONMEBOL",
    "Colombia": "CONMEBOL", "Chile": "CONMEBOL", "Paraguay": "CONMEBOL",
    "Peru": "CONMEBOL", "Ecuador": "CONMEBOL", "Venezuela": "CONMEBOL",
    "France": "UEFA", "Germany": "UEFA", "Italy": "UEFA", "Spain": "UEFA",
    "England": "UEFA", "Portugal": "UEFA", "Netherlands": "UEFA",
    "Belgium": "UEFA", "Croatia": "UEFA", "Denmark": "UEFA",
    "Switzerland": "UEFA", "Sweden": "UEFA", "Poland": "UEFA",
    "Russia": "UEFA", "Turkey": "UEFA", "Norway": "UEFA", "Romania": "UEFA",
    "Bulgaria": "UEFA", "Yugoslavia": "UEFA", "Czechoslovakia": "UEFA",
    "Hungary": "UEFA", "Austria": "UEFA", "Scotland": "UEFA",
    "Serbia": "UEFA", "Slovakia": "UEFA", "Slovenia": "UEFA",
    "Greece": "UEFA", "Ukraine": "UEFA", "Iceland": "UEFA",
    "Wales": "UEFA", "West Germany": "UEFA", "East Germany": "UEFA",
    "Bosnia and Herzegovina": "UEFA",
    "USA": "CONCACAF", "Mexico": "CONCACAF", "Canada": "CONCACAF",
    "Costa Rica": "CONCACAF", "Honduras": "CONCACAF", "Panama": "CONCACAF",
    "El Salvador": "CONCACAF", "Cuba": "CONCACAF", "Haiti": "CONCACAF",
    "Trinidad and Tobago": "CONCACAF",
    "Japan": "AFC", "South Korea": "AFC", "Korea Republic": "AFC",
    "Korea DPR": "AFC", "North Korea": "AFC", "Iran": "AFC",
    "IR Iran": "AFC", "Saudi Arabia": "AFC", "Australia": "AFC",
    "China PR": "AFC", "Iraq": "AFC", "United Arab Emirates": "AFC",
    "Morocco": "CAF", "Nigeria": "CAF", "Senegal": "CAF",
    "Cameroon": "CAF", "Ghana": "CAF", "Ivory Coast": "CAF",
    "Tunisia": "CAF", "Algeria": "CAF", "Egypt": "CAF",
    "Togo": "CAF", "Angola": "CAF", "Zaire": "CAF", "Cape Verde": "CAF",
    "New Zealand": "OFC", "Qatar": "AFC",
}

STAGE_MAP = {
    "Group Stage": "group", "Group 1": "group", "Group 2": "group",
    "Group 3": "group", "Group 4": "group", "Group A": "group",
    "Group B": "group", "Group C": "group", "Group D": "group",
    "Group E": "group", "Group F": "group", "Group G": "group",
    "Group H": "group", "First round": "group", "Preliminary round": "group",
    "Round of 16": "r16", "Round of 16 ": "r16",
    "Quarter-finals": "qf", "Quarter Finals": "qf", "Quarter-final": "qf",
    "Semi-finals": "sf", "Semi Finals": "sf", "Semi-final": "sf",
    "Third place": "sf",  # treat as sf for model purposes
    "Final": "final",
}


def get_elo(team: str) -> float:
    return HISTORICAL_ELO.get(team, 1600)


def get_confederation(team: str) -> str:
    return CONFEDERATION_MAP.get(team, "UEFA")


def load_kaggle_matches(data_dir: str) -> pd.DataFrame:
    path = os.path.join(data_dir, "WorldCupMatches.csv")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"WorldCupMatches.csv not found in {data_dir}\n"
            "Download from: https://www.kaggle.com/datasets/abecklas/fifa-world-cup"
        )

    df = pd.read_csv(path)
    logger.info(f"Loaded {len(df)} raw matches from Kaggle")

    # Rename columns to our schema
    df = df.rename(columns={
        "Home Team Name": "team1",
        "Away Team Name": "team2",
        "Home Team Goals": "goals1",
        "Away Team Goals": "goals2",
        "Stage": "stage_raw",
        "Year": "year",
    })

    # Drop rows without result
    df = df.dropna(subset=["goals1", "goals2"])
    df["goals1"] = df["goals1"].astype(int)
    df["goals2"] = df["goals2"].astype(int)

    # Clean team names
    df["team1"] = df["team1"].str.strip()
    df["team2"] = df["team2"].str.strip()

    # Stage encoding
    df["stage"] = df["stage_raw"].str.strip().map(STAGE_MAP).fillna("group")

    # ELO features (static historical approximation)
    df["elo1"] = df["team1"].apply(get_elo)
    df["elo2"] = df["team2"].apply(get_elo)

    # Confederation
    df["confederation1"] = df["team1"].apply(get_confederation)
    df["confederation2"] = df["team2"].apply(get_confederation)
    df["confederation_same"] = (df["confederation1"] == df["confederation2"]).astype(int)

    # Rolling averages per team (computed from match history up to that point)
    df = _add_rolling_stats(df)

    # Form scores (simplified: 5-match rolling win rate)
    df = _add_form_scores(df)

    # Rest days (no data in Kaggle set, use tournament average)
    df["rest_days_1"] = 4
    df["rest_days_2"] = 4

    # xG approximation from goals (Kaggle has no xG)
    df["avg_xg_for_1"]     = df["avg_goals_for_1"]
    df["avg_xg_against_1"] = df["avg_goals_against_1"]
    df["avg_xg_for_2"]     = df["avg_goals_for_2"]
    df["avg_xg_against_2"] = df["avg_goals_against_2"]

    # Stage encoded
    stage_order = {"group": 0, "r16": 1, "qf": 2, "sf": 3, "final": 4}
    df["stage_encoded"] = df["stage"].map(stage_order).fillna(0).astype(int)

    logger.info(f"Processed {len(df)} matches ({df['year'].min():.0f}–{df['year'].max():.0f})")
    logger.info(f"Stage distribution:\n{df['stage'].value_counts().to_string()}")

    return df


def _add_rolling_stats(df: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """Compute rolling average goals for each team up to each match."""
    df = df.copy().sort_values("year").reset_index(drop=True)

    goals_for    = {}  # team → list of goals scored
    goals_against = {}

    avg_g_for_1, avg_g_ag_1 = [], []
    avg_g_for_2, avg_g_ag_2 = [], []

    for _, row in df.iterrows():
        t1, t2 = row["team1"], row["team2"]

        # Lookup (use last `window` matches)
        def avg(lst, n=window):
            return np.mean(lst[-n:]) if lst else 1.2

        avg_g_for_1.append(avg(goals_for.get(t1, [])))
        avg_g_ag_1.append(avg(goals_against.get(t1, [])))
        avg_g_for_2.append(avg(goals_for.get(t2, [])))
        avg_g_ag_2.append(avg(goals_against.get(t2, [])))

        # Update history
        goals_for.setdefault(t1, []).append(row["goals1"])
        goals_against.setdefault(t1, []).append(row["goals2"])
        goals_for.setdefault(t2, []).append(row["goals2"])
        goals_against.setdefault(t2, []).append(row["goals1"])

    df["avg_goals_for_1"]     = avg_g_for_1
    df["avg_goals_against_1"] = avg_g_ag_1
    df["avg_goals_for_2"]     = avg_g_for_2
    df["avg_goals_against_2"] = avg_g_ag_2
    return df


def _add_form_scores(df: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """5-match rolling win rate per team."""
    df = df.copy()
    results = {}  # team → list of 1(W)/0.5(D)/0(L)

    form1_list, form2_list = [], []
    for _, row in df.iterrows():
        t1, t2 = row["team1"], row["team2"]

        def form(lst, n=window):
            return np.mean(lst[-n:]) if lst else 0.5

        form1_list.append(form(results.get(t1, [])))
        form2_list.append(form(results.get(t2, [])))

        if row["goals1"] > row["goals2"]:
            r1, r2 = 1.0, 0.0
        elif row["goals1"] == row["goals2"]:
            r1, r2 = 0.5, 0.5
        else:
            r1, r2 = 0.0, 1.0

        results.setdefault(t1, []).append(r1)
        results.setdefault(t2, []).append(r2)

    df["form_score_1"] = form1_list
    df["form_score_2"] = form2_list
    return df


def download_with_kaggle_cli(data_dir: str):
    """Download Kaggle dataset using the kaggle CLI (requires ~/.kaggle/kaggle.json)."""
    import subprocess
    os.makedirs(data_dir, exist_ok=True)
    logger.info("Downloading from Kaggle API…")
    result = subprocess.run(
        ["kaggle", "datasets", "download", "-d", "abecklas/fifa-world-cup",
         "--unzip", "-p", data_dir],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        logger.error(f"Kaggle CLI failed:\n{result.stderr}")
        raise RuntimeError("Kaggle download failed. Check ~/.kaggle/kaggle.json")
    logger.info("Download complete")


def main():
    parser = argparse.ArgumentParser(description="Load Kaggle WC data → data/wc_matches.csv")
    parser.add_argument("--kaggle", action="store_true",
                        help="Download from Kaggle API (requires kaggle CLI + credentials)")
    parser.add_argument("--data-dir", default="data/kaggle",
                        help="Directory containing Kaggle CSV files")
    parser.add_argument("--output", default="data/wc_matches.csv",
                        help="Output CSV path for train_model.py")
    args = parser.parse_args()

    if args.kaggle:
        download_with_kaggle_cli(args.data_dir)

    df = load_kaggle_matches(args.data_dir)

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    df.to_csv(args.output, index=False)
    logger.info(f"✓ Saved {len(df)} matches → {args.output}")
    logger.info("Next step: python scripts/train_model.py")


if __name__ == "__main__":
    main()
