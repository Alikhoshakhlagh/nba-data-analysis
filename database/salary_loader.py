from pathlib import Path
import sqlite3
import re
import unicodedata
import pandas as pd

DATABASE = "database/data/nba_star.db"
CSV_FOLDER = "scraper/output"

ALIASES = {
    "mohamed bamba": "mo bamba",
    "marcos louzada silva": "didi louzada",
}


def clean_name(name):
    name = unicodedata.normalize("NFKD", str(name))
    name = name.encode("ascii", "ignore").decode().lower()
    name = re.sub(r"[.'’]", "", name).replace("-", " ")
    name = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", name)
    return " ".join(name.split())


files = list(Path(CSV_FOLDER).glob("*/salaries.csv"))
parts = [pd.read_csv(file, encoding="utf-8-sig") for file in files]
salaries = pd.concat(parts, ignore_index=True)

connection = sqlite3.connect(DATABASE)
players = pd.read_sql_query(
    "SELECT player_key, player_name FROM dim_player", connection
)
seasons = dict(connection.execute(
    "SELECT season_label, season_key FROM dim_season"
).fetchall())

player_keys = {}
for row in players.itertuples(index=False):
    name = clean_name(row.player_name)
    player_keys[ALIASES.get(name, name)] = row.player_key

salaries = salaries[salaries["season"].isin(seasons)].copy()
salaries["salary_usd"] = pd.to_numeric(salaries["salary_usd"], errors="coerce")
salaries = salaries.dropna(subset=["player_name", "salary_usd"])
salaries = salaries[salaries["salary_usd"] > 0].copy()
salaries["name_key"] = salaries["player_name"].apply(clean_name)
salaries["name_key"] = salaries["name_key"].replace(ALIASES)
salaries["player_key"] = salaries["name_key"].map(player_keys)
salaries = salaries.dropna(subset=["player_key"])

totals = salaries.groupby(["player_key", "season"], as_index=False)["salary_usd"].sum()
rows = []

for number, row in enumerate(totals.itertuples(index=False), start=1):
    rows.append((
        number,
        int(row.player_key),
        int(seasons[row.season]),
        int(round(row.salary_usd)),
    ))

with connection:
    connection.executemany(
        "INSERT INTO fact_player_salary "
        "(salary_key, player_key, season_key, annual_salary_usd) "
        "VALUES (?, ?, ?, ?)",
        rows,
    )

connection.close()
print(f"Inserted {len(rows)} salary rows.")
