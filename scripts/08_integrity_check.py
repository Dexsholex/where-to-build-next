"""
08 - Integrity check: recompute the key results by routes that do not reuse the pipeline's own code.

  - tile counts and tests straight from DSN's GeoPackage
  - the urban/rural label of tiles, re-sampled from the GHSL raster with rasterio's own sampler
  - the triage of a random sample of cells, using great-circle distances on raw coordinates
    instead of the projected grid and KD-trees
  - the people covered by the chosen sites, by brute force over raw coordinates
  - speeds and latency where people test, from DSN's raw file with the re-sampled labels
  - the thinly settled priority LGAs: every raw host inside each LGA polygon, great-circle 5 km reach
  - the all-year check: great-circle distances from a sample of rural-gap cells to the Q1-Q3 2024 tiles
  - the OpenCelliD comparison: great-circle distances from a sample of rural-gap cells to raw cell positions
  - internal consistency of the budget table, and every number printed in the PDF and the dashboard

Output: outputs/tables/integrity_check.csv
"""
import json
import re

import geopandas as gpd
import numpy as np
import pandas as pd
import pymupdf
import rasterio
from pyproj import Transformer

import config as C

rows = []


def check(claim, printed, recomputed, how, tol=0.0):
    if isinstance(printed, (int, float, np.integer, np.floating)) and isinstance(recomputed, (int, float, np.integer, np.floating)):
        ok = abs(float(printed) - float(recomputed)) <= tol
    else:
        ok = printed == recomputed
    rows.append(dict(status="PASS" if ok else "FAIL", claim=claim, printed=printed, recomputed=recomputed, how=how))


def note(claim, value, how):
    rows.append(dict(status="NOTE", claim=claim, printed="-", recomputed=value, how=how))


def haversine_km(lat1, lon1, lat2, lon2):
    p = np.pi / 180
    a = (np.sin((lat2 - lat1) * p / 2) ** 2 + np.cos(lat1 * p) * np.cos(lat2 * p) * np.sin((lon2 - lon1) * p / 2) ** 2)
    return 12742 * np.arcsin(np.sqrt(a))


H = json.load(open(C.TABLES / "headline.json"))
B = pd.read_csv(C.TABLES / "budgets.csv")
eff = pd.read_csv(C.TABLES / "sites_efficiency.csv")
equ = pd.read_csv(C.TABLES / "sites_equity.csv")

# ----------------------------------------------------------------- 1. Ookla, from DSN's file
raw = gpd.read_file(C.OOKLA_GPKG, layer=C.OOKLA_LAYER)
check("Ookla tiles", H["tiles"], len(raw), "DSN GeoPackage row count")
check("Ookla tests", H["tests"], int(raw["tests"].sum()), "DSN GeoPackage, sum of tests")
rel = pd.read_csv(C.TABLES / "ookla_release.csv")
check("Release match: mobile Q4 2024, all sampled tiles identical", True,
      bool(len(rel) >= 8 and (rel["release"] == "mobile year=2024 quarter=4").all()), "outputs/tables/ookla_release.csv")

yr_tab = pd.read_csv(C.TABLES / "ookla_all_year.csv")
check("DSN tiles identical to Ookla's public Q4 2024 file (all tiles)", H["tiles"], int(yr_tab["dsn_tiles_identical"].max()),
      "outputs/tables/ookla_all_year.csv, written by step 02b from the public file")

# ----------------------------------------------------------------- 2. urban/rural label of tiles, other sampler
tiles = gpd.read_file(C.PROCESSED / "ookla_tiles.gpkg")
tll = gpd.GeoSeries(gpd.points_from_xy(tiles["x"], tiles["y"]), crs=tiles.crs).to_crs(C.CRS_WGS84)
tif = "zip://" + str(C.SMOD_ZIP).replace("\\", "/") + "!/GHS_SMOD_E2020_GLOBE_R2023A_54009_1000_V2_0.tif"
with rasterio.open(tif) as src:
    mx, my = Transformer.from_crs(C.CRS_WGS84, src.crs, always_xy=True).transform(tll.x.to_numpy(), tll.y.to_numpy())
    smod2 = np.array([v[0] for v in src.sample(zip(mx, my))])
urban2 = np.isin(smod2, list(C.SMOD_URBAN))
check("Tiles labelled urban (%)", H["tiles_urban_pct"], round(100 * urban2.mean(), 1), "rasterio.sample on raw lon/lat")
meets2 = raw["avg_d_kbps"].to_numpy() >= np.where(urban2, C.URBAN_MIN_KBPS, C.RURAL_MIN_KBPS)
check("Tiles meeting the plan's speed (%)", H["tiles_meeting_plan_pct"], round(100 * meets2.mean(), 1),
      "raw speeds against 25/10 Mbps with the re-sampled labels")
for lab, m in [("urban", urban2), ("rural", ~urban2)]:
    w = raw["tests"].to_numpy()[m]
    check(f"Average download where people test, {lab} (Mbps, weighted by tests)", H[f"down_mbps_{lab}"],
          round(float((raw["avg_d_kbps"].to_numpy()[m] * w).sum() / w.sum()) / 1000, 1), "raw file, re-sampled labels", tol=0.1)
    check(f"Average latency where people test, {lab} (ms, weighted by tests)", H[f"latency_ms_{lab}"],
          round(float((raw["avg_lat_ms"].to_numpy()[m] * w).sum() / w.sum()), 1), "raw file, re-sampled labels", tol=0.1)
check("Rural tiles", H["tiles_rural"], int((~urban2).sum()), "re-sampled labels")
check("Town tiles reaching 25 Mbps (%)", H["tiles_meeting_plan_pct_urban"], round(100 * meets2[urban2].mean(), 1),
      "raw speeds, re-sampled labels")

# ----------------------------------------------------------------- 3. triage of sampled cells, great-circle distances
g = np.load(C.PROCESSED / "grid.npz")
cls = np.load(C.PROCESSED / "triage.npz")["cls"]
x0, y1, cell = float(g["x0"]), float(g["y1"]), float(g["cell"])
pop, urban = g["pop"], g["urban"]
rr, cc = np.nonzero(pop > 0)
check("Population on the grid (millions)", H["population_m"], round(pop.sum() / 1e6, 2), "sum of grid cells")
check("Four needs add up to the population (millions)", round(sum(H["people_by_class_m"].values()), 2),
      round(pop.sum() / 1e6, 2), "headline classes (each rounded to 0.01 M) vs grid", tol=0.03)
rng = np.random.default_rng(7)
pick = rng.choice(len(rr), 3000, replace=False)
to_ll = Transformer.from_crs(C.CRS_EQUAL_AREA, C.CRS_WGS84, always_xy=True)
lon, lat = to_ll.transform(x0 + (cc[pick] + 0.5) * cell, y1 - (rr[pick] + 0.5) * cell)
tlat, tlon = tll.y.to_numpy(), tll.x.to_numpy()
ok_t = meets2 & (raw["tests"].to_numpy() >= C.MIN_TESTS)
agree = 0
for la, lo, r, c in zip(lat, lon, rr[pick], cc[pick]):
    d = haversine_km(la, lo, tlat, tlon)
    k = 0 if d[ok_t].min() <= C.SERVE_RADIUS_KM else 1 if d.min() <= C.SERVE_RADIUS_KM else 2 if urban[r, c] else 3
    agree += int(k == cls[r, c])
check("Triage of 3,000 random cells, great-circle recomputation (% agreeing)", 100.0, round(100 * agree / len(pick), 1),
      "haversine on raw coordinates; small differences at the 2 km edge are expected", tol=1.0)

# ----------------------------------------------------------------- 4. people covered by the chosen sites, brute force
cover_need = (cls == 3)
cr, ccx = np.nonzero(cover_need)
clon, clat = to_ll.transform(x0 + (ccx + 0.5) * cell, y1 - (cr + 0.5) * cell)
cpop = pop[cr, ccx]
cpoor = np.where(np.isfinite(g["rwi"][cr, ccx]) & (g["rwi"][cr, ccx] <= H["rwi_cut_poorer40"]), cpop, 0.0)
covered_by = {}
for name, df, n in [("efficiency", eff, 100), ("equity", equ, 100)]:
    covered = np.zeros(len(cpop), dtype=bool)
    for _, s in df.head(n).iterrows():
        near = (np.abs(clat - s["lat"]) < 0.06) & (np.abs(clon - s["lon"]) < 0.06)
        idx = np.nonzero(near)[0]
        covered[idx[haversine_km(s["lat"], s["lon"], clat[idx], clon[idx]) <= C.SITE_RADIUS_KM]] = True
    covered_by[name] = covered
    printed = int(df["cum_people"].iloc[n - 1])
    check(f"People reached by the first {n} sites ({name})", printed, int(cpop[covered].sum()),
          "brute-force great-circle coverage of rural-gap cells", tol=0.01 * printed)

# ----------------------------------------------------------------- 4b. the thinly settled priority LGAs, brute force
cov = covered_by["equity"]
check("Poorer people per km2 of gap under the 100 poorest-first sites", H["poorer_per_km2_under_eq100"],
      round(cpoor[cov].sum() / cov.sum()), "brute-force great-circle coverage", tol=0.02 * H["poorer_per_km2_under_eq100"])
a2_ll = gpd.read_file(C.PROCESSED / "admin2.gpkg").to_crs(C.CRS_WGS84)
fac_ll = gpd.read_file(C.FACILITIES).to_crs(C.CRS_WGS84)
sch_ll = gpd.read_file(f"zip://{C.SCHOOLS_ZIP}!/{C.SCHOOLS_LAYER}").to_crs(C.CRS_WGS84)
hosts_ll = pd.concat([fac_ll[["geometry"]], sch_ll[sch_ll.geometry.notna()][["geometry"]]], ignore_index=True)
n_thin = 0
for pl in H["priority_lgas"]:
    poly = a2_ll[(a2_ll["lga"] == pl["lga"]) & (a2_ll["state"] == pl["state"])]
    hs = gpd.sjoin(hosts_ll, poly[["geometry"]], predicate="within")
    best = 0.0
    for hx, hy in zip(hs.geometry.x, hs.geometry.y):
        near = np.nonzero((np.abs(clat - hy) < 0.06) & (np.abs(clon - hx) < 0.06))[0]
        best = max(best, cpoor[near[haversine_km(hy, hx, clat[near], clon[near]) <= C.SITE_RADIUS_KM]].sum())
    n_thin += int(best < H["eq_site100_poorer"])
    check(f"Best single site in {pl['lga']}, poorer people reached", pl["best_site_poorer"], round(best),
          "every raw host inside the LGA polygon, great-circle 5 km", tol=0.05 * pl["best_site_poorer"])
check("Priority LGAs whose best site reaches fewer than the 100th poorest-first site", sum(
      p["best_site_poorer"] < H["eq_site100_poorer"] for p in H["priority_lgas"]), n_thin, "brute-force recomputation above")

# ----------------------------------------------------------------- 4c. the all-year check, great-circle on a sample
yr = pd.concat([pd.read_parquet(f) for f in C.OOKLA_2024_OTHER], ignore_index=True)
ylat, ylon = yr["tile_y"].to_numpy(), yr["tile_x"].to_numpy()
pick = np.random.default_rng(11).choice(len(cpop), 6000, replace=False)
never = np.array([not (haversine_km(clat[i], clon[i], ylat, ylon) <= C.SERVE_RADIUS_KM).any() for i in pick])
check("People in rural gaps with no test in any quarter of 2024 (%)", H["allyear_gap_untested_pct"],
      round(100 * cpop[pick][never].sum() / cpop[pick].sum(), 1),
      "haversine to Q1-Q3 tiles for 6,000 random rural-gap cells (a sample, so within 1.5 points)", tol=1.5)

# ----------------------------------------------------------------- 4d. OpenCelliD, great-circle on a sample
oc = pd.read_parquet(C.OPENCELLID_CELLS, columns=["lon", "lat"])
olat, olon = oc["lat"].to_numpy(), oc["lon"].to_numpy()
pick = np.random.default_rng(13).choice(len(cpop), 4000, replace=False)
far = []
for i in pick:
    near = np.nonzero((np.abs(olat - clat[i]) < 0.06) & (np.abs(olon - clon[i]) < 0.06))[0]
    far.append(not (haversine_km(clat[i], clon[i], olat[near], olon[near]) <= 5).any())
far = np.array(far)
check("People in rural gaps with no OpenCelliD cell within 5 km (%)", H["ocid_gap_no_cell5_pct"],
      round(100 * cpop[pick][far].sum() / cpop[pick].sum(), 1),
      "haversine to raw cell positions for 4,000 random rural-gap cells (a sample, so within 1.5 points)", tol=1.5)
ocf = pd.read_csv(C.TABLES / "opencellid_fetch.csv")
check("OpenCelliD cells file matches the checksum recorded when fetched", ocf["sha256"].iloc[0],
      __import__("hashlib").sha256(C.OPENCELLID_CELLS.read_bytes()).hexdigest(), "outputs/tables/opencellid_fetch.csv")

# ----------------------------------------------------------------- 5. internal consistency
check("Cumulative reach never falls (both objectives)", True,
      bool((np.diff(eff["cum_people"]) >= 0).all() and (np.diff(equ["cum_people"]) >= 0).all()), "site tables")
check("Efficiency reaches more people than equity at every budget", True, bool((B["eff_people"] >= B["eq_people"]).all()),
      "budgets.csv")
check("Equity reaches more poorer people than efficiency at every budget", True,
      bool((B["eq_poorer"] >= B["eff_poorer"]).all()), "budgets.csv")
rwi = g["rwi"]
v = (pop > 0) & np.isfinite(rwi)
check("Poorer group is 40% of people with a wealth score (%)", 40.0,
      round(100 * pop[v & (rwi <= H["rwi_cut_poorer40"])].sum() / pop[v].sum(), 1), "grid wealth scores", tol=0.5)
note("People reached per site, first 100 (efficiency): median and largest",
     f"{int(eff['people_reached'].head(100).median()):,} and {int(eff['people_reached'].max()):,} "
     f"({eff.loc[eff['people_reached'].idxmax(), 'name']})", "sites_efficiency.csv")

# ----------------------------------------------------------------- 6. numbers printed in the PDF and the tool
pdf = " ".join(p.get_text() for p in pymupdf.open(next(C.SUBMISSION.glob("DSN_Geospatial_WhereToBuildNext*.pdf"))))
pdf = re.sub(r"\s+", " ", pdf)
pc = H["people_by_class_m"]
b100 = B.set_index("sites").loc[100]
expected = [f"{pc[k]:.1f} M" for k in pc] + [
    f"{H['served_rural_pct']}%", f"{H['served_urban_pct']}%", f"{H['tests_per_10k_urban']}", f"{H['tests_per_10k_rural']}",
    f"{H['coverage_gap_poorer_pct']:.0f}%", f"{H['lgas_with_no_tile']} of 774", f"{H['facilities_by_class']['coverage']:,}",
    f"{b100['eff_people'] / 1e6:.2f} million", f"{b100['poorer_gained_by_equity'] / 1e3:,.0f} thousand",
    f"{b100['people_given_up_for_equity'] / 1e3:,.0f} thousand", f"{H['facilities']:,}", f"{H['tests']:,}",
    f"{H['schools']:,}", f"{H['schools_by_class']['coverage']:,}",
    f"{H['down_mbps_urban']} Mbps in towns", f"{H['down_mbps_rural']} Mbps in rural", f"{H['tiles_rural']:,} of the {H['tiles']:,} tiles",
    f"{H['tiles_meeting_plan_pct_urban']}% of town tiles", f"{b100['eq_people'] / 1e6:.2f} million",
    f"{H['poorer_per_km2_under_eq100']} under the 100", f"{H['eq100_sites_at_schools']} of them are schools",
    f"{H['eq100_multi_host_cells']} of the 100 squares", f"all {H['dsn_tiles_identical']:,} tiles identical",
    f"{H['allyear_gap_untested_pct']}% of people in them", f"{H['ocid_gap_no_cell5_pct']}% have no mobile cell",
    f"against {H['ocid_served_no_cell5_pct']}% in served areas", "the low end of ITU's 5 to 15 km range for mobile cells"]
PLd = pd.DataFrame(H["priority_lgas"])
expected.append(f"{PLd['poorer_per_km2'].min()} to {PLd['poorer_per_km2'].max()} poorer people per km²")
expected += [f"{r['people_reached']:,} {r['poorer_reached']:,}" for _, r in equ.head(10).iterrows()]
LG = pd.read_csv(C.TABLES / "lga_summary.csv")
for col in ["coverage_poorer", "measure", "capacity"]:
    for _, r in LG.nlargest(5, col).iterrows():
        expected.append(f"{r['lga']}, {r['state']} {r[col] / 1e3:,.0f}")
missing = [e for e in expected if e not in pdf]
check(f"All {len(expected)} key numbers appear in the PDF as computed", "none missing", ", ".join(missing) or "none missing",
      "text extracted from the PDF")
html = (C.ROOT / "outputs" / "dashboard" / "where_to_build_next.html").read_text(encoding="utf-8")
data = json.loads(re.search(r"const D = (\{.*?\});\nconst TRIAGE_PNG", html, re.S).group(1))
ok_sites = all([r[9] for r in data["sites"][h][o]] == pd.read_csv(C.TABLES / f"sites_{h}_{o}.csv")["cum_people"].tolist()
               for h in ["both", "clinics", "schools"] for o in ["efficiency", "equity"])
check("Dashboard sites match the tables (3 host sets x 2 objectives, all ranks)", True, ok_sites,
      "data embedded in the HTML")
check("Equity runs count people outside the poorer 40% too (coverage of all gap cells)", True,
      bool((B["eq_people"] > B["eq_poorer"]).all()), "budgets.csv")
sch_raw = gpd.read_file(f"zip://{C.SCHOOLS_ZIP}!/{C.SCHOOLS_LAYER}").to_crs(C.CRS_EQUAL_AREA)
a2 = gpd.read_file(C.PROCESSED / "admin2.gpkg")
inside_sch = gpd.sjoin(sch_raw[sch_raw.geometry.notna()], a2[["geometry"]], predicate="within")
check("Schools used as candidates (inside an LGA)", H["schools"], int(inside_sch.index.nunique()),
      "fresh spatial join of the raw GRID3 schools file")
check("Dashboard Ookla tiles", H["tiles"], len(data["tiles"]), "data embedded in the HTML")
for key, col in [("gp", "coverage_poorer"), ("m", "measure"), ("c", "capacity")]:
    check(f"Dashboard LGA totals match the LGA table ({col}, thousands)", round(LG[col].sum() / 1e3),
          round(sum(f["properties"][key] for f in data["lgas"]["features"])), "data embedded in the HTML", tol=2)
check("LGA rural-poor-no-evidence totals add up to the national figure (millions)",
      round(H["coverage_gap_poorer_m"], 1), round(LG["coverage_poorer"].sum() / 1e6, 1), "lga_summary.csv", tol=0.2)

out = pd.DataFrame(rows)
out.to_csv(C.TABLES / "integrity_check.csv", index=False)
pd.set_option("display.width", 220); pd.set_option("display.max_colwidth", 80)
print(out[["status", "claim", "printed", "recomputed"]].to_string(index=False))
print("\nPASS", (out.status == "PASS").sum(), "| FAIL", (out.status == "FAIL").sum(), "| NOTE", (out.status == "NOTE").sum())
