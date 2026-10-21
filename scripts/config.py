"""
Where to Build Next: paths and every assumption in one place.

Everything the pipeline reads lives in this repository or is downloaded by 01_download.py:
  data/input/   small inputs shipped with the code (Ookla tiles, boundaries, the cleaned facility list)
  data/raw/     downloads, verified against data/raw/PROVENANCE.csv
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "input"
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
FIGS = ROOT / "outputs" / "figures"
TABLES = ROOT / "outputs" / "tables"
SUBMISSION = ROOT / "submission"
for d in [RAW, PROCESSED, FIGS, TABLES, SUBMISSION]:
    d.mkdir(parents=True, exist_ok=True)

# --- inputs ------------------------------------------------------------------
OOKLA_GPKG = INPUT / "ookla_mobile_2024q4_nigeria.gpkg"   # supplied by DSN; identical to Ookla mobile Q4 2024 (scripts/02)
OOKLA_LAYER = "nigeria_ookla"                       # identical to "Nigeria Ookla", which lacks a CRS
# Ookla mobile tiles for January to September 2024, touching Nigeria (scripts/02b), for the all-year check only
OOKLA_2024_OTHER = [INPUT / f"ookla_mobile_2024q{q}_nigeria.parquet" for q in (1, 2, 3)]
RWI_CSV = RAW / "rwi" / "nga_relative_wealth_index.csv"
SMOD_ZIP = RAW / "ghsl_smod" / "GHS_SMOD_E2020_GLOBE_R2023A_54009_1000_V2_0.zip"
SCHOOLS_ZIP = RAW / "grid3_education" / "nga_education.zip"   # GRID3 NGA Education Facilities, 204,513 schools
SCHOOLS_LAYER = "NGA_Education.shp"
# OCHA COD-AB boundaries and GRID3 health facilities (v3.0 for 24 states, v2.0 for the other 13; records without
# coordinates, flagged as duplicates, or marked Not-Functional or Closed removed), in the equal-area CRS below
ADMIN0 = INPUT / "nigeria_admin0.gpkg"
ADMIN1 = INPUT / "nigeria_admin1.gpkg"
ADMIN2 = INPUT / "nigeria_admin2.gpkg"
FACILITIES = INPUT / "grid3_health_facilities_clean.gpkg"
POP_CSV_ZIP = RAW / "meta_population" / "nga_general_2020_csv.zip"
# OpenCelliD cell positions of Nigerian networks (MCC 621), CC BY-SA 4.0, fetched by scripts/02c
OPENCELLID_CELLS = RAW / "opencellid" / "nigeria_cells.parquet"

CRS_WGS84 = "EPSG:4326"
CRS_EQUAL_AREA = "+proj=aea +lat_1=4 +lat_2=13 +lat_0=9 +lon_0=8 +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"

# --- analysis grid -----------------------------------------------------------
CELL_M = 1000                                        # 1 km equal-area cells
# Meta's CSV holds 256 pixels with one of two repeated values (2,433.3 and 1,603.1 people per ~31 m pixel;
# 545,717 people in Yamaltu/Deba, Isokan and Ona-Ara), where a census count sits on a few detected buildings.
# No genuine pixel exceeds 333 (the 99.999th percentile), so pixels above this cap are excluded as unplaceable.
POP_PIXEL_MAX = 1000

# --- what counts as usable broadband -----------------------------------------
# Nigerian National Broadband Plan 2020-2025 (FMoCDE 2020), pp. 36 and 38: broadband is a minimum
# download speed of 25 Mbps in urban areas and 10 Mbps in rural areas by 2025.
URBAN_MIN_KBPS = 25_000
RURAL_MIN_KBPS = 10_000
# GHSL degree of urbanisation (SMOD) classes treated as urban: 30 urban centre, 23 dense urban
# cluster, 22 semi-dense urban cluster, 21 suburban or peri-urban. Rural: 13, 12, 11.
SMOD_URBAN = {30, 23, 22, 21}
MIN_TESTS = 1                                        # tests a tile needs to count as evidence
SERVE_RADIUS_KM = 2.0                                # a person counts as served within this distance
                                                     # of a tile that meets the speed benchmark

# --- siting ------------------------------------------------------------------
SITE_RADIUS_KM = 5.0                                 # assumed reach of one new connectivity site
BUDGETS = [10, 25, 50, 100, 200]                     # numbers of sites offered in the tool
MAX_SITES = 200
POORER_SHARE = 0.40                                  # "poorer" = bottom 40% of people by wealth index

# sensitivity runs: (label, overrides)
SENSITIVITY = [
    ("base", {}),
    ("serve 1 km", {"SERVE_RADIUS_KM": 1.0}),
    ("serve 5 km", {"SERVE_RADIUS_KM": 5.0}),
    ("tiles with 3+ tests", {"MIN_TESTS": 3}),
    ("site reach 3 km", {"SITE_RADIUS_KM": 3.0}),
    ("site reach 10 km", {"SITE_RADIUS_KM": 10.0}),
]
