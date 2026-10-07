import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, List, Optional

from config import Config

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    league TEXT NOT NULL,
    api_id INTEGER,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(name, league)
);

CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    home_team_id INTEGER REFERENCES teams(id),
    away_team_id INTEGER REFERENCES teams(id),
    match_date TEXT,
    league TEXT,
    season TEXT,
    home_goals INTEGER,
    away_goals INTEGER,
    home_shots INTEGER,
    away_shots INTEGER,
    home_corners INTEGER,
    away_corners INTEGER,
    home_possession REAL,
    away_possession REAL,
    UNIQUE(home_team_id, away_team_id, match_date)
);

CREATE TABLE IF NOT EXISTS team_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER REFERENCES teams(id),
    season TEXT NOT NULL,
    league TEXT,
    position INTEGER,
    played INTEGER DEFAULT 0,
    won INTEGER DEFAULT 0,
    drawn INTEGER DEFAULT 0,
    lost INTEGER DEFAULT 0,
    goals_for INTEGER DEFAULT 0,
    goals_against INTEGER DEFAULT 0,
    shots_on_target INTEGER DEFAULT 0,
    corners INTEGER DEFAULT 0,
    possession_avg REAL DEFAULT 0,
    home_won INTEGER DEFAULT 0,
    home_drawn INTEGER DEFAULT 0,
    home_lost INTEGER DEFAULT 0,
    home_goals_for INTEGER DEFAULT 0,
    home_goals_against INTEGER DEFAULT 0,
    away_won INTEGER DEFAULT 0,
    away_drawn INTEGER DEFAULT 0,
    away_lost INTEGER DEFAULT 0,
    away_goals_for INTEGER DEFAULT 0,
    away_goals_against INTEGER DEFAULT 0,
    UNIQUE(team_id, season)
);

CREATE TABLE IF NOT EXISTS h2h (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id_a INTEGER REFERENCES teams(id),
    team_id_b INTEGER REFERENCES teams(id),
    match_date TEXT,
    home_team TEXT,
    away_team TEXT,
    home_goals INTEGER,
    away_goals INTEGER,
    home_corners INTEGER,
    away_corners INTEGER,
    UNIQUE(team_id_a, team_id_b, match_date)
);

CREATE TABLE IF NOT EXISTS api_cache (
    cache_key TEXT PRIMARY KEY,
    data TEXT,
    fetched_at TEXT DEFAULT (datetime('now')),
    expires_at TEXT
);

CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_description TEXT,
    recommendations TEXT,
    confidence TEXT,
    probabilities TEXT,
    expected_goals REAL,
    reasoning TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS prediction_locks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    league TEXT NOT NULL,
    kickoff TEXT NOT NULL,
    locked_at TEXT NOT NULL,
    probabilities TEXT NOT NULL,
    expected_goals TEXT NOT NULL,
    recommendations TEXT NOT NULL,
    ensemble_weights TEXT NOT NULL,
    brier_scores TEXT NOT NULL,
    confidence_score INTEGER,
    confidence_breakdown TEXT,
    kelly_stakes TEXT,
    immutable_hash TEXT NOT NULL,
    UNIQUE(match_id, locked_at)
);

CREATE TABLE IF NOT EXISTS calibration_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name TEXT NOT NULL,
    league TEXT NOT NULL,
    season TEXT NOT NULL,
    date TEXT NOT NULL,
    brier_score REAL,
    log_loss REAL,
    ece REAL,
    sample_size INTEGER,
    reliability_data TEXT,
    UNIQUE(model_name, league, season, date)
);

CREATE TABLE IF NOT EXISTS clv_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    league TEXT NOT NULL,
    opening_odds TEXT,
    closing_odds TEXT,
    model_probs TEXT,
    actual_result TEXT,
    clv_home REAL,
    clv_draw REAL,
    clv_away REAL,
    beat_closing_line INTEGER,
    date TEXT NOT NULL,
    UNIQUE(match_id)
);

CREATE TABLE IF NOT EXISTS bookmaker_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bookmaker TEXT NOT NULL,
    league TEXT NOT NULL,
    period_days INTEGER NOT NULL,
    accuracy REAL,
    consistency REAL,
    clv_score REAL,
    volume INTEGER,
    last_updated TEXT NOT NULL,
    UNIQUE(bookmaker, league, period_days, last_updated)
);

CREATE TABLE IF NOT EXISTS odds_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id TEXT NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    league TEXT NOT NULL,
    kickoff TEXT NOT NULL,
    bookmaker TEXT NOT NULL,
    market TEXT NOT NULL,
    odds_home REAL,
    odds_draw REAL,
    odds_away REAL,
    odds_over REAL,
    odds_under REAL,
    odds_btts_yes REAL,
    odds_btts_no REAL,
    snapshot_at TEXT NOT NULL,
    is_sharp INTEGER DEFAULT 0,
    UNIQUE(match_id, bookmaker, market, snapshot_at)
);

CREATE INDEX IF NOT EXISTS idx_matches_teams ON matches(home_team_id, away_team_id);
CREATE INDEX IF NOT EXISTS idx_stats_team_season ON team_stats(team_id, season);
CREATE INDEX IF NOT EXISTS idx_cache_expiry ON api_cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_prediction_locks_match ON prediction_locks(match_id);
CREATE INDEX IF NOT EXISTS idx_calibration_model_league ON calibration_records(model_name, league);
CREATE INDEX IF NOT EXISTS idx_clv_match ON clv_records(match_id);
CREATE INDEX IF NOT EXISTS idx_bookmaker_scores ON bookmaker_scores(bookmaker, league);
CREATE INDEX IF NOT EXISTS idx_odds_snapshots_match ON odds_snapshots(match_id);
CREATE INDEX IF NOT EXISTS idx_odds_snapshots_time ON odds_snapshots(snapshot_at);
CREATE INDEX IF NOT EXISTS idx_odds_snapshots_sharp ON odds_snapshots(is_sharp, snapshot_at);

CREATE TABLE IF NOT EXISTS paper_portfolio (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL DEFAULT 'Default',
    initial_bankroll REAL NOT NULL DEFAULT 1000,
    current_bankroll REAL NOT NULL DEFAULT 1000,
    currency TEXT NOT NULL DEFAULT 'EUR',
    kelly_fraction REAL NOT NULL DEFAULT 0.25,
    max_bet_pct REAL NOT NULL DEFAULT 0.05,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    is_active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS paper_picks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id INTEGER NOT NULL REFERENCES paper_portfolio(id),
    match_id TEXT NOT NULL,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    league TEXT NOT NULL,
    kickoff TEXT NOT NULL,
    market TEXT NOT NULL,
    choice TEXT NOT NULL,
    odds REAL NOT NULL,
    probability REAL NOT NULL,
    edge REAL,
    kelly_stake_pct REAL,
    stake_units REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, won, lost, void, settled
    result TEXT,  -- win, loss, push
    pnl REAL,
    settled_at TEXT,
    placed_at TEXT DEFAULT (datetime('now')),
    source TEXT,  -- 'manual', 'auto', 'scheduler'
    confidence_score INTEGER,
    ensemble_weights TEXT,
    expected_goals TEXT
);

CREATE TABLE IF NOT EXISTS paper_settlements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pick_id INTEGER NOT NULL REFERENCES paper_picks(id),
    actual_result TEXT,  -- home_win, draw, away_win, over, under, btts_yes, btts_no
    actual_score TEXT,  -- "2-1"
    settled_at TEXT NOT NULL,
    pnl REAL NOT NULL,
    roi_pct REAL
);

CREATE INDEX IF NOT EXISTS idx_paper_picks_portfolio ON paper_picks(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_paper_picks_status ON paper_picks(status);
CREATE INDEX IF NOT EXISTS idx_paper_picks_kickoff ON paper_picks(kickoff);
CREATE INDEX IF NOT EXISTS idx_paper_settlements_pick ON paper_settlements(pick_id);

-- Risk Management Tables
CREATE TABLE IF NOT EXISTS risk_limits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id INTEGER NOT NULL REFERENCES paper_portfolio(id),
    limit_type TEXT NOT NULL,  -- max_exposure_league, max_exposure_market, max_correlation, max_drawdown, stop_loss_pct
    limit_value REAL NOT NULL,
    current_value REAL DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(portfolio_id, limit_type)
);

CREATE TABLE IF NOT EXISTS risk_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id INTEGER NOT NULL REFERENCES paper_portfolio(id),
    alert_type TEXT NOT NULL,  -- exposure_breach, correlation_high, drawdown_warning, stop_loss_triggered
    severity TEXT NOT NULL,    -- info, warning, critical
    message TEXT NOT NULL,
    metric_value REAL,
    limit_value REAL,
    acknowledged INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    acknowledged_at TEXT
);

CREATE TABLE IF NOT EXISTS portfolio_correlations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id INTEGER NOT NULL REFERENCES paper_portfolio(id),
    pick_id_a INTEGER NOT NULL REFERENCES paper_picks(id),
    pick_id_b INTEGER NOT NULL REFERENCES paper_picks(id),
    correlation REAL NOT NULL,
    shared_team INTEGER DEFAULT 0,      -- 1 if same team involved
    shared_league INTEGER DEFAULT 0,    -- 1 if same league
    shared_market INTEGER DEFAULT 0,    -- 1 if same market type
    calculated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(pick_id_a, pick_id_b)
);

CREATE INDEX IF NOT EXISTS idx_risk_limits_portfolio ON risk_limits(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_risk_alerts_portfolio ON risk_alerts(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_risk_alerts_ack ON risk_alerts(acknowledged);
CREATE INDEX IF NOT EXISTS idx_correlations_portfolio ON portfolio_correlations(portfolio_id);
"""


class Database:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Config.DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.executescript(SCHEMA)

    def execute(self, query: str, params: tuple = ()) -> int:
        with self._get_conn() as conn:
            cur = conn.execute(query, params)
            return cur.lastrowid

    def executemany(self, query: str, params_list: list) -> None:
        with self._get_conn() as conn:
            conn.executemany(query, params_list)

    def query(self, query: str, params: tuple = ()) -> List[dict]:
        with self._get_conn() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def query_one(self, query: str, params: tuple = ()) -> Optional[dict]:
        rows = self.query(query, params)
        return rows[0] if rows else None

    # ---------- Teams ----------
    def upsert_team(self, name: str, league: str, api_id: Optional[int] = None) -> int:
        existing = self.query_one(
            "SELECT id FROM teams WHERE name = ? AND league = ?", (name, league)
        )
        if existing:
            if api_id:
                self.execute(
                    "UPDATE teams SET api_id = ? WHERE id = ?", (api_id, existing["id"])
                )
            return existing["id"]
        return self.execute(
            "INSERT INTO teams (name, league, api_id) VALUES (?, ?, ?)",
            (name, league, api_id),
        )

    def get_team_by_name(self, name: str, league: str) -> Optional[dict]:
        return self.query_one(
            "SELECT * FROM teams WHERE name = ? AND league = ?", (name, league)
        )

    def get_all_teams(self) -> List[dict]:
        return self.query("SELECT * FROM teams ORDER BY league, name")

    # ---------- Matches ----------
    def insert_match(self, match: dict) -> None:
        self.execute(
            """INSERT OR IGNORE INTO matches
               (home_team_id, away_team_id, match_date, league, season,
                home_goals, away_goals, home_shots, away_shots,
                home_corners, away_corners, home_possession, away_possession)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                match["home_team_id"], match["away_team_id"], match["match_date"],
                match.get("league", ""), match.get("season", ""),
                match.get("home_goals"), match.get("away_goals"),
                match.get("home_shots"), match.get("away_shots"),
                match.get("home_corners"), match.get("away_corners"),
                match.get("home_possession"), match.get("away_possession"),
            ),
        )

    def get_matches_between(
        self, team_id_a: int, team_id_b: int, limit: int = 10
    ) -> List[dict]:
        return self.query(
            """SELECT * FROM matches
               WHERE (home_team_id = ? AND away_team_id = ?)
                  OR (home_team_id = ? AND away_team_id = ?)
               ORDER BY match_date DESC LIMIT ?""",
            (team_id_a, team_id_b, team_id_b, team_id_a, limit),
        )

    def get_recent_matches(self, team_id: int, limit: int = 10) -> List[dict]:
        return self.query(
            """SELECT * FROM matches
               WHERE home_team_id = ? OR away_team_id = ?
               ORDER BY match_date DESC LIMIT ?""",
            (team_id, team_id, limit),
        )

    # ---------- Team stats ----------
    def upsert_team_stats(self, team_id: int, stats: dict) -> None:
        self.execute(
            """INSERT OR REPLACE INTO team_stats
               (team_id, season, league, position, played, won, drawn, lost,
                goals_for, goals_against, shots_on_target, corners, possession_avg,
                home_won, home_drawn, home_lost, home_goals_for, home_goals_against,
                away_won, away_drawn, away_lost, away_goals_for, away_goals_against)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                team_id, stats.get("season", ""), stats.get("league", ""),
                stats.get("position"), stats.get("played", 0),
                stats.get("won", 0), stats.get("drawn", 0), stats.get("lost", 0),
                stats.get("goals_for", 0), stats.get("goals_against", 0),
                stats.get("shots_on_target", 0), stats.get("corners", 0),
                stats.get("possession_avg", 0.0),
                stats.get("home_won", 0), stats.get("home_drawn", 0),
                stats.get("home_lost", 0), stats.get("home_goals_for", 0),
                stats.get("home_goals_against", 0),
                stats.get("away_won", 0), stats.get("away_drawn", 0),
                stats.get("away_lost", 0), stats.get("away_goals_for", 0),
                stats.get("away_goals_against", 0),
            ),
        )

    def get_team_stats(self, team_id: int, season: str) -> Optional[dict]:
        return self.query_one(
            "SELECT * FROM team_stats WHERE team_id = ? AND season = ?",
            (team_id, season),
        )

    def get_all_seasons_stats(self, team_id: int) -> List[dict]:
        return self.query(
            "SELECT * FROM team_stats WHERE team_id = ? ORDER BY season",
            (team_id,),
        )

    # ---------- H2H ----------
    def insert_h2h(self, record: dict) -> None:
        self.execute(
            """INSERT OR IGNORE INTO h2h
               (team_id_a, team_id_b, match_date, home_team, away_team,
                home_goals, away_goals, home_corners, away_corners)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record["team_id_a"], record["team_id_b"], record["match_date"],
                record["home_team"], record["away_team"],
                record["home_goals"], record["away_goals"],
                record.get("home_corners"), record.get("away_corners"),
            ),
        )

    def get_h2h(self, team_id_a: int, team_id_b: int, limit: int = 10) -> List[dict]:
        return self.query(
            """SELECT * FROM h2h
               WHERE (team_id_a = ? AND team_id_b = ?)
                  OR (team_id_a = ? AND team_id_b = ?)
               ORDER BY match_date DESC LIMIT ?""",
            (team_id_a, team_id_b, team_id_b, team_id_a, limit),
        )

    # ---------- Cache ----------
    def cache_get(self, key: str) -> Optional[str]:
        row = self.query_one(
            """SELECT data FROM api_cache
               WHERE cache_key = ? AND expires_at > datetime('now')""",
            (key,),
        )
        return row["data"] if row else None

    def cache_set(self, key: str, data: Any, ttl_hours: int = 24) -> None:
        self.execute(
            """INSERT OR REPLACE INTO api_cache
               (cache_key, data, fetched_at, expires_at)
               VALUES (?, ?, datetime('now'), datetime('now', ?))""",
            (key, json.dumps(data), f"+{ttl_hours} hours"),
        )

    # ---------- Predictions ----------
    def save_prediction(self, prediction: dict) -> int:
        return self.execute(
            """INSERT INTO predictions
               (match_description, recommendations, confidence, probabilities,
                expected_goals, reasoning)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                prediction.get("match_description", ""),
                json.dumps(prediction.get("recommendations", [])),
                prediction.get("confidence", ""),
                json.dumps(prediction.get("probabilities", {})),
                prediction.get("expected_goals", 0.0),
                prediction.get("reasoning", ""),
            ),
        )

    def get_recent_predictions(self, limit: int = 20) -> List[dict]:
        return self.query(
            "SELECT * FROM predictions ORDER BY created_at DESC LIMIT ?", (limit,)
        )

    # ---------- Prediction Locks (Transparency) ----------
    def save_prediction_lock(self, lock: dict) -> int:
        return self.execute(
            """INSERT OR REPLACE INTO prediction_locks
               (match_id, home_team, away_team, league, kickoff, locked_at,
                probabilities, expected_goals, recommendations, ensemble_weights,
                brier_scores, confidence_score, confidence_breakdown, kelly_stakes, immutable_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                lock.get("match_id"),
                lock.get("home_team"),
                lock.get("away_team"),
                lock.get("league"),
                lock.get("kickoff"),
                lock.get("locked_at"),
                json.dumps(lock.get("probabilities", {})),
                json.dumps(lock.get("expected_goals", {})),
                json.dumps(lock.get("recommendations", [])),
                json.dumps(lock.get("ensemble_weights", {})),
                json.dumps(lock.get("brier_scores", {})),
                lock.get("confidence_score"),
                json.dumps(lock.get("confidence_breakdown", {})),
                json.dumps(lock.get("kelly_stakes", {})),
                lock.get("immutable_hash"),
            ),
        )

    def get_prediction_lock(self, match_id: str) -> Optional[dict]:
        return self.query_one(
            "SELECT * FROM prediction_locks WHERE match_id = ? ORDER BY locked_at DESC LIMIT 1",
            (match_id,),
        )

    def get_all_prediction_locks(self, limit: int = 100) -> List[dict]:
        return self.query(
            "SELECT * FROM prediction_locks ORDER BY locked_at DESC LIMIT ?", (limit,)
        )

    # ---------- Calibration Records ----------
    def save_calibration_record(self, record: dict) -> int:
        return self.execute(
            """INSERT OR REPLACE INTO calibration_records
               (model_name, league, season, date, brier_score, log_loss, ece, sample_size, reliability_data)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.get("model_name"),
                record.get("league"),
                record.get("season"),
                record.get("date"),
                record.get("brier_score"),
                record.get("log_loss"),
                record.get("ece"),
                record.get("sample_size"),
                json.dumps(record.get("reliability_data", {})),
            ),
        )

    def get_calibration_history(self, model_name: str = None, league: str = None, 
                                 limit: int = 100) -> List[dict]:
        query = "SELECT * FROM calibration_records WHERE 1=1"
        params = []
        if model_name:
            query += " AND model_name = ?"
            params.append(model_name)
        if league:
            query += " AND league = ?"
            params.append(league)
        query += " ORDER BY date DESC LIMIT ?"
        params.append(limit)
        return self.query(query, tuple(params))

    # ---------- CLV Records ----------
    def save_clv_record(self, record: dict) -> int:
        return self.execute(
            """INSERT OR REPLACE INTO clv_records
               (match_id, home_team, away_team, league, opening_odds, closing_odds,
                model_probs, actual_result, clv_home, clv_draw, clv_away, beat_closing_line, date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.get("match_id"),
                record.get("home_team"),
                record.get("away_team"),
                record.get("league"),
                json.dumps(record.get("opening_odds", {})),
                json.dumps(record.get("closing_odds", {})),
                json.dumps(record.get("model_probs", {})),
                record.get("actual_result"),
                record.get("clv_home"),
                record.get("clv_draw"),
                record.get("clv_away"),
                1 if record.get("beat_closing_line") else 0,
                record.get("date"),
            ),
        )

    def get_clv_history(self, league: str = None, limit: int = 500) -> List[dict]:
        query = "SELECT * FROM clv_records WHERE 1=1"
        params = []
        if league:
            query += " AND league = ?"
            params.append(league)
        query += " ORDER BY date DESC LIMIT ?"
        params.append(limit)
        return self.query(query, tuple(params))

    def get_clv_stats(self, league: str = None, days: int = 30) -> dict:
        from datetime import date, timedelta
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        
        query = "SELECT * FROM clv_records WHERE date >= ?"
        params = [cutoff]
        if league:
            query += " AND league = ?"
            params.append(league)
        
        records = self.query(query, tuple(params))
        
        if not records:
            return {"total": 0, "beat_rate": 0, "avg_clv": 0}
        
        beat = sum(1 for r in records if r["beat_closing_line"])
        avg_clv = sum(r["clv_home"] + r["clv_draw"] + r["clv_away"] for r in records) / len(records) / 3
        
        return {
            "total": len(records),
            "beat_count": beat,
            "beat_rate": round(beat / len(records) * 100, 1),
            "avg_clv": round(avg_clv * 100, 2),
        }

    # ---------- Bookmaker Scores ----------
    def save_bookmaker_score(self, record: dict) -> int:
        return self.execute(
            """INSERT OR REPLACE INTO bookmaker_scores
               (bookmaker, league, period_days, accuracy, consistency, clv_score, volume, last_updated)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.get("bookmaker"),
                record.get("league"),
                record.get("period_days"),
                record.get("accuracy"),
                record.get("consistency"),
                record.get("clv_score"),
                record.get("volume"),
                record.get("last_updated"),
            ),
        )

    def get_bookmaker_scores(self, league: str = None, period_days: int = 30) -> List[dict]:
        query = "SELECT * FROM bookmaker_scores WHERE period_days = ?"
        params = [period_days]
        if league:
            query += " AND league = ?"
            params.append(league)
        query += " ORDER BY last_updated DESC"
        return self.query(query, tuple(params))

    # ---------- Odds Snapshots (Steam Move Detection) ----------
    def save_odds_snapshot(self, snapshot: dict) -> int:
        return self.execute(
            """INSERT OR REPLACE INTO odds_snapshots
               (match_id, home_team, away_team, league, kickoff, bookmaker, market,
                odds_home, odds_draw, odds_away, odds_over, odds_under,
                odds_btts_yes, odds_btts_no, snapshot_at, is_sharp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot.get("match_id"),
                snapshot.get("home_team"),
                snapshot.get("away_team"),
                snapshot.get("league"),
                snapshot.get("kickoff"),
                snapshot.get("bookmaker"),
                snapshot.get("market"),
                snapshot.get("odds_home"),
                snapshot.get("odds_draw"),
                snapshot.get("odds_away"),
                snapshot.get("odds_over"),
                snapshot.get("odds_under"),
                snapshot.get("odds_btts_yes"),
                snapshot.get("odds_btts_no"),
                snapshot.get("snapshot_at"),
                1 if snapshot.get("is_sharp") else 0,
            ),
        )

    def get_odds_snapshots(self, match_id: str, bookmaker: str = None, 
                           market: str = None, hours_back: int = 24) -> List[dict]:
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(hours=hours_back)).isoformat()
        
        query = "SELECT * FROM odds_snapshots WHERE match_id = ? AND snapshot_at >= ?"
        params = [match_id, cutoff]
        
        if bookmaker:
            query += " AND bookmaker = ?"
            params.append(bookmaker)
        if market:
            query += " AND market = ?"
            params.append(market)
            
        query += " ORDER BY snapshot_at ASC"
        return self.query(query, tuple(params))

    def get_latest_odds(self, match_id: str, market: str = "h2h") -> List[dict]:
        return self.query(
            """SELECT * FROM odds_snapshots 
               WHERE match_id = ? AND market = ?
               ORDER BY snapshot_at DESC LIMIT 1""",
            (match_id, market),
        )

    def get_sharp_bookmakers_odds(self, match_id: str, market: str = "h2h", 
                                   hours_back: int = 6) -> List[dict]:
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(hours=hours_back)).isoformat()
        
        return self.query(
            """SELECT * FROM odds_snapshots 
               WHERE match_id = ? AND market = ? AND is_sharp = 1 AND snapshot_at >= ?
               ORDER BY bookmaker, snapshot_at ASC""",
            (match_id, market, cutoff),
        )

    # ---------- Paper Trading ----------
    def create_portfolio(self, name: str = "Default", initial_bankroll: float = 1000,
                         kelly_fraction: float = 0.25, max_bet_pct: float = 0.05,
                         currency: str = "EUR") -> int:
        return self.execute(
            """INSERT INTO paper_portfolio
               (name, initial_bankroll, current_bankroll, currency, kelly_fraction, max_bet_pct)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, initial_bankroll, initial_bankroll, currency, kelly_fraction, max_bet_pct),
        )

    def get_portfolio(self, portfolio_id: int) -> Optional[dict]:
        return self.query_one("SELECT * FROM paper_portfolio WHERE id = ?", (portfolio_id,))

    def get_active_portfolio(self) -> Optional[dict]:
        return self.query_one(
            "SELECT * FROM paper_portfolio WHERE is_active = 1 ORDER BY created_at DESC LIMIT 1"
        )

    def update_portfolio_bankroll(self, portfolio_id: int, new_bankroll: float) -> None:
        self.execute(
            "UPDATE paper_portfolio SET current_bankroll = ?, updated_at = datetime('now') WHERE id = ?",
            (new_bankroll, portfolio_id),
        )

    def get_all_portfolios(self) -> List[dict]:
        return self.query("SELECT * FROM paper_portfolio ORDER BY created_at DESC")

    def place_pick(self, pick: dict) -> int:
        return self.execute(
            """INSERT INTO paper_picks
               (portfolio_id, match_id, home_team, away_team, league, kickoff, market, choice,
                odds, probability, edge, kelly_stake_pct, stake_units, status, source,
                confidence_score, ensemble_weights, expected_goals)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                pick.get("portfolio_id"),
                pick.get("match_id"),
                pick.get("home_team"),
                pick.get("away_team"),
                pick.get("league"),
                pick.get("kickoff"),
                pick.get("market"),
                pick.get("choice"),
                pick.get("odds"),
                pick.get("probability"),
                pick.get("edge"),
                pick.get("kelly_stake_pct"),
                pick.get("stake_units"),
                pick.get("status", "pending"),
                pick.get("source", "manual"),
                pick.get("confidence_score"),
                pick.get("ensemble_weights"),
                pick.get("expected_goals"),
            ),
        )

    def get_picks(self, portfolio_id: int, status: str = None, limit: int = 100) -> List[dict]:
        query = "SELECT * FROM paper_picks WHERE portfolio_id = ?"
        params = [portfolio_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY placed_at DESC LIMIT ?"
        params.append(limit)
        return self.query(query, tuple(params))

    def get_pending_picks(self, portfolio_id: int = None) -> List[dict]:
        query = "SELECT * FROM paper_picks WHERE status = 'pending'"
        params = []
        if portfolio_id:
            query += " AND portfolio_id = ?"
            params.append(portfolio_id)
        query += " ORDER BY kickoff ASC"
        return self.query(query, tuple(params))

    def get_pick(self, pick_id: int) -> Optional[dict]:
        return self.query_one("SELECT * FROM paper_picks WHERE id = ?", (pick_id,))

    def update_pick_status(self, pick_id: int, status: str, result: str = None, 
                           pnl: float = None, settled_at: str = None) -> None:
        updates = ["status = ?"]
        params = [status]
        if result:
            updates.append("result = ?")
            params.append(result)
        if pnl is not None:
            updates.append("pnl = ?")
            params.append(pnl)
        if settled_at:
            updates.append("settled_at = ?")
            params.append(settled_at)
        params.append(pick_id)
        self.execute(
            f"UPDATE paper_picks SET {', '.join(updates)} WHERE id = ?",
            tuple(params),
        )

    def settle_pick(self, pick_id: int, actual_result: str, actual_score: str,
                    pnl: float, roi_pct: float) -> int:
        from datetime import datetime
        settled_at = datetime.now().isoformat()
        
        # Update pick
        self.execute(
            """UPDATE paper_picks SET status = 'settled', result = ?, pnl = ?, settled_at = ?
               WHERE id = ?""",
            ("win" if pnl > 0 else "loss" if pnl < 0 else "push", pnl, settled_at, pick_id),
        )
        
        # Record settlement
        return self.execute(
            """INSERT INTO paper_settlements
               (pick_id, actual_result, actual_score, settled_at, pnl, roi_pct)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (pick_id, actual_result, actual_score, settled_at, pnl, roi_pct),
        )

    def get_portfolio_performance(self, portfolio_id: int, days: int = 30) -> dict:
        from datetime import date, timedelta
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        
        picks = self.query(
            """SELECT * FROM paper_picks 
               WHERE portfolio_id = ? AND placed_at >= ? AND status = 'settled'
               ORDER BY settled_at ASC""",
            (portfolio_id, cutoff),
        )
        
        if not picks:
            return {"total_picks": 0, "wins": 0, "losses": 0, "pushes": 0, 
                    "total_staked": 0, "total_pnl": 0, "roi_pct": 0, 
                    "win_rate": 0, "avg_odds": 0, "sharpe": 0, "max_drawdown": 0}
        
        total_picks = len(picks)
        wins = sum(1 for p in picks if p["result"] == "win")
        losses = sum(1 for p in picks if p["result"] == "loss")
        pushes = sum(1 for p in picks if p["result"] == "push")
        total_staked = sum(p["stake_units"] for p in picks)
        total_pnl = sum(p["pnl"] for p in picks)
        roi_pct = (total_pnl / total_staked * 100) if total_staked > 0 else 0
        win_rate = wins / total_picks * 100 if total_picks > 0 else 0
        avg_odds = sum(p["odds"] for p in picks) / total_picks if total_picks > 0 else 0
        
        # Sharpe ratio (daily returns)
        daily_pnl = {}
        for p in picks:
            day = p["settled_at"][:10]
            daily_pnl[day] = daily_pnl.get(day, 0) + p["pnl"]
        returns = list(daily_pnl.values())
        sharpe = 0
        if len(returns) > 1:
            mean_r = np.mean(returns) if 'np' in globals() else sum(returns)/len(returns)
            std_r = np.std(returns) if 'np' in globals() else (sum((r-mean_r)**2 for r in returns)/len(returns))**0.5
            if std_r > 0:
                sharpe = mean_r / std_r * (252**0.5)  # annualized
        
        # Max drawdown
        peak = 0
        max_dd = 0
        running = 0
        for p in picks:
            running += p["pnl"]
            if running > peak:
                peak = running
            dd = peak - running
            if dd > max_dd:
                max_dd = dd
        
        # By market
        by_market = {}
        for p in picks:
            m = p["market"]
            if m not in by_market:
                by_market[m] = {"picks": 0, "wins": 0, "pnl": 0, "staked": 0}
            by_market[m]["picks"] += 1
            if p["result"] == "win":
                by_market[m]["wins"] += 1
            by_market[m]["pnl"] += p["pnl"]
            by_market[m]["staked"] += p["stake_units"]
        
        for m in by_market:
            by_market[m]["win_rate"] = round(by_market[m]["wins"] / by_market[m]["picks"] * 100, 1)
            by_market[m]["roi"] = round(by_market[m]["pnl"] / by_market[m]["staked"] * 100, 1) if by_market[m]["staked"] > 0 else 0
        
        # By league
        by_league = {}
        for p in picks:
            l = p["league"]
            if l not in by_league:
                by_league[l] = {"picks": 0, "wins": 0, "pnl": 0, "staked": 0}
            by_league[l]["picks"] += 1
            if p["result"] == "win":
                by_league[l]["wins"] += 1
            by_league[l]["pnl"] += p["pnl"]
            by_league[l]["staked"] += p["stake_units"]
        
        for l in by_league:
            by_league[l]["win_rate"] = round(by_league[l]["wins"] / by_league[l]["picks"] * 100, 1)
            by_league[l]["roi"] = round(by_league[l]["pnl"] / by_league[l]["staked"] * 100, 1) if by_league[l]["staked"] > 0 else 0
        
        return {
            "total_picks": total_picks,
            "wins": wins,
            "losses": losses,
            "pushes": pushes,
            "total_staked": round(total_staked, 2),
            "total_pnl": round(total_pnl, 2),
            "roi_pct": round(roi_pct, 2),
            "win_rate": round(win_rate, 1),
            "avg_odds": round(avg_odds, 2),
            "sharpe": round(sharpe, 2),
            "max_drawdown": round(max_dd, 2),
            "by_market": by_market,
            "by_league": by_league,
            "current_bankroll": self.get_portfolio(portfolio_id)["current_bankroll"] if self.get_portfolio(portfolio_id) else 0,
        }

    def get_recent_picks(self, portfolio_id: int, limit: int = 20) -> List[dict]:
        return self.query(
            """SELECT * FROM paper_picks WHERE portfolio_id = ? 
               ORDER BY placed_at DESC LIMIT ?""",
            (portfolio_id, limit),
        )

    # ---------- Risk Management ----------
    def set_risk_limit(self, portfolio_id: int, limit_type: str, limit_value: float) -> int:
        return self.execute(
            """INSERT OR REPLACE INTO risk_limits
               (portfolio_id, limit_type, limit_value, updated_at)
               VALUES (?, ?, ?, datetime('now'))""",
            (portfolio_id, limit_type, limit_value),
        )

    def get_risk_limits(self, portfolio_id: int) -> List[dict]:
        return self.query(
            "SELECT * FROM risk_limits WHERE portfolio_id = ? AND is_active = 1",
            (portfolio_id,),
        )

    def update_risk_limit_current(self, portfolio_id: int, limit_type: str, current_value: float) -> None:
        self.execute(
            "UPDATE risk_limits SET current_value = ?, updated_at = datetime('now') WHERE portfolio_id = ? AND limit_type = ?",
            (current_value, portfolio_id, limit_type),
        )

    def create_risk_alert(self, portfolio_id: int, alert_type: str, severity: str,
                           message: str, metric_value: float = None, limit_value: float = None) -> int:
        return self.execute(
            """INSERT INTO risk_alerts
               (portfolio_id, alert_type, severity, message, metric_value, limit_value)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (portfolio_id, alert_type, severity, message, metric_value, limit_value),
        )

    def get_risk_alerts(self, portfolio_id: int, acknowledged: int = None, limit: int = 50) -> List[dict]:
        query = "SELECT * FROM risk_alerts WHERE portfolio_id = ?"
        params = [portfolio_id]
        if acknowledged is not None:
            query += " AND acknowledged = ?"
            params.append(acknowledged)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return self.query(query, tuple(params))

    def acknowledge_risk_alert(self, alert_id: int) -> None:
        self.execute(
            "UPDATE risk_alerts SET acknowledged = 1, acknowledged_at = datetime('now') WHERE id = ?",
            (alert_id,),
        )

    def save_correlation(self, portfolio_id: int, pick_id_a: int, pick_id_b: int,
                          correlation: float, shared_team: int = 0,
                          shared_league: int = 0, shared_market: int = 0) -> int:
        return self.execute(
            """INSERT OR REPLACE INTO portfolio_correlations
               (portfolio_id, pick_id_a, pick_id_b, correlation, shared_team, shared_league, shared_market)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (portfolio_id, pick_id_a, pick_id_b, correlation, shared_team, shared_league, shared_market),
        )

    def get_portfolio_correlations(self, portfolio_id: int, min_correlation: float = 0.3) -> List[dict]:
        return self.query(
            """SELECT * FROM portfolio_correlations 
               WHERE portfolio_id = ? AND correlation >= ?
               ORDER BY correlation DESC""",
            (portfolio_id, min_correlation),
        )

    def get_pending_picks_for_risk(self, portfolio_id: int) -> List[dict]:
        """Obtiene picks pendientes con info para análisis de riesgo."""
        return self.query(
            """SELECT * FROM paper_picks 
               WHERE portfolio_id = ? AND status = 'pending'
               ORDER BY kickoff ASC""",
            (portfolio_id,),
        )
