"""Independent design contract and constraint tests, using synthetic memory data."""

import re
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError

from nba_star import create_schema, create_sqlite_engine
from nba_star import schema as s
from nba_star.database import require_strict_support
from nba_star.validation import validate_schema


def player_row(key, **changes):
    row = dict(player_key=key, source_player_id=100 + key, player_name=f"Synthetic Player {key}",
               birth_date="1990-01-01", listed_height_inches=78, listed_weight_pounds=200)
    row.update(changes)
    return row


def stat_row(**changes):
    row = dict(stat_key=1, source_stat_id=101, player_key=1, season_key=1, scope_key=1,
               phase_key=1, context_key=1, totals_source_rank=1, advanced_source_rank=2,
               is_player_phase_total=1, awards_source_text="")
    row.update({name: 0 for name in s.TOTALS})
    row["games_played"] = 1
    row.update({name: 0.0 if name in s.REQUIRED_ADVANCED else None for name in s.ADVANCED})
    row.update(changes)
    return row


def vote_row(**changes):
    row = dict(mvp_vote_key=1, player_key=1, season_key=1, scope_key=1, phase_key=1,
               context_key=1, source_representative_stat_id=101, first_place_votes=1,
               voting_points_won=10)
    row.update(changes)
    return row


class StarSchemaTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_sqlite_engine()
        self.addCleanup(self.engine.dispose)
        create_schema(self.engine)
        self.connection = self.engine.connect()
        self.addCleanup(self.connection.close)
        transaction = self.connection.begin()
        self.addCleanup(transaction.rollback)
        self.connection.execute(s.dim_player.insert(), [player_row(1), player_row(2)])
        self.connection.execute(s.dim_season.insert(), [
            dict(season_key=1, season_label="2019-20", champion_team_code="ALP",
                 champion_team_name="Alpha", maximum_mvp_voting_points=1000),
            dict(season_key=2, season_label="2020-21", champion_team_code="BET",
                 champion_team_name="Beta", maximum_mvp_voting_points=990),
        ])
        self.connection.execute(s.dim_team_scope.insert(), [
            dict(scope_key=1, scope_code="ALP", scope_kind="team", source_team_id=1,
                 team_name="Alpha", aggregate_team_count=None),
            dict(scope_key=2, scope_code="BET", scope_kind="team", source_team_id=2,
                 team_name="Beta", aggregate_team_count=None),
            dict(scope_key=3, scope_code="2TM", scope_kind="aggregate", source_team_id=None,
                 team_name=None, aggregate_team_count=2),
        ])
        self.connection.execute(s.dim_phase.insert(), [
            dict(phase_key=1, phase_code="regular_season", phase_name="Regular Season"),
            dict(phase_key=2, phase_code="playoffs", phase_name="Playoffs"),
        ])
        self.connection.execute(s.dim_player_context.insert(), [
            dict(context_key=1, reported_age=30, experience_years=6, position_code="PG"),
            dict(context_key=2, reported_age=30, experience_years=6, position_code="C"),
        ])

    def reject(self, statement, message):
        with self.assertRaisesRegex(IntegrityError, message):
            with self.connection.begin_nested():
                self.connection.execute(statement)

    def salary(self, **changes):
        row = dict(salary_key=1, player_key=1, season_key=1, annual_salary_usd=12345678)
        row.update(changes)
        return s.fact_player_salary.insert().values(**row)

    def test_all_nine_entities_90_columns_types_and_nullability_match_erd(self):
        erd = (Path(__file__).resolve().parents[1] / "ERD.mmd").read_text()
        entities = re.findall(r"^    ((?:dim|fact)_\w+) \{\n(.*?)^    }", erd, re.M | re.S)
        self.assertEqual(len(entities), 9)
        inspector = inspect(self.connection)
        self.assertEqual(set(inspector.get_table_names()), {name for name, _ in entities})
        total = 0
        for name, body in entities:
            expected = {}
            for line in body.splitlines():
                match = re.match(r"\s+(INTEGER|REAL|TEXT) (\w+)(.*)", line)
                if match:
                    expected[match[2]] = (match[1], '"nullable' in match[3], None)
            actual = {col["name"]: (str(col["type"]), col["nullable"], col["default"])
                      for col in inspector.get_columns(name)}
            self.assertEqual(actual, expected, name)
            self.assertEqual(len(inspector.get_pk_constraint(name)["constrained_columns"]), 1)
            total += len(actual)
        self.assertEqual(total, 90)

    def test_schema_topology_constraints_strict_and_partial_index(self):
        self.assertEqual(validate_schema(self.connection), dict(
            tables=9, dimensions=5, facts=4, columns=90, primary_keys=9,
            foreign_keys=16, unique_constraints=13, check_constraints=55,
            partial_unique_indexes=1, strict_tables=9,
        ))

    def test_erd_all_16_direct_relationships_match_foreign_keys(self):
        erd = (Path(__file__).resolve().parents[1] / "ERD.mmd").read_text()
        edges = set(re.findall(r"^    (dim_\w+) \|\|\.\.o\{ (fact_\w+) :", erd, re.M))
        inspector = inspect(self.connection)
        actual = set()
        for name in inspector.get_table_names():
            for fk in inspector.get_foreign_keys(name):
                actual.add((fk["referred_table"], name))
                self.assertEqual(fk["options"], {"ondelete": "RESTRICT", "onupdate": "RESTRICT"})
        self.assertEqual(edges, actual)
        self.assertEqual(len(edges), 16)
        self.assertEqual({parent for parent, child in edges if child == "fact_player_salary"},
                         {"dim_player", "dim_season"})

    def test_salary_table_initially_empty_and_has_no_defaults(self):
        self.assertEqual(self.connection.exec_driver_sql("SELECT COUNT(*) FROM fact_player_salary").scalar_one(), 0)
        columns = inspect(self.connection).get_columns("fact_player_salary")
        self.assertEqual([col["name"] for col in columns],
                         ["salary_key", "player_key", "season_key", "annual_salary_usd"])
        self.assertTrue(all(col["default"] is None for col in columns))

    def test_salary_negative_is_rejected(self):
        self.reject(self.salary(annual_salary_usd=-1), "CHECK constraint failed")

    def test_salary_required_columns_reject_null(self):
        for column in ("player_key", "season_key", "annual_salary_usd"):
            with self.subTest(column=column):
                self.reject(self.salary(**{column: None}), "NOT NULL constraint failed")

    def test_salary_both_foreign_keys_reject_orphans(self):
        for column in ("player_key", "season_key"):
            with self.subTest(column=column):
                self.reject(self.salary(**{column: 999999}), "FOREIGN KEY constraint failed")

    def test_salary_player_season_unique_and_primary_key(self):
        self.connection.execute(self.salary())
        self.reject(self.salary(salary_key=2, annual_salary_usd=22222222), "UNIQUE constraint failed")
        self.reject(self.salary(player_key=2), "UNIQUE constraint failed")

    def test_salary_can_represent_different_players_and_seasons_in_test_only(self):
        self.connection.execute(self.salary())
        self.connection.execute(self.salary(salary_key=2, player_key=2))
        self.connection.execute(self.salary(salary_key=3, season_key=2))
        self.assertEqual(self.connection.exec_driver_sql("SELECT COUNT(*) FROM fact_player_salary").scalar_one(), 3)

    def test_salary_strict_integer_rejects_fraction_and_unknown_text(self):
        for amount in (123.5, "unknown", b"123"):
            with self.subTest(amount=amount):
                self.reject(self.salary(annual_salary_usd=amount), "cannot store")

    def test_salary_parents_cannot_be_deleted_or_rekeyed(self):
        self.connection.execute(self.salary())
        for table, column in ((s.dim_player, "player_key"), (s.dim_season, "season_key")):
            self.reject(table.delete().where(table.c[column] == 1), "FOREIGN KEY constraint failed")
            self.reject(table.update().where(table.c[column] == 1).values(**{column: 99}), "FOREIGN KEY constraint failed")

    def test_each_other_fact_foreign_key_rejects_orphan(self):
        fixtures = [
            (s.fact_player_stats, stat_row()), (s.fact_mvp_voting, vote_row()),
            (s.fact_roster, dict(roster_key=1, player_key=1, season_key=1, scope_key=1, context_key=1)),
        ]
        for table, fixture in fixtures:
            for column in (col.name for col in table.columns if col.foreign_keys):
                with self.subTest(table=table.name, column=column):
                    message = "CHECK constraint failed" if table.name == "fact_mvp_voting" and column == "phase_key" else "FOREIGN KEY constraint failed"
                    self.reject(table.insert().values(**dict(fixture, **{column: 999999})), message)

    def test_duplicate_aggregate_scope_rejected_without_null_uniqueness_hole(self):
        self.connection.execute(s.fact_player_stats.insert().values(**stat_row(scope_key=3)))
        self.reject(s.fact_player_stats.insert().values(**stat_row(
            stat_key=2, source_stat_id=102, scope_key=3, is_player_phase_total=0,
        )), "UNIQUE constraint failed")

    def test_two_canonical_observations_rejected_by_partial_index(self):
        self.connection.execute(s.fact_player_stats.insert().values(**stat_row(scope_key=3)))
        self.reject(s.fact_player_stats.insert().values(**stat_row(
            stat_key=2, source_stat_id=102, scope_key=1,
        )), "UNIQUE constraint failed")

    def test_multiple_detail_rows_can_repeat_both_source_ranks(self):
        self.connection.execute(s.fact_player_stats.insert(), [
            stat_row(scope_key=3),
            stat_row(stat_key=2, source_stat_id=102, scope_key=1, is_player_phase_total=0),
            stat_row(stat_key=3, source_stat_id=103, scope_key=2, is_player_phase_total=0),
        ])
        self.assertEqual(self.connection.exec_driver_sql("SELECT COUNT(*) FROM fact_player_stats").scalar_one(), 3)

    def test_context_not_part_of_stat_grain(self):
        self.connection.execute(s.fact_player_stats.insert().values(**stat_row()))
        self.reject(s.fact_player_stats.insert().values(**stat_row(
            stat_key=2, source_stat_id=102, context_key=2, is_player_phase_total=0,
        )), "UNIQUE constraint failed")

    def test_source_stat_id_unique_across_distinct_grains(self):
        self.connection.execute(s.fact_player_stats.insert().values(**stat_row()))
        self.reject(s.fact_player_stats.insert().values(**stat_row(stat_key=2, player_key=2)), "UNIQUE constraint failed")

    def test_four_counter_identities_are_enforced(self):
        for column in ("field_goals", "field_goal_attempts", "total_rebounds", "points"):
            with self.subTest(column=column):
                self.reject(s.fact_player_stats.insert().values(**stat_row(**{column: 1})), "CHECK constraint failed")

    def test_all_totals_counter_bounds(self):
        for column in s.TOTALS:
            with self.subTest(column=column):
                self.reject(s.fact_player_stats.insert().values(**stat_row(
                    **{column: 0 if column == "games_played" else -1},
                )), "CHECK constraint failed")
        for column in ("games_started", "triple_doubles"):
            self.reject(s.fact_player_stats.insert().values(**stat_row(**{column: 2})), "CHECK constraint failed")

    def test_source_ranks_and_canonical_flag_checks(self):
        for column, value in (("totals_source_rank", 0), ("advanced_source_rank", 0), ("is_player_phase_total", 2)):
            self.reject(s.fact_player_stats.insert().values(**stat_row(**{column: value})), "CHECK constraint failed")

    def test_valid_null_and_negative_advanced_values_remain_independent(self):
        self.connection.execute(s.fact_player_stats.insert().values(**stat_row(
            offensive_win_shares=-0.1, defensive_win_shares=0.1, win_shares=0.1,
            value_over_replacement_player=-0.2, box_plus_minus=-4.5,
        )))
        self.assertEqual(self.connection.exec_driver_sql(
            "SELECT player_efficiency_rating, box_plus_minus, win_shares FROM fact_player_stats"
        ).one(), (None, -4.5, 0.1))

    def test_real_team_and_aggregate_conditional_fields_reject_null_loopholes(self):
        for changes in (
            dict(scope_kind="aggregate", aggregate_team_count=None, source_team_id=None, team_name=None),
            dict(scope_kind="team", aggregate_team_count=None, source_team_id=None, team_name="Wrong"),
            dict(scope_kind="aggregate", aggregate_team_count=3, source_team_id=None, team_name=None),
            dict(scope_kind="aggregate", aggregate_team_count=2, source_team_id=999, team_name=None),
        ):
            with self.subTest(changes=changes):
                self.reject(s.dim_team_scope.insert().values(scope_key=99, scope_code="2TM", **changes), "CHECK constraint failed")

    def test_multiple_aggregate_members_share_null_source_team_id(self):
        self.connection.execute(s.dim_team_scope.insert(), [
            dict(scope_key=4, scope_code="3TM", scope_kind="aggregate", aggregate_team_count=3, source_team_id=None, team_name=None),
            dict(scope_key=5, scope_code="4TM", scope_kind="aggregate", aggregate_team_count=4, source_team_id=None, team_name=None),
        ])
        self.assertEqual(self.connection.exec_driver_sql("SELECT COUNT(*) FROM dim_team_scope WHERE source_team_id IS NULL").scalar_one(), 3)

    def test_tot_or_fake_team_codes_are_rejected(self):
        for code in ("TOT", "2TM", "3TM", "4TM", "bad"):
            self.reject(s.dim_team_scope.insert().values(
                scope_key=99, scope_code=code, scope_kind="team", source_team_id=99,
                team_name="Synthetic Wrong", aggregate_team_count=None,
            ), "CHECK constraint failed")

    def test_scope_codes_and_nonnull_source_ids_unique(self):
        self.reject(s.dim_team_scope.insert().values(
            scope_key=99, scope_code="GAM", scope_kind="team", source_team_id=1,
            team_name="Gamma", aggregate_team_count=None,
        ), "UNIQUE constraint failed")

    def test_context_unique_and_value_checks(self):
        self.reject(s.dim_player_context.insert().values(
            context_key=3, reported_age=30, experience_years=6, position_code="PG",
        ), "UNIQUE constraint failed")
        for changes in (dict(reported_age=0), dict(experience_years=-1), dict(position_code="PG-SG")):
            row = dict(context_key=3, reported_age=31, experience_years=7, position_code="PG")
            row.update(changes)
            self.reject(s.dim_player_context.insert().values(**row), "CHECK constraint failed")

    def test_valid_calendar_date_and_player_identity_guard(self):
        for value in ("2021-02-29", "2020-13-01", "1990-1-01", "unknown"):
            self.reject(s.dim_player.insert().values(**player_row(3, birth_date=value)), "CHECK constraint failed")
        self.connection.execute(s.dim_player.insert().values(**player_row(3, birth_date="2000-02-29")))
        self.reject(s.dim_player.insert().values(**player_row(4, player_name="Synthetic Player 1")), "UNIQUE constraint failed")

    def test_fixed_phase_and_season_allowlists(self):
        self.reject(s.dim_phase.insert().values(phase_key=3, phase_code="preseason", phase_name="Preseason"), "CHECK constraint failed")
        self.reject(s.dim_season.insert().values(
            season_key=3, season_label="2018-19", champion_team_code="ALP", champion_team_name="Alpha", maximum_mvp_voting_points=1000,
        ), "CHECK constraint failed")

    def test_mvp_only_regular_and_player_season_unique(self):
        self.reject(s.fact_mvp_voting.insert().values(**vote_row(phase_key=2)), "CHECK constraint failed")
        self.connection.execute(s.fact_mvp_voting.insert().values(**vote_row()))
        self.reject(s.fact_mvp_voting.insert().values(**vote_row(mvp_vote_key=2, source_representative_stat_id=102)), "UNIQUE constraint failed")

    def test_roster_grain_is_unique(self):
        row = dict(roster_key=1, player_key=1, season_key=1, scope_key=1, context_key=1)
        self.connection.execute(s.fact_roster.insert().values(**row))
        self.reject(s.fact_roster.insert().values(**dict(row, roster_key=2, context_key=2)), "UNIQUE constraint failed")

    def test_foreign_keys_enabled_on_multiple_physical_connections(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = create_sqlite_engine(URL.create("sqlite+pysqlite", database=str(Path(directory) / "two.db")))
            try:
                with engine.connect() as first, engine.connect() as second:
                    self.assertIsNot(first.connection.dbapi_connection, second.connection.dbapi_connection)
                    for connection in (first, second):
                        self.assertEqual(connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one(), 1)
            finally:
                engine.dispose()

    def test_sqlite_version_guard_and_unmanaged_foreign_keys_guard(self):
        with self.assertRaisesRegex(RuntimeError, "STRICT requires"):
            require_strict_support("3.36.0")
        require_strict_support("3.37.0")
        engine = create_engine("sqlite+pysqlite:///:memory:")
        self.addCleanup(engine.dispose)
        with self.assertRaisesRegex(RuntimeError, "Foreign keys are OFF"):
            create_schema(engine)


if __name__ == "__main__":
    unittest.main()
