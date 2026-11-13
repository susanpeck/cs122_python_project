import pandas as pd


MIN_YEAR = 2011
MAX_YEAR = 2025
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
ALLOWED_GROUPS = {
    "Overall": {"Overall"},
    "Sex": {"Female", "Male"},
    "Age Group": {"18-24", "25-34", "35-44", "45-54", "55-64", "65+"},
    "Education Attained": {
        "College graduate", "H.S. or G.E.D.", "Less than H.S.", "Some post-H.S.",
    },
    "Race/Ethnicity": {"White, non-Hispanic", "Black, non-Hispanic", "Hispanic"},
}
APPROVED_QUESTIONS = frozenset(
    {
        "Adults who have had at least one drink of alcohol within the past 30 days",
        "During the past month, did you participate in any physical activities? (variable calculated from one or more BRFSS questions)",
        "Adults who have been told they have arthritis",
        "Adults who have been told they currently have asthma (variable calculated from one or more BRFSS questions)",
        "Adults who have ever been told they have asthma (variable calculated from one or more BRFSS questions)",
        "Binge drinkers (males having five or more drinks on one occasion, females having four or more drinks on one occasion) (variable calculated from one or more BRFSS questions)",
        "Ever told you have COPD?",
        "Ever told you have angina or coronary heart disease?",
        "Adults who are current smokers (variable calculated from one or more BRFSS questions)",
        "Ever told you that you have a form of depression?",
        "Have you ever been told by a doctor that you have diabetes?",
        "How is your general health?",
        "Adults aged 65+ who have had a flu shot within the past year (variable calculated from one or more BRFSS questions)",
        "Adults aged 18-64 who have any kind of health care coverage (variable calculated from one or more BRFSS questions)",
        "Ever told you had a heart attack (myocardial infarction)?",
        "Ever told you have kidney disease?",
        "Ever told you have any other types of cancer?",
        "Adults aged 65+ who have ever had a pneumonia vaccination (variable calculated from one or more BRFSS questions)",
        "Ever told you have skin cancer?",
        "Four Level Smoking Status (variable calculated from one or more BRFSS questions)",
        "Ever told you had a stroke?",
        "Weight classification by Body Mass Index (BMI) (variable calculated from one or more BRFSS questions)",
    }
)

REQUIRED_COLUMNS = {"year", "locationabbr", "locationdesc", "question", "data_value"}


def clean_brfss_data(data: pd.DataFrame) -> pd.DataFrame:
    """Standardize the CDC response for use by the Flask application."""
    if data.empty:
        return data.copy()

    cleaned = data.copy()
    cleaned.columns = [column.strip().lower() for column in cleaned.columns]

    missing = REQUIRED_COLUMNS - set(cleaned.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    numeric_columns = ["year", "sample_size", "data_value", "confidence_limit_low", "confidence_limit_high"]
    for column in numeric_columns:
        if column in cleaned:
            cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce")

    cleaned["locationabbr"] = cleaned["locationabbr"].fillna("").astype(str).str.strip().str.upper()
    cleaned = cleaned[cleaned["locationabbr"].isin(STATE_ABBREVIATIONS)]
    cleaned = cleaned.dropna(subset=["year", "locationdesc", "question"])
    cleaned = cleaned[cleaned["year"].between(MIN_YEAR, MAX_YEAR)]
    cleaned = cleaned[cleaned["question"].isin(APPROVED_QUESTIONS)]

    # Keep only the approved population groups. Missing data_value is retained:
    # CDC-suppressed estimates are displayed as "Data not available".
    if {"break_out_category", "break_out"}.issubset(cleaned.columns):
        cleaned["break_out_category"] = cleaned["break_out_category"].fillna("").astype(str).str.strip()
        cleaned["break_out"] = cleaned["break_out"].fillna("").astype(str).str.strip()
        cleaned = cleaned[
            cleaned.apply(
                lambda row: row["break_out"] in ALLOWED_GROUPS.get(row["break_out_category"], set()),
                axis=1,
            )
        ]

    if "response" in cleaned.columns:
        response = cleaned["response"].fillna("").astype(str).str.strip()
        response = response.str.replace(r"\bbmi\b", "BMI", case=False, regex=True)
        response = response.mask(response.str.casefold().eq("yes"), "Yes")
        response = response.mask(response.str.casefold().eq("no"), "No")
        cleaned["response"] = response

    cleaned = cleaned.drop_duplicates()
    cleaned = cleaned.sort_values(["question", "locationdesc", "year"])

    return cleaned.reset_index(drop=True)
