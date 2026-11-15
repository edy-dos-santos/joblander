"""Paths, source locations and business rules shared by every step."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXTRACT = ROOT / "data" / "extract"
COMPOSITION = EXTRACT / "he_workforce_composition.csv"
MOVEMENTS = EXTRACT / "he_workforce_movements.csv"
OUT = ROOT / "outputs"
FIGS = OUT / "figures"

# WGEA public data files, published on data.gov.au under CC BY 3.0 AU.
DATASET_PAGE = "https://data.gov.au/data/dataset/wgea-dataset"
_BASE = "https://data.gov.au/data/dataset/4d35cd80-2538-4705-82f3-d0d18e823d98/resource"
SOURCES = {
    "2022-23": f"{_BASE}/4f716314-5de2-425b-aef2-6501c0be076f/download/wgea_public_dataset_2023.zip",
    "2023-24": f"{_BASE}/f12cc138-44a8-45fc-9ba7-97ee5dadd683/download/wgea_public_dataset_2024.zip",
    "2024-25": f"{_BASE}/380faa66-1126-4020-8b89-496821290624/download/wgea_public_dataset_2025.zip",
}
YEARS = list(SOURCES)
LATEST = YEARS[-1]

INDUSTRY_CLASS = "Higher Education"
FOCUS = "Queensland University Of Technology"   # the university the briefing is written for
FOCUS_SHORT = "QUT"

# A "university" for benchmarking: a higher-education employer whose name contains
# "University", is not a subsidiary/pathway entity, and has at least this many employees.
MIN_UNIVERSITY_HEADCOUNT = 1000
SUBSIDIARY_WORDS = ["College", "Enterprises", "Online", "Ventures", "Training", "Admissions"]

MANAGER_TIERS = ["CEOs", "Key Management Personnel", "Other Executives and General Managers",
                 "Senior managers", "Other managers"]
TIER_LABELS = {"CEOs": "CEO / head of business", "Key Management Personnel": "Key management personnel",
               "Other Executives and General Managers": "Executives / general managers",
               "Senior managers": "Senior managers", "Other managers": "Other managers"}
SENIOR_TIERS = MANAGER_TIERS[:4]   # everything above "Other managers"
EMPLOYMENT_TYPES = ["Permanent", "Contract", "Casual"]
SMALL_BASE = 20   # rates on a base smaller than this are flagged as unreliable
