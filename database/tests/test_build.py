"""Real-source load, semantic validation, failure isolation and publication tests."""

import copy
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError, OperationalError

from nba_star import create_schema, create_sqlite_engine
from nba_star.build import build_database, load_rows, main, readonly_engine
from nba_star.source import SOURCE_SHA256, TARGET_COUNTS, StarError, read_source, sha256
from nba_star.transform import prepare_rows
from nba_star.validation import SQL_FOLDER, rounded_ratio, stats_projection, validate_target


class StarBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        default = Path(__file__).resolve().parents[2] / "nba.db"
        cls.source_path = Path(os.environ.get("NBA_SOURCE_DB", default)).resolve()
        cls.source = read_source(cls.source_path)
        cls.directory = tempfile.TemporaryDirectory(prefix="nba_star_tests_")
        cls.addClassCleanup(cls.directory.cleanup)
        cls.path = Path(cls.directory.name) / "star.db"
        cls.report = build_database(cls.source_path, cls.path)
        cls.engine = readonly_engine(cls.path)
        cls.addClassCleanup(cls.engine.dispose)

    def folder(self):
        directory = tempfile.TemporaryDirectory(prefix="nba_star_case_")
        self.addCleanup(directory.cleanup)
        return Path(directory.name)

    def mutable_copy(self):
        path = self.folder() / "copy.db"
        shutil.copyfile(self.path, path)
        engine = create_sqlite_engine(URL.create("sqlite+pysqlite", database=str(path)))
        self.addCleanup(engine.dispose)
        return engine

    def assert_mutation_detected(self, sql, diagnostic):
        engine = self.mutable_copy()
        with engine.begin() as connection:
            connection.exec_driver_sql(sql)
        with engine.connect() as connection:
            with self.assertRaisesRegex(StarError, diagnostic):
                validate_target(connection, self.source)

    def test_real_source_all_nine_counts_and_reopened_validation(self):
        self.assertTrue(self.report["reopened_read_only_and_validated"])
        self.assertEqual(self.report["validation"]["table_counts"], TARGET_COUNTS)
        self.assertEqual(self.report["database_sha256"], sha256(self.path))
        self.assertEqual(self.report["source_sha256_before"], SOURCE_SHA256)
        self.assertEqual(self.report["source_sha256_after"], SOURCE_SHA256)

    def test_every_source_relation_and_full_projection_preserved(self):
        result = self.report["validation"]
        self.assertEqual(set(result["source_relation_field_comparisons"]), {
            "players", "teams", "seasons", "player_seasons", "player_phases", "rosters", "player_stats", "mvp_votes",
        })
        self.assertEqual(result["statistical_projection_fields_compared"], 4686 * 70)
        self.assertEqual(result["mvp_projection_fields_compared"], 61 * 27)
        self.assertEqual(result["reported_advanced_fields_compared"], 4686 * 16)
        self.assertEqual((result["player_seasons"], result["player_phases"]), (2789, 3889))

    def test_canonical_team_scope_and_aggregate_counter_controls(self):
        result = self.report["validation"]
        self.assertEqual(result["phase_counts"], {"regular_season": 3582, "playoffs": 1104})
        self.assertEqual(result["scope_counts"], {"team": 4302, "aggregate": 384})
        self.assertEqual(result["aggregate_label_counts"], {"2TM": 356, "3TM": 27, "4TM": 1})
        self.assertEqual(result["aggregate_counter_comparisons"], 8064)
        self.assertEqual(result["point_sums"], dict(canonical_regular=1314107, team_only_regular=1314107, all_regular=1459081))
        self.assertEqual((result["canonical_observations"], result["canonical_regular"], result["noncanonical_observations"]),
                         (3889, 2785, 797))

    def test_wiggins_two_team_detail_and_one_canonical_observation(self):
        with self.engine.connect() as connection:
            rows = connection.exec_driver_sql(
                "SELECT sc.scope_code, f.points, f.is_player_phase_total FROM fact_player_stats f "
                "JOIN dim_player p ON p.player_key=f.player_key JOIN dim_season se ON se.season_key=f.season_key "
                "JOIN dim_team_scope sc ON sc.scope_key=f.scope_key "
                "WHERE p.player_name='Andrew Wiggins' AND se.season_label='2019-20' AND f.phase_key=1 ORDER BY sc.scope_code"
            ).all()
        self.assertEqual(rows, [("2TM", 1175, 1), ("GSW", 233, 0), ("MIN", 942, 0)])

    def test_playoff_only_seasons_preserved(self):
        with self.engine.connect() as connection:
            rows = connection.exec_driver_sql(
                "SELECT p.player_name, se.season_label FROM fact_player_stats f "
                "JOIN dim_player p ON p.player_key=f.player_key JOIN dim_season se ON se.season_key=f.season_key "
                "GROUP BY f.player_key, f.season_key HAVING MIN(f.phase_key)=2 ORDER BY se.season_label, p.player_name"
            ).all()
        self.assertEqual(rows, [("Jaylen Adams", "2019-20"), ("Luca Vildoza", "2021-22"),
                                ("DaQuan Jeffries", "2022-23"), ("Tristan Thompson", "2022-23")])

    def test_mvp_tot_alias_and_pg_cohort_preserved(self):
        result = self.report["validation"]
        self.assertEqual((result["aggregate_mvp_results"], result["pg_mvp_results"]), (2, 26))
        with self.engine.connect() as connection:
            rows = connection.exec_driver_sql(
                "SELECT p.player_name, se.season_label, sc.scope_code FROM fact_mvp_voting m "
                "JOIN dim_player p ON p.player_key=m.player_key JOIN dim_season se ON se.season_key=m.season_key "
                "JOIN dim_team_scope sc ON sc.scope_key=m.scope_key WHERE sc.scope_kind='aggregate' ORDER BY p.player_name"
            ).all()
        self.assertEqual(rows, [("Derrick Rose", "2020-21", "2TM"), ("James Harden", "2020-21", "2TM")])

    def test_ranks_advanced_nulls_and_champion_memberships_preserved(self):
        result = self.report["validation"]
        self.assertEqual(result["differing_source_rank_observations"], 4599)
        self.assertEqual(sorted(result["advanced_null_counts"].values()), [0] * 4 + [6] * 12)
        self.assertEqual(result["champion_memberships"], 96)
        self.assertEqual([row["champion_memberships"] for row in result["season_counts"]], [20, 22, 17, 18, 19])

    def test_salary_table_empty_no_salary_import_implemented_or_attempted(self):
        self.assertFalse(self.report["salary_ingestion_implemented"])
        self.assertFalse(self.report["validation"]["salary_import_attempted"])
        self.assertEqual(self.report["validation"]["salary_rows"], 0)
        rows = prepare_rows(self.source)
        self.assertEqual(rows["fact_player_salary"], [])
        self.assertTrue(all(row["fact_player_salary"] == 0 for row in self.report["validation"]["season_counts"]))

    def test_nonempty_salary_batch_is_refused(self):
        rows = prepare_rows(self.source)
        rows["fact_player_salary"] = [dict(salary_key=1, player_key=1, season_key=1, annual_salary_usd=12345678)]
        engine = create_sqlite_engine()
        self.addCleanup(engine.dispose)
        create_schema(engine)
        with self.assertRaisesRegex(StarError, "Salary ingestion is not part"):
            with engine.begin() as connection:
                load_rows(connection, rows)

    def test_complete_transaction_rolls_back_partial_batch_on_failure(self):
        rows = prepare_rows(self.source)
        rows["fact_player_stats"].append(dict(rows["fact_player_stats"][0]))
        engine = create_sqlite_engine()
        self.addCleanup(engine.dispose)
        create_schema(engine)
        with self.assertRaises(IntegrityError):
            with engine.begin() as connection:
                load_rows(connection, rows)
        with engine.connect() as connection:
            for name in rows:
                self.assertEqual(connection.exec_driver_sql(f'SELECT COUNT(*) FROM "{name}"').scalar_one(), 0, name)

    def test_reimport_into_nonempty_target_is_refused(self):
        engine = self.mutable_copy()
        with self.assertRaisesRegex(StarError, "requires empty tables"):
            with engine.begin() as connection:
                load_rows(connection, prepare_rows(self.source))

    def test_changed_advanced_value_is_detected(self):
        self.assert_mutation_detected("UPDATE fact_player_stats SET win_shares=win_shares+0.1 WHERE stat_key=1", "win_shares")

    def test_changed_stat_counter_or_awards_is_detected(self):
        for sql, field in (
            ("UPDATE fact_player_stats SET minutes_played=minutes_played+1 WHERE stat_key=1", "minutes_played"),
            ("UPDATE fact_player_stats SET awards_source_text='changed' WHERE stat_key=1", "awards"),
        ):
            with self.subTest(field=field):
                self.assert_mutation_detected(sql, field)

    def test_missing_canonical_flag_is_detected(self):
        self.assert_mutation_detected(
            "UPDATE fact_player_stats SET is_player_phase_total=0 WHERE source_stat_id=("
            "SELECT MIN(source_stat_id) FROM fact_player_stats WHERE is_player_phase_total=1)",
            "Missing or duplicate canonical",
        )

    def test_wrong_canonical_detail_is_detected(self):
        engine = self.mutable_copy()
        with engine.begin() as connection:
            group = connection.exec_driver_sql(
                "SELECT player_key, season_key, phase_key FROM fact_player_stats WHERE is_player_phase_total=0 LIMIT 1"
            ).one()
            args = tuple(group)
            connection.exec_driver_sql(
                "UPDATE fact_player_stats SET is_player_phase_total=0 WHERE player_key=? AND season_key=? AND phase_key=?", args)
            connection.exec_driver_sql(
                "UPDATE fact_player_stats SET is_player_phase_total=1 WHERE stat_key=(SELECT MIN(f.stat_key) FROM fact_player_stats f "
                "JOIN dim_team_scope sc ON sc.scope_key=f.scope_key WHERE f.player_key=? AND f.season_key=? AND f.phase_key=? AND sc.scope_kind='team')", args)
        with engine.connect() as connection:
            with self.assertRaisesRegex(StarError, "Wrong aggregate/canonical"):
                validate_target(connection, self.source)

    def test_roster_aggregate_reference_is_detected(self):
        self.assert_mutation_detected(
            "UPDATE fact_roster SET scope_key=(SELECT scope_key FROM dim_team_scope WHERE scope_code='2TM') WHERE roster_key=1",
            "Roster references an aggregate",
        )

    def test_wrong_mvp_representative_lineage_is_detected(self):
        self.assert_mutation_detected(
            "UPDATE fact_mvp_voting SET source_representative_stat_id=(SELECT MIN(source_stat_id) FROM fact_player_stats "
            "WHERE source_stat_id NOT IN (SELECT source_representative_stat_id FROM fact_mvp_voting)) WHERE mvp_vote_key=1",
            "MVP representative context",
        )

    def test_mvp_contest_maximum_is_checked(self):
        self.assert_mutation_detected(
            "UPDATE fact_mvp_voting SET voting_points_won=999999 WHERE mvp_vote_key=1", "MVP contest maximum exceeded")

    def test_changed_champion_descriptor_is_detected(self):
        self.assert_mutation_detected("UPDATE dim_season SET champion_team_name='Wrong' WHERE season_key=1", "Champion descriptor")

    def test_missing_partial_unique_index_is_detected(self):
        self.assert_mutation_detected("DROP INDEX uq_stats_canonical_player_phase", "canonical partial unique index")

    def test_salary_row_added_after_build_is_detected_by_initial_delivery_validator(self):
        self.assert_mutation_detected(
            "INSERT INTO fact_player_salary VALUES(1,1,1,12345678)", "Target counts conflict")

    def test_source_and_target_readonly_connections_reject_writes(self):
        for path, table in ((self.source_path, "player_stats"), (self.path, "fact_player_stats")):
            engine = readonly_engine(path)
            try:
                with engine.connect() as connection:
                    self.assertEqual(connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one(), 1)
                    with self.assertRaisesRegex(OperationalError, "readonly"):
                        connection.exec_driver_sql(f"DELETE FROM {table}")
            finally:
                engine.dispose()
        self.assertEqual(sha256(self.source_path), SOURCE_SHA256)

    def test_source_fingerprint_conflict_stops_before_publishing(self):
        folder = self.folder()
        source = folder / "changed.db"
        shutil.copyfile(self.source_path, source)
        with source.open("ab") as stream:
            stream.write(b"changed source")
        destination = folder / "target.db"
        with self.assertRaisesRegex(StarError, "Source fingerprint conflict"):
            build_database(source, destination)
        self.assertFalse(destination.exists())

    def test_unresolved_source_scope_and_duplicate_stat_id_are_diagnostics(self):
        changed = copy.deepcopy(self.source)
        changed.stats[0]["team"] = "ZZZ"
        with self.assertRaisesRegex(StarError, "Unresolved statistics reporting scope"):
            prepare_rows(changed)
        changed = copy.deepcopy(self.source)
        changed.stats.append(dict(changed.stats[0]))
        with self.assertRaisesRegex(StarError, "Duplicate source stat ID"):
            prepare_rows(changed)

    def test_source_aggregate_counter_conflict_is_not_silently_repaired(self):
        changed = copy.deepcopy(self.source)
        combined = next(row for row in changed.stats if row["scope_kind"] == "aggregate")
        combined["points"] += 1
        with self.assertRaisesRegex(StarError, "Aggregate counter conflict"):
            prepare_rows(changed)

    def test_existing_file_symlink_and_source_destination_are_preserved(self):
        folder = self.folder()
        occupied = folder / "occupied.db"
        occupied.write_bytes(b"keep existing")
        symlink = folder / "link.db"
        symlink.symlink_to(occupied)
        dangling = folder / "dangling.db"
        dangling.symlink_to(folder / "missing.db")
        for destination in (occupied, symlink, dangling, self.source_path):
            with self.subTest(destination=destination):
                with self.assertRaisesRegex(StarError, "already exists"):
                    build_database(self.source_path, destination)
        self.assertEqual(occupied.read_bytes(), b"keep existing")
        self.assertTrue(symlink.is_symlink())
        self.assertTrue(dangling.is_symlink())
        self.assertEqual(sha256(self.source_path), SOURCE_SHA256)

    def test_concurrent_destination_creation_cannot_be_overwritten(self):
        folder = self.folder()
        destination = folder / "raced.db"
        original_link = os.link

        def raced_link(source, target):
            Path(target).write_bytes(b"created by another process")
            return original_link(source, target)

        with patch("nba_star.build.os.link", side_effect=raced_link):
            with self.assertRaises(FileExistsError):
                build_database(self.source_path, destination)
        self.assertEqual(destination.read_bytes(), b"created by another process")
        self.assertEqual(list(folder.glob(".nba_star_build_*")), [])

    def test_validation_failure_cleans_staging_and_never_publishes(self):
        folder = self.folder()
        destination = folder / "failed.db"
        with patch("nba_star.build.validate_target", side_effect=StarError("synthetic validation conflict")):
            with self.assertRaisesRegex(StarError, "synthetic validation conflict"):
                build_database(self.source_path, destination)
        self.assertFalse(destination.exists())
        self.assertEqual(list(folder.glob(".nba_star_build_*")), [])

    def test_source_change_during_build_is_detected_before_publication(self):
        destination = self.folder() / "changed.db"
        real_sha256 = sha256

        def different_source_hash(path):
            return "changed" if Path(path).resolve() == self.source_path else real_sha256(path)

        with patch("nba_star.build.sha256", side_effect=different_source_hash):
            with self.assertRaisesRegex(StarError, "Source database changed during"):
                build_database(self.source_path, destination)
        self.assertFalse(destination.exists())

    def test_missing_source_and_invalid_destination_are_rejected(self):
        folder = self.folder()
        with self.assertRaisesRegex(StarError, "does not exist"):
            build_database(folder / "missing.db", folder / "target.db")
        with self.assertRaisesRegex(StarError, "parent does not exist"):
            build_database(self.source_path, folder / "missing" / "target.db")
        with self.assertRaisesRegex(StarError, ".db suffix"):
            build_database(self.source_path, folder / "target.txt")

    def test_cli_reports_are_created_and_existing_reports_are_protected(self):
        folder = self.folder()
        target, md, js = folder / "built.db", folder / "report.md", folder / "report.json"
        with redirect_stdout(io.StringIO()):
            code = main([str(self.source_path), "--database", str(target), "--report", str(md), "--json-report", str(js)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(js.read_text())["validation"]["table_counts"]["fact_player_salary"], 0)
        self.assertIn("**zero rows**", md.read_text())
        next_target = folder / "next.db"
        with redirect_stderr(io.StringIO()):
            code = main([str(self.source_path), "--database", str(next_target), "--report", str(md)])
        self.assertEqual(code, 1)
        self.assertFalse(next_target.exists())

    def test_importing_modules_does_not_create_any_database(self):
        folder = self.folder()
        environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
        result = subprocess.run([sys.executable, "-B", "-c", "import nba_star; import nba_star.build"],
                                cwd=folder, env=environment, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(list(folder.iterdir()), [])

    def test_all_example_queries_and_salary_left_join_semantics(self):
        content = (SQL_FOLDER / "example_queries.sql").read_text()
        pieces = re.split(r"^-- name: ([a-z_]+)\n", content, flags=re.M)
        results = {}
        with self.engine.connect() as connection:
            for index in range(1, len(pieces), 2):
                results[pieces[index]] = connection.exec_driver_sql(pieces[index + 1], {"season": "2023-24"}).mappings().all()
        self.assertEqual(len(results), 6)
        self.assertEqual(len(results["canonical_player_example"]), 10)
        self.assertEqual(len(results["champion_rosters"]), 96)
        self.assertEqual(sum(row["mvp_seasons"] for row in results["pg_mvp_appearances"]), 26)
        self.assertEqual(sum(row["points"] for row in results["canonical_season_comparisons"]), 1314107)
        self.assertEqual(len(results["canonical_season_comparisons"]), 5)
        self.assertEqual(len(results["salary_availability"]), 572)
        self.assertTrue(all(row["annual_salary_usd"] is None and row["salary_status"] == "unavailable"
                            for row in results["salary_availability"]))

    def test_half_up_rounding_tie_and_zero_denominator(self):
        self.assertEqual(rounded_ratio(1, 16), 0.063)
        self.assertEqual(rounded_ratio(1, 4, 10), 0.3)
        self.assertIsNone(rounded_ratio(0, 0))


if __name__ == "__main__":
    unittest.main()
