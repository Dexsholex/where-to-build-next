"""
04 - Not every gap needs a tower: triage every 1 km cell, then site new coverage at clinics and schools.

Triage (SERVE_RADIUS_KM around each cell; speed benchmark from the National Broadband Plan 2020-2025):
  served     an Ookla tile meeting the plan's speed for its setting is nearby
  capacity   Ookla tiles are nearby but none meets the speed: signal exists, it is too slow -> upgrade
  measure    urban, and no Ookla test nearby at all: no coverage cannot be told from no testers -> measure first
  coverage   rural, and no Ookla test nearby: the case for a new site -> build

Siting covers the "coverage" cells only. Candidate hosts are registered health facilities (GRID3 health
facilities, cleaned as described in config.py) and schools (GRID3 education facilities). The plan's rural broadband
initiative names schools, telecentres and hospitals as sites (p. 47) and targets connecting 80% of primary
health centres per LGA (p. 40). Three host sets are run: clinics, schools, and both (the default).

Coverage is measured on a 1 km grid, so hosts in the same 1 km cell are interchangeable: each set keeps one
candidate per cell (clinic first, then secondary, tertiary, mixed, primary, pre-primary school) and records how
many other hosts share that cell.

Method: the maximal covering location problem (choose N sites to cover the most demand within a radius),
solved by greedy selection with lazy evaluation; coverage is submodular, so greedy reaches at least 1 - 1/e
(63%) of the optimum. Gains are computed on demand, so memory stays small with 100,000+ candidates.
Objectives: efficiency (most people in coverage gaps) and equity (most such people in the poorer 40%).
"""
import heapq
import json

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

import config as C

CLASSES = ["served", "capacity", "measure", "coverage"]
HOSTS = ["both", "clinics", "schools"]
OBJECTIVES = ["efficiency", "equity"]

g = np.load(C.PROCESSED / "grid.npz")
x0, y1, cell = float(g["x0"]), float(g["y1"]), float(g["cell"])
nrow, ncol = int(g["nrow"]), int(g["ncol"])
pop, urban, rwi, lga = g["pop"], g["urban"], g["rwi"], g["lga"]
XX, YY = np.meshgrid(x0 + (np.arange(ncol) + 0.5) * cell, y1 - (np.arange(nrow) + 0.5) * cell)

valid = pop > 0                         # population comes only from pixels inside Nigeria
cx, cy, cpop = XX[valid], YY[valid], pop[valid]
curban, crwi, clga = urban[valid], rwi[valid], lga[valid]
cell_tree = cKDTree(np.c_[cx, cy])

# poorer 40% of people by wealth index (population-weighted)
has_rwi = np.isfinite(crwi)
order = np.argsort(crwi[has_rwi])
cum = np.cumsum(cpop[has_rwi][order]) / cpop[has_rwi].sum()
RWI_CUT = float(crwi[has_rwi][order][np.searchsorted(cum, C.POORER_SHARE)])
cpoor = has_rwi & (crwi <= RWI_CUT)

tiles = gpd.read_file(C.PROCESSED / "ookla_tiles.gpkg")
d_any = cKDTree(np.c_[tiles["x"], tiles["y"]]).query(np.c_[cx, cy])[0] / 1000
adm2 = gpd.read_file(C.PROCESSED / "admin2.gpkg").drop(columns=["lga_idx"], errors="ignore").reset_index(drop=True)

# ----------------------------------------------------------------- candidate hosts
fac = gpd.read_file(C.FACILITIES).to_crs(C.CRS_EQUAL_AREA)
clinics = pd.DataFrame({"host": "clinic", "name": fac["facility_name"], "kind": fac["facility_type"].astype(str),
                        "lga": fac["lga"], "state": fac["state"], "x": fac.geometry.x, "y": fac.geometry.y, "prio": 0})
sch = gpd.read_file(f"zip://{C.SCHOOLS_ZIP}!/{C.SCHOOLS_LAYER}").to_crs(C.CRS_EQUAL_AREA)
sch = sch[sch.geometry.notna() & ~sch.geometry.is_empty]
sch = gpd.sjoin(sch, adm2[["lga", "state", "geometry"]].rename(columns={"lga": "lga_n", "state": "state_n"}),
                predicate="within", how="inner")
sch = sch[~sch.index.duplicated()]
SCHOOL_PRIO = {"Secondary": 1, "Tertiary": 2, "Mixed": 3, "Primary": 4, "Pre Primary": 5}
schools = pd.DataFrame({"host": "school", "name": sch["name"].fillna("Unnamed school").astype(str),
                        "kind": sch["category"].fillna("Other").astype(str) + " school",
                        "lga": sch["lga_n"], "state": sch["state_n"], "x": sch.geometry.x, "y": sch.geometry.y,
                        "prio": sch["category"].map(SCHOOL_PRIO).fillna(6).astype(int)})
allc = pd.concat([clinics, schools], ignore_index=True)
allc["r"] = np.floor((y1 - allc["y"]) / cell).astype(int)
allc["c"] = np.floor((allc["x"] - x0) / cell).astype(int)
lon, lat = gpd.GeoSeries(gpd.points_from_xy(allc["x"], allc["y"]), crs=C.CRS_EQUAL_AREA).to_crs(C.CRS_WGS84).pipe(
    lambda s: (s.x.round(5), s.y.round(5)))
allc["lon"], allc["lat"] = lon.to_numpy(), lat.to_numpy()


def thin(df):
    """One candidate per 1 km cell, best host first; keeps a count of hosts in the cell."""
    df = df.sort_values(["r", "c", "prio"]).copy()
    df["hosts_in_cell"] = df.groupby(["r", "c"])["host"].transform("size")
    return df.drop_duplicates(["r", "c"]).reset_index(drop=True)


CAND = {"both": thin(allc), "clinics": thin(allc[allc["host"] == "clinic"]),
        "schools": thin(allc[allc["host"] == "school"])}


def triage(serve_km, min_tests):
    t = tiles[tiles["meets_plan"] & (tiles["tests"] >= min_tests)]
    d_ok = cKDTree(np.c_[t["x"], t["y"]]).query(np.c_[cx, cy])[0] / 1000
    return np.select([d_ok <= serve_km, d_any <= serve_km, curban], [0, 1, 2], 3)


def greedy(cand, demand, weights, site_km, n_sites):
    """Lazy greedy maximal covering. Coverage is over every gap cell (demand > 0); the objective
    weights decide which site adds most. Gains are computed on demand."""
    gap = np.nonzero(demand > 0)[0]
    tree = cKDTree(np.c_[cx[gap], cy[gap]])
    w = weights[gap]
    xy = cand[["x", "y"]].to_numpy()
    r = site_km * 1000
    gains = np.zeros(len(xy))
    for s in range(0, len(xy), 20000):
        gains[s:s + 20000] = [w[l].sum() for l in tree.query_ball_point(xy[s:s + 20000], r)]
    heap = [(-gv, i) for i, gv in enumerate(gains) if gv > 0]
    heapq.heapify(heap)
    covered = np.zeros(len(gap), dtype=bool)
    chosen = []
    while heap and len(chosen) < n_sites:
        _, i = heapq.heappop(heap)
        cells = np.asarray(tree.query_ball_point(xy[i], r), dtype=int)
        cells = cells[~covered[cells]]
        gain = w[cells].sum()
        if gain <= 0:
            continue
        if heap and gain < -heap[0][0]:
            heapq.heappush(heap, (-gain, i))
            continue
        covered[cells] = True
        chosen.append((i, gap[cells]))
    return chosen


def run(serve_km=C.SERVE_RADIUS_KM, min_tests=C.MIN_TESTS, site_km=C.SITE_RADIUS_KM, n_sites=C.MAX_SITES,
        hosts=HOSTS):
    cls = triage(serve_km, min_tests)
    w_all = np.where(cls == 3, cpop, 0.0)
    w_poor = np.where((cls == 3) & cpoor, cpop, 0.0)
    out = {}
    for h in hosts:
        for name, w in [("efficiency", w_all), ("equity", w_poor)]:
            rows, ca, cp = [], 0.0, 0.0
            for rank, (i, cells) in enumerate(greedy(CAND[h], w_all, w, site_km, n_sites), start=1):
                ga, gp = w_all[cells].sum(), w_poor[cells].sum()
                ca += ga; cp += gp
                rows.append(dict(rank=rank, cand=i, people_reached=round(ga), poorer_reached=round(gp),
                                 cum_people=round(ca), cum_poorer=round(cp)))
            out[(h, name)] = pd.DataFrame(rows)
    return cls, w_all, w_poor, out


cls, w_all, w_poor, res = run()
U_ALL, U_POOR = w_all.sum(), w_poor.sum()
cls_grid = np.full((nrow, ncol), -1, dtype=np.int8)
cls_grid[valid] = cls
np.savez_compressed(C.PROCESSED / "triage.npz", cls=cls_grid, rwi_cut=RWI_CUT)

# ----------------------------------------------------------------- site tables
COLS = ["host", "name", "kind", "lga", "state", "lon", "lat", "hosts_in_cell"]
for (h, name), df in res.items():
    df = pd.concat([df, CAND[h].iloc[df["cand"]][COLS].reset_index(drop=True)], axis=1)
    df["share_of_coverage_gap"] = (100 * df["cum_people"] / U_ALL).round(2)
    res[(h, name)] = df
    out = df.drop(columns="cand")
    out.to_csv(C.TABLES / f"sites_{h}_{name}.csv", index=False)
    if h == "both":                                   # the default, read by the maps, tool and report
        out.to_csv(C.TABLES / f"sites_{name}.csv", index=False)

budgets, by_host = [], []
for n in C.BUDGETS:
    e, q = res[("both", "efficiency")].iloc[n - 1], res[("both", "equity")].iloc[n - 1]
    budgets.append(dict(sites=n, eff_people=e["cum_people"], eff_poorer=e["cum_poorer"], eq_people=q["cum_people"],
                        eq_poorer=q["cum_poorer"], eff_share=round(100 * e["cum_people"] / U_ALL, 2),
                        eq_share=round(100 * q["cum_people"] / U_ALL, 2),
                        people_given_up_for_equity=e["cum_people"] - q["cum_people"],
                        poorer_gained_by_equity=q["cum_poorer"] - e["cum_poorer"],
                        sites_at_schools=int((res[("both", "efficiency")]["host"].iloc[:n] == "school").sum())))
    for h in HOSTS:
        for name in OBJECTIVES:
            d = res[(h, name)].iloc[n - 1]
            by_host.append(dict(sites=n, hosts=h, objective=name, people=d["cum_people"], poorer=d["cum_poorer"]))
budgets = pd.DataFrame(budgets)
assert (budgets["eq_people"] > budgets["eq_poorer"]).all(), "equity run counts only poorer people: coverage bug"
budgets.to_csv(C.TABLES / "budgets.csv", index=False)
by_host = pd.DataFrame(by_host)
by_host.to_csv(C.TABLES / "budgets_by_host.csv", index=False)

# ----------------------------------------------------------------- LGA triage table
L = pd.DataFrame({"lga_idx": clga, "pop": cpop, **{c: np.where(cls == k, cpop, 0.0) for k, c in enumerate(CLASSES)},
                  "coverage_poorer": w_poor})
L = L[L["lga_idx"] >= 0].groupby("lga_idx").sum()
pts = tiles.set_geometry(gpd.points_from_xy(tiles["x"], tiles["y"]), crs=tiles.crs)
tj = gpd.sjoin(pts[["tests", "avg_d_kbps", "geometry"]], adm2[["geometry"]], predicate="within")
tj["dxt"] = tj["avg_d_kbps"] * tj["tests"]
T = tj.groupby("index_right").agg(tiles=("tests", "size"), tests=("tests", "sum"), dxt=("dxt", "sum"))
L = L.join(T, how="left").fillna({"tiles": 0, "tests": 0, "dxt": 0})
L["mean_down_mbps"] = np.where(L["tests"] > 0, L["dxt"] / L["tests"] / 1000, np.nan)
L["tests_per_10k"] = 1e4 * L["tests"] / L["pop"]
for c in CLASSES:
    L[f"pct_{c}"] = 100 * L[c] / L["pop"]
cell_lga = np.full((nrow, ncol), -1, dtype=int)
cell_lga[valid] = clga
for name in OBJECTIVES:
    s = res[("both", name)].iloc[:100]
    rc = CAND["both"].iloc[s["cand"]][["r", "c"]].to_numpy()
    ok = (rc[:, 0] >= 0) & (rc[:, 0] < nrow) & (rc[:, 1] >= 0) & (rc[:, 1] < ncol)
    picked = pd.Series(lga[rc[ok, 0], rc[ok, 1]])
    L[f"sites100_{name}"] = picked[picked >= 0].value_counts().reindex(L.index).fillna(0).astype(int)
L["dominant_need"] = L[CLASSES].idxmax(axis=1)
L = adm2[["state", "lga", "lga_pcode"]].join(L.drop(columns="dxt"), how="right")
L.round(2).to_csv(C.TABLES / "lga_summary.csv", index_label="lga_idx")

# ----------------------------------------------------------------- facts for the insights
def host_classes(df):
    return cls[cell_tree.query(df[["x", "y"]].to_numpy())[1]]


fac_cls, sch_cls = host_classes(clinics), host_classes(schools)
lga_no_tiles = L[L["tiles"] == 0]
P = cpop.sum()
H = {
    "ookla_release": "Speedtest by Ookla, mobile, Q4 2024 (identified by exact match, scripts/02)",
    "population_m": round(P / 1e6, 2),
    "people_by_class_m": {c: round(cpop[cls == k].sum() / 1e6, 2) for k, c in enumerate(CLASSES)},
    "people_by_class_pct": {c: round(100 * cpop[cls == k].sum() / P, 1) for k, c in enumerate(CLASSES)},
    "urban_pop_m": round(cpop[curban].sum() / 1e6, 2), "rural_pop_m": round(cpop[~curban].sum() / 1e6, 2),
    "served_urban_pct": round(100 * cpop[curban & (cls == 0)].sum() / cpop[curban].sum(), 1),
    "served_rural_pct": round(100 * cpop[~curban & (cls == 0)].sum() / cpop[~curban].sum(), 1),
    "coverage_gap_poorer_m": round(U_POOR / 1e6, 2),
    "coverage_gap_poorer_pct": round(100 * U_POOR / U_ALL, 1), "rwi_cut_poorer40": round(RWI_CUT, 3),
    "tiles": int(len(tiles)), "tiles_urban_pct": round(100 * tiles["urban"].mean(), 1),
    "tiles_meeting_plan_pct": round(100 * tiles["meets_plan"].mean(), 1), "tests": int(tiles["tests"].sum()),
    "tests_per_10k_urban": round(1e4 * tiles.loc[tiles["urban"], "tests"].sum() / cpop[curban].sum(), 2),
    "tests_per_10k_rural": round(1e4 * tiles.loc[~tiles["urban"], "tests"].sum() / cpop[~curban].sum(), 2),
    "people_no_tile_within_10km_m": round(cpop[d_any > 10].sum() / 1e6, 2),
    "lgas_with_no_tile": int(len(lga_no_tiles)), "lgas_total": int(len(L)),
    "pop_in_lgas_with_no_tile_m": round(lga_no_tiles["pop"].sum() / 1e6, 2),
    "facilities": int(len(clinics)), "schools": int(len(schools)),
    "schools_raw": int(len(gpd.read_file(f"zip://{C.SCHOOLS_ZIP}!/{C.SCHOOLS_LAYER}", ignore_geometry=True))),
    "candidate_cells": {h: int(len(CAND[h])) for h in HOSTS},
    "facilities_by_class": {c: int((fac_cls == k).sum()) for k, c in enumerate(CLASSES)},
    "schools_by_class": {c: int((sch_cls == k).sum()) for k, c in enumerate(CLASSES)},
    "budgets": budgets.to_dict("records"),
    "by_host_100": by_host[by_host["sites"] == 100].to_dict("records"),
    "params": {k: getattr(C, k) for k in ["URBAN_MIN_KBPS", "RURAL_MIN_KBPS", "MIN_TESTS", "SERVE_RADIUS_KM",
                                           "SITE_RADIUS_KM", "POORER_SHARE"]},
}

# ----------------------------------------------------------------- speeds where people do test
# Tile values are averages over their tests, so national figures weight each tile by its tests (Ookla's advice).
for lab, m in [("urban", tiles["urban"].to_numpy()), ("rural", ~tiles["urban"].to_numpy())]:
    t = tiles[m]
    H[f"tiles_{lab}"] = int(m.sum())
    H[f"down_mbps_{lab}"] = round(float(np.average(t["avg_d_kbps"], weights=t["tests"])) / 1000, 1)
    H[f"latency_ms_{lab}"] = round(float(np.average(t["avg_lat_ms"], weights=t["tests"])), 1)
    H[f"tiles_meeting_plan_pct_{lab}"] = round(100 * t["meets_plan"].mean(), 1)

# ----------------------------------------------------------------- why the top LGAs get few sites
# The LGAs with the most poorer rural people and no test are large and thinly settled, so even their best host
# reaches fewer people than the sites the search picks elsewhere. Gains use the same 5 km reach as greedy().
SITE_M = C.SITE_RADIUS_KM * 1000
gapc = cls == CLASSES.index("coverage")
cand = CAND["both"]
cand_xy = cand[["x", "y"]].to_numpy()
cr_, cc_ = cand["r"].to_numpy(), cand["c"].to_numpy()
inside = (cr_ >= 0) & (cr_ < nrow) & (cc_ >= 0) & (cc_ < ncol)
cand_lga = np.full(len(cand), -1)
cand_lga[inside] = lga[cr_[inside], cc_[inside]]
eq100 = res[("both", "equity")].iloc[:100]
under = np.unique(np.concatenate(cell_tree.query_ball_point(cand_xy[eq100["cand"].to_numpy()], SITE_M)).astype(int))
under = under[gapc[under]]
H["priority_lgas"] = []
for i, r in L.nlargest(5, "coverage_poorer").iterrows():
    in_lga = gapc & (clga == i)
    best = max((w_poor[n].sum() for n in cell_tree.query_ball_point(cand_xy[cand_lga == i], SITE_M)), default=0.0)
    H["priority_lgas"].append(dict(lga=r["lga"], state=r["state"], poorer_per_km2=int(round(w_poor[in_lga].sum() / in_lga.sum())),
                                   best_site_poorer=int(round(best)), sites100_equity=int(r["sites100_equity"])))
H["poorer_per_km2_under_eq100"] = int(round(w_poor[under].sum() / len(under)))
H["poorer_per_km2_gap_national"] = int(round(w_poor[gapc].sum() / gapc.sum()))
H["eq_site100_poorer"] = int(eq100["poorer_reached"].iloc[-1])
H["eq100_sites_at_schools"] = int((res[("both", "equity")]["host"].iloc[:100] == "school").sum())
H["eq100_multi_host_cells"] = int((res[("both", "equity")]["hosts_in_cell"].iloc[:100] >= 2).sum())

# ----------------------------------------------------------------- all-year check (scripts/02b)
# Rural gaps are set from October to December 2024. Tiles from January to September show whether the absence of
# tests lasts all year or is one quarter's chance. A rural-gap cell has no Q4 tile within reach by definition.
yr = pd.concat([pd.read_parquet(f) for f in C.OOKLA_2024_OTHER], ignore_index=True)
yr_xy = gpd.GeoSeries(gpd.points_from_xy(yr["tile_x"], yr["tile_y"]), crs=C.CRS_WGS84).to_crs(C.CRS_EQUAL_AREA)
never = cKDTree(np.c_[yr_xy.x, yr_xy.y]).query(np.c_[cx, cy])[0] / 1000 > C.SERVE_RADIUS_KM
H["allyear_gap_untested_pct"] = round(100 * cpop[gapc & never].sum() / cpop[gapc].sum(), 1)
H["allyear_gap_untested_m"] = round(cpop[gapc & never].sum() / 1e6, 1)
H["allyear_gap_poorer_untested_pct"] = round(100 * w_poor[never].sum() / w_poor.sum(), 1)
H["allyear_eq100_untested_pct"] = round(100 * cpop[under][never[under]].sum() / cpop[under].sum(), 1)
H["dsn_tiles_identical"] = int(pd.read_csv(C.TABLES / "ookla_all_year.csv")["dsn_tiles_identical"].max())

# ----------------------------------------------------------------- sensitivity (default hosts: clinics and schools)
sens = []
for label, ov in C.SENSITIVITY:
    c_, wa, wp, r = run(serve_km=ov.get("SERVE_RADIUS_KM", C.SERVE_RADIUS_KM), min_tests=ov.get("MIN_TESTS", C.MIN_TESTS),
                        site_km=ov.get("SITE_RADIUS_KM", C.SITE_RADIUS_KM), n_sites=100, hosts=["both"])
    e, q = r[("both", "efficiency")], r[("both", "equity")]
    sens.append(dict(setting=label, coverage_gap_m=round(wa.sum() / 1e6, 2),
                     **{f"{c}_m": round(cpop[c_ == k].sum() / 1e6, 2) for k, c in enumerate(CLASSES[:3])},
                     reached_50_m=round(e["cum_people"].iloc[49] / 1e6, 2),
                     reached_100_m=round(e["cum_people"].iloc[99] / 1e6, 2),
                     equity_cost_100_m=round((e["cum_people"].iloc[99] - q["cum_people"].iloc[99]) / 1e6, 2),
                     equity_gain_poorer_100_m=round((q["cum_poorer"].iloc[99] - e["cum_poorer"].iloc[99]) / 1e6, 2)))
    print(sens[-1], flush=True)
sens = pd.DataFrame(sens)
sens.to_csv(C.TABLES / "sensitivity.csv", index=False)
H["sensitivity"] = sens.to_dict("records")
json.dump(H, open(C.TABLES / "headline.json", "w"), indent=2, default=float)
print(json.dumps({k: v for k, v in H.items() if k not in ("budgets", "sensitivity", "by_host_100")}, indent=1, default=float))
print(budgets.to_string(index=False))
print(by_host[by_host["sites"] == 100].to_string(index=False))
for (h, name), df in res.items():
    if h == "both":
        print(f"\n{h} / {name}: first 6 sites")
        print(df.head(6)[["rank", "host", "name", "kind", "lga", "state", "people_reached", "hosts_in_cell"]].to_string(index=False))
