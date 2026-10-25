"""SQLAlchemy Core implementation of Phase 5A plus the approved salary fact.

Every FK points directly from a fact to a dimension. Cross-table semantic
rules are validated by validation.py, rather than hidden in triggers.
"""

from sqlalchemy import (
    INTEGER, REAL, TEXT, CheckConstraint, Column, ForeignKey, Index,
    MetaData, Table, UniqueConstraint,
)

metadata = MetaData()
FK_OPTIONS = {"ondelete": "RESTRICT", "onupdate": "RESTRICT"}
SEASONS = ("2019-20", "2020-21", "2021-22", "2022-23", "2023-24")

# Preserve this order in the schema and the source-to-target comparison.
TOTALS = (
    "games_played", "games_started", "minutes_played", "field_goals",
    "field_goal_attempts", "two_point_field_goals", "two_point_attempts",
    "three_point_field_goals", "three_point_attempts", "free_throws",
    "free_throw_attempts", "offensive_rebounds", "defensive_rebounds",
    "total_rebounds", "assists", "steals", "blocks", "turnovers",
    "personal_fouls", "points", "triple_doubles",
)
ADVANCED = (
    "player_efficiency_rating", "offensive_rebound_percentage",
    "defensive_rebound_percentage", "total_rebound_percentage",
    "assist_percentage", "steal_percentage", "block_percentage",
    "usage_percentage", "offensive_win_shares", "defensive_win_shares",
    "win_shares", "win_shares_per_48_minutes", "offensive_box_plus_minus",
    "defensive_box_plus_minus", "box_plus_minus", "value_over_replacement_player",
)
REQUIRED_ADVANCED = {
    "offensive_win_shares", "defensive_win_shares", "win_shares",
    "value_over_replacement_player",
}


def dimension_fk(column, dimension):
    """All fact FK columns are required and use the same RESTRICT policy."""
    return Column(column, INTEGER, ForeignKey(
        f"{dimension}.{column}", **FK_OPTIONS,
    ), nullable=False)


dim_player = Table(
    "dim_player", metadata,
    Column("player_key", INTEGER, primary_key=True, nullable=False),
    Column("source_player_id", INTEGER, nullable=False),
    Column("player_name", TEXT, nullable=False),
    Column("birth_date", TEXT, nullable=False),
    Column("listed_height_inches", INTEGER, nullable=False),
    Column("listed_weight_pounds", INTEGER, nullable=False),
    UniqueConstraint("source_player_id", name="uq_player_source_id"),
    UniqueConstraint("player_name", "birth_date", name="uq_player_identity"),
    CheckConstraint("player_key > 0 AND source_player_id > 0", name="ck_player_keys"),
    CheckConstraint("length(trim(player_name)) > 0", name="ck_player_name"),
    CheckConstraint("listed_height_inches > 0", name="ck_player_height"),
    CheckConstraint("listed_weight_pounds > 0", name="ck_player_weight"),
    CheckConstraint(
        "birth_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' "
        "AND date(birth_date, '+0 days') IS NOT NULL "
        "AND date(birth_date, '+0 days') = birth_date", name="ck_player_birth_date",
    ),
    sqlite_strict=True,
)

dim_season = Table(
    "dim_season", metadata,
    Column("season_key", INTEGER, primary_key=True, nullable=False),
    Column("season_label", TEXT, nullable=False),
    Column("champion_team_code", TEXT, nullable=False),
    Column("champion_team_name", TEXT, nullable=False),
    Column("maximum_mvp_voting_points", INTEGER, nullable=False),
    UniqueConstraint("season_label", name="uq_season_label"),
    CheckConstraint("season_key > 0", name="ck_season_key"),
    CheckConstraint(
        "season_label IN ('2019-20','2020-21','2021-22','2022-23','2023-24')",
        name="ck_season_range",
    ),
    CheckConstraint("maximum_mvp_voting_points > 0", name="ck_season_vote_max"),
    sqlite_strict=True,
)

dim_team_scope = Table(
    "dim_team_scope", metadata,
    Column("scope_key", INTEGER, primary_key=True, nullable=False),
    Column("scope_code", TEXT, nullable=False),
    Column("scope_kind", TEXT, nullable=False),
    Column("source_team_id", INTEGER, nullable=True),
    Column("team_name", TEXT, nullable=True),
    Column("aggregate_team_count", INTEGER, nullable=True),
    UniqueConstraint("scope_code", name="uq_scope_code"),
    UniqueConstraint("source_team_id", name="uq_scope_source_team"),
    CheckConstraint("scope_key > 0", name="ck_scope_key"),
    CheckConstraint(
        "(scope_kind = 'team' AND source_team_id IS NOT NULL "
        "AND source_team_id > 0 AND team_name IS NOT NULL "
        "AND length(trim(team_name)) > 0 AND aggregate_team_count IS NULL "
        "AND length(scope_code) = 3 AND scope_code NOT GLOB '*[^A-Z]*' "
        "AND scope_code NOT IN ('TOT','2TM','3TM','4TM')) "
        "OR (scope_kind = 'aggregate' AND source_team_id IS NULL "
        "AND team_name IS NULL AND aggregate_team_count IS NOT NULL "
        "AND ((scope_code='2TM' AND aggregate_team_count=2) "
        "OR (scope_code='3TM' AND aggregate_team_count=3) "
        "OR (scope_code='4TM' AND aggregate_team_count=4)))",
        name="ck_scope_kind_fields",
    ),
    sqlite_strict=True,
)

dim_phase = Table(
    "dim_phase", metadata,
    Column("phase_key", INTEGER, primary_key=True, nullable=False),
    Column("phase_code", TEXT, nullable=False),
    Column("phase_name", TEXT, nullable=False),
    UniqueConstraint("phase_code", name="uq_phase_code"),
    CheckConstraint(
        "(phase_key=1 AND phase_code='regular_season' AND phase_name='Regular Season') "
        "OR (phase_key=2 AND phase_code='playoffs' AND phase_name='Playoffs')",
        name="ck_phase_dictionary",
    ),
    sqlite_strict=True,
)

dim_player_context = Table(
    "dim_player_context", metadata,
    Column("context_key", INTEGER, primary_key=True, nullable=False),
    Column("reported_age", INTEGER, nullable=False),
    Column("experience_years", INTEGER, nullable=False),
    Column("position_code", TEXT, nullable=False),
    UniqueConstraint("reported_age", "experience_years", "position_code", name="uq_context"),
    CheckConstraint("context_key > 0", name="ck_context_key"),
    CheckConstraint("reported_age > 0", name="ck_context_age"),
    CheckConstraint("experience_years >= 0", name="ck_context_experience"),
    CheckConstraint("position_code IN ('PG','SG','SF','PF','C')", name="ck_context_position"),
    sqlite_strict=True,
)

fact_player_stats = Table(
    "fact_player_stats", metadata,
    Column("stat_key", INTEGER, primary_key=True, nullable=False),
    Column("source_stat_id", INTEGER, nullable=False),
    dimension_fk("player_key", "dim_player"),
    dimension_fk("season_key", "dim_season"),
    dimension_fk("scope_key", "dim_team_scope"),
    dimension_fk("phase_key", "dim_phase"),
    dimension_fk("context_key", "dim_player_context"),
    Column("totals_source_rank", INTEGER, nullable=False),
    Column("advanced_source_rank", INTEGER, nullable=False),
    Column("is_player_phase_total", INTEGER, nullable=False),
    Column("awards_source_text", TEXT, nullable=False),
    *(Column(name, INTEGER, nullable=False) for name in TOTALS),
    *(Column(name, REAL, nullable=name not in REQUIRED_ADVANCED) for name in ADVANCED),
    UniqueConstraint("source_stat_id", name="uq_stat_source_id"),
    UniqueConstraint("player_key", "season_key", "phase_key", "scope_key", name="uq_stat_grain"),
    CheckConstraint("stat_key > 0 AND source_stat_id > 0", name="ck_stat_keys"),
    CheckConstraint("totals_source_rank > 0 AND advanced_source_rank > 0", name="ck_stat_ranks"),
    CheckConstraint("is_player_phase_total IN (0,1)", name="ck_stat_canonical_flag"),
    CheckConstraint("games_played > 0", name="ck_stat_games"),
    *(CheckConstraint(f"{name} >= 0", name=f"ck_stat_{name}")
      for name in TOTALS if name != "games_played"),
    CheckConstraint("games_started <= games_played", name="ck_stat_starts"),
    CheckConstraint("triple_doubles <= games_played", name="ck_stat_triple_doubles_games"),
    CheckConstraint("two_point_field_goals <= two_point_attempts", name="ck_stat_two_makes"),
    CheckConstraint("three_point_field_goals <= three_point_attempts", name="ck_stat_three_makes"),
    CheckConstraint("free_throws <= free_throw_attempts", name="ck_stat_free_makes"),
    CheckConstraint("field_goals <= field_goal_attempts", name="ck_stat_all_makes"),
    CheckConstraint("field_goals = two_point_field_goals + three_point_field_goals", name="ck_stat_fg_identity"),
    CheckConstraint("field_goal_attempts = two_point_attempts + three_point_attempts", name="ck_stat_fga_identity"),
    CheckConstraint("total_rebounds = offensive_rebounds + defensive_rebounds", name="ck_stat_rebounds_identity"),
    CheckConstraint("points = 2*two_point_field_goals + 3*three_point_field_goals + free_throws", name="ck_stat_points_identity"),
    sqlite_strict=True,
)

Index(
    "uq_stats_canonical_player_phase",
    fact_player_stats.c.player_key, fact_player_stats.c.season_key,
    fact_player_stats.c.phase_key, unique=True,
    sqlite_where=fact_player_stats.c.is_player_phase_total == 1,
)

fact_mvp_voting = Table(
    "fact_mvp_voting", metadata,
    Column("mvp_vote_key", INTEGER, primary_key=True, nullable=False),
    dimension_fk("player_key", "dim_player"),
    dimension_fk("season_key", "dim_season"),
    dimension_fk("scope_key", "dim_team_scope"),
    dimension_fk("phase_key", "dim_phase"),
    dimension_fk("context_key", "dim_player_context"),
    Column("source_representative_stat_id", INTEGER, nullable=False),
    Column("first_place_votes", INTEGER, nullable=False),
    Column("voting_points_won", INTEGER, nullable=False),
    UniqueConstraint("player_key", "season_key", name="uq_mvp_grain"),
    UniqueConstraint("source_representative_stat_id", name="uq_mvp_source_representative"),
    CheckConstraint("mvp_vote_key > 0 AND source_representative_stat_id > 0", name="ck_mvp_keys"),
    CheckConstraint("phase_key = 1", name="ck_mvp_regular_only"),
    CheckConstraint("first_place_votes >= 0", name="ck_mvp_first_votes"),
    CheckConstraint("voting_points_won > 0", name="ck_mvp_points"),
    sqlite_strict=True,
)

fact_roster = Table(
    "fact_roster", metadata,
    Column("roster_key", INTEGER, primary_key=True, nullable=False),
    dimension_fk("player_key", "dim_player"),
    dimension_fk("season_key", "dim_season"),
    dimension_fk("scope_key", "dim_team_scope"),
    dimension_fk("context_key", "dim_player_context"),
    UniqueConstraint("player_key", "season_key", "scope_key", name="uq_roster_grain"),
    CheckConstraint("roster_key > 0", name="ck_roster_key"),
    sqlite_strict=True,
)

# Future data only. No defaults, seed rows, or ingestion path are provided.
# Provisional grain must be re-audited against the actual salary source.
fact_player_salary = Table(
    "fact_player_salary", metadata,
    Column("salary_key", INTEGER, primary_key=True, nullable=False),
    dimension_fk("player_key", "dim_player"),
    dimension_fk("season_key", "dim_season"),
    Column("annual_salary_usd", INTEGER, nullable=False),
    CheckConstraint("annual_salary_usd >= 0", name="ck_salary_nonnegative"),
    UniqueConstraint("player_key", "season_key", name="uq_salary_player_season"),
    sqlite_strict=True,
)

DIMENSIONS = (dim_player, dim_season, dim_team_scope, dim_phase, dim_player_context)
FACTS = (fact_player_stats, fact_mvp_voting, fact_roster, fact_player_salary)
