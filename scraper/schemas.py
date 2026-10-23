ROSTER_COLUMN_MAP = {
    "No.": "jersey_number",
    "Player": "player_name",
    "Pos": "position",
    "Ht": "height_feet_inches",
    "Wt": "weight_pounds",
    "Birth Date": "birth_date",
    "Birth": "birth_country",
    "Exp": "experience",
    "College": "college"
}

ROSTER_DROP_COLUMNS = [
    "Player-additional"
]

ROSTER_DATE_FORMATS = {
    "birth_date": "%B %d %Y",
}

ROSTER_REQUIRED_COLUMNS = [
    "Player",
    "Pos",
    "Player-additional",
]

TOTALS_COLUMN_MAP = {
    "Rk": "rank",
    "Player": "player_name",
    "Age": "age",
    "Team": "team",
    "Pos": "position",
    "G": "games_played",
    "GS": "games_started",
    "MP": "minutes_played",
    "FG": "field_goals",
    "FGA": "field_goal_attempts",
    "FG%": "field_goal_percentage",
    "3P": "three_point_field_goals",
    "3PA": "three_point_attempts",
    "3P%": "three_point_percentage",
    "2P": "two_point_field_goals",
    "2PA": "two_point_attempts",
    "2P%": "two_point_percentage",
    "eFG%": "effective_field_goal_percentage",
    "FT": "free_throws",
    "FTA": "free_throw_attempts",
    "FT%": "free_throw_percentage",
    "ORB": "offensive_rebounds",
    "DRB": "defensive_rebounds",
    "TRB": "total_rebounds",
    "AST": "assists",
    "STL": "steals",
    "BLK": "blocks",
    "TOV": "turnovers",
    "PF": "personal_fouls",
    "PTS": "points",
    "Trp-Dbl": "triple_doubles",
    "Awards": "awards",
}

TOTALS_REQUIRED_COLUMNS = [
    "Player",
    "G",
    "PTS"
]

TOTALS_DROP_COLUMNS = [
    "Player-additional"
]

ADVANCED_REQUIRED_COLUMNS = [
    "Player",
    "PER",
    "WS",
]

ADVANCED_DROP_COLUMNS = [
    "Player-additional",
]

ADVANCED_COLUMN_MAP = {
    "Rk": "rank",
    "Player": "player_name",
    "Age": "age",
    "Team": "team",
    "Pos": "position",
    "G": "games_played",
    "GS": "games_started",
    "MP": "minutes_played",
    "PER": "player_efficiency_rating",
    "TS%": "true_shooting_percentage",
    "3PAr": "three_point_attempt_rate",
    "FTr": "free_throw_attempt_rate",
    "ORB%": "offensive_rebound_percentage",
    "DRB%": "defensive_rebound_percentage",
    "TRB%": "total_rebound_percentage",
    "AST%": "assist_percentage",
    "STL%": "steal_percentage",
    "BLK%": "block_percentage",
    "TOV%": "turnover_percentage",
    "USG%": "usage_percentage",
    "OWS": "offensive_win_shares",
    "DWS": "defensive_win_shares",
    "WS": "win_shares",
    "WS/48": "win_shares_per_48_minutes",
    "OBPM": "offensive_box_plus_minus",
    "DBPM": "defensive_box_plus_minus",
    "BPM": "box_plus_minus",
    "VORP": "value_over_replacement_player",
    "Awards": "awards",
}

MVP_REQUIRED_COLUMNS = [
    "Rank",
    "Player",
    "Pts Won",
    "Share",
]

MVP_DROP_COLUMNS = [
    "-9999",
]

MVP_COLUMN_MAP = {
    "Rank": "rank",
    "Player": "player_name",
    "Age": "age",
    "Tm": "team",
    "First": "first_place_votes",
    "Pts Won": "voting_points_won",
    "Pts Max": "maximum_voting_points",
    "Share": "voting_points_share",
    "G": "games_played",
    "MP": "minutes_per_game",
    "PTS": "points_per_game",
    "TRB": "rebounds_per_game",
    "AST": "assists_per_game",
    "STL": "steals_per_game",
    "BLK": "blocks_per_game",
    "FG%": "field_goal_percentage",
    "3P%": "three_point_percentage",
    "FT%": "free_throw_percentage",
    "WS": "win_shares",
    "WS/48": "win_shares_per_48_minutes",
}