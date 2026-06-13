"""
FinalWhistle — Data layer
Handles all API-Football requests and Supabase read/write operations.
"""
import logging
from datetime import date, datetime, timedelta
from typing import Optional

import requests
from supabase import create_client, Client

from config import (
    SUPABASE_URL, SUPABASE_SECRET_KEY,
    API_FOOTBALL_BASE, API_FOOTBALL_KEY,
    WC_2026_LEAGUE_ID, WC_2026_SEASON,
)

logger = logging.getLogger(__name__)

# ── Supabase client (service role — bypasses RLS) ─────────────────────────
def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)


# ══════════════════════════════════════════════════════════════════════════
# API-Football client
# ══════════════════════════════════════════════════════════════════════════
class APIFootballClient:
    def __init__(self):
        self.base    = API_FOOTBALL_BASE
        self.headers = {
            "x-apisports-key": API_FOOTBALL_KEY,
            "x-rapidapi-host": "v3.football.api-sports.io",
        }

    def _get(self, endpoint: str, params: dict) -> dict:
        url = f"{self.base}/{endpoint}"
        resp = requests.get(url, headers=self.headers, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("errors"):
            raise ValueError(f"API-Football error: {data['errors']}")
        return data

    # ── Fixtures ──────────────────────────────────────────────────────────
    def get_fixtures_by_date(self, match_date: date) -> list[dict]:
        data = self._get("fixtures", {
            "league": WC_2026_LEAGUE_ID,
            "season": WC_2026_SEASON,
            "date":   match_date.isoformat(),
        })
        return data.get("response", [])

    def get_fixture(self, fixture_id: int) -> Optional[dict]:
        data = self._get("fixtures", {"id": fixture_id})
        resp = data.get("response", [])
        return resp[0] if resp else None

    def get_all_wc_fixtures(self) -> list[dict]:
        """Fetch the full WC 2026 bracket."""
        data = self._get("fixtures", {
            "league": WC_2026_LEAGUE_ID,
            "season": WC_2026_SEASON,
        })
        return data.get("response", [])

    # ── Statistics ────────────────────────────────────────────────────────
    def get_fixture_stats(self, fixture_id: int) -> list[dict]:
        data = self._get("fixtures/statistics", {"fixture": fixture_id})
        return data.get("response", [])

    def get_fixture_events(self, fixture_id: int) -> list[dict]:
        data = self._get("fixtures/events", {"fixture": fixture_id})
        return data.get("response", [])

    # ── Lineups & injuries ────────────────────────────────────────────────
    def get_lineups(self, fixture_id: int) -> list[dict]:
        data = self._get("fixtures/lineups", {"fixture": fixture_id})
        return data.get("response", [])

    def get_injuries(self, fixture_id: int) -> list[dict]:
        data = self._get("injuries", {
            "fixture": fixture_id,
            "league":  WC_2026_LEAGUE_ID,
            "season":  WC_2026_SEASON,
        })
        return data.get("response", [])

    # ── Player stats ──────────────────────────────────────────────────────
    def get_player_stats(self, fixture_id: int) -> list[dict]:
        data = self._get("fixtures/players", {"fixture": fixture_id})
        return data.get("response", [])


# ══════════════════════════════════════════════════════════════════════════
# Supabase helpers
# ══════════════════════════════════════════════════════════════════════════
class SupabaseStore:
    def __init__(self):
        self.db = get_supabase()

    # ── Teams ──────────────────────────────────────────────────────────────
    def get_all_teams(self) -> dict[str, dict]:
        rows = self.db.table("teams").select("*").execute().data
        return {r["name"]: r for r in rows}

    def update_team_elo(self, team_name: str, new_elo: float):
        self.db.table("teams").update({"elo": round(new_elo, 1)}).eq("name", team_name).execute()
        logger.debug(f"ELO updated: {team_name} → {new_elo:.1f}")

    # ── Matches ────────────────────────────────────────────────────────────
    def upsert_match(self, match_data: dict):
        self.db.table("matches").upsert(match_data, on_conflict="fixture_id").execute()

    def get_matches_by_stage(self, stage: str) -> list[dict]:
        return self.db.table("matches").select("*").eq("stage", stage).execute().data

    def get_match(self, fixture_id: int) -> Optional[dict]:
        rows = self.db.table("matches").select("*").eq("fixture_id", fixture_id).execute().data
        return rows[0] if rows else None

    def get_today_matches(self) -> list[dict]:
        today = date.today().isoformat()
        return (
            self.db.table("matches")
            .select("*")
            .eq("date", today)
            .neq("status", "FT")
            .execute()
            .data
        )

    # ── Predictions ────────────────────────────────────────────────────────
    def upsert_prediction(self, pred: dict):
        pred["updated_at"] = datetime.utcnow().isoformat()
        self.db.table("predictions").upsert(pred, on_conflict="fixture_id").execute()
        logger.info(f"Prediction saved: {pred['team1']} vs {pred['team2']} (fixture {pred['fixture_id']})")

    def get_prediction(self, fixture_id: int) -> Optional[dict]:
        rows = self.db.table("predictions").select("*").eq("fixture_id", fixture_id).execute().data
        return rows[0] if rows else None

    def mark_prediction_result(self, fixture_id: int, score1: int, score2: int):
        pred = self.get_prediction(fixture_id)
        if not pred:
            return
        winner_predicted = pred["team1"] if pred["win_prob"] >= pred["loss_prob"] else pred["team2"]
        if score1 > score2:
            actual_winner = pred["team1"]
        elif score2 > score1:
            actual_winner = pred["team2"]
        else:
            actual_winner = None  # draw
        was_correct = actual_winner == winner_predicted if actual_winner else pred["draw_prob"] > 0.3
        self.db.table("predictions").update({
            "actual_score1": score1,
            "actual_score2": score2,
            "was_correct":   was_correct,
        }).eq("fixture_id", fixture_id).execute()

    # ── Team form ──────────────────────────────────────────────────────────
    def upsert_form(self, form_data: dict):
        self.db.table("team_form").upsert(form_data, on_conflict="team_name,match_date").execute()

    def get_team_form(self, team_name: str, n: int = 5) -> list[dict]:
        return (
            self.db.table("team_form")
            .select("*")
            .eq("team_name", team_name)
            .order("match_date", desc=True)
            .limit(n)
            .execute()
            .data
        )

    # ── Player stats ───────────────────────────────────────────────────────
    def upsert_player_stats(self, stats: list[dict]):
        if stats:
            self.db.table("player_stats").upsert(
                stats, on_conflict="fixture_id,player_name"
            ).execute()

    # ── Fixture sync from API-Football ────────────────────────────────────
    def sync_fixtures_from_api(self, api_client: APIFootballClient):
        """Pull all WC 2026 fixtures and store in matches table."""
        fixtures = api_client.get_all_wc_fixtures()
        for f in fixtures:
            fixture   = f["fixture"]
            teams     = f["teams"]
            goals     = f["goals"]
            stage_raw = f["league"].get("round", "group").lower()

            # Map API round strings to our stage codes
            stage_map = {
                "group stage": "group",
                "round of 16": "r16",
                "quarter-finals": "qf",
                "semi-finals": "sf",
                "final": "final",
                "3rd place final": "sf",  # treat as sf for bracket purposes
            }
            stage = next((v for k, v in stage_map.items() if k in stage_raw), "group")

            self.upsert_match({
                "fixture_id":  fixture["id"],
                "team1":       teams["home"]["name"],
                "team2":       teams["away"]["name"],
                "goals1":      goals["home"],
                "goals2":      goals["away"],
                "stage":       stage,
                "date":        fixture["date"][:10],
                "status":      fixture["status"]["short"],
            })
        logger.info(f"Synced {len(fixtures)} fixtures from API-Football")
