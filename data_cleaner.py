# pandas handles data
import pandas as pd

# Keeping only survey years 2011-2025
# earlier years used a different weighting method and are not comparable
MIN_YEAR = 2011
MAX_YEAR = 2025

# 50 states and DC
# territories and the median rows (US, UW) are not included
STATE_ABBREVIATIONS = frozenset(
    {
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
        "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
        "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
        "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
        "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
        "DC",
    }
)

# Population groups kept, each group category mapped to the set of groups allowed in that category
# Household Income and the smaller race and age groups are left out
ALLOWED_GROUPS = {
    "Overall": {"Overall"},
    "Sex": {"Female", "Male"},
    "Age Group": {"18-24", "25-34", "35-44", "45-54", "55-64", "65+"},
    "Education Attained": {
        "College graduate", "H.S. or G.E.D.", "Less than H.S.", "Some post-H.S.",
    },
    "Race/Ethnicity": {"White, non-Hispanic", "Black, non-Hispanic", "Hispanic"},
}

# Dictionary of 23 short labels paired with the full CDC question text
# The single source for the 23 measures, app.py imports MEASURE_QUESTIONS from here
# Texts must match the CDC data character for character, since rows are kept only on an exact match
MEASURE_QUESTIONS = {
    "Any alcohol (past 30 days)": "Adults who have had at least one drink of alcohol within the past 30 days",
    "Any exercise (past month)": "During the past month, did you participate in any physical activities? (variable calculated from one or more BRFSS questions)",
    "Arthritis": "Adults who have been told they have arthritis (variable calculated from one or more BRFSS questions)",
    "Asthma (current)": "Adults who have been told they currently have asthma (variable calculated from one or more BRFSS questions)",
    "Asthma (ever)": "Adults who have ever been told they have asthma (variable calculated from one or more BRFSS questions)",
    "Binge drinking": "Binge drinkers (males having five or more drinks on one occasion, females having four or more drinks on one occasion) (variable calculated from one or more BRFSS questions)",
    "COPD": "Ever told you have COPD?",
    "Coronary heart disease": "Ever told you had angina or coronary heart disease?",
    "Current smoking": "Adults who are current smokers (variable calculated from one or more BRFSS questions)",
    "Depression": "Ever told you that you have a form of depression?",
    "Diabetes": "Have you ever been told by a doctor that you have diabetes?",
    "Fair or poor health": "Health Status (variable calculated from one or more BRFSS questions)",
    "Flu shot (ages 65+)": "Adults aged 65+ who have had a flu shot within the past year (variable calculated from one or more BRFSS questions)",
    "General health rating": "How is your general health?",
    "Health insurance (ages 18-64)": "Adults aged 18-64 who have any kind of health care coverage (variable calculated from one or more BRFSS questions)",
    "Heart attack": "Ever told you had a heart attack (myocardial infarction)?",
    "Kidney disease": "Ever told you have kidney disease?",
    "Other cancer": "Ever told you had any other types of cancer?",
    "Pneumonia vaccine (ages 65+)": "Adults aged 65+ who have ever had a pneumonia vaccination (variable calculated from one or more BRFSS questions)",
    "Skin cancer": "Ever told you had skin cancer?",
    "Smoking status": "Four Level Smoking Status (variable calculated from one or more BRFSS questions)",
    "Stroke": "Ever told you had a stroke?",
    "Weight category (BMI)": "Weight classification by Body Mass Index (BMI) (variable calculated from one or more BRFSS questions)",
}

# The 23 question texts alone, built from MEASURE_QUESTIONS so the two can never disagree
# frozenset is a set that cannot be changed after creation, data_loader.py imports APPROVED_QUESTIONS
APPROVED_QUESTIONS = frozenset(MEASURE_QUESTIONS.values())

# Columns the cleaner needs, a download missing any required column is rejected
REQUIRED_COLUMNS = {"year", "locationabbr", "locationdesc", "question", "data_value"}


def clean_brfss_data(data: pd.DataFrame) -> pd.DataFrame:
    """
    Standardize the CDC response for use by the Flask application

    Keeps only the approved states, years, health measures and population
    groups, converts number columns to numbers, and makes response labels
    consistent. Rows with a missing estimate are kept, since the app shows
    them as "Data not available"

    Parameters
    ----------
    data : pandas.DataFrame
        Rows as downloaded from the CDC API or read from the saved cleaned CSV.
        Column names may be in any capitalization

    Returns
    -------
    pandas.DataFrame
        Cleaned rows with lowercase column names, sorted by question, state and
        year, with the row index numbered from 0

    Raises
    ------
    ValueError
        If any column in REQUIRED_COLUMNS is missing
    """
    # an empty table has nothing to clean, copy() returns a separate table so the input is never changed
    if data.empty:
        return data.copy()

    cleaned = data.copy()
    # strip spaces and lowercase every column name so "Year" and "year " both become "year"
    cleaned.columns = [column.strip().lower() for column in cleaned.columns]

    # set difference: required names not found among the columns
    missing = REQUIRED_COLUMNS - set(cleaned.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    # convert to numbers, errors="coerce" turns anything unreadable into NaN instead of failing
    numeric_columns = ["year", "sample_size", "data_value", "confidence_limit_low", "confidence_limit_high"]
    for column in numeric_columns:
        if column in cleaned:
            cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce")

    # tidy state codes (blank for missing, no spaces, uppercase), then keep only the 50 states and DC
    cleaned["locationabbr"] = cleaned["locationabbr"].fillna("").astype(str).str.strip().str.upper()
    cleaned = cleaned[cleaned["locationabbr"].isin(STATE_ABBREVIATIONS)]
    # drop rows missing a year, state name or question, then keep only 2011 to 2025
    cleaned = cleaned.dropna(subset=["year", "locationdesc", "question"])
    cleaned = cleaned[cleaned["year"].between(MIN_YEAR, MAX_YEAR)]
    # keep only the 23 approved measures, isin checks each question for an exact match
    cleaned = cleaned[cleaned["question"].isin(APPROVED_QUESTIONS)]

    # Keep only the approved population groups. Missing data_value is retained:
    # CDC-suppressed estimates are displayed as "Data not available".
    if {"break_out_category", "break_out"}.issubset(cleaned.columns):
        cleaned["break_out_category"] = cleaned["break_out_category"].fillna("").astype(str).str.strip()
        cleaned["break_out"] = cleaned["break_out"].fillna("").astype(str).str.strip()
        # apply with axis=1 runs the lambda once per row, keeping the row when the group is allowed
        # for the row's category, .get(..., set()) gives an empty set for a category not in ALLOWED_GROUPS
        cleaned = cleaned[
            cleaned.apply(
                lambda row: row["break_out"] in ALLOWED_GROUPS.get(row["break_out_category"], set()),
                axis=1,
            )
        ]

    if "response" in cleaned.columns:
        response = cleaned["response"].fillna("").astype(str).str.strip()
        # BMI label merge: 2015 to 2017 labels say "bmi", \b marks a whole word so only that word changes
        response = response.str.replace(r"\bbmi\b", "BMI", case=False, regex=True)
        # casefold compares without capitalization, mask swaps in "Yes" or "No" where the match is True
        response = response.mask(response.str.casefold().eq("yes"), "Yes")
        response = response.mask(response.str.casefold().eq("no"), "No")
        cleaned["response"] = response

    # remove rows repeated in every column, then sort for a predictable order
    cleaned = cleaned.drop_duplicates()
    cleaned = cleaned.sort_values(["question", "locationdesc", "year"])

    # drop=True discards the old row numbers instead of keeping them as a column
    return cleaned.reset_index(drop=True)