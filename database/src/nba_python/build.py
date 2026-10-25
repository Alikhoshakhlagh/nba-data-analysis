"""Explicit protected build: python -m nba_star.build nba.db --database nba_star.db."""

import argparse
import json
import os
import platform
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError

from .database import create_schema, create_sqlite_engine
from .schema import metadata
from .source import SOURCE_COUNTS, StarError, read_source, require, sha256
from .transform import prepare_rows
from .validation import validate_target


def readonly_engine(path):
    url = URL.create("sqlite+pysqlite", database=Path(path).resolve().as_uri(),
                     query={"mode": "ro", "uri": "true"})
    return create_sqlite_engine(url)


def load_rows(connection, rows):
    """Insert the prepared snapshot into empty tables, inside the caller's transaction."""
    for name in metadata.tables:
        count = connection.exec_driver_sql(f'SELECT COUNT(*) FROM "{name}"').scalar_one()
        require(count == 0, f"Import requires empty tables; {name} has {count} rows")
    require(not rows["fact_player_salary"], "Salary ingestion is not part of this build")
    for table in metadata.sorted_tables:
        if rows[table.name]:
            connection.execute(table.insert(), rows[table.name])


def build_database(source_path, destination_path):
    """Validate a temporary file, then atomically publish without replacement.

    No --force/overwrite option is supplied. The original nba.db is always
    opened read-only; neither the ZIP nor any salary source is accessed.
    """
    destination = Path(destination_path).absolute()
    require(not destination.exists() and not destination.is_symlink(),
            f"Database already exists: {destination}; refusing to overwrite it. Choose a new path.")
    require(destination.parent.is_dir(), f"Destination parent does not exist: {destination.parent}")
    require(destination.suffix.lower() == ".db", "Destination must have a .db suffix")
    source = read_source(source_path)
    rows = prepare_rows(source)
    with tempfile.TemporaryDirectory(prefix=".nba_star_build_", dir=destination.parent) as folder:
        staged = Path(folder) / "validated_star.db"
        engine = create_sqlite_engine(URL.create("sqlite+pysqlite", database=str(staged)))
        try:
            create_schema(engine)
            with engine.connect() as connection:
                connection.exec_driver_sql("BEGIN IMMEDIATE")
                try:
                    load_rows(connection, rows)
                    validation = validate_target(connection, source)
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
        finally:
            engine.dispose()
        reopened = readonly_engine(staged)
        try:
            with reopened.connect() as connection:
                reopened_validation = validate_target(connection, source)
                require(reopened_validation == validation, "Reopened target validation changed")
        finally:
            reopened.dispose()
        require(sha256(source.path) == source.sha256, "Source database changed during the build")
        fingerprint = sha256(staged)
        # The temporary file lives beside the target, so this hard link is on
        # the same filesystem. It cannot replace an existing path, even in a race.
        os.link(staged, destination)
    require(sha256(destination) == fingerprint, "Published target fingerprint changed")
    require(sha256(source.path) == source.sha256, "Source database changed before final reporting")
    return dict(
        phase="5B - star implementation, including empty salary fact",
        status="PASS", created_at_utc=datetime.now(timezone.utc).isoformat(),
        source_database=source.path, source_sha256_before=source.sha256,
        source_sha256_after=sha256(source.path), source_unchanged=True,
        source_table_counts=dict(SOURCE_COUNTS), database=str(destination),
        database_sha256=fingerprint, database_bytes=destination.stat().st_size,
        python_version=platform.python_version(), sqlite_version=sqlite3.sqlite_version,
        sqlalchemy_version=sqlalchemy.__version__, reopened_read_only_and_validated=True,
        salary_ingestion_implemented=False, validation=validation,
    )


def markdown_report(report):
    validation = report["validation"]
    lines = [
        "# NBA star schema - final validation report", "",
        f"Status: **{report['status']}**. Source: validated `nba.db` only. "
        "Five dimensions and four facts; no salary ingestion.", "",
        f"Generated UTC: {report['created_at_utc']}", "",
        "## Source and target counts", "",
        "| Source relation / mapping | Source rows | Star target | Inserted rows |",
        "|---|---:|---|---:|",
    ]
    mappings = [
        ("players", 964, "dim_player", 964), ("seasons", 5, "dim_season", 5),
        ("teams + observed 2TM/3TM/4TM labels", "30 + 3", "dim_team_scope", 33),
        ("competition phases", 2, "dim_phase", 2),
        ("distinct age/experience/position tuples", 538, "dim_player_context", 538),
        ("player_stats", 4686, "fact_player_stats", 4686),
        ("mvp_votes", 61, "fact_mvp_voting", 61), ("rosters", 3203, "fact_roster", 3203),
        ("salary source unavailable; ingestion deferred", "None", "fact_player_salary", 0),
    ]
    lines += [f"| {source} | {count} | `{target}` | {inserted:,} |" for source, count, target, inserted in mappings]
    lines += ["", "Reconstructed source context relations: 2,789 player-seasons and 3,889 player-phases, "
              "both exactly equal to their source relations.", "", "## Database structure and integrity", ""]
    lines += [f"- {name.replace('_', ' ')}: {value}" for name, value in validation["schema"].items()]
    lines += [
        "- All 16 FKs point directly from facts to dimensions; dimensions have zero FKs.",
        "- All required values and all nullable Advanced values match the approved contract.",
        "- No salary defaults, seed rows, placeholder rows or salary INSERTs.",
        "- No fact-to-fact FKs, snowflakes, extra tables, stored views or triggers.",
        "- PRAGMA integrity_check: ok; foreign_key_check: zero violations.",
        "- Foreign-key enforcement verified on each managed connection.",
        "- All inserts and complete-load validation run in one transaction; failed builds remain unpublished.",
        "- Target closed, reopened read-only, and fully validated again before publication.",
        "", "## Exact data comparisons", "",
        "| Reconstructed source relation | Individual fields compared |", "|---|---:|",
    ]
    lines += [f"| {name} | {count:,} |" for name, count in validation["source_relation_field_comparisons"].items()]
    lines += [
        "", f"Full statistical projection: **{validation['statistical_projection_fields_compared']:,}** "
        "field comparisons across all 4,686 observations, including nine derived rates and six per-game values.",
        f"Reported Advanced measures: **{validation['reported_advanced_fields_compared']:,}** values "
        "checked without changing precision, valid negatives or NULLs.",
        f"Full MVP projection: **{validation['mvp_projection_fields_compared']:,}** field comparisons "
        "including source rank/ties, voting share, team/TOT labels and accompanying statistical fields.",
        "", "## Aggregate and canonical controls", "",
        "- Statistics: 3,582 Regular Season + 1,104 Playoffs = 4,686.",
        "- Real-team details: 4,302. Aggregate observations: 384 (356 2TM, 27 3TM, one 4TM).",
        "- Canonical observations: 3,889 (2,785 regular + 1,104 playoff). Other team details: 797.",
        "- All 384 aggregate groups reconcile on 21 Totals counters: 8,064 exact comparisons.",
        "- Canonical and real-team-only regular points both equal 1,314,107.",
        "- Unfiltered regular points: 1,459,081; overcount: 144,974. Canonical/team filtering is essential.",
        "- Both source ranks preserved; 4,599 observations have different Totals and Advanced ranks.",
        "- All four playoff-only player-seasons retained; no fabricated regular-season rows.",
        "- 61 MVP results retain exact canonical regular representatives: 59 real-team and two 2TM.",
        "- Two MVP TOT cases: Derrick Rose and James Harden, 2020-21; PG observations: 26.",
        "- Roster memberships: 3,203. Champion memberships: 96; no phase duplication.",
        "", "## Per-season controls", "",
        "| Season | Stats | Roster | MVP | Salary | Canonical regular | Champion memberships |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in validation["season_counts"]:
        lines.append("| {season} | {fact_player_stats:,} | {fact_roster:,} | {fact_mvp_voting:,} | "
                     "{fact_player_salary} | {canonical_regular:,} | {champion_memberships} |".format(**row))
    lines += ["", "## Advanced NULLs", "", "| Measure | NULL values |", "|---|---:|"]
    lines += [f"| `{name}` | {count} |" for name, count in validation["advanced_null_counts"].items()]
    lines += [
        "", "## Salary readiness and limits", "",
        "`fact_player_salary` exists and contains **zero rows**. Its provisional grain is one player-season; "
        "PK salary_key, required player/season dimension FKs, required INTEGER annual_salary_usd >= 0, "
        "and UNIQUE(player_key, season_key) are enforced. No salary source was opened or imported.", "",
        "Before a separate future salary importer is written, audit the real columns, identity matching, "
        "season definition, currency/units, and whether rows represent a player-season, a team, or a contract. "
        "If the latter grains apply, revise the design and uniqueness rules before import. "
        "An absent salary row means unavailable data; it must not become NULL/zero placeholder storage.", "",
        "The nonnegative CHECK allows an actual, verified zero in a future source; this build inserts no salaries of any value.",
        "", "## Enforcement boundary and remaining decisions", "",
        "Local PK/FK/UNIQUE/CHECK rules are enforced in SQLite. Full-load validation additionally enforces "
        "canonical choice/existence, real-team roster scopes, MVP representative alignment and contest maxima, "
        "shared age/experience, source rank ownership, champion consistency, and aggregate reconciliation. "
        "Arbitrary later manual writes can violate those cross-table semantics; no complex triggers are supplied.", "",
        "The Top 15/20/50 metric, eligibility and ties remain team decisions. Roster rows mean season membership, "
        "not a Finals game-day roster. Listed height/weight are source measurements rather than annual measurement history.",
        "", "## Preservation evidence and runtime", "",
        f"Source SHA-256 before: `{report['source_sha256_before']}`", "",
        f"Source SHA-256 after: `{report['source_sha256_after']}`", "",
        f"Target SHA-256: `{report['database_sha256']}`", "",
        f"Target bytes: {report['database_bytes']:,}. Python {report['python_version']}; "
        f"SQLite {report['sqlite_version']}; SQLAlchemy {report['sqlalchemy_version']}.", "",
        "The existing nba.db and Phase 4 implementation were preserved. The original ZIP/CSVs were not modified "
        "or used as inputs to this star load.", "",
        "Detected source/data conflicts: **none**. See the separate executed test report for test outcomes.", "",
    ]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="The validated original nba.db")
    parser.add_argument("--database", required=True, type=Path, help="A NEW destination .db file")
    parser.add_argument("--report", type=Path, help="A NEW Markdown validation report")
    parser.add_argument("--json-report", type=Path, help="A NEW JSON validation report")
    args = parser.parse_args(argv)
    try:
        paths = [path.absolute() for path in (args.database, args.report, args.json_report) if path is not None]
        require(len(set(path.resolve() for path in paths)) == len(paths), "Database/report output paths must be different")
        for path in paths:
            require(not path.exists() and not path.is_symlink(), f"Output already exists: {path}")
            require(path.parent.is_dir(), f"Output parent does not exist: {path.parent}")
        require(args.report is None or args.report.suffix.lower() == ".md", "Markdown report must have a .md suffix")
        require(args.json_report is None or args.json_report.suffix.lower() == ".json", "JSON report must have a .json suffix")
        report = build_database(args.source, args.database)
        if args.report:
            with args.report.open("x", encoding="utf-8") as stream:
                stream.write(markdown_report(report))
        if args.json_report:
            with args.json_report.open("x", encoding="utf-8") as stream:
                json.dump(report, stream, indent=2, ensure_ascii=False)
                stream.write("\n")
    except (StarError, OSError, SQLAlchemyError, sqlite3.Error, RuntimeError) as error:
        print(f"Star build stopped: {error}", file=sys.stderr)
        return 1
    print(f"PASS: {args.database}; 9 tables, 4,686 stats, 3,203 rosters, 61 MVP, 0 salaries.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
