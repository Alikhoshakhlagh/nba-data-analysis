"""Read the accepted nba.db snapshot without opening a writable connection."""

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path


SOURCE_SHA256 = "49f057cf1dab88b91529c23694e47af0698622f29dcbc6be631a6d984c8b8a9e"
SOURCE_COUNTS = {
    "players": 964, "teams": 30, "seasons": 5, "player_seasons": 2789,
    "player_phases": 3889, "rosters": 3203, "player_stats": 4686, "mvp_votes": 61,
}
TARGET_COUNTS = {
    "dim_player": 964, "dim_season": 5, "dim_team_scope": 33,
    "dim_phase": 2, "dim_player_context": 538, "fact_player_stats": 4686,
    "fact_mvp_voting": 61, "fact_roster": 3203, "fact_player_salary": 0,
}


class StarError(ValueError):
    """A source conflict, validation failure, or protected-build diagnostic."""


def require(condition, diagnostic):
    if not condition:
        raise StarError(diagnostic)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@dataclass
class SourceSnapshot:
    path: str
    sha256: str
    tables: dict
    stats: list
    canonical_regular_ids: set
    mvp_projection: list


def read_source(path):
    """Accept only the reviewed snapshot; never reread the scraped ZIP here."""
    path = Path(path).resolve()
    require(path.is_file(), f"Source database does not exist: {path}")
    fingerprint = sha256(path)
    require(fingerprint == SOURCE_SHA256,
            f"Source fingerprint conflict: expected {SOURCE_SHA256}, got {fingerprint}. "
            "Review the changed nba.db before building a new star snapshot.")
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("BEGIN")
        require([row[0] for row in connection.execute("PRAGMA integrity_check")] == ["ok"],
                "Source integrity_check failed")
        require(not connection.execute("PRAGMA foreign_key_check").fetchall(),
                "Source foreign_key_check failed")
        actual_tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )}
        require(actual_tables == set(SOURCE_COUNTS), "Unexpected source table set")
        tables = {}
        for name, expected in SOURCE_COUNTS.items():
            rows = [dict(row) for row in connection.execute(f'SELECT * FROM "{name}"')]
            require(len(rows) == expected,
                    f"Source {name}: expected {expected} rows, got {len(rows)}")
            tables[name] = rows
        stats = [dict(row) for row in connection.execute(
            "SELECT * FROM v_player_stats_source ORDER BY stat_id"
        )]
        require(len(stats) == SOURCE_COUNTS["player_stats"], "Source statistics view lost rows")
        canonical = {row[0] for row in connection.execute(
            "SELECT stat_id FROM v_player_season_regular"
        )}
        require(len(canonical) == 2785, "Source canonical regular count changed")
        mvp_projection = [dict(row) for row in connection.execute("SELECT * FROM v_mvp_voting_source")]
    finally:
        connection.close()
    require(sha256(path) == fingerprint, "Source file changed while it was being read")
    return SourceSnapshot(str(path), fingerprint, tables, stats, canonical, mvp_projection)
