from playwright.sync_api import sync_playwright
from urllib.parse import urljoin


class BrowserClient:
    """Manage the Playwright browser and its resources."""

    def __init__(self):
        """Initialize browser resources before startup."""
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def start(self):
        """Start Chromium and create one browser context and page.

        Raises:
            RuntimeError: If the browser client has already been started.
        """
        if self.playwright is not None:
            raise RuntimeError("The browser client has already been started.")

        self.playwright = sync_playwright().start()

        self.browser = self.playwright.chromium.launch(
            headless=False
        )

        self.context = self.browser.new_context()
        self.page = self.context.new_page()

    def open_page(self, url):
        """Open a URL and return its page title.

        Args:
            url: The address of the page to open.

        Returns:
            The title of the loaded page.

        Raises:
            RuntimeError: If the browser has not started or navigation
                returns no response or an HTTP error.
        """
        if self.page is None:
            raise RuntimeError("Start the browser before opening a page.")

        response = self.page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        if response is None:
            raise RuntimeError("Navigation returned no HTTP response.")

        if response.status >= 400:
            raise RuntimeError(
                f"HTTP {response.status} while opening {url}"
            )

        return self.page.title()

    def close(self):
        """Close browser resources, including after a partial startup."""
        try:
            if self.context is not None:
                self.context.close()
        finally:
            try:
                if self.browser is not None:
                    self.browser.close()
            finally:
                try:
                    if self.playwright is not None:
                        self.playwright.stop()
                finally:
                    self.page = None
                    self.context = None
                    self.browser = None
                    self.playwright = None

    def export_table(self, table_id):
        """Export a table and return its non-empty raw CSV text.

        Args:
            table_id: The HTML ID of the table to export.

        Returns:
            The raw CSV text exported from the table.

        Raises:
            RuntimeError: If the browser has not started or the export is empty.
        """
        if self.page is None:
            raise RuntimeError("Start the browser before exporting a table.")

        csv_id = f"csv_{table_id}"

        csv_locator = self.page.locator(f"#{csv_id}")

        section_locator = self.page.locator(f"#{table_id}_sh")

        share_button = section_locator.get_by_text(
            "Share & Export",
            exact=True
        )

        csv_button = section_locator.get_by_role(
            "button",
            name="Get table as CSV (for Excel)",
            exact=True
        )

        if csv_locator.count() == 0:
            share_button.hover()
            csv_button.dispatch_event("click")

        csv_text = csv_locator.inner_text()

        if not csv_text.strip():
            raise RuntimeError("The CSV export is empty.")
        return csv_text

    def select_table_tab(self, section_id, tab_name):
        """Select a table tab within the specified page section.

        Args:
            section_id: The HTML ID of the section containing the tabs.
            tab_name: The exact text of the tab to select.

        Raises:
            RuntimeError: If the browser has not been started.
        """
        if self.page is None:
            raise RuntimeError("Start the browser before selecting a table tab.")

        section = self.page.locator(f"#{section_id}")
        tab = section.get_by_role(
            "link",
            name=tab_name,
            exact=True
        )

        tab.dispatch_event("click")

    def extract_links(self, selector):
        """Extract link text and absolute URLs from the current page.

        Args:
            selector: A selector matching the links to extract.

        Returns:
            A list of dictionaries containing text and url.

        Raises:
            RuntimeError: If the browser has not been started.
        """
        if self.page is None:
            raise RuntimeError("Start the browser before extracting links.")

        links_locator = self.page.locator(selector)
        links_locator.first.wait_for(state="attached")

        results = []

        for link in links_locator.all():
            text = link.inner_text().strip()

            href = link.get_attribute("href")

            absolute_url = urljoin(self.page.url, href)

            results.append({
                "text": text,
                "url": absolute_url,
            })

        return results

    def extract_table(self, table_id, field_map):
        """Extract selected fields from the current page's table body.

        Args:
            table_id: The HTML ID of the table to read.
            field_map: A dictionary mapping data-stat values to output keys.

        Returns:
            A list of dictionaries containing stripped cell text.
            Empty cells are preserved as empty strings.

        Raises:
            RuntimeError: If the browser has not been started.
        """
        if self.page is None:
            raise RuntimeError("Start the browser before extracting table.")

        rows_locator = self.page.locator(f"#{table_id} tbody tr")
        rows_locator.first.wait_for(state="attached")

        results = []

        for row in rows_locator.all():

            salary = {}

            for source_field, output_field in field_map.items():

                cell = row.locator(f'[data-stat="{source_field}"]')
                value = cell.inner_text().strip()

                salary[output_field] = value

            results.append(salary)

        return results