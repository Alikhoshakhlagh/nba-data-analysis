# NBA star schema - Phase 5B

`../nba_star.db` is a separate analytical database built only from the validated
`nba.db`. It contains **five dimensions and four facts**. The original 3NF
database, its code, and the scraped ZIP/CSVs are preserved.

The eight tables approved in Phase 5A retain their columns and grains. The only
design addition is `fact_player_salary`, with **zero rows**. Salaries have not
been scraped into this delivery, and there is no salary importer.

## Open the delivered database

You need a SQLite client using SQLite **3.37.0 or later** because all nine tables
are STRICT. Python/SQLAlchemy is needed to rebuild or test, not to query the file.
Extract the delivery ZIP before opening the database.

From the delivery folder containing `nba_star.db`:

```sh
sqlite3 --version
sqlite3 -readonly nba_star.db
```

Inside the SQLite shell:

```sql
.headers on
.mode column
.tables
PRAGMA integrity_check;
PRAGMA foreign_key_check;
SELECT COUNT(*) AS salary_records FROM fact_player_salary;

SELECT p.player_name, se.season_label, f.points, f.win_shares
FROM fact_player_stats AS f
JOIN dim_player AS p ON p.player_key = f.player_key
JOIN dim_season AS se ON se.season_key = f.season_key
WHERE f.phase_key = 1 AND f.is_player_phase_total = 1
  AND se.season_label = '2023-24'
ORDER BY f.win_shares DESC, p.player_name
LIMIT 10;
```

The dot commands work in the SQLite shell. In a GUI, select Open Database,
choose `nba_star.db`, and use the SQL editor for the SELECT/PRAGMA statements.
The Win Shares example is a demonstration, not the team's final ranking metric.

## Table grains and counts

| Table | Grain | Rows |
|---|---|---:|
| `dim_player` | One source player identity; DOB and listed height/weight | 964 |
| `dim_season` | One approved season; flattened champion and MVP contest maximum | 5 |
| `dim_team_scope` | One real team or aggregate reporting label | 33 |
| `dim_phase` | Regular Season or Playoffs | 2 |
| `dim_player_context` | One exact observed age/experience/position combination | 538 |
| `fact_player_stats` | Player-season-phase-source scope | 4,686 |
| `fact_mvp_voting` | Player-season MVP result with canonical regular context | 61 |
| `fact_roster` | Player-season-real-team membership; no phase | 3,203 |
| `fact_player_salary` | PROVISIONAL player-season annual USD salary | 0 |

Only 2019-20 through 2023-24 are included. The statistics contain 3,582 Regular
Season observations and 1,104 Playoffs observations. Every FK goes directly
from a fact to a dimension: 16 links in total. There are no dimension chains,
fact-to-fact FKs, hidden tables, stored analytical views or triggers.

The source's 2,789 player-seasons and 3,889 player-phases are reconstructed
exactly through the facts and dimensions; they do not become extra tables.
The 538-row context mini-dimension has no FK of its own. Age is the source's
reported age, experience is exact (rookie = 0), and position may differ by scope.
Champion code/name are stored directly in `dim_season`, avoiding a snowflake.

`ERD.mmd` contains the complete typed Mermaid ERD, including the salary fact.

## Choose the correct scope before summing

For whole-player Regular Season comparisons use:

```sql
WHERE f.phase_key = 1 AND f.is_player_phase_total = 1
```

For team analysis join `dim_team_scope`, select `scope_kind='team'`, and select
or group the competition phase. `2TM`, `3TM` and `4TM` are reporting scopes,
not fake teams. Their source team ID/name are NULL, while every fact's scope
key is non-NULL. `TOT` is reconstructed only as the MVP source display alias.

All 384 aggregate observations remain stored alongside 797 noncanonical team
details. A canonical row is the aggregate if present, otherwise the sole team
row. There are 3,889 canonical rows across both phases, including 2,785 Regular
Season rows. All playoff rows are canonical in this source snapshot.

Andrew Wiggins in 2019-20 has MIN 942 points, GSW 233, and 2TM 1,175. Whole-player
analysis takes 2TM once; team analysis takes MIN and GSW. Summing all three is
incorrect. Across all five seasons, canonical and real-team-only Regular Season
points both equal 1,314,107. Unfiltered points total 1,459,081, an overcount of
144,974. Games summed across players count player appearances, not NBA games.

Facts have different grains. Aggregate each fact to a shared grain or select
one canonical row before combining facts. Raw roster/statistics/voting joins
can multiply rows. A future salary should join once to the canonical
player-season result, not to every phase/team observation.

## Salaries: schema ready, data deferred

The implemented salary contract is exactly:

```text
salary_key INTEGER PRIMARY KEY
player_key INTEGER NOT NULL REFERENCES dim_player(player_key)
season_key INTEGER NOT NULL REFERENCES dim_season(season_key)
annual_salary_usd INTEGER NOT NULL CHECK (annual_salary_usd >= 0)
UNIQUE(player_key, season_key)
```

Both FKs use ON UPDATE RESTRICT / ON DELETE RESTRICT. There are no salary
defaults, seed rows, placeholder records or salary INSERTs in the loader.
The delivered salary table is empty, not a table of NULL or zero values.
The nonnegative constraint permits an actual verified zero in a future source;
this phase inserts no salary of any value.

Before a **separate future importer** is implemented:

1. Audit the scraped columns and establish whether the grain is player-season,
   team allocation, contract year or something else. Revise keys/constraints
   first if the data is team/contract-level. Do not merge with unsupported
   SUM/MAX/DISTINCT operations.
2. Define what annual salary means, which season the year refers to, USD units,
   integer dollars versus fractional dollars, and treatment of contract,
   guaranteed, cap-hit or other distinct amounts.
3. Match identities to the reviewed player dimension; unknown/ambiguous players
   must stop import for review. Names alone are not guaranteed identifiers.
4. Diagnose missing values and duplicates. Absence stays absence; do not create
   zero/NULL stand-ins. Preserve real source precision or revise the design.
5. Write separate salary validation/import tests and a versioned report. The
   current initial-delivery validator intentionally requires zero salary rows;
   update that contract only after the salary design/data is reviewed.

`salary_availability` in the example SQL uses a LEFT JOIN and reports missing
salary data as unavailable. NULLs in the query result are not stored placeholder
rows. It does not use COALESCE(...,0).

## Statistics, source ranks and NULLs

The main fact retains both source ranks; neither becomes the team's final
ranking metric. Rank repetition across a player's team/aggregate rows is
expected. Loading validates one rank owner per season/phase/source and consistent
ranks across each player's observations.

All 21 Totals counters are stored. Four counters derived by the validated
source view are materialized with exact arithmetic CHECK identities: FG, FGA,
TRB and PTS. All 16 reported Advanced measures are copied unchanged, including
negative values and valid NULLs. Do not reconstruct WS/BPM from their rounded
components. Raw awards remain on their exact source observation; blank text
stays blank. Removed country, college and jersey attributes are not restored.

`nba_star/sql/stats_projection.sql` is a **read-only SELECT**, not a stored view.
It reconstructs all 70 source-view fields, including nine rounded rates and six
per-game values. It uses the previously validated nonnegative HALF_UP integer
ratio expressions and NULLIF for zero denominators. Shooting/TS/attempt ratios
use three decimals; TOV percentage and per-game values use one. Reported
Advanced columns remain direct columns. All projected values match the source.

MVP voting preserves its original canonical regular source stat ID as lineage
without a fact-to-fact FK. Full-load validation checks its existence and exact
player/season/scope/phase/context alignment. Two aggregate MVP cases remain:
Derrick Rose and James Harden, 2020-21. Voting rank/tie suffix and share remain
reconstructible, as verified against the complete source projection.

## Query examples

`nba_star/sql/example_queries.sql` contains six separate read-only statements:

- Canonical Regular Season players, ordered by reported WS as a demonstration.
- Champion season roster memberships and their height/weight/experience.
- PG MVP appearances, counting distinct seasons per player.
- Canonical season totals and weighted FG ratio.
- Real-team statistics grouped by phase and season.
- Salary availability for canonical player-seasons, without storing placeholders.

Bind `:season` to a label such as `2023-24`, or substitute a reviewed SQL literal
when running one query manually. Run each named block separately.

The Top 15/20/50 metric, eligibility, tie handling, and PG/active-roster cohort
rules remain team decisions. Champion memberships are scraped season
memberships, not Finals game-day rosters. Listed height/weight are not annual
physical-measurement history or direct measurements of agility/innate ability.

## Rebuild explicitly into a NEW file

From this `nba_star_schema/` folder, use Python 3.9+, SQLite 3.37.0+ and the
SQLAlchemy dependency below. The runtime checks STRICT support before creation.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -B -m nba_star.build /path/to/validated/nba.db \
  --database ../nba_star_rebuilt.db \
  --report ../NBA_Star_Rebuild_Report.md \
  --json-report ../NBA_Star_Rebuild_Report.json
```

The source must match the accepted SHA-256:
`49f057cf1dab88b91529c23694e47af0698622f29dcbc6be631a6d984c8b8a9e`.
A changed source stops with a diagnostic; review it instead of bypassing the
fingerprint. The original ZIP is not a star-load input.

The database argument is required. Module imports do not create files. The
destination parent must exist and all output paths must be new. Existing files,
empty files, symlinks and racing destinations are protected; there is no force
overwrite flag. A temporary database beside the destination receives all inserts
in one transaction. Full validation runs before commit; the staged file is then
closed and reopened read-only for validation again. Publication uses an atomic
hard link without replacement, requiring local hard-link filesystem support.
The temporary directory is removed after success or failure. Report writing
occurs after successful publication.

All source connections use read-only/query-only access. Every managed target
connection enables foreign keys. External writers must enable
`PRAGMA foreign_keys=ON` too; SQLite does not persist that setting in the file.

## Tests and enforcement boundary

The executed delivery checks passed **164/164 tests**: 66 new star schema/build
tests and all 98 unchanged 3NF schema/ETL/Phase 4 regression tests, with no failures
or skips. The detailed test report records the commands and every executed method.

```sh
NBA_SOURCE_DB=/path/to/validated/nba.db \
  .venv/bin/python -B -m unittest discover -s tests -v
```

All tests use memory or temporary databases. Salary constraint tests use
synthetic positive salary fixtures only in disposable test databases; they
never insert salaries into the delivered file. Tests cover the exact ERD
contract, all 16 FKs, 13 UNIQUE constraints, 55 CHECKs, the canonical partial
unique index, STRICT tables, salary absence/constraints, exact source fidelity,
aggregate/canonical/MVP rules, read-only access, rollback, diagnostic failures,
and publication protection.

SQLite enforces the declared local constraints. Full-load validation separately
enforces real-team roster scopes, canonical existence/choice, aggregate counts
and reconciliation, repeated ranks and source rank ownership, correct context,
champions, MVP representatives and contest limits. Arbitrary later manual writes
can violate those cross-table rules. No complex triggers are supplied; revalidate
the snapshot or design a separate approved writing workflow.

## Source files

- `nba_star/schema.py`: all nine SQLAlchemy Core tables and their constraints.
- `nba_star/database.py`: engine configuration, STRICT guard and explicit DDL.
- `nba_star/source.py`: fingerprinted, read-only source snapshot and count contract.
- `nba_star/transform.py`: explicit dimensional lookups and canonical selection.
- `nba_star/validation.py`: source relation reconstruction and complete-load checks.
- `nba_star/build.py`: transactional import, protected publication and CLI reports.
- `nba_star/sql/stats_projection.sql`: full source-equivalent statistical SELECT.
- `nba_star/sql/example_queries.sql`: teammate query examples.
- `ERD.mmd`: complete updated nine-table ERD, including salary.
- `tests/test_schema.py`, `tests/test_build.py`: schema and real-source tests.

See the accompanying Phase 5B validation and executed test reports for actual
results and fingerprints. The older Phase 5A PDF is the historical eight-table
proposal; the updated nine-table design/ERD supersedes it for implementation.
