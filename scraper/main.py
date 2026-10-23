from playwright.sync_api import Error as PlaywrightError

from browser import BrowserClient
from parsers import CsvParser
from scraper import BasketballScraper
from storage import save_csv

from config import SEASON_END_YEARS


def main():
    """Extract and save all required datasets for the configured seasons."""

    client = BrowserClient()
    parser = CsvParser()

    try:
        client.start()

        scraper = BasketballScraper(client, parser)

        for year in SEASON_END_YEARS:

            print(f"Scraping season ending in {year}...")

            datasets = scraper.scrape_season(year)
            season = datasets["season_champion"]["season"].iloc[0]

            for dataset_name, df in datasets.items():

                path = save_csv(
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