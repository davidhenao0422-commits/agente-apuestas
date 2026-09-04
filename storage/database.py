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

CREATE INDEX IF NOT EXISTS idx_matches_teams ON matches(home_team_id, away_team_id);
CREATE INDEX IF NOT EXISTS idx_stats_team_season ON team_stats(team_id, season);
CREATE INDEX IF NOT EXISTS idx_cache_expiry ON api_cache(expires_at);
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
