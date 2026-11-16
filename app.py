# stores files or locations as an object
from pathlib import Path

# flask runs the website
from flask import Flask, flash, redirect, render_template, request, url_for

# pandas handles data
import pandas as pd

# import functions created in other files
from data_cleaner import MAX_YEAR, MIN_YEAR, MEASURE_QUESTIONS, clean_brfss_data
from data_loader import load_cleaned_data, refresh_brfss_data # reads saved CSV file, downloads from CDC

# file locations
BASE_DIR = Path(__file__).resolve().parent # file path that app.py is in
RAW_DIR = BASE_DIR / "data" / "raw" # each new download saved to raw folder
CLEANED_DIR = BASE_DIR / "data" / "cleaned" # combined clean data saved to cleaned folder
CLEANED_FILE = CLEANED_DIR / "brfss_cleaned.csv"

# The health measure shown by default
DEFAULT_INDICATOR = MEASURE_QUESTIONS["Current smoking"]

# Break-out categories offered in the dropdown, mapped to the label shown on the page
# The empty string means no category filter.
GROUP_CATEGORIES = {
    "": "All population groups",
    "Overall": "Overall",
    "Sex": "Sex",
    "Age Group": "Age",
    "Education Attained": "Education",
    "Race/Ethnicity": "Race/ethnicity",
}

# GROUP_VALUES are the 16 groups kept from the dataset build decisions
# Overall, Female, Male, 6 age groups, 4 education levels, White, Black, Hispanic
# The empty string means all groups
GROUP_VALUES = [
    "", "Overall", "Female", "Male", "18-24", "25-34", "35-44", "45-54", "55-64", "65+",
    "College graduate", "H.S. or G.E.D.", "Less than H.S.",
    "Some post-H.S.", "White, non-Hispanic", "Black, non-Hispanic", "Hispanic",
]

# Lowercase column names from the CDC download, mapped to readable table headings
COLUMN_LABELS = {
    "year": "Year",
    "locationabbr": "State code",
    "locationdesc": "State",
    "class": "Class",
    "topic": "Topic",
    "question": "Indicator",
    "response": "Response",
    "break_out": "Group value",
    "break_out_category": "Group category",
    "sample_size": "Sample size",
    "data_value": "Estimate",
    "confidence_limit_low": "Lower confidence limit",
    "confidence_limit_high": "Upper confidence limit",
    "data_value_unit": "Unit",
}

app = Flask(__name__)
app.config["SECRET_KEY"] = "cs122-development-key"


@app.template_filter("display_value")
def display_value(value):
    """
    Show CDC-suppressed estimates in a user-friendly way

    CDC leaves an estimate blank when too few people in a group answered.
    Registered as a Jinja template filter, so the HTML template calls it as
    {{ value | display_value }}

    Parameters
    ----------
    value : object
        One cell from the data table, usually a number or NaN

    Returns
    -------
    object
        The string "Data not available" when the value is missing, otherwise
        the original value unchanged
    """
    return "Data not available" if pd.isna(value) else value


def explorer_context(data, selected=None, option_data=None):
    """
    Build the values used by the Data Explorer template

    Collects the filtered table, the options for every dropdown, and the
    choices currently made in the form, so the page redraws with the same
    choices still selected

    Parameters
    ----------
    data : pandas.DataFrame
        Rows left after the filters from the page address are applied
    selected : dict, optional
        Form choices read from the page address, such as indicator, state,
        start_year, end_year, group_category and group_value. Missing keys
        count as no choice
    option_data : pandas.DataFrame, optional
        Full saved data used to fill the dropdown options, so options do not
        disappear as filters narrow the table. Defaults to data when not given

    Returns
    -------
    dict
        Keyword values passed to render_template for data.html
    """
    selected = selected or {}
    option_data = option_data if option_data is not None else data
    indicators = list(MEASURE_QUESTIONS.items())
    states = sorted(option_data["locationdesc"].dropna().unique()) if "locationdesc" in option_data else []
    years = sorted(option_data["year"].dropna().astype(int).unique()) if "year" in option_data else []
    group_categories = dict(GROUP_CATEGORIES)
    if "break_out_category" in option_data:
        for category in option_data["break_out_category"].dropna().unique():
            group_categories.setdefault(category, category)
    group_values = list(GROUP_VALUES)
    if "break_out" in option_data:
        group_values = sorted(set(group_values) | set(option_data["break_out"].dropna().unique()))
    refresh_indicator = selected.get("indicator") or DEFAULT_INDICATOR
    preview_indicator = selected.get("indicator", "")
    loaded_measure_count = (
        int(option_data["question"].nunique()) if "question" in option_data else 0
    )
    return {
        "data": data,
        "row_count": len(data),
        "loaded_measure_count": loaded_measure_count,
        "indicators": indicators,
        "measure_labels": MEASURE_QUESTIONS,
        "column_labels": COLUMN_LABELS,
        "group_categories": group_categories,
        "group_values": group_values,
        "states": states,
        "years": years,
        "refresh_indicator": refresh_indicator,
        "preview_indicator": preview_indicator,
        "selected_state": selected.get("state", ""),
        "selected_start_year": selected.get("start_year", ""),
        "selected_end_year": selected.get("end_year", ""),
        "preview_rows": int(selected.get("preview_rows", 25) or 25),
        "show_intervals": selected.get("show_intervals", "") == "on",
        "selected_group_category": selected.get("group_category", ""),
        "selected_group_value": selected.get("group_value", ""),
        "min_year": MIN_YEAR,
        "max_year": MAX_YEAR,
    }


@app.route("/")
def home():
    """
    Display the Partner 1 data explorer page

    Reads the saved cleaned CSV on every visit, then filters by measure,
    state, year range, group category and group, in that order. Each filter
    applies only when a choice was made in the form

    Returns
    -------
    str
        Rendered HTML for data.html
    """
    all_data = load_cleaned_data(CLEANED_FILE)
    data = all_data.copy()

    selected = request.args.to_dict()
    indicator_filter = request.args.get("indicator", "").strip()
    if not data.empty:
        if indicator_filter and "question" in data:
            data = data[data["question"] == indicator_filter]
        if selected.get("state") and "locationdesc" in data:
            data = data[data["locationdesc"] == selected["state"]]
        if selected.get("start_year") and "year" in data:
            data = data[data["year"] >= int(selected["start_year"])]
        if selected.get("end_year") and "year" in data:
            data = data[data["year"] <= int(selected["end_year"])]
        if selected.get("group_category") and "break_out_category" in data:
            data = data[data["break_out_category"] == selected["group_category"]]
        if selected.get("group_value") and "break_out" in data:
            data = data[data["break_out"] == selected["group_value"]]
    return render_template("data.html", **explorer_context(data, selected, all_data))


@app.post("/refresh-data")
def refresh_data():
    """
    Request a filtered BRFSS sample and save raw and cleaned copies

    Checks the form's year range and measure, downloads matching rows through
    the CDC API, and replaces any saved rows for the same measure and years.
    A one-time message reports success or failure, and the saved file is left
    unchanged when anything fails

    Returns
    -------
    flask.Response
        Redirect back to the home page
    """
    indicator = request.form.get("indicator", "").strip() or DEFAULT_INDICATOR
    start_year = request.form.get("start_year", str(MIN_YEAR)).strip()
    end_year = request.form.get("end_year", str(MAX_YEAR)).strip()
    group_category = request.form.get("group_category", "").strip()
    group_value = request.form.get("group_value", "").strip()

    try:
        start_year_number = int(start_year)
        end_year_number = int(end_year)
        if not MIN_YEAR <= start_year_number <= MAX_YEAR:
            raise ValueError(f"Start year must be between {MIN_YEAR} and {MAX_YEAR}.")
        if not MIN_YEAR <= end_year_number <= MAX_YEAR:
            raise ValueError(f"End year must be between {MIN_YEAR} and {MAX_YEAR}.")
        if start_year_number > end_year_number:
            raise ValueError("Start year cannot be later than end year.")

        if indicator not in MEASURE_QUESTIONS.values():
            raise ValueError("Choose one of the 23 approved health measures.")

        raw_data = refresh_brfss_data(
            raw_dir=RAW_DIR,
            cleaned_file=CLEANED_FILE,
            indicator=indicator or None,
            start_year=start_year_number,
            end_year=end_year_number,
            group_category=group_category or None,
            group_value=group_value or None,
        )
        clean_brfss_data(raw_data)  # Validation is performed before saving.
        flash(f"Refresh succeeded: {len(raw_data):,} rows downloaded and saved.", "success")
    except Exception as exc:  # Keep the existing local file if refresh fails.
        flash(
            "Refresh failed. Existing local data were preserved. "
            f"Details: {exc}",
            "error",
        )

    return redirect(url_for("home"))


@app.post("/load-data")
def load_data():
    """
    Reload the existing local file without contacting the CDC

    Only checks that the saved cleaned file exists and shows a message. The
    home page reads the saved file on every visit, so the reload happens
    after the redirect

    Returns
    -------
    flask.Response
        Redirect back to the home page
    """
    if CLEANED_FILE.exists():
        flash("Local cleaned data loaded successfully.", "success")
    else:
        flash("No local cleaned file exists yet. Use Refresh CDC data first.", "error")
    return redirect(url_for("home"))


if __name__ == "__main__":
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CLEANED_DIR.mkdir(parents=True, exist_ok=True)
    app.run(debug=True)