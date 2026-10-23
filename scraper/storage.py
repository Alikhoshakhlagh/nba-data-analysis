from pathlib import Path


def save_csv(df, file_path):
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