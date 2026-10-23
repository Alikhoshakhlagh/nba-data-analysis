from schemas import *
import pandas as pd

class BasketballScraper:
    """Coordinate page extraction and data processing."""

    def __init__(self, browser, parser):
        """Store the browser and parser used by the scraper.

        Args:
            browser: The browser client used for navigation and exports.
            parser: The CSV parser used for table processing.
        """
        self.browser = browser
        self.parser = parser

    def scrape_roster(self, url, season, team_name):
        """Extract and process a team roster for a season.

        Args:
            url: The address of the team's season page.
            season: season label, such as "2023-24".
            team_name: team name to include in the output.

        Returns:
            A pandas DataFrame containing the processed roster.
            Season and team_name columns are added.

        Raises:
            RuntimeError: If navigation fails or the page title
                does not identify a team roster and stats page.
            ValueError: If header detection or date parsing fails.
            KeyError: If a configured column is missing.
        """
        title = self.browser.open_page(url)

        if "Roster and Stats" not in title:
            raise RuntimeError(
                "The loaded page is not a team roster and stats page."
            )

        csv_text = self.browser.export_table("roster")

        df = self.parser.parse_export(
            csv_text,
            required_columns=ROSTER_REQUIRED_COLUMNS,
            drop_columns=ROSTER_DROP_COLUMNS
        )

        normalized_df = self.parser.normalize_headers(
            df,
            ROSTER_COLUMN_MAP,
        )

        cleaned_df = self.parser.normalize_dates(
            normalized_df,
            ROSTER_DATE_FORMATS,
        )

        cleaned_df["season"] = season

        cleaned_df["team_name"] = team_name

        return cleaned_df

    def scrape_totals(self, url, season):
        """Extract and process regular-season and playoff player Totals.

        Args:
            url: The address of the season's player Totals page.
            season: The season label, such as "2023-24".

        Returns:
            A dictionary mapping regular_season and playoffs to processed
            DataFrames with standardized columns and season information.
            League Average rows and player IDs are excluded.

        Raises:
            RuntimeError: If navigation fails or the page title is unexpected.
            ValueError: If the CSV header cannot be found.
            KeyError: If a configured column is missing.
        """
        title = self.browser.open_page(url)
        if "Player Stats: Totals" not in title:
            raise RuntimeError(
                "The loaded page is not a Total stats page."
            )

        report_settings = {
            "regular_season": {
                "section_id": "all_totals_stats",
                "tab_name": "Regular Season",
                "table_id": "totals_stats",
            },
            "playoffs": {
                "section_id": "all_totals_stats",
                "tab_name": "Playoffs",
                "table_id": "totals_stats_post",
            },
        }

        results = {}

        for report_type, settings in report_settings.items():

            self.browser.select_table_tab(
                settings["section_id"],
                settings["tab_name"],
            )

            csv_text = self.browser.export_table(settings["table_id"])

            df = self.parser.parse_export(
                csv_text,
                required_columns=TOTALS_REQUIRED_COLUMNS,
                drop_columns=TOTALS_DROP_COLUMNS
            )

            filtered_df = df.loc[df["Player"] != "League Average"].copy()

            normalized_df = self.parser.normalize_headers(
                filtered_df,
                TOTALS_COLUMN_MAP
            )

            normalized_df["season"] = season
            normalized_df["season_type"] = report_type

            results[report_type] = normalized_df

        return results

    def scrape_advanced(self, url, season):
        """Extract and process regular-season and playoff Advanced statistics.

        Args:
            url: The address of the season's player Advanced statistics page.
            season: The season label, such as "2023-24".

        Returns:
            A dictionary mapping regular_season and playoffs to processed
            DataFrames with standardized columns and season information.
            League Average rows and player IDs are excluded.

        Raises:
            RuntimeError: If navigation fails or the page title is unexpected.
            ValueError: If the CSV header cannot be found.
            KeyError: If a configured column is missing.
        """
        title = self.browser.open_page(url)
        if "Player Stats: Advanced" not in title:
            raise RuntimeError(
                "The loaded page is not an Advanced stats page."
            )

        report_settings = {
            "regular_season": {
                "section_id": "all_advanced",
                "tab_name": "Regular Season",
                "table_id": "advanced",
            },
            "playoffs": {
                "section_id": "all_advanced",
                "tab_name": "Playoffs",
                "table_id": "advanced_post",
            },
        }

        results = {}

        for report_type, settings in report_settings.items():

            self.browser.select_table_tab(
                settings["section_id"],
                settings["tab_name"],
            )

            csv_text = self.browser.export_table(settings["table_id"])

            df = self.parser.parse_export(
                csv_text,
                required_columns=ADVANCED_REQUIRED_COLUMNS,
                drop_columns=ADVANCED_DROP_COLUMNS
            )

            filtered_df = df.loc[df["Player"] != "League Average"].copy()

            normalized_df = self.parser.normalize_headers(
                filtered_df,
                ADVANCED_COLUMN_MAP
            )

            normalized_df["season"] = season
            normalized_df["season_type"] = report_type

            results[report_type] = normalized_df

        return results

    def scrape_mvp_voting(self, url, season):
        """Extract and process a season's MVP voting table.

        Args:
            url: The address of the season's awards voting page.
            season: The season label, such as "2023-24".

        Returns:
            A DataFrame with standardized column names and a season column.
            Player IDs are excluded.

        Raises:
            RuntimeError: If navigation fails or the page title is unexpected.
            ValueError: If the CSV header cannot be found.
            KeyError: If a configured column is missing.
        """
        title = self.browser.open_page(url)

        if "NBA Awards Voting" not in title:
            raise RuntimeError(
                "The loaded page is not a NBA Awards Voting page."
            )

        csv_text = self.browser.export_table("mvp")

        df = self.parser.parse_export(
            csv_text,
            required_columns=MVP_REQUIRED_COLUMNS,
            drop_columns=MVP_DROP_COLUMNS
        )

        normalized_df = self.parser.normalize_headers(
            df,
            MVP_COLUMN_MAP,
        )

        normalized_df["season"] = season

        return normalized_df

    def scrape_season_overview(self, url, season):
        """Extract team page URLs and the league champion for a season.

        Args:
            url: The address of the season summary page.
            season: The season label, such as "2023-24".

        Returns:
            A dictionary containing a teams list with team_name and url,
            and a champion DataFrame with season and champion_team_name.

        Raises:
            RuntimeError: If navigation fails or the page title is unexpected.
        """
        title = self.browser.open_page(url)

        if "NBA Season Summary" not in title:
            raise RuntimeError(
                "The loaded page is not an NBA Season Summary page."
            )

        team_links = self.browser.extract_links(
            '#totals-team tbody td[data-stat="team"] a'
        )

        champion_links = self.browser.extract_links(
            'div#info p:has-text("League Champion") a'
        )

        teams = []

        for link in team_links:
            teams.append({
                "team_name": link["text"],
                "url": link["url"],
            })

        champion_df = pd.DataFrame([
            {
                "season": season,
                "champion_team_name": champion_links[0]["text"],
            }
        ])

        return {
            "teams": teams,
            "champion": champion_df,
        }

    def scrape_season_rosters(self, teams, season):
        """Extract and combine rosters for all supplied teams in a season.

        Args:
            teams: A list of dictionaries containing team_name and url.
            season: The season label, such as "2023-24".

        Returns:
            A combined roster DataFrame with season and team_name columns
            and a continuous index.

        Raises:
            RuntimeError: If navigation fails or a team page is unexpected.
            ValueError: If header detection or date parsing fails.
            KeyError: If a configured column is missing.
        """
        data_frames = []

        for team in teams:
            data_frames.append(self.scrape_roster(team["url"], season, team["team_name"]))

        combined_df = pd.concat(
            data_frames,
            ignore_index=True,
        )

        return combined_df

    def scrape_season(self, end_year):
        """Extract all required datasets for a season.

        Args:
            end_year: The calendar year in which the season ends.

        Returns:
            A dictionary mapping dataset names to seven processed DataFrames.

        Raises:
            RuntimeError: If navigation fails or a page is unexpected.
            ValueError: If header detection or date parsing fails.
            KeyError: If a configured column is missing.
        """
        start_year = end_year - 1
        short_end_year = str(end_year)[-2:]
        time_period = f"{start_year}-{short_end_year}"

        overview_url = f"https://www.basketball-reference.com/leagues/NBA_{end_year}.html"
        totals_url = f"https://www.basketball-reference.com/leagues/NBA_{end_year}_totals.html"
        advanced_url = f"https://www.basketball-reference.com/leagues/NBA_{end_year}_advanced.html"
        mvp_url = f"https://www.basketball-reference.com/awards/awards_{end_year}.html"

        overview = self.scrape_season_overview(overview_url, time_period)
        totals = self.scrape_totals(totals_url, time_period)
        advanced = self.scrape_advanced(advanced_url, time_period)
        mvp_voting = self.scrape_mvp_voting(mvp_url, time_period)
        rosters = self.scrape_season_rosters(overview["teams"], time_period)

        return {
            "rosters": rosters,
            "totals_regular": totals["regular_season"],
            "totals_playoffs": totals["playoffs"],
            "advanced_regular": advanced["regular_season"],
            "advanced_playoffs": advanced["playoffs"],
            "mvp_voting": mvp_voting,
            "season_champion": overview["champion"],
        }