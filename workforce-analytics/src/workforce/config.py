"""Shared configuration: paths, reporting period, reference lists and business rules.

Keeping every definition in one place means the Excel workbook, the slide deck and
the statistical outputs can never drift apart on (for example) what "senior" means.
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "employees_raw.csv"
CLEAN = ROOT / "data" / "processed" / "employees_clean.csv"
OUT = ROOT / "outputs"
FIGS = OUT / "figures"
TABLES = OUT / "tables"

UNIVERSITY = "Riverbend University"  # fictional
SEED = 2026

# Data covers 2021-2025. 2021 is treated as a burn-in year for the simulation,
# so reporting uses the four complete years 2022-2025.
SIM_START = pd.Timestamp("2021-01-01")
SNAPSHOT = pd.Timestamp("2025-12-31")
REPORT_YEARS = [2022, 2023, 2024, 2025]

ACADEMIC_LEVELS = ["Level A", "Level B", "Level C", "Level D", "Level E"]
PROFESSIONAL_LEVELS = ["HEW 3", "HEW 4", "HEW 5", "HEW 6", "HEW 7", "HEW 8", "HEW 9", "HEW 10+"]
LEVELS = ACADEMIC_LEVELS + PROFESSIONAL_LEVELS
SENIOR_LEVELS = ["Level D", "Level E", "HEW 10+"]

EMPLOYMENT_TYPES = ["Ongoing", "Fixed-term", "Casual"]
GENDERS = ["Woman", "Man", "Non-binary"]
INDIGENOUS_YES = "Aboriginal and/or Torres Strait Islander"
INDIGENOUS_VALUES = [INDIGENOUS_YES, "Neither", "Not disclosed"]
SEPARATION_REASONS = ["Resignation", "End of contract", "Retirement", "Redundancy", "Other"]
VOLUNTARY_REASONS = ["Resignation"]

DIVISIONS = [
    "Faculty of Health",
    "Faculty of Science",
    "Faculty of Engineering",
    "Faculty of Business & Law",
    "Faculty of Arts & Education",
    "Student Services",
    "Digital & Technology",
    "Finance & Facilities",
    "Research Office",
    "People & Culture",
]

# Business rules
SMALL_CELL_THRESHOLD = 5        # counts below this are suppressed in any published table
INDIGENOUS_TARGET = 0.03        # illustrative institutional target for the fictional university
RETIREMENT_AGE_FLAG = 55        # "approaching retirement" age band starts here

AGE_BINS = [0, 29, 39, 49, 54, 59, 64, 120]
AGE_LABELS = ["Under 30", "30-39", "40-49", "50-54", "55-59", "60-64", "65+"]
TENURE_BINS = [-0.01, 1, 3, 5, 10, 100]
TENURE_LABELS = ["<1 yr", "1-3 yrs", "3-5 yrs", "5-10 yrs", "10+ yrs"]
