-- Each named block is a separate read-only query.
-- Ranking by reported Win Shares is a demonstration, not the team's final metric.

-- name: canonical_player_example
SELECT p.player_name, se.season_label, sc.scope_code, c.position_code,
       f.games_played, f.points, f.win_shares,
       f.totals_source_rank, f.advanced_source_rank
FROM fact_player_stats AS f
JOIN dim_player AS p ON p.player_key = f.player_key
JOIN dim_season AS se ON se.season_key = f.season_key
JOIN dim_team_scope AS sc ON sc.scope_key = f.scope_key
JOIN dim_player_context AS c ON c.context_key = f.context_key
WHERE f.phase_key = 1 AND f.is_player_phase_total = 1
  AND se.season_label = :season
ORDER BY f.win_shares DESC, p.player_name
LIMIT 10;

-- name: champion_rosters
SELECT se.season_label, sc.scope_code AS champion_team, p.player_name,
       c.reported_age, c.experience_years, c.position_code,
       p.listed_height_inches, p.listed_weight_pounds
FROM fact_roster AS r
JOIN dim_player AS p ON p.player_key = r.player_key
JOIN dim_season AS se ON se.season_key = r.season_key
JOIN dim_team_scope AS sc ON sc.scope_key = r.scope_key
JOIN dim_player_context AS c ON c.context_key = r.context_key
WHERE sc.scope_kind = 'team' AND sc.scope_code = se.champion_team_code
ORDER BY se.season_label, p.player_name;

-- name: pg_mvp_appearances
SELECT p.player_name, COUNT(DISTINCT se.season_label) AS mvp_seasons
FROM fact_mvp_voting AS m
JOIN dim_player AS p ON p.player_key = m.player_key
JOIN dim_season AS se ON se.season_key = m.season_key
JOIN dim_player_context AS c ON c.context_key = m.context_key
WHERE c.position_code = 'PG'
GROUP BY p.player_key, p.player_name
ORDER BY mvp_seasons DESC, p.player_name;

-- name: canonical_season_comparisons
SELECT se.season_label, COUNT(*) AS player_seasons,
       SUM(f.points) AS points, SUM(f.assists) AS assists,
       1.0 * SUM(f.field_goals) / NULLIF(SUM(f.field_goal_attempts), 0) AS weighted_fg_ratio
FROM fact_player_stats AS f
JOIN dim_season AS se ON se.season_key = f.season_key
WHERE f.phase_key = 1 AND f.is_player_phase_total = 1
GROUP BY se.season_key, se.season_label
ORDER BY se.season_label;

-- name: real_team_stats
SELECT se.season_label, ph.phase_code, sc.scope_code,
       SUM(f.points) AS points, COUNT(*) AS player_observations
FROM fact_player_stats AS f
JOIN dim_season AS se ON se.season_key = f.season_key
JOIN dim_phase AS ph ON ph.phase_key = f.phase_key
JOIN dim_team_scope AS sc ON sc.scope_key = f.scope_key
WHERE sc.scope_kind = 'team'
GROUP BY se.season_key, ph.phase_key, sc.scope_key
ORDER BY se.season_label, ph.phase_code, sc.scope_code;

-- name: salary_availability
-- Salary rows are absent. A NULL in a LEFT JOIN result is not a stored placeholder.
-- Select canonical statistics first so a later player-season salary appears once.
SELECT p.player_name, se.season_label, sal.annual_salary_usd,
       CASE WHEN sal.salary_key IS NULL THEN 'unavailable' ELSE 'reported' END AS salary_status
FROM fact_player_stats AS f
JOIN dim_player AS p ON p.player_key = f.player_key
JOIN dim_season AS se ON se.season_key = f.season_key
LEFT JOIN fact_player_salary AS sal
       ON sal.player_key = f.player_key AND sal.season_key = f.season_key
WHERE f.phase_key = 1 AND f.is_player_phase_total = 1
  AND se.season_label = :season
ORDER BY p.player_name;
