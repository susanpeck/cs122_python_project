"""
Trend over time analysis for the BRFSS State Health Explorer

Filters the cleaned BRFSS data for one health measure and one state, builds a
table of estimates by year, and draws a trend plot saved as a PNG file. No Flask
code lives here, so every function can be tested in a notebook first

Two views share the same table shape (year, line, estimate, lower, upper):

- Compare groups: one answer, one line per group in a group category,
  for example Yes for Female and Male
- All answers: one group, one line per answer of the measure,
  for example Excellent through Poor for Female
"""

import re
import textwrap
from pathlib import Path

import matplotlib

# "Agg" draws into image files without opening a window, which a web server needs
# must run before pyplot is imported
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from data_cleaner import MEASURE_QUESTIONS


# Answer preselected in the Answer dropdown for each measure
# General health rating and Smoking status are left out on purpose, so the dropdown starts on the first answer
DEFAULT_RESPONSES = {
    "Any alcohol (past 30 days)": "Yes",
    "Any exercise (past month)": "Yes",
    "Arthritis": "Yes",
    "Asthma (current)": "Yes",
    "Asthma (ever)": "Yes",
    "Binge drinking": "Yes",
    "COPD": "Yes",
    "Coronary heart disease": "Yes",
    "Current smoking": "Yes",
    "Depression": "Yes",
    "Diabetes": "Yes",
    "Fair or poor health": "Fair or Poor Health",
    "Flu shot (ages 65+)": "Yes",
    "Health insurance (ages 18-64)": "Yes",
    "Heart attack": "Yes",
    "Kidney disease": "Yes",
    "Other cancer": "Yes",
    "Pneumonia vaccine (ages 65+)": "Yes",
    "Skin cancer": "Yes",
    "Stroke": "Yes",
    "Weight category (BMI)": "Obese (BMI 30.0 - 99.8)",
}

# Natural order for answers, used for dropdowns, legends and table columns
# Answers not listed here come after the listed ones, in alphabetical order
ANSWER_ORDER = [
    "Yes",
    "No",
    "Yes, pregnancy-related",
    "No, pre-diabetes or borderline diabetes",
    "Excellent",
    "Very good",
    "Good",
    "Fair",
    "Poor",
    "Fair or Poor Health",
    "Good or Better Health",
    "Never smoked",
    "Former smoker",
    "Smoke some days",
    "Smoke everyday",
    "Underweight (BMI 12.0-18.4)",
    "Normal Weight (BMI 18.5-24.9)",
    "Overweight (BMI 25.0-29.9)",
    "Obese (BMI 30.0 - 99.8)",
]

# Natural order for groups within each group category, Female listed first for the women's health focus
GROUP_ORDER = {
    "Overall": ["Overall"],
    "Sex": ["Female", "Male"],
    "Age Group": ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"],
    "Education Attained": ["Less than H.S.", "H.S. or G.E.D.", "Some post-H.S.", "College graduate"],
    "Race/Ethnicity": ["White, non-Hispanic", "Black, non-Hispanic", "Hispanic"],
}

# Line colors in fixed order: line 1 always gets the first color, line 2 the second, and so on
# Checked for colorblind separation, the most lines any view draws is 6 (the age groups)
LINE_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]

# A different marker shape per line, so lines can be told apart without color (print, colorblind readers)
LINE_MARKERS = ["o", "s", "^", "D", "v", "P"]

# Columns of the standard table returned by both filter functions
TREND_COLUMNS = ["year", "line", "estimate", "lower", "upper"]

# Reverse lookup from full CDC question text to short label
QUESTION_TO_LABEL = {question: label for label, question in MEASURE_QUESTIONS.items()}

def _ever_never(condition):
    """
    Build the Yes and No phrases for a measure asking whether a person was ever diagnosed

    Parameters
    ----------
    condition : str
        Condition as it reads after "Diagnosed with", for example "Depression"

    Returns
    -------
    dict
        Phrases for the responses Yes and No
    """
    return {"Yes": f"Ever Diagnosed with {condition}", "No": f"Never Diagnosed with {condition}"}


# Words that finish the title "Percent of Adults ___ in <state>", for every measure and survey response
# "Ever Diagnosed with" is used where the survey asks whether a doctor ever told the person
RESPONSE_PHRASES = {
    "Any alcohol (past 30 days)": {
        "Yes": "Who Drank Alcohol in the Past 30 Days",
        "No": "Who Did Not Drink Alcohol in the Past 30 Days",
    },
    "Any exercise (past month)": {
        "Yes": "Who Exercised in the Past Month",
        "No": "Who Did Not Exercise in the Past Month",
    },
    "Arthritis": _ever_never("Arthritis"),
    "Asthma (current)": {"Yes": "with Current Asthma", "No": "without Current Asthma"},
    "Asthma (ever)": _ever_never("Asthma"),
    "Binge drinking": {"Yes": "Who Binge Drink", "No": "Who Do Not Binge Drink"},
    "COPD": _ever_never("COPD"),
    "Coronary heart disease": _ever_never("Angina or Coronary Heart Disease"),
    "Current smoking": {"Yes": "Who Currently Smoke", "No": "Who Do Not Currently Smoke"},
    "Depression": _ever_never("Depression"),
    "Diabetes": {
        "Yes": "Ever Diagnosed with Diabetes",
        "Yes, pregnancy-related": "Told They Had Diabetes Only During Pregnancy",
        "No, pre-diabetes or borderline diabetes": "Ever Diagnosed with Prediabetes or Borderline Diabetes",
        "No": "Never Diagnosed with Diabetes or Prediabetes",
    },
    "Fair or poor health": {
        "Fair or Poor Health": "in Fair or Poor Health",
        "Good or Better Health": "in Good or Better Health",
    },
    "Flu shot (ages 65+)": {
        "Yes": "Aged 65+ with a Flu Shot in the Past Year",
        "No": "Aged 65+ without a Flu Shot in the Past Year",
    },
    "General health rating": {
        "Excellent": "Who Rate Their Health as Excellent",
        "Very good": "Who Rate Their Health as Very Good",
        "Good": "Who Rate Their Health as Good",
        "Fair": "Who Rate Their Health as Fair",
        "Poor": "Who Rate Their Health as Poor",
    },
    "Health insurance (ages 18-64)": {
        "Yes": "Aged 18-64 with Health Insurance",
        "No": "Aged 18-64 without Health Insurance",
    },
    "Heart attack": _ever_never("a Heart Attack"),
    "Kidney disease": _ever_never("Kidney Disease"),
    "Other cancer": _ever_never("Other Cancer"),
    "Pneumonia vaccine (ages 65+)": {
        "Yes": "Aged 65+ Ever Vaccinated for Pneumonia",
        "No": "Aged 65+ Never Vaccinated for Pneumonia",
    },
    "Skin cancer": _ever_never("Skin Cancer"),
    "Smoking status": {
        "Never smoked": "Who Never Smoked",
        "Former smoker": "Who Formerly Smoked",
        "Smoke everyday": "Who Smoke Every Day",
        "Smoke some days": "Who Smoke Some Days",
    },
    "Stroke": _ever_never("a Stroke"),
    "Weight category (BMI)": {
        "Underweight (BMI 12.0-18.4)": "with Underweight (BMI Under 18.5)",
        "Normal Weight (BMI 18.5-24.9)": "with Normal Weight (BMI 18.5 to 24.9)",
        "Overweight (BMI 25.0-29.9)": "with Overweight (BMI 25.0 to 29.9)",
        "Obese (BMI 30.0 - 99.8)": "with Obesity (BMI 30 or Higher)",
    },
}

# Title-case names for the measures with more than two survey responses, used in the response comparison title
TITLE_NAMES = {
    "Diabetes": "Diabetes",
    "General health rating": "General Health Rating",
    "Smoking status": "Smoking Status",
    "Weight category (BMI)": "Weight Category (BMI)",
}

# How each group category is described in the subtitle of the Compare groups view
COMPARISON_TEXT = {
    "Overall": "All adults",
    "Sex": "Female vs Male",
    "Age Group": "By age group",
    "Education Attained": "By education",
    "Race/Ethnicity": "By race/ethnicity",
}

# How each single group is described in the title of the All answers view
GROUP_DESCRIPTIONS = {
    "Overall": "Adults",
    "Female": "Female Adults",
    "Male": "Male Adults",
    "18-24": "Adults Aged 18-24",
    "25-34": "Adults Aged 25-34",
    "35-44": "Adults Aged 35-44",
    "45-54": "Adults Aged 45-54",
    "55-64": "Adults Aged 55-64",
    "65+": "Adults Aged 65+",
    "Less than H.S.": "Adults with Less than High School",
    "H.S. or G.E.D.": "Adults with High School or G.E.D.",
    "Some post-H.S.": "Adults with Some College",
    "College graduate": "College Graduates",
    "White, non-Hispanic": "White, non-Hispanic Adults",
    "Black, non-Hispanic": "Black, non-Hispanic Adults",
    "Hispanic": "Hispanic Adults",
}

# Note CDC adds to some question texts, removed from subtitles so subtitles stay readable
CDC_CALCULATED_NOTE = " (variable calculated from one or more BRFSS questions)"

# Footnote drawn inside every plot image, so the source travels with the plot into slides or the README
PLOT_FOOTNOTE = (
    "Percents are weighted to each state's adult population and are not age-adjusted.\n"
    "Source: CDC Behavioral Risk Factor Surveillance System (BRFSS), data.cdc.gov"
)


def order_values(values, preferred_order):
    """
    Sort values so that any listed in preferred_order come first, in that order

    Parameters
    ----------
    values : iterable of str
        Values to sort, such as the answers of one measure
    preferred_order : list of str
        Values in the order they should appear

    Returns
    -------
    list of str
        Values from preferred_order that are present, followed by the rest in
        alphabetical order
    """
    values = set(values)
    listed = [value for value in preferred_order if value in values]
    # set difference keeps the values not in preferred_order, sorted() puts them in alphabetical order
    unlisted = sorted(values - set(preferred_order))
    return listed + unlisted


def answers_by_measure(data):
    """
    List the answers available for each health measure in the data

    Fills the Answer dropdown, and the page's JavaScript uses the result to
    refill that dropdown when a different measure is chosen

    Parameters
    ----------
    data : pandas.DataFrame
        Cleaned BRFSS data with question and response columns

    Returns
    -------
    dict
        Short label mapped to a list of answers in ANSWER_ORDER, only for
        measures present in the data
    """
    lookup = {}
    if data.empty:
        return lookup
    # groupby splits the rows by question text, then each group's distinct non-empty answers are collected
    for question, responses in data.groupby("question")["response"]:
        label = QUESTION_TO_LABEL.get(question)
        if label is None:
            continue
        answers = [answer for answer in responses.dropna().unique() if answer != ""]
        lookup[label] = order_values(answers, ANSWER_ORDER)
    return lookup


def pick_answer(label, requested, answer_lookup):
    """
    Choose a valid answer for a measure

    Protects against an answer left over from a previously chosen measure, for
    example "Excellent" arriving together with Depression

    Parameters
    ----------
    label : str
        Short label of the chosen measure
    requested : str
        Answer sent by the form, may be empty
    answer_lookup : dict
        Result of answers_by_measure

    Returns
    -------
    str
        The requested answer when it belongs to the measure, otherwise the
        default from DEFAULT_RESPONSES, otherwise the first available answer.
        An empty string when the measure has no data
    """
    answers = answer_lookup.get(label, [])
    if requested in answers:
        return requested
    default = DEFAULT_RESPONSES.get(label, "")
    if default in answers:
        return default
    return answers[0] if answers else ""


def question_for(label):
    """
    Look up the full CDC question text for a short label

    Parameters
    ----------
    label : str
        Short label, one of the keys of MEASURE_QUESTIONS

    Returns
    -------
    str
        Full CDC question text

    Raises
    ------
    ValueError
        If the label is not one of the 23 health measures
    """
    if label not in MEASURE_QUESTIONS:
        raise ValueError(f"Unknown health measure: {label!r}")
    return MEASURE_QUESTIONS[label]


def complete_years(table, lines, start_year, end_year):
    """
    Add an empty row for every year a line has no row at all

    CDC leaves out some rows entirely (for example CA, MS and NV have no 2025
    data). An empty row makes the plot leave a gap there and lets
    find_missing_years report the year

    Parameters
    ----------
    table : pandas.DataFrame
        Rows with the columns in TREND_COLUMNS
    lines : list of str
        Every line that should appear, in display order
    start_year, end_year : int
        First and last year of the range, both included

    Returns
    -------
    pandas.DataFrame
        One row per line and year, with NaN estimates where data is absent,
        sorted by line order and then year
    """
    # every line paired with every year, as a two-level index
    full_index = pd.MultiIndex.from_product(
        [lines, range(start_year, end_year + 1)], names=["line", "year"]
    )
    # reindex keeps existing rows and inserts NaN rows for any line and year pair not found
    completed = table.set_index(["line", "year"]).reindex(full_index).reset_index()
    return completed[TREND_COLUMNS]


def _to_trend_table(rows, line_column):
    """
    Rename filtered rows into the standard trend table columns

    Parameters
    ----------
    rows : pandas.DataFrame
        Filtered cleaned rows
    line_column : str
        Column that names each line, "break_out" or "response"

    Returns
    -------
    pandas.DataFrame
        Columns year, line, estimate, lower and upper
    """
    table = rows.rename(
        columns={
            line_column: "line",
            "data_value": "estimate",
            "confidence_limit_low": "lower",
            "confidence_limit_high": "upper",
        }
    )[TREND_COLUMNS].copy()
    table["year"] = table["year"].astype(int)
    return table


def filter_group_view(data, label, answer, state, group_category, start_year, end_year):
    """
    Build the Compare groups table: one answer, one line per group

    Parameters
    ----------
    data : pandas.DataFrame
        Cleaned BRFSS data
    label : str
        Short label of the health measure
    answer : str
        Answer to plot, for example "Yes"
    state : str
        State name as in the locationdesc column, for example "Ohio"
    group_category : str
        Group category, for example "Sex" or "Age Group"
    start_year, end_year : int
        First and last year, both included

    Returns
    -------
    pandas.DataFrame
        Columns year, line, estimate, lower and upper, one line per group with
        data, in GROUP_ORDER, with an empty row for each year a group has no data
    """
    question = question_for(label)
    # each comparison gives True or False per row, & keeps rows where every condition is True
    rows = data[
        (data["question"] == question)
        & (data["response"] == answer)
        & (data["locationdesc"] == state)
        & (data["break_out_category"] == group_category)
        & (data["year"].between(start_year, end_year))
    ]
    # only groups with rows for the chosen measure become lines, for example Flu shot (ages 65+) has only the 65+ age group
    lines = order_values(rows["break_out"].unique(), GROUP_ORDER.get(group_category, []))
    return complete_years(_to_trend_table(rows, "break_out"), lines, start_year, end_year)


def filter_answer_view(data, label, state, group, start_year, end_year):
    """
    Build the All answers table: one group, one line per answer

    Parameters
    ----------
    data : pandas.DataFrame
        Cleaned BRFSS data
    label : str
        Short label of the health measure
    state : str
        State name as in the locationdesc column, for example "Ohio"
    group : str
        One group, for example "Female" or "Overall". Group names are unique
        across categories, so the category is not needed
    start_year, end_year : int
        First and last year, both included

    Returns
    -------
    pandas.DataFrame
        Columns year, line, estimate, lower and upper, one line per answer in
        ANSWER_ORDER, with an empty row for each year an answer has no data
    """
    question = question_for(label)
    rows = data[
        (data["question"] == question)
        & (data["locationdesc"] == state)
        & (data["break_out"] == group)
        & (data["year"].between(start_year, end_year))
    ]
    # skip blank answers so a blank never becomes a line
    rows = rows[rows["response"].fillna("") != ""]
    lines = order_values(rows["response"].unique(), ANSWER_ORDER)
    return complete_years(_to_trend_table(rows, "response"), lines, start_year, end_year)


def years_with_no_data(table):
    """
    List the years where every line is missing

    These are usually years with no data for the state at all, for example
    California in 2025, as opposed to a single group whose estimate CDC withheld

    Parameters
    ----------
    table : pandas.DataFrame
        Result of filter_group_view or filter_answer_view

    Returns
    -------
    list of int
        Years in which no line has an estimate, in order
    """
    # all() per year is True only when every line's estimate is missing in that year
    all_missing = table["estimate"].isna().groupby(table["year"]).all()
    return [int(year) for year in all_missing.index[all_missing]]


def find_missing_years(table, skip_years=()):
    """
    List the years with no estimate for each line

    Supplies the "Data not available" notes shown under the plot

    Parameters
    ----------
    table : pandas.DataFrame
        Result of filter_group_view or filter_answer_view
    skip_years : iterable of int, default ()
        Years to leave out, usually the result of years_with_no_data so those
        years are reported once instead of once per line

    Returns
    -------
    dict
        Line name mapped to a list of years with no estimate, only for lines
        missing at least one year, in display order
    """
    missing = {}
    # sort=False keeps the lines in display order instead of alphabetical order
    for line, rows in table.groupby("line", sort=False):
        years = [int(year) for year in rows.loc[rows["estimate"].isna(), "year"] if year not in skip_years]
        if years:
            missing[line] = years
    return missing


def trend_table(table, show_intervals=False):
    """
    Reshape the trend table to one row per year and one column per line

    Parameters
    ----------
    table : pandas.DataFrame
        Result of filter_group_view or filter_answer_view
    show_intervals : bool, default False
        When True, each cell reads like "22.0 (20.2 to 23.7)" instead of a
        number alone

    Returns
    -------
    pandas.DataFrame
        Index named Year, columns in display order, NaN where no estimate
        exists so the page can show "Data not available"
    """
    lines = list(table["line"].unique())
    values = table.copy()
    if show_intervals:
        # format each row as text, rows with no estimate stay NaN
        def format_cell(row):
            if pd.isna(row["estimate"]):
                return float("nan")
            if pd.isna(row["lower"]) or pd.isna(row["upper"]):
                return f"{row['estimate']:.1f}"
            return f"{row['estimate']:.1f} ({row['lower']:.1f} to {row['upper']:.1f})"

        # apply with axis=1 runs format_cell once per row
        values["cell"] = values.apply(format_cell, axis=1)
    else:
        values["cell"] = values["estimate"].round(1)
    # pivot turns the line values into columns, reindex restores display order since pivot sorts alphabetically
    wide = values.pivot(index="year", columns="line", values="cell").reindex(columns=lines)
    wide.index.name = "Year"
    wide.columns.name = None
    return wide


def download_csv_table(table):
    """
    Reshape the trend table for the CSV download, with numbers in separate columns

    Unlike trend_table, every value is a plain number so the file opens cleanly
    in Excel, R or pandas. Each line gets three columns: percent, lower 95%
    confidence limit and upper 95% confidence limit

    Parameters
    ----------
    table : pandas.DataFrame
        Result of filter_group_view or filter_answer_view

    Returns
    -------
    pandas.DataFrame
        One row per year, a Year column first, empty cells where no estimate exists
    """
    lines = list(table["line"].unique())
    pieces = {}
    for line in lines:
        # set_index("year") lines up each line's values by year before the columns are joined
        rows = table[table["line"] == line].set_index("year")
        pieces[f"{line}: Percent (%)"] = rows["estimate"]
        pieces[f"{line}: 95% CI lower (%)"] = rows["lower"]
        pieces[f"{line}: 95% CI upper (%)"] = rows["upper"]
    wide = pd.DataFrame(pieces)
    wide.index.name = "Year"
    return wide.reset_index()


def make_file_stem(view, label, state, start_year, end_year, answer="", group_category="", group=""):
    """
    Build a descriptive file name, without extension, for downloaded plots and tables

    For example "depression-yes_ohio_sex_2011-2025" or
    "general-health-rating_california_female-by-response_2011-2025"

    Parameters
    ----------
    view : str
        "groups" or "answers", as in make_title
    label : str
        Short label of the health measure
    state : str
        State name
    start_year, end_year : int
        First and last year shown
    answer : str, default ""
        Survey response plotted in the groups view
    group_category : str, default ""
        Group category used in the groups view
    group : str, default ""
        Single group used in the response comparison view

    Returns
    -------
    str
        Lowercase name made of letters, digits, dashes and underscores only
    """
    def slug(text):
        # re.sub swaps every run of characters other than letters and digits for one dash
        return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")

    if view == "answers":
        parts = [slug(label), slug(state), slug(group) + "-by-response"]
    else:
        parts = [slug(label) + "-" + slug(answer), slug(state), slug(group_category)]
    parts.append(f"{start_year}-{end_year}")
    return "_".join(parts)


def make_title(view, label, state, start_year, end_year, answer="", group_category="", group=""):
    """
    Build the plot title and subtitle from the user's choices

    Compare groups view reads like "Percent of Adults Ever Diagnosed with
    Depression in Ohio", using RESPONSE_PHRASES for the chosen survey response.
    A response with no phrase falls back to
    "Percent of Adults Answering 'No': Depression in Ohio". The response
    comparison view reads like
    "Percent of Female Adults by Survey Response: General Health Rating in Ohio"

    Parameters
    ----------
    view : str
        "groups" for Compare groups or "answers" for All answers
    label : str
        Short label of the health measure
    state : str
        State name, for example "Ohio"
    start_year, end_year : int
        First and last year shown
    answer : str, default ""
        Answer plotted in the Compare groups view
    group_category : str, default ""
        Group category used in the Compare groups view, for example "Sex"
    group : str, default ""
        Single group used in the All answers view, for example "Female"

    Returns
    -------
    tuple of str
        Title and subtitle. The subtitle names the comparison, the years and
        the survey question
    """
    question = question_for(label).replace(CDC_CALCULATED_NOTE, "")
    years = f"{start_year} to {end_year}"
    # "in the District of Columbia" reads correctly where "in District of Columbia" does not
    place = f"the {state}" if state == "District of Columbia" else state

    if view == "answers":
        who = GROUP_DESCRIPTIONS.get(group, f"{group} Adults")
        title = f"Percent of {who} by Survey Response: {TITLE_NAMES.get(label, label)} in {place}"
        subtitle = f"{years}. Survey question: {question}"
    else:
        phrase = RESPONSE_PHRASES.get(label, {}).get(answer)
        if phrase:
            title = f"Percent of Adults {phrase} in {place}"
        else:
            title = f"Percent of Adults Answering '{answer}': {label} in {place}"
        comparison = COMPARISON_TEXT.get(group_category, group_category)
        subtitle = f"{comparison}, {years}. Survey question: {question}"
    return title, subtitle


def plot_trend(table, title, output_path, show_intervals=True, legend_title="", subtitle="", footnote=PLOT_FOOTNOTE):
    """
    Draw a trend over time plot and save it as a PNG file

    Draws one line per entry in the table with a marker at each year. A year
    with no estimate leaves a gap in the line instead of joining across it

    Parameters
    ----------
    table : pandas.DataFrame
        Result of filter_group_view or filter_answer_view
    title : str
        Plot title, for example "Depression, Ohio"
    output_path : str or pathlib.Path
        Where to save the PNG, parent folders are created when missing
    show_intervals : bool, default True
        Shade the 95% confidence interval around each line
    legend_title : str, default ""
        Heading above the legend, for example "Sex" or "Answer"
    subtitle : str, default ""
        Smaller gray line under the title, usually the second value returned
        by make_title
    footnote : str, default PLOT_FOOTNOTE
        Small gray text under the legend. An empty string leaves it out

    Returns
    -------
    pathlib.Path
        Path of the saved PNG

    Raises
    ------
    ValueError
        If the table has no estimates to plot, or more lines than LINE_COLORS
    """
    if table.empty or table["estimate"].isna().all():
        raise ValueError("No data available for these choices")

    lines = list(table["line"].unique())
    if len(lines) > len(LINE_COLORS):
        raise ValueError(f"Too many lines to plot ({len(lines)}), the most supported is {len(LINE_COLORS)}")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    text_color = "#3d3d3a"
    muted_color = "#73726c"
    fig, ax = plt.subplots(figsize=(9, 5.5))

    for position, line in enumerate(lines):
        rows = table[table["line"] == line].sort_values("year")
        color = LINE_COLORS[position]
        if show_intervals:
            # shaded band between the confidence limits, NaN years leave a gap
            ax.fill_between(rows["year"], rows["lower"], rows["upper"], color=color, alpha=0.15, linewidth=0)
        ax.plot(
            rows["year"],
            rows["estimate"],
            color=color,
            linewidth=2,
            marker=LINE_MARKERS[position],
            markersize=6,
            label=line,
        )
        # direct label at the last year with data, only when the plot has 4 lines or fewer
        if len(lines) <= 4:
            last = rows.dropna(subset=["estimate"]).tail(1)
            if not last.empty:
                ax.annotate(
                    line,
                    xy=(last["year"].iloc[0], last["estimate"].iloc[0]),
                    xytext=(8, 0),
                    textcoords="offset points",
                    va="center",
                    fontsize=9,
                    color=text_color,
                )

    years = sorted(table["year"].unique())
    ax.set_xticks(years)
    # rotate year labels when many years would crowd the axis
    ax.tick_params(axis="x", labelrotation=45 if len(years) > 10 else 0, colors=muted_color)
    ax.tick_params(axis="y", colors=muted_color)
    ax.set_xlabel("Year", color=text_color)
    ax.set_ylabel("Percent of adults (%)", color=text_color)

    # textwrap.fill breaks long text into lines of at most the given number of characters
    subtitle_text = textwrap.fill(subtitle, width=110) if subtitle else ""
    subtitle_lines = subtitle_text.count("\n") + 1 if subtitle_text else 0
    # pad lifts the title above the axes, leaving room for the subtitle lines underneath
    ax.set_title(
        textwrap.fill(title, width=75),
        color=text_color,
        loc="left",
        fontsize=13,
        pad=8 + 14 * subtitle_lines,
    )
    if subtitle_text:
        # transform=ax.transAxes places text by position in the axes (0 is left edge, 1 is top edge)
        ax.text(0, 1.02, subtitle_text, transform=ax.transAxes, va="bottom", fontsize=9, color=muted_color)

    # light horizontal grid and no top or right border keep attention on the data
    ax.grid(axis="y", color="#e6e5e0", linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ["top", "right"]:
        ax.spines[side].set_visible(False)
    for side in ["left", "bottom"]:
        ax.spines[side].set_color("#c3c2b7")

    # room on the right for the direct labels
    ax.margins(x=0.08)
    # legend in a row under the plot, so the direct labels at the right edge never collide with the legend
    legend = ax.legend(
        title=legend_title or None,
        frameon=False,
        loc="upper left",
        bbox_to_anchor=(0.0, -0.18),
        ncol=min(len(lines), 6),
        fontsize=9,
    )

    fig.tight_layout()
    if footnote and show_intervals:
        # the shading is explained inside the image, so a downloaded plot explains itself
        footnote = "Shaded bands show 95% confidence intervals.\n" + footnote
    if footnote:
        # draw once so the legend's final position is known, then place the footnote just below the legend
        fig.canvas.draw()
        # get_window_extent gives the legend box in pixels, transFigure.inverted converts pixels to figure fractions
        legend_box = legend.get_window_extent().transformed(fig.transFigure.inverted())
        axes_left = ax.get_position().x0
        fig.text(axes_left, legend_box.y0 - 0.02, footnote, va="top", ha="left", fontsize=8, color=muted_color)
    # bbox_inches="tight" grows the saved image to include the legend and footnote below the plot
    fig.savefig(output_path, dpi=120, facecolor="white", bbox_inches="tight", pad_inches=0.2)
    # close the figure to free memory, a web server would otherwise keep every plot ever drawn
    plt.close(fig)
    return output_path