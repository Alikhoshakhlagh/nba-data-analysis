import csv
from io import StringIO
import pandas as pd
from pathlib import Path

class CsvParser:
    """Parse CSV exports, normalize table data, and save CSV files."""

    def parse_export(self, csv_text, required_columns, drop_columns=None):
        """Parse an exported CSV table into a string-valued DataFrame.

        Args:
            csv_text: Raw CSV text exported from the website.
            required_columns: Column names required to identify the header.
            drop_columns: Optional original column names to remove.

        Returns:
            A DataFrame containing the detected table with string-valued
            columns and the specified columns removed.

        Raises:
            csv.Error: If the CSV reader encounters a parsing error.
            ValueError: If header detection or DataFrame construction fails.
            KeyError: If a column requested for removal does not exist.
        """
        text_file = StringIO(csv_text)
        reader = csv.reader(text_file)
        rows = list(reader)

        header_index = self.find_header(rows, required_columns)

        table_rows = rows[header_index:]

        headers_row = table_rows[0]
        data_rows = table_rows[1:]

        df = pd.DataFrame(data=data_rows, columns=headers_row, dtype="string")

        if drop_columns is not None:
            df = df.drop(columns=drop_columns)

        return df

    def find_header(self, rows, required_columns):
        """Return the index of the row containing all required columns.

        Args:
            rows: Parsed CSV rows.
            required_columns: Column names required to identify the header.

        Returns:
            The zero-based index of the header row.

        Raises:
            ValueError: If no matching header row is found.
        """
        required = set(required_columns)

        for index, row in enumerate(rows):
            if required.issubset(row):
                return index

        raise ValueError("The CSV header row was not found.")

    def normalize_headers(self,df, column_map):
        """Return a DataFrame with columns renamed using a mapping.

        Args:
            df: The DataFrame whose columns should be renamed.
            column_map: A dictionary mapping original column names
                to their standardized names.

        Returns:
            A new DataFrame with renamed columns and unchanged values.
        """
        normalized_df = df.rename(columns=column_map)
        return normalized_df

    def normalize_dates(self, df, date_formats):
        """Convert specified date columns without modifying the input.

        Args:
            df: The DataFrame containing date columns.
            date_formats: A dictionary mapping column names to their
                input date formats.

        Returns:
            A new DataFrame with the specified columns converted
            to datetime dtype.

        Raises:
            KeyError: If a specified column does not exist.
            ValueError: If a date cannot be parsed using its input format.
        """
        cleaned_df = df.copy()

        for column_name, date_format in date_formats.items():
            cleaned_df[column_name] = pd.to_datetime(
                cleaned_df[column_name],
                format=date_format,
                errors="raise",
            )

        return cleaned_df

    def normalize_currency(self, df, columns):
        """Convert dollar amounts to nullable integer columns.

        Args:
            df: The DataFrame containing currency columns.
            columns: Names of the currency columns to convert.

        Returns:
            A new DataFrame with currency columns converted to Int64.
            Empty amounts are preserved as missing values.

        Raises:
            KeyError: If a specified column does not exist.
            ValueError: If a non-empty amount cannot be converted.
        """
        clean_df = df.copy()

        for column in columns:
            amounts = (
                clean_df[column]
                .str.replace("$", "", regex=False)
                .str.replace(",", "", regex=False)
                .str.strip()
                .replace("", pd.NA)
            )

            clean_df[column] = pd.to_numeric(
                amounts,
                errors="raise",
            ).astype("Int64")

        return clean_df

    def save_csv(self, df, file_path):
        """Save a DataFrame as CSV, creating parent directories if needed.

        Args:
            df: The DataFrame to save.
            file_path: The destination CSV file path.

        Returns:
            A pathlib.Path pointing to the saved CSV file.

        Raises:
            OSError: If the destination directory or file cannot be written.
        """
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(
            path,
            index=False,
            encoding="utf-8-sig",
            date_format="%Y-%m-%d",
        )
        return path