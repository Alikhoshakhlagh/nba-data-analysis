-- Read-only validation projection, not a stored view.
-- This reconstructs the validated source columns using only direct star joins.
WITH counts AS (
    SELECT
        f.*, f.source_stat_id AS stat_id,
        p.source_player_id AS player_id, s.season_label AS season,
        ph.phase_code AS phase, sc.source_team_id AS team_id,
        sc.scope_code AS team, sc.team_name, sc.scope_kind,
        p.player_name, p.birth_date, p.listed_height_inches, p.listed_weight_pounds,
        c.reported_age AS age, c.experience_years, c.position_code AS position
    FROM fact_player_stats AS f
    JOIN dim_player AS p ON p.player_key = f.player_key
    JOIN dim_season AS s ON s.season_key = f.season_key
    JOIN dim_phase AS ph ON ph.phase_key = f.phase_key
    JOIN dim_team_scope AS sc ON sc.scope_key = f.scope_key
    JOIN dim_player_context AS c ON c.context_key = f.context_key
), denominators AS (
    SELECT counts.*,
        50 * field_goal_attempts + 22 * free_throw_attempts AS ts_denominator,
        25 * (field_goal_attempts + turnovers) + 11 * free_throw_attempts AS tov_denominator
    FROM counts
)
SELECT
    stat_id, player_id, season, phase AS season_type,
    team_id, team, team_name, scope_kind, player_name, age, position,
    birth_date, listed_height_inches, listed_weight_pounds, experience_years,
    totals_source_rank, advanced_source_rank,
    games_played, games_started, minutes_played,
    field_goals, field_goal_attempts,
    ((2 * field_goals * 1000 + field_goal_attempts)
        / NULLIF(2 * field_goal_attempts, 0)) / 1000.0 AS field_goal_percentage,
    three_point_field_goals, three_point_attempts,
    ((2 * three_point_field_goals * 1000 + three_point_attempts)
        / NULLIF(2 * three_point_attempts, 0)) / 1000.0 AS three_point_percentage,
    two_point_field_goals, two_point_attempts,
    ((2 * two_point_field_goals * 1000 + two_point_attempts)
        / NULLIF(2 * two_point_attempts, 0)) / 1000.0 AS two_point_percentage,
    ((2 * (2 * field_goals + three_point_field_goals) * 1000 + 2 * field_goal_attempts)
        / NULLIF(4 * field_goal_attempts, 0)) / 1000.0 AS effective_field_goal_percentage,
    free_throws, free_throw_attempts,
    ((2 * free_throws * 1000 + free_throw_attempts)
        / NULLIF(2 * free_throw_attempts, 0)) / 1000.0 AS free_throw_percentage,
    offensive_rebounds, defensive_rebounds, total_rebounds,
    assists, steals, blocks, turnovers, personal_fouls, points, triple_doubles,
    ((2 * 25 * points * 1000 + ts_denominator)
        / NULLIF(2 * ts_denominator, 0)) / 1000.0 AS true_shooting_percentage,
    ((2 * three_point_attempts * 1000 + field_goal_attempts)
        / NULLIF(2 * field_goal_attempts, 0)) / 1000.0 AS three_point_attempt_rate,
    ((2 * free_throw_attempts * 1000 + field_goal_attempts)
        / NULLIF(2 * field_goal_attempts, 0)) / 1000.0 AS free_throw_attempt_rate,
    ((2 * 2500 * turnovers * 10 + tov_denominator)
        / NULLIF(2 * tov_denominator, 0)) / 10.0 AS turnover_percentage,
    -- All 16 reported Advanced measures below are direct, unchanged columns.
    player_efficiency_rating, offensive_rebound_percentage, defensive_rebound_percentage,
    total_rebound_percentage, assist_percentage, steal_percentage, block_percentage,
    usage_percentage, offensive_win_shares, defensive_win_shares, win_shares,
    win_shares_per_48_minutes, offensive_box_plus_minus, defensive_box_plus_minus,
    box_plus_minus, value_over_replacement_player,
    awards_source_text AS awards,
    ((2 * minutes_played * 10 + games_played) / NULLIF(2 * games_played, 0)) / 10.0 AS minutes_per_game,
    ((2 * points * 10 + games_played) / NULLIF(2 * games_played, 0)) / 10.0 AS points_per_game,
    ((2 * total_rebounds * 10 + games_played) / NULLIF(2 * games_played, 0)) / 10.0 AS rebounds_per_game,
    ((2 * assists * 10 + games_played) / NULLIF(2 * games_played, 0)) / 10.0 AS assists_per_game,
    ((2 * steals * 10 + games_played) / NULLIF(2 * games_played, 0)) / 10.0 AS steals_per_game,
    ((2 * blocks * 10 + games_played) / NULLIF(2 * games_played, 0)) / 10.0 AS blocks_per_game
FROM denominators;
