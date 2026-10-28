from playwright.sync_api import Error as PlaywrightError

from browser import BrowserClient
from config import SEASON_END_YEARS
from parsers import CsvParser
from scraper import BasketballScraper


def main():
    """Extract and save all eight datasets for the configured seasons."""
    client = BrowserClient()
    parser = CsvParser()

    try:
        client.start()
        scraper = BasketballScraper(client, parser)

        for end_year in SEASON_END_YEARS:
            print(f"\nScraping season ending in {end_year}...")

            datasets = scraper.scrape_season(end_year)
            season = datasets["season_champion"]["season"].iloc[0]

            for dataset_name, df in datasets.items():
                path = parser.save_csv(
                    df,
                    f"output/{season}/{dataset_name}.csv",
                )

                print(f"Saved: {path} | Shape: {df.shape}")

    except (PlaywrightError, RuntimeError, ValueError, KeyError) as error:
        print(f"Error: {error}")
        raise SystemExit(1) from error

    except KeyboardInterrupt:
        print("\nStopped by the user.")

    finally:
        client.close()


if __name__ == "__main__":
    main()