import { useState, useEffect, useCallback } from "react";

// ── Supabase config (anon/public key — safe for frontend) ──────────────────
const SUPABASE_URL = "https://mbtmimfhjepwhpyaztqn.supabase.co";
const SUPABASE_KEY = "sb_publishable_WxKmGpwc8oPq7HOuLN0eLw_h0SSn9CM";

const supabase = {
  async query(table, params = "") {
    const res = await fetch(`${SUPABASE_URL}/rest/v1/${table}?${params}`, {
      headers: {
        apikey: SUPABASE_KEY,
        Authorization: `Bearer ${SUPABASE_KEY}`,
        "Content-Type": "application/json",
      },
    });
    if (!res.ok) throw new Error(`Supabase error: ${res.status}`);
    return res.json();
  },
};

// ── Static team metadata (flags, colours) ──────────────────────────────────
const TEAM_META = {
  Argentina:   { flag: "🇦🇷", code: "ARG", color: "#74ACDF" },
  France:      { flag: "🇫🇷", code: "FRA", color: "#002395" },
  Brazil:      { flag: "🇧🇷", code: "BRA", color: "#009C3B" },
  England:     { flag: "🏴󠁧󠁢󠁥󠁮󠁧󠁿", code: "ENG", color: "#CF081F" },
  Spain:       { flag: "🇪🇸", code: "ESP", color: "#AA151B" },
  Portugal:    { flag: "🇵🇹", code: "POR", color: "#006600" },
  Netherlands: { flag: "🇳🇱", code: "NED", color: "#FF6600" },
  Germany:     { flag: "🇩🇪", code: "GER", color: "#000000" },
  Belgium:     { flag: "🇧🇪", code: "BEL", color: "#EF3340" },
  Croatia:     { flag: "🇭🇷", code: "CRO", color: "#FF0000" },
  Morocco:     { flag: "🇲🇦", code: "MAR", color: "#006233" },
  USA:         { flag: "🇺🇸", code: "USA", color: "#B22234" },
  Mexico:      { flag: "🇲🇽", code: "MEX", color: "#006847" },
  Uruguay:     { flag: "🇺🇾", code: "URU", color: "#5EB6E4" },
  Japan:       { flag: "🇯🇵", code: "JPN", color: "#BC002D" },
  Colombia:    { flag: "🇨🇴", code: "COL", color: "#FCD116" },
  Senegal:     { flag: "🇸🇳", code: "SEN", color: "#00853F" },
  Italy:       { flag: "🇮🇹", code: "ITA", color: "#003399" },
  Switzerland: { flag: "🇨🇭", code: "SUI", color: "#FF0000" },
  Denmark:     { flag: "🇩🇰", code: "DEN", color: "#C60C30" },
  Canada:      { flag: "🇨🇦", code: "CAN", color: "#FF0000" },
  Ecuador:     { flag: "🇪🇨", code: "ECU", color: "#FFD100" },
  Australia:   { flag: "🇦🇺", code: "AUS", color: "#00008B" },
  Iran:        { flag: "🇮🇷", code: "IRN", color: "#239F40" },
  Nigeria:     { flag: "🇳🇬", code: "NGA", color: "#008751" },
  "South Korea": { flag: "🇰🇷", code: "KOR", color: "#CD2E3A" },
  "Saudi Arabia": { flag: "🇸🇦", code: "KSA", color: "#006C35" },
};

const getMeta = (name) => TEAM_META[name] || { flag: "🏳️", code: "???", color: "#334155" };

// ── Helpers ────────────────────────────────────────────────────────────────
const confidenceColor = (c) => c >= 75 ? "#4ade80" : c >= 55 ? "#facc15" : "#f87171";
const confidenceLabel = (c) => c >= 75 ? "HIGH" : c >= 55 ? "MEDIUM" : "LOW";

// ── Fallback fixtures (used until live data arrives from Supabase) ─────────
const DEMO_FIXTURES = {
  QF: [
    { id: "qf1", fixture_id: 9001, team1: "Argentina", team2: "Netherlands", stage: "qf" },
    { id: "qf2", fixture_id: 9002, team1: "France",    team2: "England",     stage: "qf" },
    { id: "qf3", fixture_id: 9003, team1: "Brazil",    team2: "Portugal",    stage: "qf" },
    { id: "qf4", fixture_id: 9004, team1: "Spain",     team2: "Germany",     stage: "qf" },
  ],
  SF: [
    { id: "sf1", fixture_id: 9005, team1: null, team2: null, stage: "sf", from: ["qf1","qf2"] },
    { id: "sf2", fixture_id: 9006, team1: null, team2: null, stage: "sf", from: ["qf3","qf4"] },
  ],
  F: [
    { id: "f1",  fixture_id: 9007, team1: null, team2: null, stage: "final", from: ["sf1","sf2"] },
  ],
};

// ── Build bracket from live Supabase matches ───────────────────────────────
function buildFixturesFromDB(rows) {
  const byStage = { qf: [], sf: [], final: [] };
  rows.forEach(m => {
    if (byStage[m.stage] !== undefined) byStage[m.stage].push(m);
  });

  // Sort each stage by fixture_id (chronological)
  Object.values(byStage).forEach(arr => arr.sort((a, b) => a.fixture_id - b.fixture_id));

  const qf = byStage.qf.map((m, i) => ({
    id: `qf${i+1}`, fixture_id: m.fixture_id,
    team1: m.team1, team2: m.team2, stage: "qf",
  }));

  // SF slots — link to QF winners in pairs
  const sf = byStage.sf.map((m, i) => ({
    id: `sf${i+1}`, fixture_id: m.fixture_id,
    team1: m.team1, team2: m.team2, stage: "sf",
    from: qf.length >= (i+1)*2 ? [`qf${i*2+1}`, `qf${i*2+2}`] : [],
  }));

  const f = byStage.final.map((m, i) => ({
    id: `f${i+1}`, fixture_id: m.fixture_id,
    team1: m.team1, team2: m.team2, stage: "final",
    from: sf.length >= 2 ? ["sf1","sf2"] : [],
  }));

  if (!qf.length && !sf.length && !f.length) return null; // fall back to demo
  return {
    QF: qf.length ? qf : DEMO_FIXTURES.QF,
    SF: sf.length ? sf : DEMO_FIXTURES.SF,
    F:  f.length  ? f  : DEMO_FIXTURES.F,
  };
}

// ══════════════════════════════════════════════════════════════════════════
// Prediction Card
// ══════════════════════════════════════════════════════════════════════════
function PredictionCard({ match, prediction, onPredict, isLoading, isLive }) {
  const [expanded, setExpanded] = useState(false);
  const t1 = getMeta(match.team1);
  const t2 = getMeta(match.team2);

  const stageName = { qf: "Quarter Final", sf: "Semi Final", final: "Final", group: "Group Stage", r16: "Round of 16" }[match.stage] || match.stage;

  // Awaiting teams from prior round
  if (!match.team1 || !match.team2) {
    return (
      <div style={cardStyle()}>
        <CardHeader stage={stageName} />
        <div style={{ padding: "32px 20px", color: "#334155", fontSize: 13, textAlign: "center" }}>
          Awaiting previous round results
        </div>
      </div>
    );
  }

  const winner = prediction?.win_prob > prediction?.loss_prob ? match.team1 : match.team2;

  return (
    <div style={cardStyle(prediction ? confidenceColor(prediction.confidence) : null)}>
      <CardHeader
        stage={stageName}
        confidence={prediction?.confidence}
        isLive={isLive}
      />

      {/* Teams + Score */}
      <div style={{ padding: "16px 20px" }}>
        {[
          { team: match.team1, meta: t1, score: prediction?.predicted_score1,
            prob: prediction?.win_prob, isWinner: prediction && winner === match.team1 },
          { team: match.team2, meta: t2, score: prediction?.predicted_score2,
            prob: prediction?.loss_prob, isWinner: prediction && winner === match.team2 },
        ].map(({ team, meta, score, prob, isWinner }, i) => (
          <div key={team} style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "10px 0",
            borderBottom: i === 0 ? "1px solid #1e293b" : "none",
            opacity: prediction && !isWinner ? 0.42 : 1,
            transition: "opacity 0.4s ease",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 26 }}>{meta.flag}</span>
              <div>
                <div style={{ color: isWinner ? "#f8fafc" : "#94a3b8", fontSize: 14, fontWeight: isWinner ? 700 : 400 }}>
                  {team}
                </div>
                {prediction && (
                  <div style={{ color: "#334155", fontSize: 10, marginTop: 2 }}>
                    {(prob * 100).toFixed(0)}% win prob
                  </div>
                )}
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {score !== undefined && score !== null && (
                <span style={{ fontSize: 30, fontWeight: 800, color: isWinner ? "#f8fafc" : "#475569", fontVariantNumeric: "tabular-nums" }}>
                  {score}
                </span>
              )}
              {isWinner && (
                <span style={{ width: 6, height: 6, borderRadius: "50%", background: confidenceColor(prediction.confidence), display: "inline-block", boxShadow: `0 0 8px ${confidenceColor(prediction.confidence)}` }} />
              )}
            </div>
          </div>
        ))}

        {/* xG row */}
        {prediction?.xg1 !== undefined && (
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 10, padding: "6px 0", borderTop: "1px solid #0f172a" }}>
            <span style={{ color: "#38bdf8", fontSize: 11, fontWeight: 600 }}>{prediction.xg1} xG</span>
            <span style={{ color: "#475569", fontSize: 10, letterSpacing: 1 }}>EXPECTED GOALS</span>
            <span style={{ color: "#38bdf8", fontSize: 11, fontWeight: 600 }}>{prediction.xg2} xG</span>
          </div>
        )}

        {/* Confidence bar */}
        {prediction && (
          <div style={{ marginTop: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
              <span style={{ color: "#475569", fontSize: 10, letterSpacing: 1, textTransform: "uppercase" }}>Confidence</span>
              <span style={{ color: confidenceColor(prediction.confidence), fontSize: 11, fontWeight: 700 }}>
                {confidenceLabel(prediction.confidence)} · {prediction.confidence}%
              </span>
            </div>
            <div style={{ height: 3, background: "#1e293b", borderRadius: 2 }}>
              <div style={{
                height: "100%", borderRadius: 2,
                width: `${prediction.confidence}%`,
                background: `linear-gradient(90deg, ${confidenceColor(prediction.confidence)}66, ${confidenceColor(prediction.confidence)})`,
                transition: "width 1s cubic-bezier(0.4,0,0.2,1)",
              }} />
            </div>
          </div>
        )}

        {/* Model breakdown */}
        {prediction?.model_breakdown && (
          <div style={{ marginTop: 12, display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px 12px" }}>
            {[
              { label: "ELO",     val: prediction.model_breakdown.elo?.win },
              { label: "Poisson", val: prediction.model_breakdown.poisson?.win },
              { label: "XGBoost",  val: prediction.model_breakdown.xgb?.win },
              { label: "Form",    val: prediction.model_breakdown.form?.win },
            ].map(({ label, val }) => val !== undefined && (
              <div key={label} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ color: "#334155", fontSize: 9, letterSpacing: 1, textTransform: "uppercase" }}>{label}</span>
                <span style={{ color: "#475569", fontSize: 10, fontWeight: 600 }}>{(val * 100).toFixed(0)}%</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Reasoning */}
      {prediction?.reasoning && (
        <div style={{ borderTop: "1px solid #1e293b" }}>
          <button onClick={() => setExpanded(!expanded)} style={reasoningBtnStyle}>
            <span>AI Analysis</span>
            <span style={{ transform: expanded ? "rotate(180deg)" : "none", transition: "transform 0.2s", display: "inline-block" }}>▾</span>
          </button>
          {expanded && (
            <div style={{ padding: "0 20px 16px", color: "#64748b", fontSize: 12, lineHeight: 1.8, borderTop: "1px solid #0c1526" }}>
              {prediction.reasoning}
            </div>
          )}
        </div>
      )}

      {/* Actions */}
      {!prediction && !isLoading && (
        <div style={{ padding: "0 20px 16px" }}>
          <button onClick={() => onPredict(match)} style={predictBtnStyle}
            onMouseEnter={e => { e.currentTarget.style.borderColor = "#38bdf8"; e.currentTarget.style.background = "#1e3a5f33"; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = "#1e3a5f"; e.currentTarget.style.background = "transparent"; }}>
            Generate Prediction
          </button>
        </div>
      )}
      {isLoading && (
        <div style={{ padding: "0 20px 16px", textAlign: "center", color: "#38bdf8", fontSize: 11, letterSpacing: 2, textTransform: "uppercase" }}>
          <span style={{ animation: "pulse 1.2s infinite", display: "inline-block" }}>Analysing match data...</span>
        </div>
      )}
    </div>
  );
}

// Sub-components
function CardHeader({ stage, confidence, isLive }) {
  return (
    <div style={{ padding: "8px 16px", background: "#060f1e", borderBottom: "1px solid #1e293b", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
      <span style={{ color: "#475569", fontSize: 10, letterSpacing: 2, textTransform: "uppercase" }}>{stage}</span>
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        {isLive && <span style={{ fontSize: 9, color: "#f87171", letterSpacing: 1, textTransform: "uppercase", animation: "pulse 1.5s infinite" }}>● LIVE</span>}
        {confidence && <span style={{ fontSize: 9, color: confidenceColor(confidence), letterSpacing: 1, textTransform: "uppercase", fontWeight: 700 }}>{confidenceLabel(confidence)}</span>}
      </div>
    </div>
  );
}

// Styles
const cardStyle = (accentColor) => ({
  background: "#0f172a",
  border: `1px solid ${accentColor ? accentColor + "33" : "#1e293b"}`,
  borderRadius: 12,
  overflow: "hidden",
  transition: "border-color 0.3s",
  boxShadow: accentColor ? `0 0 24px ${accentColor}0d` : "none",
});

const reasoningBtnStyle = {
  width: "100%", background: "none", border: "none",
  padding: "10px 20px", color: "#475569", fontSize: 11,
  letterSpacing: 1, textTransform: "uppercase", cursor: "pointer",
  display: "flex", justifyContent: "space-between", alignItems: "center",
};

const predictBtnStyle = {
  width: "100%", padding: "9px 0", background: "transparent",
  border: "1px solid #1e3a5f", borderRadius: 8, color: "#38bdf8",
  fontSize: 12, letterSpacing: 1, textTransform: "uppercase",
  cursor: "pointer", transition: "all 0.2s",
};

// ══════════════════════════════════════════════════════════════════════════
// Main App
// ══════════════════════════════════════════════════════════════════════════
const STAGES = [
  { key: "QF", label: "Quarter Finals", dbStage: "qf" },
  { key: "SF", label: "Semi Finals",    dbStage: "sf" },
  { key: "F",  label: "Final",          dbStage: "final" },
];

export default function WorldCupPredictor() {
  const [activeStage, setActiveStage]   = useState("QF");
  const [fixtures, setFixtures]         = useState(DEMO_FIXTURES);
  const [predictions, setPredictions]   = useState({});
  const [teams, setTeams]               = useState({});
  const [loadingMatch, setLoadingMatch] = useState(null);
  const [loadingAll, setLoadingAll]     = useState(false);
  const [dbConnected, setDbConnected]   = useState(false);
  const [lastRefresh, setLastRefresh]   = useState(null);

  // ── Load teams + live fixtures from Supabase ─────────────────
  useEffect(() => {
    supabase.query("teams", "select=name,elo,confederation,flag_emoji")
      .then(rows => {
        const map = {};
        rows.forEach(t => { map[t.name] = t; });
        setTeams(map);
        setDbConnected(true);
      })
      .catch(() => setDbConnected(false));

    // Try to load real fixture bracket from matches table
    supabase.query("matches", "select=fixture_id,team1,team2,stage,date&stage=in.(qf,sf,final)&order=date")
      .then(rows => {
        if (rows && rows.length > 0) {
          const live = buildFixturesFromDB(rows);
          if (live) setFixtures(live);
        }
      })
      .catch(() => {}); // silently fall back to DEMO_FIXTURES
  }, []);

  // ── Load predictions from Supabase ───────────────────────────
  const loadPredictions = useCallback(async () => {
    try {
      const rows = await supabase.query(
        "predictions",
        "select=fixture_id,team1,team2,win_prob,draw_prob,loss_prob,predicted_score1,predicted_score2,confidence,reasoning,model_breakdown,xg1,xg2,updated_at&order=updated_at.desc"
      );
      const map = {};
      rows.forEach(p => { map[p.fixture_id] = p; });
      setPredictions(map);
      setLastRefresh(new Date());

      // Cascade winners into bracket
      setFixtures(prev => cascadeWinners(prev, rows));
    } catch (e) {
      console.warn("Could not load predictions from Supabase:", e);
    }
  }, []);

  useEffect(() => {
    loadPredictions();
    // Auto-refresh every 2 minutes
    const interval = setInterval(loadPredictions, 120_000);
    return () => clearInterval(interval);
  }, [loadPredictions]);

  // ── Cascade winners through bracket ──────────────────────────
  const cascadeWinners = (prev, predRows) => {
    const winnerByFixture = {};
    predRows.forEach(p => {
      winnerByFixture[p.fixture_id] = p.win_prob >= p.loss_prob ? p.team1 : p.team2;
    });

    const next = JSON.parse(JSON.stringify(prev));

    // Map fixture_id → bracket slot id
    const fixtureToSlot = {};
    ["QF","SF","F"].forEach(stage => {
      next[stage].forEach(m => { fixtureToSlot[m.fixture_id] = m.id; });
    });

    // For each SF/F slot, fill in teams from winners of their source matches
    ["SF","F"].forEach(stage => {
      next[stage] = next[stage].map(m => {
        if (!m.from) return m;
        const [src1, src2] = m.from;
        // Find source fixtures
        const srcMatch1 = findMatchById(next, src1);
        const srcMatch2 = findMatchById(next, src2);
        const w1 = srcMatch1 ? winnerByFixture[srcMatch1.fixture_id] : null;
        const w2 = srcMatch2 ? winnerByFixture[srcMatch2.fixture_id] : null;
        return { ...m, team1: w1 || m.team1, team2: w2 || m.team2 };
      });
    });
    return next;
  };

  const findMatchById = (fixtures, slotId) => {
    for (const stage of Object.values(fixtures)) {
      const found = stage.find(m => m.id === slotId);
      if (found) return found;
    }
    return null;
  };

  // ── Generate prediction via Claude API ───────────────────────
  const generatePrediction = async (match) => {
    if (!match.team1 || !match.team2) return;
    setLoadingMatch(match.fixture_id);

    const t1 = teams[match.team1] || { elo: 1500, confederation: "UEFA" };
    const t2 = teams[match.team2] || { elo: 1500, confederation: "UEFA" };
    const stageName = { qf: "Quarter Final", sf: "Semi Final", final: "Final" }[match.stage] || match.stage;

    try {
      const resp = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: "claude-sonnet-4-6",
          max_tokens: 1000,
          system: `You are an elite football data scientist generating World Cup match predictions.
You have access to ELO ratings, Poisson models, and form data.
Always respond with ONLY valid JSON — no markdown, no explanation outside JSON.`,
          messages: [{
            role: "user",
            content: `Generate a prediction for this World Cup ${stageName}:

${match.team1} (ELO: ${t1.elo}, Confederation: ${t1.confederation})
vs
${match.team2} (ELO: ${t2.elo}, Confederation: ${t2.confederation})

ELO difference: ${(t1.elo - t2.elo).toFixed(0)} points in favour of ${t1.elo > t2.elo ? match.team1 : match.team2}

Return ONLY this JSON:
{
  "fixture_id": ${match.fixture_id},
  "team1": "${match.team1}",
  "team2": "${match.team2}",
  "win_prob": <0.0-1.0, P(${match.team1} wins)>,
  "draw_prob": <0.0-1.0>,
  "loss_prob": <0.0-1.0, P(${match.team2} wins)>,
  "predicted_score1": <integer>,
  "predicted_score2": <integer>,
  "xg1": <float, expected goals ${match.team1}>,
  "xg2": <float, expected goals ${match.team2}>,
  "confidence": <integer 45-92>,
  "reasoning": "<3-4 sentences: tactical analysis, key players, what tips the balance. Be specific — name real squad strengths, statistical edges, historical patterns.>",
  "model_breakdown": {
    "elo":     { "win": <float>, "elo1": ${t1.elo}, "elo2": ${t2.elo} },
    "poisson": { "win": <float>, "xg1": <float>, "xg2": <float> },
    "xgb":     { "win": <float> },
    "form":    { "win": <float>, "momentum1": <0-1>, "momentum2": <0-1> }
  }
}`
          }]
        })
      });

      const data = await resp.json();
      const text = data.content?.find(b => b.type === "text")?.text || "{}";
      const parsed = JSON.parse(text.replace(/```json|```/g, "").trim());

      // Save to Supabase
      await fetch(`${SUPABASE_URL}/rest/v1/predictions`, {
        method: "POST",
        headers: {
          apikey: SUPABASE_KEY,
          Authorization: `Bearer ${SUPABASE_KEY}`,
          "Content-Type": "application/json",
          Prefer: "resolution=merge-duplicates,return=representation",
        },
        body: JSON.stringify({ ...parsed, updated_at: new Date().toISOString() }),
      });

      // Refresh from DB
      await loadPredictions();

    } catch (err) {
      console.error("Prediction failed:", err);
    } finally {
      setLoadingMatch(null);
    }
  };

  const generateAll = async () => {
    setLoadingAll(true);
    const matches = fixtures[activeStage].filter(m => m.team1 && m.team2 && !predictions[m.fixture_id]);
    for (const match of matches) {
      await generatePrediction(match);
    }
    setLoadingAll(false);
  };

  const currentFixtures = fixtures[activeStage] || [];
  const champion = (() => {
    const final = fixtures.F?.[0];
    const pred  = final && predictions[final.fixture_id];
    if (!pred) return null;
    return pred.win_prob >= pred.loss_prob ? final.team1 : final.team2;
  })();

  return (
    <div style={{ minHeight: "100vh", background: "#020817", fontFamily: "'Inter', -apple-system, sans-serif", color: "#f8fafc" }}>
      <style>{`
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.35} }
        @keyframes fadeIn { from{opacity:0;transform:translateY(10px)} to{opacity:1;transform:translateY(0)} }
        * { box-sizing:border-box; margin:0; padding:0; }
        button { font-family: inherit; }
      `}</style>

      {/* ── Header ── */}
      <div style={{ borderBottom: "1px solid #0f172a", padding: "20px 28px", background: "#020817", position: "sticky", top: 0, zIndex: 10, display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontSize: 20 }}>⚽</span>
          <div>
            <h1 style={{ fontSize: 16, fontWeight: 800, letterSpacing: -0.5 }}>World Cup 2026</h1>
            <div style={{ color: "#1e3a5f", fontSize: 10, letterSpacing: 2, textTransform: "uppercase", marginTop: 1, display: "flex", gap: 8, alignItems: "center" }}>
              <span style={{ color: dbConnected ? "#4ade80" : "#f87171" }}>●</span>
              <span style={{ color: "#334155" }}>{dbConnected ? "Supabase connected" : "Offline mode"}</span>
              {lastRefresh && <span style={{ color: "#1e293b" }}>· {lastRefresh.toLocaleTimeString()}</span>}
            </div>
          </div>
        </div>

        {/* Stage tabs */}
        <div style={{ display: "flex", gap: 3, background: "#0a1628", borderRadius: 10, padding: 4 }}>
          {STAGES.map(s => (
            <button key={s.key} onClick={() => setActiveStage(s.key)} style={{
              padding: "7px 16px", borderRadius: 7, border: "none",
              background: activeStage === s.key ? "#1e3a5f" : "transparent",
              color: activeStage === s.key ? "#38bdf8" : "#475569",
              fontSize: 12, fontWeight: activeStage === s.key ? 700 : 400,
              letterSpacing: 0.5, cursor: "pointer", transition: "all 0.2s",
            }}>
              {s.label}
            </button>
          ))}
        </div>

        <button
          onClick={generateAll}
          disabled={loadingAll}
          style={{ padding: "9px 18px", background: loadingAll ? "#0a1628" : "transparent", border: "1px solid #1e3a5f", borderRadius: 8, color: "#38bdf8", fontSize: 12, fontWeight: 600, letterSpacing: 1, textTransform: "uppercase", cursor: "pointer", transition: "all 0.2s", opacity: loadingAll ? 0.6 : 1 }}
          onMouseEnter={e => !loadingAll && (e.currentTarget.style.borderColor = "#38bdf8")}
          onMouseLeave={e => (e.currentTarget.style.borderColor = "#1e3a5f")}
        >
          {loadingAll ? "Predicting..." : "Predict All →"}
        </button>
      </div>

      {/* ── Fixture grid ── */}
      <div style={{ padding: "36px 28px", display: "flex", flexDirection: "column", alignItems: "center" }}>

        {/* Stage divider */}
        <div style={{ width: "100%", maxWidth: 960, marginBottom: 28, display: "flex", alignItems: "center", gap: 16 }}>
          <div style={{ height: 1, flex: 1, background: "#1e293b" }} />
          <span style={{ color: "#334155", fontSize: 10, letterSpacing: 3, textTransform: "uppercase" }}>
            {STAGES.find(s => s.key === activeStage)?.label}
          </span>
          <div style={{ height: 1, flex: 1, background: "#1e293b" }} />
        </div>

        {/* Cards */}
        <div style={{
          display: "grid",
          gridTemplateColumns: currentFixtures.length === 1 ? "minmax(280px,400px)" : "repeat(auto-fit, minmax(280px, 340px))",
          gap: 20, justifyContent: "center", width: "100%", maxWidth: 1200,
          animation: "fadeIn 0.4s ease",
        }}>
          {currentFixtures.map(match => (
            <PredictionCard
              key={match.id}
              match={match}
              prediction={predictions[match.fixture_id]}
              onPredict={generatePrediction}
              isLoading={loadingMatch === match.fixture_id}
              isLive={false}
            />
          ))}
        </div>

        {/* Champion reveal */}
        {activeStage === "F" && champion && (
          <div style={{ marginTop: 40, padding: "28px 48px", background: "linear-gradient(135deg, #0c1f38, #0f172a)", border: "1px solid #facc1533", borderRadius: 16, textAlign: "center", animation: "fadeIn 0.6s ease", boxShadow: "0 0 48px #facc1509" }}>
            <div style={{ color: "#334155", fontSize: 10, letterSpacing: 3, marginBottom: 12, textTransform: "uppercase" }}>Predicted Champion</div>
            <div style={{ fontSize: 52, marginBottom: 8 }}>{getMeta(champion).flag}</div>
            <div style={{ fontSize: 22, fontWeight: 800, color: "#facc15", letterSpacing: -0.5 }}>{champion}</div>
            <div style={{ color: "#334155", fontSize: 11, marginTop: 8, letterSpacing: 1 }}>
              {predictions[fixtures.F[0].fixture_id]?.confidence}% model confidence
            </div>
          </div>
        )}

        {/* Hint */}
        {activeStage !== "F" && (
          <div style={{ marginTop: 32, color: "#1e293b", fontSize: 11, letterSpacing: 2, textTransform: "uppercase" }}>
            Predict this round to unlock {activeStage === "QF" ? "Semi Finals →" : "the Final →"}
          </div>
        )}
      </div>
    </div>
  );
}
