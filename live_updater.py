"""
FinalWhistle — Live updater / scheduler
Polls API-Football every 5 minutes on match days.
- Pre-match:  fetch lineups + injuries → refresh prediction
- Post-match: fetch xG + stats → update ELO, Form, Poisson, save to Supabase
"""
import json
import logging
import time
from datetime import date, datetime

from apscheduler.schedulers.blocking import BlockingScheduler

from config import POLL_INTERVAL_SECS
from data_layer import APIFootballClient, SupabaseStore
from models.prediction_models import PredictionEnsemble, EloModel
from reasoning_engine import generate_reasoning

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("live_updater")

api    = APIFootballClient()
store  = SupabaseStore()
models = PredictionEnsemble()


# ── Helpers ───────────────────────────────────────────────────────────────
def parse_xg_from_stats(stats: list[dict], team_name: str) -> float:
    """Extract xG for a given team from fixture statistics response."""
    for team_stats in stats:
        if team_stats["team"]["name"] == team_name:
            for stat in team_stats.get("statistics", []):
                if "Expected Goals" in stat.get("type", "") or stat.get("type") == "expected_goals":
                    try:
                        return float(stat["value"] or 0)
                    except (TypeError, ValueError):
                        pass
    return 0.0


def teams_data(team1: str, team2: str) -> tuple[dict, dict]:
    """Fetch team records from Supabase."""
    all_teams = store.get_all_teams()
    t1 = all_teams.get(team1, {"elo": 1500, "confederation": "UEFA"})
    t2 = all_teams.get(team2, {"elo": 1500, "confederation": "UEFA"})
    return t1, t2


def run_prediction(match: dict):
    """Generate and save a full prediction for a match."""
    fixture_id = match["fixture_id"]
    team1, team2 = match["team1"], match["team2"]
    t1, t2 = teams_data(team1, team2)

    form1 = store.get_team_form(team1)
    form2 = store.get_team_form(team2)

    pred = models.predict(
        fixture_id=fixture_id,
        team1=team1, team2=team2,
        elo1=t1.get("elo", 1500),
        elo2=t2.get("elo", 1500),
        form_rows_1=form1,
        form_rows_2=form2,
        stage=match.get("stage", "qf"),
    )

    reasoning = generate_reasoning(team1, team2, match.get("stage", "qf"), pred, t1, t2)
    pred["reasoning"] = reasoning
    pred["model_breakdown"] = json.dumps(pred["model_breakdown"])  # JSONB

    store.upsert_prediction(pred)
    logger.info(f"✓ Prediction saved: {team1} {pred['predicted_score1']}–{pred['predicted_score2']} {team2} (confidence {pred['confidence']}%)")


def post_match_update(match: dict):
    """After a match finishes: update ELO, save form, mark prediction result."""
    fixture_id = match["fixture_id"]
    team1, team2 = match["team1"], match["team2"]
    score1, score2 = match.get("goals1"), match.get("goals2")

    if score1 is None or score2 is None:
        logger.warning(f"No final score available for fixture {fixture_id}, skipping post-match update")
        return

    # Get real xG from API stats
    stats = api.get_fixture_stats(fixture_id)
    xg1   = parse_xg_from_stats(stats, team1) or match.get("xg1", 0)
    xg2   = parse_xg_from_stats(stats, team2) or match.get("xg2", 0)

    # Update ELO
    t1, t2 = teams_data(team1, team2)
    new_elo1, new_elo2 = models.elo.update(
        t1.get("elo", 1500), t2.get("elo", 1500), score1, score2
    )
    store.update_team_elo(team1, new_elo1)
    store.update_team_elo(team2, new_elo2)
    logger.info(f"ELO updated: {team1} {t1['elo']} → {new_elo1} | {team2} {t2['elo']} → {new_elo2}")

    # Save form
    result1 = "W" if score1 > score2 else ("D" if score1 == score2 else "L")
    result2 = "W" if score2 > score1 else ("D" if score2 == score1 else "L")
    match_date = match.get("date", date.today().isoformat())

    store.upsert_form({
        "team_name": team1, "match_date": match_date,
        "result": result1, "xg_for": xg1, "xg_against": xg2,
        "goals_for": score1, "goals_against": score2,
        "opponent": team2, "stage": match.get("stage"),
    })
    store.upsert_form({
        "team_name": team2, "match_date": match_date,
        "result": result2, "xg_for": xg2, "xg_against": xg1,
        "goals_for": score2, "goals_against": score1,
        "opponent": team1, "stage": match.get("stage"),
    })

    # Mark prediction accuracy
    store.mark_prediction_result(fixture_id, score1, score2)

    # Now re-predict any upcoming matches involving the newly-ELO-updated teams
    logger.info(f"Post-match update complete for {team1} vs {team2} ({score1}–{score2})")


# ── Poll function ─────────────────────────────────────────────────────────
def poll():
    """Main polling loop: called every POLL_INTERVAL_SECS on match days."""
    today = date.today()
    logger.info(f"Poll cycle — {today.isoformat()}")

    try:
        today_fixtures = api.get_fixtures_by_date(today)
    except Exception as e:
        logger.error(f"API-Football fetch failed: {e}")
        return

    if not today_fixtures:
        logger.info("No fixtures today — nothing to do")
        return

    for f in today_fixtures:
        fixture    = f["fixture"]
        teams      = f["teams"]
        goals      = f["goals"]
        status     = fixture["status"]["short"]
        fixture_id = fixture["id"]

        match = {
            "fixture_id": fixture_id,
            "team1":      teams["home"]["name"],
            "team2":      teams["away"]["name"],
            "goals1":     goals["home"],
            "goals2":     goals["away"],
            "status":     status,
            "stage":      f["league"].get("round", "group").lower(),
            "date":       today.isoformat(),
        }

        # Upsert match record
        store.upsert_match(match)

        if status == "NS":
            # Not started: generate/refresh prediction (uses latest lineups)
            existing = store.get_prediction(fixture_id)
            if not existing:
                logger.info(f"Pre-match: generating prediction for {match['team1']} vs {match['team2']}")
                run_prediction(match)

        elif status in ("FT", "AET", "PEN"):
            # Finished: post-match update
            existing = store.get_prediction(fixture_id)
            if existing and existing.get("actual_score1") is None:
                logger.info(f"Post-match update: {match['team1']} {match['goals1']}–{match['goals2']} {match['team2']}")
                post_match_update(match)

        elif status in ("1H", "HT", "2H", "ET", "BT"):
            # Live — update status in DB, don't re-predict
            logger.info(f"LIVE: {match['team1']} {match['goals1'] or 0}–{match['goals2'] or 0} {match['team2']} [{status}]")


# ── Entry point ───────────────────────────────────────────────────────────
def main():
    logger.info("FinalWhistle live updater starting…")

    # Sync all WC 2026 fixture IDs on startup
    logger.info("Syncing WC 2026 fixtures from API-Football…")
    try:
        store.sync_fixtures_from_api(api)
    except Exception as e:
        logger.warning(f"Fixture sync failed (continuing): {e}")

    # Run once immediately
    poll()

    # Then schedule
    scheduler = BlockingScheduler()
    scheduler.add_job(poll, "interval", seconds=POLL_INTERVAL_SECS, id="poll")
    logger.info(f"Scheduler running — polling every {POLL_INTERVAL_SECS}s")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Updater stopped")


if __name__ == "__main__":
    main()
