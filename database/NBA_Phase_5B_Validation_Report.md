# NBA star schema - final validation report

Status: **PASS**. Source: validated `nba.db` only. Five dimensions and four facts; no salary ingestion.

Generated UTC: 2026-10-24T14:39:22.089716+00:00

## Source and target counts

| Source relation / mapping | Source rows | Star target | Inserted rows |
|---|---:|---|---:|
| players | 964 | `dim_player` | 964 |
| seasons | 5 | `dim_season` | 5 |
| teams + observed 2TM/3TM/4TM labels | 30 + 3 | `dim_team_scope` | 33 |
| competition phases | 2 | `dim_phase` | 2 |
| distinct age/experience/position tuples | 538 | `dim_player_context` | 538 |
| player_stats | 4686 | `fact_player_stats` | 4,686 |
| mvp_votes | 61 | `fact_mvp_voting` | 61 |
| rosters | 3203 | `fact_roster` | 3,203 |
| salary source unavailable; ingestion deferred | None | `fact_player_salary` | 0 |

Reconstructed source context relations: 2,789 player-seasons and 3,889 player-phases, both exactly equal to their source relations.

## Database structure and integrity

- tables: 9
- dimensions: 5
- facts: 4
- columns: 90
- primary keys: 9
- foreign keys: 16
- unique constraints: 13
- check constraints: 55
- partial unique indexes: 1
- strict tables: 9
- All 16 FKs point directly from facts to dimensions; dimensions have zero FKs.
- All required values and all nullable Advanced values match the approved contract.
- No salary defaults, seed rows, placeholder rows or salary INSERTs.
- No fact-to-fact FKs, snowflakes, extra tables, stored views or triggers.
- PRAGMA integrity_check: ok; foreign_key_check: zero violations.
- Foreign-key enforcement verified on each managed connection.
- All inserts and complete-load validation run in one transaction; failed builds remain unpublished.
- Target closed, reopened read-only, and fully validated again before publication.

## Exact data comparisons

| Reconstructed source relation | Individual fields compared |
|---|---:|
| players | 4,820 |
| teams | 90 |
| seasons | 15 |
| player_stats | 182,754 |
| rosters | 12,812 |
| player_seasons | 11,156 |
| player_phases | 27,223 |
| mvp_votes | 305 |

Full statistical projection: **328,020** field comparisons across all 4,686 observations, including nine derived rates and six per-game values.
Reported Advanced measures: **74,976** values checked without changing precision, valid negatives or NULLs.
Full MVP projection: **1,647** field comparisons including source rank/ties, voting share, team/TOT labels and accompanying statistical fields.

## Aggregate and canonical controls

- Statistics: 3,582 Regular Season + 1,104 Playoffs = 4,686.
- Real-team details: 4,302. Aggregate observations: 384 (356 2TM, 27 3TM, one 4TM).
- Canonical observations: 3,889 (2,785 regular + 1,104 playoff). Other team details: 797.
- All 384 aggregate groups reconcile on 21 Totals counters: 8,064 exact comparisons.
- Canonical and real-team-only regular points both equal 1,314,107.
- Unfiltered regular points: 1,459,081; overcount: 144,974. Canonical/team filtering is essential.
- Both source ranks preserved; 4,599 observations have different Totals and Advanced ranks.
- All four playoff-only player-seasons retained; no fabricated regular-season rows.
- 61 MVP results retain exact canonical regular representatives: 59 real-team and two 2TM.
- Two MVP TOT cases: Derrick Rose and James Harden, 2020-21; PG observations: 26.
- Roster memberships: 3,203. Champion memberships: 96; no phase duplication.

## Per-season controls

| Season | Stats | Roster | MVP | Salary | Canonical regular | Champion memberships |
|---|---:|---:|---:|---:|---:|---:|
| 2019-20 | 868 | 592 | 12 | 0 | 529 | 20 |
| 2020-21 | 944 | 626 | 15 | 0 | 540 | 22 |
| 2021-22 | 1,029 | 716 | 12 | 0 | 605 | 17 |
| 2022-23 | 896 | 612 | 13 | 0 | 539 | 18 |
| 2023-24 | 949 | 657 | 9 | 0 | 572 | 19 |

## Advanced NULLs

| Measure | NULL values |
|---|---:|
| `player_efficiency_rating` | 6 |
| `offensive_rebound_percentage` | 6 |
| `defensive_rebound_percentage` | 6 |
| `total_rebound_percentage` | 6 |
| `assist_percentage` | 6 |
| `steal_percentage` | 6 |
| `block_percentage` | 6 |
| `usage_percentage` | 6 |
| `offensive_win_shares` | 0 |
| `defensive_win_shares` | 0 |
| `win_shares` | 0 |
| `win_shares_per_48_minutes` | 6 |
| `offensive_box_plus_minus` | 6 |
| `defensive_box_plus_minus` | 6 |
| `box_plus_minus` | 6 |
| `value_over_replacement_player` | 0 |

## Salary readiness and limits

`fact_player_salary` exists and contains **zero rows**. Its provisional grain is one player-season; PK salary_key, required player/season dimension FKs, required INTEGER annual_salary_usd >= 0, and UNIQUE(player_key, season_key) are enforced. No salary source was opened or imported.

Before a separate future salary importer is written, audit the real columns, identity matching, season definition, currency/units, and whether rows represent a player-season, a team, or a contract. If the latter grains apply, revise the design and uniqueness rules before import. An absent salary row means unavailable data; it must not become NULL/zero placeholder storage.

The nonnegative CHECK allows an actual, verified zero in a future source; this build inserts no salaries of any value.

## Enforcement boundary and remaining decisions

Local PK/FK/UNIQUE/CHECK rules are enforced in SQLite. Full-load validation additionally enforces canonical choice/existence, real-team roster scopes, MVP representative alignment and contest maxima, shared age/experience, source rank ownership, champion consistency, and aggregate reconciliation. Arbitrary later manual writes can violate those cross-table semantics; no complex triggers are supplied.

The Top 15/20/50 metric, eligibility and ties remain team decisions. Roster rows mean season membership, not a Finals game-day roster. Listed height/weight are source measurements rather than annual measurement history.

## Preservation evidence and runtime

Source SHA-256 before: `49f057cf1dab88b91529c23694e47af0698622f29dcbc6be631a6d984c8b8a9e`

Source SHA-256 after: `49f057cf1dab88b91529c23694e47af0698622f29dcbc6be631a6d984c8b8a9e`

Target SHA-256: `fc5755547c1e48227396b210053116f0f68339ac98d219859d9773e3f7994c95`

Target bytes: 1,462,272. Python 3.9.6; SQLite 3.54.0; SQLAlchemy 2.0.55.

The existing nba.db and Phase 4 implementation were preserved. The original ZIP/CSVs were not modified or used as inputs to this star load.

Detected source/data conflicts: **none**. See the separate executed test report for test outcomes.

## Executed automated tests

All **164 tests passed**: 32 new schema tests, 34 new real-source build/validation tests, 36 original schema tests, 37 original ETL tests and 25 original Phase 4 tests. There were no failures, errors or skips. See `NBA_Phase_5B_Test_Results.md` for the complete new-method listing and `NBA_Phase_5B_Test_Results.json` for every executed method in both suites.

All 18 existing Phase 4 source/test/document files are byte-for-byte unchanged. The original ZIP SHA-256 still equals `9a8806d643c28dcfca1b2b0585cc7b32d5db3e4286513f8936d7d71c97baae37`.
