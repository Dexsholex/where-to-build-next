"""
06 - The interactive tool: one self-contained HTML page, written to outputs/dashboard/ and to index.html at the
repository root (served by GitHub Pages at https://dexsholex.github.io/where-to-build-next/).

Everything ships inside the page: the triage layer as a PNG data URI, simplified LGA and state outlines,
the Ookla tiles, both ranked site lists, and the headline numbers. Leaflet's script loads from cdnjs;
its stylesheet is inlined (assets/leaflet-1.9.4.css, BSD-2-Clause) because the viewer only allows
stylesheets from Google Fonts.
"""
import base64
import json

import geopandas as gpd
import numpy as np
import pandas as pd

import config as C

OUT = C.ROOT / "outputs" / "dashboard"
OUT.mkdir(parents=True, exist_ok=True)
H = json.load(open(C.TABLES / "headline.json"))
bounds = json.load(open(C.PROCESSED / "triage_webmap_bounds.json"))
png = base64.b64encode((C.PROCESSED / "triage_webmap.png").read_bytes()).decode()

lga = pd.read_csv(C.TABLES / "lga_summary.csv")
# lga_idx in our tables is the row position in admin2 (see 03 and 04); drop the inherited column of that name
adm2 = (gpd.read_file(C.PROCESSED / "admin2.gpkg").drop(columns=["lga_idx"], errors="ignore")
        .reset_index().rename(columns={"index": "lga_idx"}))
g2 = adm2[["lga_idx", "geometry"]].merge(lga, on="lga_idx")
g2["geometry"] = g2.geometry.simplify(400)
g2 = g2.to_crs(C.CRS_WGS84)
props = pd.DataFrame({
    "n": g2["lga"], "s": g2["state"], "p": (g2["pop"] / 1e3).round(0).astype(int),
    "sv": g2["pct_served"].round(0), "cp": g2["pct_capacity"].round(0), "ms": g2["pct_measure"].round(0),
    "cv": g2["pct_coverage"].round(0), "d": g2["dominant_need"], "t": g2["tests"].astype(int),
    "sp": g2["mean_down_mbps"].round(1), "x": g2["sites100_efficiency"], "q": g2["sites100_equity"],
    "gp": (g2["coverage_poorer"] / 1e3).round(1), "m": (g2["measure"] / 1e3).round(1),
    "c": (g2["capacity"] / 1e3).round(1)})
lga_geo = json.loads(gpd.GeoDataFrame(props, geometry=g2.geometry).to_json(drop_id=True))
adm1 = gpd.read_file(C.ADMIN1).to_crs(C.CRS_EQUAL_AREA)
adm1["geometry"] = adm1.geometry.simplify(1500)
states_geo = json.loads(adm1[["state", "geometry"]].to_crs(C.CRS_WGS84).to_json(drop_id=True))


def round_geo(obj, nd=4):
    if isinstance(obj, float):
        return round(obj, nd)
    if isinstance(obj, list):
        return [round_geo(v, nd) for v in obj]
    if isinstance(obj, dict):
        return {k: round_geo(v, nd) for k, v in obj.items()}
    return obj


lga_geo, states_geo = round_geo(lga_geo), round_geo(states_geo)
tiles = gpd.read_file(C.PROCESSED / "ookla_tiles.gpkg")                     # equal-area CRS
tc = gpd.GeoSeries(gpd.points_from_xy(tiles["x"], tiles["y"]), crs=tiles.crs).to_crs(C.CRS_WGS84)
tile_rows = np.c_[tc.y.round(4), tc.x.round(4), (tiles["avg_d_kbps"] / 1000).round(1), tiles["tests"],
                  tiles["meets_plan"].astype(int)].tolist()


def site_rows(hosts, name):
    s = pd.read_csv(C.TABLES / f"sites_{hosts}_{name}.csv")
    return [[int(r["rank"]), str(r["name"]), str(r["kind"]), r["lga"], r["state"], r["lat"], r["lon"],
             int(r["people_reached"]), int(r["poorer_reached"]), int(r["cum_people"]), int(r["cum_poorer"]),
             r["host"], int(r["hosts_in_cell"])] for _, r in s.iterrows()]


DATA = {"bounds": bounds, "lgas": lga_geo, "states": states_geo, "tiles": tile_rows,
        "sites": {h: {o: site_rows(h, o) for o in ["efficiency", "equity"]} for h in ["both", "clinics", "schools"]},
        "h": {k: H[k] for k in ["population_m", "people_by_class_m", "people_by_class_pct", "tiles", "tests",
                                "tests_per_10k_urban", "tests_per_10k_rural", "lgas_with_no_tile",
                                "pop_in_lgas_with_no_tile_m", "facilities", "facilities_by_class",
                                "coverage_gap_poorer_pct", "down_mbps_urban", "down_mbps_rural", "tiles_rural", "allyear_gap_untested_pct"]},
        "gap_m": H["people_by_class_m"]["coverage"], "sens": H["sensitivity"],
        "excl": {"pixels": int(np.load(C.PROCESSED / "grid.npz")["excluded_pixels"]),
                 "people_m": round(float(np.load(C.PROCESSED / "grid.npz")["excluded_people"]) / 1e6, 2)}}
leaflet_css = (C.ROOT / "assets" / "leaflet-1.9.4.css").read_text(encoding="utf-8")
html = (C.ROOT / "scripts" / "dashboard_template.html").read_text(encoding="utf-8")
html = (html.replace("/*__LEAFLET_CSS__*/", leaflet_css)
            .replace("__TRIAGE_PNG__", png)
            .replace("/*__DATA__*/null", json.dumps(DATA, separators=(",", ":"), ensure_ascii=False)))
out = OUT / "where_to_build_next.html"
out.write_text(html, encoding="utf-8")
# the same page at the repository root, where GitHub Pages serves it
(C.ROOT / "index.html").write_text(html, encoding="utf-8")
print(f"saved {out} ({out.stat().st_size / 1e6:.2f} MB)")
