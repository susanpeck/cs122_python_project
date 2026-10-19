# BRFSS State Health Explorer
This project was created for SJSU Advanced Python Course CS122. This is a working title.

## Authors
- Susan Peck, GitHub: [susanpeck](https://github.com/susanpeck)
- Kanishka Yadav, GitHub: <Kanishka's GitHub username>

## Project Description
This project is a Python application that retrieves state-level health survey estimates from the CDC's Behavioral Risk Factor Surveillance System (BRFSS) and lets users explore them interactively. The app downloads BRFSS prevalence data from 2011 onward from the CDC's open data portal and stores the selected indicators locally as CSV files. Users choose a health indicator, a state, and a range of years through a web interface. The app then analyzes how prevalence has changed over time and, where the data allow, how results for women compare with results for men. Results are displayed as plots with measures of uncertainty so that real differences can be told apart from sampling noise.

<!-- Uncomment and update the path once a screenshot is added to the repo -->
<!-- ![Screenshot of the app](docs/screenshot.png) -->

## Project Outline/Plan

### Interface Plan
The interface is a web application built with Flask and run locally in a web browser. It is planned as three pages linked by navigation buttons, and the plan below is subject to change.

- **Data page:** choose indicators and years, download or refresh the data, and preview the stored table.
  - Widgets: indicator dropdown, start year and end year selectors, download or refresh button, data preview table, status message.
- **Analysis page:** choose a state, an indicator, and a range of years, set options such as the women versus men comparison, and run the analysis. The numerical results (for example trend estimates and intervals) appear on this page in a table.
  - Widgets: state dropdown, indicator dropdown, start year and end year selectors, women versus men comparison checkbox, run analysis button, results table.
- **Plots page:** view the time series and state comparison plots, switch between plot types, toggle uncertainty bands, and export the figure.
  - Widgets: plot type selector, uncertainty band checkbox, export plot button.

### Data Collection and Storage Plan
- **Source:** the CDC's BRFSS Prevalence Data (2011 to present), dataset ID dttw-5yxu, on data.cdc.gov.
- **Method:** the app requests a CSV from the portal's API, with filters in the request for the chosen indicators and years, and reads it into a pandas table. The exact request and the available filter columns will be confirmed by testing against the live dataset.
- **Cleaning:** keep only state-level rows (any national or other non-state rows are removed), convert the estimate and confidence limit columns to numbers, and keep one row per state, year, indicator, and group.
- **Storage:** one cleaned CSV file per indicator in the `data` folder, with the same column names in every file so the analysis code can read any of them the same way. The raw download is kept separately from the cleaned file.
- **Refresh:** the refresh button downloads the data again and replaces the stored files. If the download fails, the app keeps using the existing local files and shows a status message.

### Data Analysis and Visualization Plan
The exact analysis depends on which columns the BRFSS prevalence data contains, such as confidence limits, sample sizes, and a sex breakout. These will be confirmed by inspecting the downloaded file, and this plan will be updated to match.

Analysis (planned):
- **Trend over time:** for the chosen state and indicator, fit a straight line to prevalence across years and test whether the slope differs from zero, using numpy and scipy. If standard errors can be recovered from the confidence limits, weight years by their precision. Otherwise use an unweighted fit.
- **Women versus men:** where the data include a sex breakout, take the difference between the two prevalence estimates in each year, along with its standard error, treating the two estimates as independent (an approximation). Flag a difference when its interval excludes zero. Also examine whether the gap changes over time.
- **Uncertainty:** carry the confidence limits from the data, where available, through to the plots.
- **Interpretation:** the data are state-level summaries, so any association is a pattern across states and cannot be read as an effect on individuals.

Visualization (planned, using matplotlib):
- A time series for the selected state and indicator with an uncertainty band, showing women and men together where possible.
- A comparison of states for a selected year, with intervals.
- Plots can be exported from the interface.

## Features
Planned features, to be updated as the app is built:
- Download and store BRFSS state-level prevalence data locally
- Select an indicator, state, and range of years
- Trend analysis with significance testing
- Women versus men comparison where the data allow
- Exportable plots with uncertainty bands

## Data sources
| Website | What is pulled | Method (API, scraping, or download) |
|---------|----------------|-------------------------------------|
| [data.cdc.gov](https://data.cdc.gov): BRFSS Prevalence Data (2011 to present), dataset ID dttw-5yxu | State-level prevalence estimates by year and health indicator | Download of CSV data from the open data portal (to be confirmed) |

Only 2011 and later data are used. CDC documentation for the 2011 data describes a change in weighting methods and the addition of cell phone respondents, so earlier years are not directly comparable.

The `data` folder is ignored by git, so it will not exist after a fresh clone.
To get or regenerate the data: <describe the script, command, or manual steps>

## Installation
1. Clone the repository:
```
git clone git@github.com:susanpeck/cs122_python_project.git
cd cs122_python_project
```
2. Create and activate the conda environment:
```
conda create -n <env-name> python=<version>
conda activate <env-name>
```
3. Install the required packages:
```
pip install -r requirements.txt
```
4. Create the `data` folder and add the data (see Data sources above):
```
mkdir data
```

## Usage
Launch the app with:
```
<command to start the app, for example python code/main.py>
```

Then open the address shown in the terminal in a web browser.

Quick walkthrough:
1. <First screen or action>
2. <Second screen or action>
3. <Third screen or action>

## Project structure
```
cs122_python_project
 |- LICENSE
 |- README.md
 |- .gitignore
 |- code
     |- <main file>.py
 |- notebooks
     |- BRFSS_FirstLook_v1.0.ipynb
 |- data        (not tracked by git)
```

## Dependencies
- Python <version>
- GUI toolkit: Flask (web interface)
- Web data libraries: <to be decided>
- Other: pandas, numpy, scipy, matplotlib

## Limitations and notes
- Known issues: <issue>
- Data availability: federal health web pages and datasets changed availability in 2025, so the app saves downloaded data locally instead of depending on the portal at run time.
- Data scope: BRFSS is a self-reported survey, and the estimates are state-level summaries.
- Rate limits and terms of service: <notes for the data source used>
- Planned improvements: <idea, for example additional indicators, county-level data, or analysis of respondent-level files with survey weights>

## Author, course, and license
- Authors: Susan Peck and Kanishka Yadav
- Course: CS122 Advanced Python, San José State University, Fall 2026
- License: see the LICENSE file

## Github notes
Changes made on remote repositories should be "pulled" to local repositories to reflect recent changes
