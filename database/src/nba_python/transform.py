"""Small, explicit source-to-target lookups; there is no salary ingestion."""

from collections import defaultdict

from .schema import ADVANCED, SEASONS, TOTALS
from .source import require


def unique_index(rows, columns, label):
    result = {}
    for row in rows:
        key = tuple(row[column] for column in columns)
        require(key not in result, f"Duplicate {label} key: {key}")
        result[key] = row
    return result


def lookup(mapping, key, label):
    require(key in mapping, f"Unresolved {label}: {key}")
    return mapping[key]


def prepare_rows(source):
    """Return deterministic insert dictionaries for the five dims/three facts.

    fact_player_salary is deliberately empty. No fabricated member, NULL
    placeholder, default salary or salary INSERT is used.
    """
    tables = source.tables
    players = sorted(tables["players"], key=lambda row: row["player_id"])
    teams = sorted(tables["teams"], key=lambda row: row["team_code"])
    seasons = sorted(tables["seasons"], key=lambda row: row["season"])
    require(tuple(row["season"] for row in seasons) == SEASONS,
            "Source seasons conflict with the five-season contract")
    player_seasons = unique_index(tables["player_seasons"], ("player_id", "season"), "player-season")
    phases = unique_index(tables["player_phases"], ("player_id", "season", "phase"), "player-phase")
    team_by_id = {row["team_id"]: row for row in teams}
    player_map = {row["player_id"]: index for index, row in enumerate(players, 1)}
    season_map = {row["season"]: index for index, row in enumerate(seasons, 1)}
    phase_map = {"regular_season": 1, "playoffs": 2}

    rows = {name: [] for name in (
        "dim_player", "dim_season", "dim_team_scope", "dim_phase",
        "dim_player_context", "fact_player_stats", "fact_mvp_voting",
        "fact_roster", "fact_player_salary",
    )}
    for player in players:
        rows["dim_player"].append(dict(
            player_key=player_map[player["player_id"]], source_player_id=player["player_id"],
            **{name: player[name] for name in (
                "player_name", "birth_date", "listed_height_inches", "listed_weight_pounds",
            )},
        ))
    for season in seasons:
        champion = lookup(team_by_id, season["champion_team_id"], "champion team")
        rows["dim_season"].append(dict(
            season_key=season_map[season["season"]], season_label=season["season"],
            champion_team_code=champion["team_code"], champion_team_name=champion["team_name"],
            maximum_mvp_voting_points=season["maximum_mvp_voting_points"],
        ))
    for index, team in enumerate(teams, 1):
        rows["dim_team_scope"].append(dict(
            scope_key=index, scope_code=team["team_code"], scope_kind="team",
            source_team_id=team["team_id"], team_name=team["team_name"], aggregate_team_count=None,
        ))

    stat_by_id = unique_index(source.stats, ("stat_id",), "source stat ID")
    groups = defaultdict(list)
    for stat in source.stats:
        groups[(stat["player_id"], stat["season"], stat["season_type"])].append(stat)
    require(set(groups) == set(phases), "Source phase/stat coverage conflict")
    canonical_ids = set()
    aggregate_codes = set()
    for group_key, stats in groups.items():
        phase = phases[group_key]
        aggregate = [row for row in stats if row["team_id"] is None]
        details = [row for row in stats if row["team_id"] is not None]
        count = phase["aggregate_team_count"]
        if count is None:
            require(not aggregate and len(details) == 1,
                    f"Expected one real-team observation for {group_key}")
            canonical_ids.add(details[0]["stat_id"])
        else:
            require(count in (2, 3, 4), f"Unsupported aggregate team count for {group_key}: {count}")
            require(len(aggregate) == 1 and len(details) == count,
                    f"Aggregate/detail cardinality conflict for {group_key}")
            combined = aggregate[0]
            code = f"{count}TM"
            require(combined["team"] == code and combined["scope_kind"] == "aggregate",
                    f"Aggregate label conflict for {group_key}")
            require(combined["position"] == phase["aggregate_position"],
                    f"Aggregate position conflict for {group_key}")
            for counter in TOTALS:
                require(combined[counter] == sum(row[counter] for row in details),
                        f"Aggregate counter conflict for {group_key}: {counter}")
            aggregate_codes.add(code)
            canonical_ids.add(combined["stat_id"])
    require(aggregate_codes == {"2TM", "3TM", "4TM"}, "Aggregate scope set changed")
    require({row["stat_id"] for row in source.stats
             if row["stat_id"] in canonical_ids and row["season_type"] == "regular_season"}
            == source.canonical_regular_ids, "Canonical selection differs from the validated source view")
    for code in sorted(aggregate_codes):
        rows["dim_team_scope"].append(dict(
            scope_key=len(rows["dim_team_scope"]) + 1, scope_code=code,
            scope_kind="aggregate", source_team_id=None, team_name=None,
            aggregate_team_count=int(code[0]),
        ))
    scope_map = {row["scope_code"]: row["scope_key"] for row in rows["dim_team_scope"]}
    rows["dim_phase"] = [
        dict(phase_key=1, phase_code="regular_season", phase_name="Regular Season"),
        dict(phase_key=2, phase_code="playoffs", phase_name="Playoffs"),
    ]

    contexts = {(row["age"], row["experience_years"], row["position"]) for row in source.stats}
    for roster in tables["rosters"]:
        player_season = lookup(player_seasons, (roster["player_id"], roster["season"]), "roster player-season")
        contexts.add((player_season["reported_age"], player_season["experience_years"], roster["position"]))
    context_map = {context: index for index, context in enumerate(sorted(contexts), 1)}
    for context, key in context_map.items():
        rows["dim_player_context"].append(dict(
            context_key=key, reported_age=context[0], experience_years=context[1], position_code=context[2],
        ))
    for index, stat in enumerate(sorted(source.stats, key=lambda row: row["stat_id"]), 1):
        rows["fact_player_stats"].append(dict(
            stat_key=index, source_stat_id=stat["stat_id"],
            player_key=lookup(player_map, stat["player_id"], "statistics player"),
            season_key=lookup(season_map, stat["season"], "statistics season"),
            scope_key=lookup(scope_map, stat["team"], "statistics reporting scope"),
            phase_key=lookup(phase_map, stat["season_type"], "statistics phase"),
            context_key=context_map[(stat["age"], stat["experience_years"], stat["position"])],
            totals_source_rank=stat["totals_source_rank"], advanced_source_rank=stat["advanced_source_rank"],
            is_player_phase_total=int(stat["stat_id"] in canonical_ids), awards_source_text=stat["awards"],
            **{name: stat[name] for name in TOTALS + ADVANCED},
        ))
    for index, roster in enumerate(sorted(tables["rosters"], key=lambda row: (
        row["player_id"], row["season"], row["team_id"],
    )), 1):
        player_season = player_seasons[(roster["player_id"], roster["season"])]
        team = lookup(team_by_id, roster["team_id"], "roster team")
        rows["fact_roster"].append(dict(
            roster_key=index, player_key=lookup(player_map, roster["player_id"], "roster player"),
            season_key=lookup(season_map, roster["season"], "roster season"),
            scope_key=scope_map[team["team_code"]],
            context_key=context_map[(player_season["reported_age"], player_season["experience_years"], roster["position"])],
        ))
    stats_target = {row["source_stat_id"]: row for row in rows["fact_player_stats"]}
    for index, vote in enumerate(sorted(tables["mvp_votes"], key=lambda row: (row["season"], row["player_id"])), 1):
        source_stat = lookup(stat_by_id, (vote["representative_stat_id"],), "MVP representative")
        require(source_stat["player_id"] == vote["player_id"] and source_stat["season"] == vote["season"],
                f"MVP representative identity conflict: {vote}")
        representative = stats_target[vote["representative_stat_id"]]
        require(representative["phase_key"] == 1 and representative["is_player_phase_total"] == 1,
                f"MVP representative is not canonical regular-season: {vote}")
        rows["fact_mvp_voting"].append(dict(
            mvp_vote_key=index,
            **{name: representative[name] for name in (
                "player_key", "season_key", "scope_key", "phase_key", "context_key",
            )},
            source_representative_stat_id=vote["representative_stat_id"],
            first_place_votes=vote["first_place_votes"], voting_points_won=vote["voting_points_won"],
        ))
    return rows
