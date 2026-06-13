"""
FinalWhistle — Reasoning engine
Calls Claude API with structured model outputs to generate match analysis.
"""
import json
import logging

import anthropic

from config import ANTHROPIC_API_KEY, REASONING_MODEL, REASONING_MAX_TOKENS

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """You are an elite football data scientist for the FinalWhistle World Cup prediction engine.
Your role is to generate concise, data-grounded analytical reasoning for match predictions.
Write 3–4 sentences only. Be specific: name real tactical strengths, squad depth, historical patterns,
and what the statistical edge means in context. Do not be vague. Do not use clichés like "both teams
will be looking to". Return plain text only — no JSON, no markdown."""


def generate_reasoning(
    team1: str,
    team2: str,
    stage: str,
    prediction: dict,
    team1_data: dict,
    team2_data: dict,
) -> str:
    """
    Generate analytical reasoning text for a match prediction.

    Args:
        team1, team2: Team names
        stage: Match stage (qf, sf, final)
        prediction: Full ensemble prediction dict (win_prob, xg1, model_breakdown, etc.)
        team1_data: Dict with elo, confederation, form summary
        team2_data: Same for team2

    Returns:
        3–4 sentence reasoning string
    """
    stage_name = {"qf": "Quarter Final", "sf": "Semi Final", "final": "Final",
                  "r16": "Round of 16", "group": "Group Stage"}.get(stage, stage)

    mb = prediction.get("model_breakdown", {})
    elo_diff = team1_data.get("elo", 1500) - team2_data.get("elo", 1500)

    prompt = f"""Generate analytical reasoning for this World Cup {stage_name} prediction:

MATCH: {team1} vs {team2}

ENSEMBLE PREDICTION:
- Win probability ({team1}): {prediction['win_prob']*100:.1f}%
- Draw probability: {prediction['draw_prob']*100:.1f}%
- Win probability ({team2}): {prediction['loss_prob']*100:.1f}%
- Predicted score: {team1} {prediction['predicted_score1']}–{prediction['predicted_score2']} {team2}
- Expected goals: {prediction['xg1']} xG vs {prediction['xg2']} xG
- Model confidence: {prediction['confidence']}%

MODEL BREAKDOWN (win prob for {team1}):
- ELO model ({team1_data.get('elo', 1500)} vs {team2_data.get('elo', 1500)}, diff={elo_diff:+.0f}): {mb.get('elo', {}).get('win', 0)*100:.1f}%
- Poisson/Dixon-Coles: {mb.get('poisson', {}).get('win', 0)*100:.1f}%
- XGBoost: {mb.get('xgb', {}).get('win', 0)*100:.1f}%
- Form/Momentum (momentum {mb.get('form', {}).get('momentum1', 0.5):.2f} vs {mb.get('form', {}).get('momentum2', 0.5):.2f}): {mb.get('form', {}).get('win', 0)*100:.1f}%

TEAM CONTEXT:
- {team1}: ELO {team1_data.get('elo', 1500)}, Confederation {team1_data.get('confederation', 'UEFA')}
- {team2}: ELO {team2_data.get('elo', 1500)}, Confederation {team2_data.get('confederation', 'UEFA')}

Write 3–4 sentences of analytical reasoning grounded in these numbers."""

    try:
        message = client.messages.create(
            model=REASONING_MODEL,
            max_tokens=REASONING_MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()
    except Exception as e:
        logger.error(f"Reasoning generation failed: {e}")
        return (
            f"{team1} hold a {abs(elo_diff):.0f}-point ELO advantage, "
            f"translating to a {prediction['win_prob']*100:.0f}% win probability. "
            f"The Poisson model projects {prediction['xg1']} vs {prediction['xg2']} expected goals, "
            f"suggesting {team1 if prediction['xg1'] > prediction['xg2'] else team2} edge the attacking battle."
        )
