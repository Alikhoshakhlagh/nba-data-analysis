"""
retuns the Top-N players of a season from the SQLite DB.

Usage:
    from sqlalchemy import create_engine
    engine = create_engine("sqlite:///nba_star.db")
    top50 = get_top_players(engine, "2019-20")
"""
import pandas as pd
from sqlalchemy import MetaData, Table, create_engine, select
from sqlalchemy.engine import Engine

# ---- metric definition (change here, nowhere else) -------------------------
MIN_MINUTES = 1000                     # qualification filter
IMPACT_COLS = ["box_plus_minus", "player_efficiency_rating", "win_shares_per_48_minutes"]
VOLUME_COLS = ["win_shares"]
W_IMPACT, W_VOLUME = 0.6, 0.4
TOP_N = 50


def _as_engine(db) -> Engine:
    """Accept an Engine, a 'sqlite:///...' URL, or a plain file path."""
    if isinstance(db, Engine):
        return db
    db = str(db)
    return create_engine(db if "://" in db else f"sqlite:///{db}")


def _load_regular_season(engine: Engine, season: str, min_minutes: int) -> pd.DataFrame:
    """One row per qualified player for the given season (regular season only)."""
    meta = MetaData()
    stats, player, season_t, scope, context, phase = (
        Table(name, meta, autoload_with=engine)
        for name in ("fact_player_stats", "dim_player", "dim_season",
                     "dim_team_scope", "dim_player_context", "dim_phase")
    )

    # Validate the season label up front, so a typo gives a clear message.
    with engine.connect() as conn:
        valid = [r[0] for r in conn.execute(select(season_t.c.season_label)
                                            .order_by(season_t.c.season_label))]
    if season not in valid:
        raise ValueError(f"Unknown season {season!r}. Available: {valid}")

    query = (
        select(
            stats.c.player_key,
            player.c.player_name,
            season_t.c.season_label.label("season"),
            scope.c.scope_code.label("team"),          # '2TM'/'3TM' for traded players
            context.c.position_code.label("position"),
            stats.c.games_played,
            stats.c.minutes_played,
            *[stats.c[c] for c in IMPACT_COLS + VOLUME_COLS],
        )
        .select_from(
            stats.join(player, stats.c.player_key == player.c.player_key)
                 .join(season_t, stats.c.season_key == season_t.c.season_key)
                 .join(scope, stats.c.scope_key == scope.c.scope_key)
                 .join(context, stats.c.context_key == context.c.context_key)
                 .join(phase, stats.c.phase_key == phase.c.phase_key)
        )
        .where(
            season_t.c.season_label == season,
            phase.c.phase_code == "regular_season",
            # canonical row per player: the combined '2TM'/'3TM' row for traded players
            stats.c.is_player_phase_total == 1,
            stats.c.minutes_played >= min_minutes,
        )
    )
    with engine.connect() as conn:
        return pd.read_sql(query, conn)


def get_top_players(db, season: str, n: int = TOP_N, min_minutes: int = MIN_MINUTES) -> pd.DataFrame:
    """
    Top `n` players of `season` (e.g. '2019-20') by:
        Impact = mean( z(BPM), z(PER), z(WS/48) )
        Score  = 0.6 * Impact + 0.4 * z(WS)
    z-scores are computed among qualified players (>= min_minutes) of that season.
    """
    df = _load_regular_season(_as_engine(db), season, min_minutes)
    if df.empty:
        raise ValueError(f"No qualified players found for {season} with min_minutes={min_minutes}.")

    cols = IMPACT_COLS + VOLUME_COLS
    z = (df[cols] - df[cols].mean()) / df[cols].std()          # sample std (ddof=1)
    df["impact_z"] = z[IMPACT_COLS].mean(axis=1)
    df["volume_z"] = z[VOLUME_COLS].mean(axis=1)
    df["score"] = W_IMPACT * df["impact_z"] + W_VOLUME * df["volume_z"]

    df = df.sort_values("score", ascending=False).head(n).reset_index(drop=True)
    df.insert(0, "rank", df.index + 1)
    return df[["rank", "player_key", "player_name", "season", "team", "position",
               "games_played", "minutes_played", *cols, "impact_z", "volume_z", "score"]]