# stores files or locations as an object
from pathlib import Path

# re checks that a requested download name holds only safe characters
import re

# time gives a changing number used to make the browser load the newest plot image
import time

# flask runs the website
from flask import Flask, abort, flash, redirect, render_template, request, send_file, session, url_for

# pandas handles data
import pandas as pd

# import functions and values created in other files
from data_cleaner import MAX_YEAR, MIN_YEAR, MEASURE_NOTES, MEASURE_QUESTIONS, clean_brfss_data
from data_loader import load_cleaned_data, refresh_brfss_data # reads saved CSV file, downloads from CDC

# trend over time filters, tables and plots for the Analysis page
import analysis

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

# Analysis page settings
# the current plot is saved here, inside the static folder Flask already serves to the browser
PLOT_FILE = BASE_DIR / "static" / "plots" / "trend.png"
# the numbers behind the current plot, offered as a CSV download
TABLE_FILE = BASE_DIR / "static" / "plots" / "trend.csv"
# session key holding the Analysis form's last choices, so the choices survive leaving the page
ANALYSIS_SESSION_KEY = "analysis_choices"
# every field of the Analysis form, in the order the form shows them
ANALYSIS_FIELDS = [
    "measure", "state", "compare_responses", "group_category", "group", "answer",
    "start_year", "end_year", "show_intervals",
]
# cached copy of the cleaned data for the Analysis page, reread only when the file changes on disk
analysis_cache = {"modified": None, "data": pd.DataFrame(), "answers": {}}


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

    Collects the filtered table, the options for every dropdown, the
    choices currently made in the form, and the note for the chosen measure,
    so the page redraws with the same choices still selected

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
    # short label of the measure chosen in the preview filter, found by matching the question text
    # next() returns the first match, or "" when no measure is chosen
    preview_label = next(
        (label for label, question in MEASURE_QUESTIONS.items() if question == preview_indicator), ""
    )
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
        "measure_note": MEASURE_NOTES.get(preview_label, ""),
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


def load_analysis_data():
    """
    Return the cleaned data and its answers by measure, rereading the file only when it changed

    Reading and cleaning the full file takes several seconds, so the result is
    kept in analysis_cache. The file's last-modified time is checked on every
    call, and a refresh on the Data page changes that time, so new downloads
    are picked up automatically

    Returns
    -------
    tuple
        The cleaned pandas.DataFrame (empty when no file exists yet) and the
        dict from analysis.answers_by_measure
    """
    if not CLEANED_FILE.exists():
        return pd.DataFrame(), {}
    # st_mtime is the time the file was last changed, in seconds
    modified = CLEANED_FILE.stat().st_mtime
    if analysis_cache["modified"] != modified:
        data = load_cleaned_data(CLEANED_FILE)
        analysis_cache["data"] = data
        analysis_cache["answers"] = analysis.answers_by_measure(data)
        analysis_cache["modified"] = modified
    return analysis_cache["data"], analysis_cache["answers"]


def read_analysis_choices(starting, measures, states):
    """
    Work out the Analysis form choices for this visit

    A submitted form provides the choices. A visit without a submitted form,
    such as clicking the navigation link, restores the choices remembered in
    the session. The Reset choices link clears the session and returns the
    starting choices

    Parameters
    ----------
    starting : dict
        Starting value for every field in ANALYSIS_FIELDS
    measures : list of str
        Short labels of the measures present in the data
    states : list of str
        State names present in the data

    Returns
    -------
    dict
        One string value per field in ANALYSIS_FIELDS
    """
    if request.args.get("reset"):
        session.pop(ANALYSIS_SESSION_KEY, None)
        return dict(starting)

    if request.args.get("submitted"):
        choices = {field: request.args.get(field, "").strip() for field in ANALYSIS_FIELDS}
        # an unchecked checkbox sends nothing, so a missing checkbox on a submitted form means off
        for checkbox in ["compare_responses", "show_intervals"]:
            choices[checkbox] = "on" if request.args.get(checkbox) else ""
    else:
        choices = dict(starting)
        choices.update(session.get(ANALYSIS_SESSION_KEY, {}))

    # a blank field, or a measure or state no longer in the data, falls back to the starting value
    for field in ["measure", "state", "group_category", "group", "start_year", "end_year"]:
        if not choices.get(field):
            choices[field] = starting[field]
    if choices["measure"] not in measures:
        choices["measure"] = starting["measure"]
    if choices["state"] not in states:
        choices["state"] = starting["state"]
    return choices


@app.route("/analysis")
def analysis_dashboard():
    """
    Display the Partner 2 trend over time analysis page

    Reads the form choices, picks a valid answer for the chosen measure, builds
    the trend table for the chosen view, saves the plot as static/plots/trend.png
    and shows the plot, footnotes and numbers table. Problems such as no data
    for the choices or a start year after the end year are shown as a message
    instead of a plot

    Returns
    -------
    str
        Rendered HTML for analysis.html
    """
    data, answer_lookup = load_analysis_data()
    if data.empty:
        return render_template("analysis.html", has_data=False)

    # only measures and states present in the downloaded data are offered
    measures = [label for label in MEASURE_QUESTIONS if label in answer_lookup]
    states = sorted(data["locationdesc"].dropna().unique())
    group_categories = [category for category in GROUP_CATEGORIES if category]
    groups = [group for category_groups in analysis.GROUP_ORDER.values() for group in category_groups]

    # starting choices: top of each dropdown, groups compared by Sex, every year
    starting = {
        "measure": measures[0],
        "state": states[0],
        "compare_responses": "",
        "group_category": "Sex",
        "group": groups[0],
        "answer": "",
        "start_year": str(MIN_YEAR),
        "end_year": str(MAX_YEAR),
        "show_intervals": "on",
    }
    choices = read_analysis_choices(starting, measures, states)
    choices["answer"] = analysis.pick_answer(choices["measure"], choices["answer"], answer_lookup)
    # the Compare survey response options checkbox only appears for measures with more than two survey responses
    # Yes and No always add to 100, so a two-response measure always compares groups
    if len(answer_lookup.get(choices["measure"], [])) <= 2:
        choices["compare_responses"] = ""
    view = "answers" if choices["compare_responses"] == "on" else "groups"
    # remember the choices for the next visit
    session[ANALYSIS_SESSION_KEY] = choices

    show_intervals = choices["show_intervals"] == "on"
    context = {
        "has_data": True,
        "choices": choices,
        "measures": measures,
        "states": states,
        "group_categories": group_categories,
        "group_category_labels": GROUP_CATEGORIES,
        "groups": groups,
        "answer_lookup": answer_lookup,
        "default_answers": analysis.DEFAULT_RESPONSES,
        "group_order": analysis.GROUP_ORDER,
        "group_descriptions": analysis.GROUP_DESCRIPTIONS,
        "min_year": MIN_YEAR,
        "max_year": MAX_YEAR,
        "measure_note": MEASURE_NOTES.get(choices["measure"], ""),
        "show_intervals": show_intervals,
        "error": "",
        "plot_url": "",
        "file_stem": "",
        "plot_title": "",
        "table": None,
        "missing": {},
        "no_data_years": [],
    }

    try:
        try:
            start_year = int(choices["start_year"])
            end_year = int(choices["end_year"])
        except ValueError:
            raise ValueError(f"Years must be whole numbers from {MIN_YEAR} to {MAX_YEAR}.")
        if not (MIN_YEAR <= start_year <= MAX_YEAR and MIN_YEAR <= end_year <= MAX_YEAR):
            raise ValueError(f"Years must be from {MIN_YEAR} to {MAX_YEAR}.")
        if start_year > end_year:
            raise ValueError("Start year cannot be later than end year.")

        if view == "answers":
            table = analysis.filter_answer_view(
                data, choices["measure"], choices["state"], choices["group"], start_year, end_year
            )
            legend_title = "Survey response"
        else:
            table = analysis.filter_group_view(
                data, choices["measure"], choices["answer"], choices["state"],
                choices["group_category"], start_year, end_year,
            )
            legend_title = GROUP_CATEGORIES.get(choices["group_category"], choices["group_category"])

        title, subtitle = analysis.make_title(
            view, choices["measure"], choices["state"], start_year, end_year,
            answer=choices["answer"], group_category=choices["group_category"], group=choices["group"],
        )
        analysis.plot_trend(
            table, title, PLOT_FILE, show_intervals=show_intervals,
            legend_title=legend_title, subtitle=subtitle,
        )
        # the changing v= number makes the browser fetch the new image instead of showing a saved older copy
        context["plot_url"] = url_for("static", filename="plots/trend.png", v=int(time.time() * 1000))
        context["plot_title"] = title
        # same numbers as the page table, in separate columns, saved for the Download table button
        # index=False leaves out pandas row numbers, empty cells mark years with no estimate
        analysis.download_csv_table(table).to_csv(TABLE_FILE, index=False)
        # descriptive name the browser gives both downloaded files
        context["file_stem"] = analysis.make_file_stem(
            view, choices["measure"], choices["state"], start_year, end_year,
            answer=choices["answer"], group_category=choices["group_category"], group=choices["group"],
        )
        context["table"] = analysis.trend_table(table, show_intervals=show_intervals)
        # years with no data for any line are reported once, the rest per line
        no_data_years = analysis.years_with_no_data(table)
        context["no_data_years"] = no_data_years
        context["missing"] = analysis.find_missing_years(table, skip_years=no_data_years)
    except ValueError as exc:
        context["error"] = str(exc)

    return render_template("analysis.html", **context)


@app.route("/analysis/download/<kind>")
def download_analysis_file(kind):
    """
    Send the current plot or table as a file download with a descriptive name

    Flask's static folder names every file by the name on disk (trend.png), and
    browsers follow that name over the link's own, so downloads go through this
    route instead

    Parameters
    ----------
    kind : str
        "png" for the plot or "csv" for the table, taken from the address

    Returns
    -------
    flask.Response
        The file sent as an attachment, named from the name value in the address
    """
    files = {"png": PLOT_FILE, "csv": TABLE_FILE}
    if kind not in files or not files[kind].exists():
        abort(404)
    # keep only letters, digits, dashes and underscores, so the name cannot point anywhere else
    name = re.sub(r"[^a-z0-9_-]", "", request.args.get("name", "").lower()) or "trend"
    # as_attachment tells the browser to save the file, max_age=0 stops the browser reusing an older copy
    return send_file(files[kind], as_attachment=True, download_name=f"{name}.{kind}", max_age=0)


if __name__ == "__main__":
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    CLEANED_DIR.mkdir(parents=True, exist_ok=True)
    app.run(debug=True)