"""Compare persisted star data with every source relation and source projection."""

from collections import Counter, defaultdict
from pathlib import Path

from sqlalchemy import inspect

from .schema import ADVANCED, DIMENSIONS, FACTS, SEASONS, TOTALS, metadata
from .source import TARGET_COUNTS, require
from .transform import unique_index

SQL_FOLDER = Path(__file__).resolve().parent / "sql"


def fetch(connection, statement):
    return [dict(row) for row in connection.exec_driver_sql(statement).mappings()]


def compare_rows(label, expected, actual, keys):
    """Compare values including NULL/empty strings; never round or repair data."""
    expected_index = unique_index(expected, keys, f"expected {label}")
    actual_index = unique_index(actual, keys, f"actual {label}")
    require(set(actual_index) == set(expected_index), f"{label}: natural key coverage conflict")
    compared = 0
    for key, expected_row in expected_index.items():
        row = actual_index[key]
        require(set(row) == set(expected_row), f"{label} {key}: column set conflict")
        for name, value in expected_row.items():
            require(row[name] == value,
                    f"{label} {key}, {name}: source={value!r}, target={row[name]!r}")
            compared += 1
    return compared


def validate_schema(connection):
    inspector = inspect(connection)
    require(set(inspector.get_table_names()) == set(metadata.tables), "Expected exactly nine target tables")
    require(inspector.get_view_names() == [], "Unexpected stored star views")
    require(connection.exec_driver_sql("SELECT COUNT(*) FROM sqlite_schema WHERE type='trigger'").scalar_one() == 0,
            "Unexpected star triggers")
    strict = {row["name"]: row["strict"] for row in connection.exec_driver_sql("PRAGMA table_list").mappings()
              if row["name"] in metadata.tables}
    require(strict == {name: 1 for name in metadata.tables}, "Every target table must be STRICT")
    fk_count = unique_count = check_count = column_count = 0
    for name, table in metadata.tables.items():
        actual_columns = {
            col["name"]: (str(col["type"]), col["nullable"], col["default"])
            for col in inspector.get_columns(name)
        }
        expected_columns = {col.name: (str(col.type), col.nullable, None) for col in table.columns}
        require(actual_columns == expected_columns, f"{name}: column/type/nullability/default contract conflict")
        require(inspector.get_pk_constraint(name)["constrained_columns"] == [col.name for col in table.primary_key],
                f"{name}: primary-key contract conflict")
        expected_unique = {tuple(col.name for col in rule.columns) for rule in table.constraints
                           if rule.__class__.__name__ == "UniqueConstraint"}
        actual_unique = {tuple(rule["column_names"]) for rule in inspector.get_unique_constraints(name)}
        require(actual_unique == expected_unique, f"{name}: UNIQUE contract conflict")
        expected_checks = {rule.name: "".join(str(rule.sqltext).split()) for rule in table.constraints
                           if rule.__class__.__name__ == "CheckConstraint"}
        actual_checks = {rule["name"]: "".join(rule["sqltext"].split())
                         for rule in inspector.get_check_constraints(name)}
        require(actual_checks == expected_checks, f"{name}: CHECK contract conflict")
        expected_fks = {(tuple(col.name for col in rule.columns),
                         tuple(element.target_fullname for element in rule.elements), "RESTRICT", "RESTRICT")
                        for rule in table.foreign_key_constraints}
        actual_fks = {(tuple(rule["constrained_columns"]),
                       tuple(f'{rule["referred_table"]}.{column}' for column in rule["referred_columns"]),
                       rule["options"].get("ondelete"), rule["options"].get("onupdate"))
                      for rule in inspector.get_foreign_keys(name)}
        require(actual_fks == expected_fks, f"{name}: FK contract conflict")
        fk_count += len(actual_fks)
        unique_count += len(actual_unique)
        check_count += len(actual_checks)
        column_count += len(actual_columns)
        if name.startswith("dim_"):
            require(not actual_fks, f"Snowflake relationship in {name}")
        for rule in inspector.get_foreign_keys(name):
            require(name.startswith("fact_") and rule["referred_table"].startswith("dim_"),
                    f"Non-star FK found in {name}")
        indexes = inspector.get_indexes(name)
        if name == "fact_player_stats":
            require(len(indexes) == 1, "Expected one canonical partial unique index")
            rule = indexes[0]
            require(rule["name"] == "uq_stats_canonical_player_phase" and rule["unique"] == 1
                    and tuple(rule["column_names"]) == ("player_key", "season_key", "phase_key")
                    and "".join(str(rule["dialect_options"].get("sqlite_where")).split()) == "is_player_phase_total=1",
                    "Canonical partial index contract conflict")
        else:
            require(not indexes, f"Unexpected explicit index in {name}")
    require(fk_count == 16 and column_count == 90, "Nine-table schema size/topology conflict")
    return dict(tables=9, dimensions=len(DIMENSIONS), facts=len(FACTS), columns=column_count,
                primary_keys=9, foreign_keys=fk_count, unique_constraints=unique_count,
                check_constraints=check_count, partial_unique_indexes=1, strict_tables=9)


def stats_projection(connection):
    return fetch(connection, (SQL_FOLDER / "stats_projection.sql").read_text())


def rounded_ratio(numerator, denominator, scale=1000):
    if denominator == 0:
        return None
    return ((2 * numerator * scale + denominator) // (2 * denominator)) / scale


def validate_target(connection, source):
    require(connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1, "Target foreign keys are OFF")
    require(connection.exec_driver_sql("PRAGMA integrity_check").scalars().all() == ["ok"], "Target integrity_check failed")
    require(connection.exec_driver_sql("PRAGMA foreign_key_check").all() == [], "Target foreign_key_check failed")
    schema = validate_schema(connection)
    target = {name: fetch(connection, f'SELECT * FROM "{name}"') for name in metadata.tables}
    counts = {name: len(rows) for name, rows in target.items()}
    require(counts == TARGET_COUNTS, f"Target counts conflict: expected {TARGET_COUNTS}, got {counts}")
    players = {row["player_key"]: row for row in target["dim_player"]}
    seasons = {row["season_key"]: row for row in target["dim_season"]}
    scopes = {row["scope_key"]: row for row in target["dim_team_scope"]}
    phases = {row["phase_key"]: row["phase_code"] for row in target["dim_phase"]}
    contexts = {row["context_key"]: row for row in target["dim_player_context"]}
    source_comparisons = {}
    actual_players = [{name: (row["source_player_id"] if name == "player_id" else row[name])
                       for name in source.tables["players"][0]} for row in players.values()]
    source_comparisons["players"] = compare_rows("players", source.tables["players"], actual_players, ("player_id",))
    actual_teams = [dict(team_id=row["source_team_id"], team_code=row["scope_code"], team_name=row["team_name"])
                    for row in scopes.values() if row["scope_kind"] == "team"]
    source_comparisons["teams"] = compare_rows("teams", source.tables["teams"], actual_teams, ("team_id",))
    teams_by_code = {row["team_code"]: row for row in actual_teams}
    actual_seasons = []
    for row in seasons.values():
        champion = teams_by_code.get(row["champion_team_code"])
        require(champion is not None and champion["team_name"] == row["champion_team_name"],
                f"Champion descriptor conflict: {row['season_label']}")
        actual_seasons.append(dict(season=row["season_label"], champion_team_id=champion["team_id"],
                                   maximum_mvp_voting_points=row["maximum_mvp_voting_points"]))
    source_comparisons["seasons"] = compare_rows("seasons", source.tables["seasons"], actual_seasons, ("season",))

    stats = target["fact_player_stats"]
    by_source_id = {row["source_stat_id"]: row for row in stats}
    source_ids = {row["stat_id"] for row in source.stats}
    require(set(by_source_id) == source_ids, "Source statistical ID coverage conflict")
    projected = stats_projection(connection)
    projection_compared = compare_rows("full statistical projection", source.stats, projected, ("stat_id",))
    actual_raw_stats = []
    projected_by_id = {row["stat_id"]: row for row in projected}
    for stat in stats:
        row = projected_by_id[stat["source_stat_id"]]
        aliases = {"phase": "season_type", "awards_source_text": "awards"}
        actual_raw_stats.append({name: row[aliases.get(name, name)] for name in source.tables["player_stats"][0]})
    source_comparisons["player_stats"] = compare_rows(
        "raw player_stats", source.tables["player_stats"], actual_raw_stats, ("stat_id",))

    groups = defaultdict(list)
    player_season_contexts = defaultdict(set)
    actual_rosters = []
    champion_counts = Counter()
    for stat in stats:
        key = (players[stat["player_key"]]["source_player_id"],
               seasons[stat["season_key"]]["season_label"], phases[stat["phase_key"]])
        groups[key].append(stat)
        context = contexts[stat["context_key"]]
        player_season_contexts[key[:2]].add((context["reported_age"], context["experience_years"]))
    for roster in target["fact_roster"]:
        scope = scopes[roster["scope_key"]]
        require(scope["scope_kind"] == "team", f"Roster references an aggregate scope: {roster['roster_key']}")
        season = seasons[roster["season_key"]]
        context = contexts[roster["context_key"]]
        player_id = players[roster["player_key"]]["source_player_id"]
        actual_rosters.append(dict(player_id=player_id, season=season["season_label"],
                                   team_id=scope["source_team_id"], position=context["position_code"]))
        player_season_contexts[(player_id, season["season_label"])].add(
            (context["reported_age"], context["experience_years"]))
        if scope["scope_code"] == season["champion_team_code"]:
            champion_counts[season["season_label"]] += 1
    source_comparisons["rosters"] = compare_rows("rosters", source.tables["rosters"], actual_rosters,
                                                 ("player_id", "season", "team_id"))
    actual_player_seasons = []
    for (player_id, season), values in player_season_contexts.items():
        require(len(values) == 1, f"Age/experience conflict for player-season {(player_id, season)}")
        age, experience = next(iter(values))
        actual_player_seasons.append(dict(player_id=player_id, season=season, reported_age=age, experience_years=experience))
    source_comparisons["player_seasons"] = compare_rows(
        "player_seasons", source.tables["player_seasons"], actual_player_seasons, ("player_id", "season"))

    aggregate_comparisons = 0
    actual_phases = []
    rank_owners = {}
    canonical_source_ids = set()
    for (player_id, season, phase), observations in groups.items():
        aggregates = [row for row in observations if scopes[row["scope_key"]]["scope_kind"] == "aggregate"]
        details = [row for row in observations if scopes[row["scope_key"]]["scope_kind"] == "team"]
        canonical = [row for row in observations if row["is_player_phase_total"] == 1]
        require(len(canonical) == 1, f"Missing or duplicate canonical observation for {(player_id, season, phase)}")
        canonical_source_ids.add(canonical[0]["source_stat_id"])
        if aggregates:
            require(len(aggregates) == 1 and canonical[0] == aggregates[0],
                    f"Wrong aggregate/canonical selection for {(player_id, season, phase)}")
            combined = aggregates[0]
            count = scopes[combined["scope_key"]]["aggregate_team_count"]
            require(len(details) == count and phase == "regular_season", "Aggregate team count/phase conflict")
            for counter in TOTALS:
                require(combined[counter] == sum(row[counter] for row in details),
                        f"Aggregate counter conflict: {(player_id, season, phase)}, {counter}")
                aggregate_comparisons += 1
            aggregate_position = contexts[combined["context_key"]]["position_code"]
        else:
            require(len(details) == 1 and canonical[0] == details[0], "Single-team canonical conflict")
            count = aggregate_position = None
        rank_values = {(row["totals_source_rank"], row["advanced_source_rank"]) for row in observations}
        require(len(rank_values) == 1, f"Repeated source ranks disagree for {(player_id, season, phase)}")
        totals_rank, advanced_rank = next(iter(rank_values))
        for label, rank in (("totals", totals_rank), ("advanced", advanced_rank)):
            owner_key = (season, phase, label, rank)
            require(owner_key not in rank_owners, f"Source rank belongs to two players: {owner_key}")
            rank_owners[owner_key] = player_id
        actual_phases.append(dict(player_id=player_id, season=season, phase=phase,
                                  totals_source_rank=totals_rank, advanced_source_rank=advanced_rank,
                                  aggregate_team_count=count, aggregate_position=aggregate_position))
    source_comparisons["player_phases"] = compare_rows(
        "player_phases", source.tables["player_phases"], actual_phases, ("player_id", "season", "phase"))
    regular_ids = {row["source_stat_id"] for row in stats if row["phase_key"] == 1 and row["is_player_phase_total"] == 1}
    require(regular_ids == source.canonical_regular_ids, "Canonical regular source ID selection conflict")

    actual_votes = []
    actual_mvp_projection = []
    pg_votes = aggregate_votes = 0
    for vote in target["fact_mvp_voting"]:
        representative = by_source_id.get(vote["source_representative_stat_id"])
        require(representative is not None, "MVP representative lineage missing")
        require(all(vote[name] == representative[name] for name in (
            "player_key", "season_key", "phase_key", "scope_key", "context_key",
        )) and representative["phase_key"] == 1 and representative["is_player_phase_total"] == 1,
                f"MVP representative context is not canonical regular-season: {vote['mvp_vote_key']}")
        season = seasons[vote["season_key"]]
        require(vote["voting_points_won"] <= season["maximum_mvp_voting_points"], "MVP contest maximum exceeded")
        stat = projected_by_id[vote["source_representative_stat_id"]]
        actual_votes.append(dict(player_id=stat["player_id"], season=stat["season"],
                                 representative_stat_id=stat["stat_id"], first_place_votes=vote["first_place_votes"],
                                 voting_points_won=vote["voting_points_won"]))
        peers = [row for row in target["fact_mvp_voting"] if row["season_key"] == vote["season_key"]]
        rank = 1 + sum(row["voting_points_won"] > vote["voting_points_won"] for row in peers)
        tied = sum(row["voting_points_won"] == vote["voting_points_won"] for row in peers) > 1
        reconstructed = dict(
            rank=str(rank) + ("T" if tied else ""), player_name=stat["player_name"], age=stat["age"],
            team="TOT" if stat["scope_kind"] == "aggregate" else stat["team"],
            first_place_votes=vote["first_place_votes"], voting_points_won=vote["voting_points_won"],
            maximum_voting_points=season["maximum_mvp_voting_points"],
            voting_points_share=rounded_ratio(vote["voting_points_won"], season["maximum_mvp_voting_points"]),
            **{name: stat[name] for name in (
                "games_played", "minutes_per_game", "points_per_game", "rebounds_per_game", "assists_per_game",
                "steals_per_game", "blocks_per_game", "field_goal_percentage", "three_point_percentage",
                "free_throw_percentage", "win_shares", "win_shares_per_48_minutes", "season", "player_id",
                "team_id", "scope_kind", "position",
            )},
            representative_stat_id=stat["stat_id"], stat_team=stat["team"],
        )
        actual_mvp_projection.append(reconstructed)
        pg_votes += stat["position"] == "PG"
        aggregate_votes += stat["scope_kind"] == "aggregate"
    source_comparisons["mvp_votes"] = compare_rows("mvp_votes", source.tables["mvp_votes"], actual_votes, ("player_id", "season"))
    mvp_projection_compared = compare_rows("full MVP projection", source.mvp_projection, actual_mvp_projection, ("player_id", "season"))

    expected_contexts = {(row["age"], row["experience_years"], row["position"]) for row in source.stats}
    source_player_seasons = {(row["player_id"], row["season"]): row for row in source.tables["player_seasons"]}
    for row in source.tables["rosters"]:
        ps = source_player_seasons[(row["player_id"], row["season"])]
        expected_contexts.add((ps["reported_age"], ps["experience_years"], row["position"]))
    actual_contexts = {(row["reported_age"], row["experience_years"], row["position_code"]) for row in contexts.values()}
    require(actual_contexts == expected_contexts, "Context combination set conflict")
    require({(row["phase_key"], row["phase_code"], row["phase_name"]) for row in target["dim_phase"]} == {
        (1, "regular_season", "Regular Season"), (2, "playoffs", "Playoffs"),
    }, "Phase dictionary conflict")
    require({(row["scope_code"], row["aggregate_team_count"], row["source_team_id"], row["team_name"])
             for row in scopes.values() if row["scope_kind"] == "aggregate"}
            == {("2TM", 2, None, None), ("3TM", 3, None, None), ("4TM", 4, None, None)},
            "Aggregate dimension members conflict")

    def points(predicate):
        return sum(row["points"] for row in stats if row["phase_key"] == 1 and predicate(row))

    sums = dict(canonical_regular=points(lambda row: row["is_player_phase_total"] == 1),
                team_only_regular=points(lambda row: scopes[row["scope_key"]]["scope_kind"] == "team"),
                all_regular=points(lambda row: True))
    require(sums == {"canonical_regular": 1314107, "team_only_regular": 1314107, "all_regular": 1459081},
            f"Point reconciliation conflict: {sums}")
    require(aggregate_comparisons == 8064 and pg_votes == 26 and aggregate_votes == 2,
            "Aggregate or MVP cohort control conflict")
    require([champion_counts[season] for season in SEASONS] == [20, 22, 17, 18, 19], "Champion roster count conflict")
    season_counts = []
    for key, season in sorted(seasons.items(), key=lambda item: item[1]["season_label"]):
        season_counts.append(dict(
            season=season["season_label"],
            fact_player_stats=sum(row["season_key"] == key for row in stats),
            fact_roster=sum(row["season_key"] == key for row in target["fact_roster"]),
            fact_mvp_voting=sum(row["season_key"] == key for row in target["fact_mvp_voting"]),
            fact_player_salary=0,
            canonical_regular=sum(row["season_key"] == key and row["phase_key"] == 1 and row["is_player_phase_total"] == 1 for row in stats),
            champion_memberships=champion_counts[season["season_label"]],
        ))
    return dict(
        status="PASS", schema=schema, table_counts=counts,
        source_relation_field_comparisons=source_comparisons,
        statistical_projection_fields_compared=projection_compared,
        reported_advanced_fields_compared=len(stats) * len(ADVANCED),
        advanced_null_counts={name: sum(row[name] is None for row in stats) for name in ADVANCED},
        mvp_projection_fields_compared=mvp_projection_compared,
        aggregate_counter_comparisons=aggregate_comparisons,
        player_seasons=len(actual_player_seasons), player_phases=len(groups),
        canonical_observations=len(canonical_source_ids), canonical_regular=len(regular_ids),
        phase_counts=dict(Counter(phases[row["phase_key"]] for row in stats)),
        scope_counts=dict(Counter(scopes[row["scope_key"]]["scope_kind"] for row in stats)),
        aggregate_label_counts=dict(Counter(scopes[row["scope_key"]]["scope_code"] for row in stats
                                           if scopes[row["scope_key"]]["scope_kind"] == "aggregate")),
        noncanonical_observations=sum(row["is_player_phase_total"] == 0 for row in stats),
        differing_source_rank_observations=sum(row["totals_source_rank"] != row["advanced_source_rank"] for row in stats),
        pg_mvp_results=pg_votes, aggregate_mvp_results=aggregate_votes,
        champion_memberships=sum(champion_counts.values()), point_sums=sums,
        season_counts=season_counts, salary_import_attempted=False,
        salary_rows=0, salary_grain="PROVISIONAL player-season; verify actual source before ingestion",
        integrity_check="ok", foreign_key_violations=0, issues=[],
    )
