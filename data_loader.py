import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from data_cleaner import ALLOWED_GROUPS, APPROVED_QUESTIONS, STATE_ABBREVIATIONS, clean_brfss_data


API_URL = "https://data.cdc.gov/resource/dttw-5yxu.json"
PAGE_SIZE = 50000
MAX_ROWS = 250000
MIN_YEAR = 2011
MAX_YEAR = 2025
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
REQUEST_TIMEOUT = 45


def load_cleaned_data(path: Path) -> pd.DataFrame:
    """Load the local cleaned file, or return an empty table if it is absent."""
    if not path.exists():
        return pd.DataFrame()
    return clean_brfss_data(pd.read_csv(path))


def download_brfss_data(
    indicator: str | None,
    start_year: int,
    end_year: int,
    group_category: str | None = None,
    group_value: str | None = None,
) -> pd.DataFrame:
    """Download a filtered BRFSS result using paginated Socrata requests."""
    if indicator not in APPROVED_QUESTIONS:
        raise ValueError("Refresh requires one approved health measure.")
    if not MIN_YEAR <= start_year <= MAX_YEAR or not MIN_YEAR <= end_year <= MAX_YEAR:
        raise ValueError(f"Years must be between {MIN_YEAR} and {MAX_YEAR}.")
    if start_year > end_year:
        raise ValueError("Start year cannot be later than end year.")
    if group_category and group_category not in ALLOWED_GROUPS:
        raise ValueError("Population group category is outside the approved scope.")
    if group_value:
        allowed_values = set().union(*ALLOWED_GROUPS.values())
        if group_value not in allowed_values:
            raise ValueError("Population group is outside the approved scope.")
        if group_category and group_value not in ALLOWED_GROUPS[group_category]:
            raise ValueError("Population group does not match its category.")
    state_values = ", ".join(f"'{state}'" for state in sorted(STATE_ABBREVIATIONS))
    conditions = [
        f"year between {start_year} and {end_year}",
        f"locationabbr in ({state_values})",
        "((break_out_category = 'Overall' AND break_out = 'Overall') "
        "OR (break_out_category = 'Sex' AND break_out in ('Female', 'Male')) "
        "OR (break_out_category = 'Age Group' AND break_out in ('18-24', '25-34', '35-44', '45-54', '55-64', '65+')) "
        "OR (break_out_category = 'Education Attained' AND break_out in ('College graduate', 'H.S. or G.E.D.', 'Less than H.S.', 'Some post-H.S.')) "
        "OR (break_out_category = 'Race/Ethnicity' AND break_out in ('White, non-Hispanic', 'Black, non-Hispanic', 'Hispanic')))"
    ]
    escaped_indicator = indicator.replace("'", "''")
    conditions.append(f"question = '{escaped_indicator}'")
    if group_category:
        escaped_category = group_category.replace("'", "''")
        conditions.append(f"break_out_category = '{escaped_category}'")
    if group_value:
        escaped_value = group_value.replace("'", "''")
        conditions.append(f"break_out = '{escaped_value}'")

    params = {
        "$select": (
            "year,locationabbr,locationdesc,class,topic,question,response,"
            "break_out,break_out_category,sample_size,data_value,"
            "confidence_limit_low,confidence_limit_high,data_value_unit"
        ),
        "$where": " AND ".join(conditions),
        "$order": "year,locationabbr,question",
    }

    rows = []
    offset = 0
    app_token = os.getenv("SOCRATA_APP_TOKEN")
    headers = {"User-Agent": "CS122 BRFSS State Health Explorer/1.0"}
    if app_token:
        headers["X-App-Token"] = app_token

    while True:
        page_params = params | {"$limit": PAGE_SIZE, "$offset": offset}
        response = None
        for attempt in range(3):
            try:
                response = requests.get(
                    API_URL,
                    params=page_params,
                    headers=headers,
                    timeout=REQUEST_TIMEOUT,
                )
            except requests.RequestException:
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
                continue
            if response.status_code not in RETRYABLE_STATUS_CODES:
                break
            if attempt < 2:
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = min(float(retry_after), 30) if retry_after else 2 ** attempt
                except ValueError:
                    delay = 2 ** attempt
                time.sleep(delay)

        if response is None:
            raise RuntimeError("The CDC request did not return a response.")
        response.raise_for_status()
        page = response.json()

        if not page:
            break

        if len(rows) + len(page) > MAX_ROWS:
            raise ValueError(
                f"The filtered request exceeded the safety limit of {MAX_ROWS:,} rows. "
                "Choose one measure, fewer years, or one population group."
            )

        rows.extend(page)
        offset += len(page)

        if len(page) < PAGE_SIZE:
            break

    return pd.DataFrame(rows)


def refresh_brfss_data(
    raw_dir: Path,
    cleaned_file: Path,
    indicator: str | None,
    start_year: int,
    end_year: int,
    group_category: str | None = None,
    group_value: str | None = None,
) -> pd.DataFrame:
    """Download, validate, and atomically merge rows into the shared cleaned file."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    cleaned_file.parent.mkdir(parents=True, exist_ok=True)

    data = download_brfss_data(
        indicator,
        start_year,
        end_year,
        group_category=group_category,
        group_value=group_value,
    )
    cleaned = clean_brfss_data(data)

    if cleaned.empty:
        raise ValueError("The request returned no usable rows.")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    raw_file = raw_dir / f"brfss_raw_{timestamp}.csv"
    raw_temp = raw_file.with_suffix(".tmp.csv")
    cleaned_temp = cleaned_file.with_suffix(".tmp.csv")

    existing = load_cleaned_data(cleaned_file)
    if existing.empty:
        merged = cleaned
    else:
        existing = clean_brfss_data(existing)
        replace_mask = existing["question"].eq(indicator) & existing["year"].between(start_year, end_year)
        if group_category:
            replace_mask &= existing["break_out_category"].eq(group_category)
        if group_value:
            replace_mask &= existing["break_out"].eq(group_value)
        merged = pd.concat([existing.loc[~replace_mask], cleaned], ignore_index=True)
        merged = merged.drop_duplicates().sort_values(["question", "locationdesc", "year"]).reset_index(drop=True)

    data.to_csv(raw_temp, index=False)
    merged.to_csv(cleaned_temp, index=False)
    raw_temp.replace(raw_file)
    cleaned_temp.replace(cleaned_file)

    metadata_dir = raw_dir.parent / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "refreshed_at_utc": datetime.now(timezone.utc).isoformat(),
        "api_url": API_URL,
        "indicator": indicator,
        "start_year": start_year,
        "end_year": end_year,
        "group_category": group_category,
        "group_value": group_value,
        "rows_downloaded": int(len(data)),
        "rows_saved": int(len(merged)),
        "rows_refreshed": int(len(cleaned)),
        "page_size": PAGE_SIZE,
    }
    (metadata_dir / "last_refresh.json").write_text(json.dumps(manifest, indent=2))
    return cleaned
