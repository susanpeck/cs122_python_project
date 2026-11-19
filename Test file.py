import analysis, data_loader
df = data_loader.load_cleaned_data(analysis.Path("data/cleaned/brfss_cleaned.csv"))
table = analysis.filter_group_view(df, "Depression", "Yes", "Ohio", "Sex", 2011, 2025)
title, subtitle = analysis.make_title("groups", "Depression", "Ohio", 2011, 2025, answer="Yes", group_category="Sex")
analysis.plot_trend(table, title, "static/plots/test.png", legend_title="Sex", subtitle=subtitle)