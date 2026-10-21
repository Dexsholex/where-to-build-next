"""
02 - Identify which Ookla release DSN supplied (fixed or mobile, which quarter).

DSN's file says neither. Ookla publishes every quarter, for fixed and mobile, as Parquet files in a public
AWS bucket (ookla-open-data, no account). This script takes a sample of DSN's tiles and looks for an exact
match (same quadkey, same average download, upload, latency, tests and devices) in each candidate release,
reading only what it needs. The match, and the rows compared, are written to outputs/tables/ookla_release.csv.
"""
import sys

import geopandas as gpd
import pandas as pd
import pyarrow.dataset as ds
import pyarrow.fs as pafs

from config import OOKLA_GPKG, OOKLA_LAYER, TABLES

s3 = pafs.S3FileSystem(anonymous=True, region="us-west-2")
BASE = "ookla-open-data/parquet/performance"
COLS = ["quadkey", "avg_d_kbps", "avg_u_kbps", "avg_lat_ms", "tests", "devices"]

dsn = gpd.read_file(OOKLA_GPKG, layer=OOKLA_LAYER)
# sample the busiest tiles: their values are distinctive, so a match cannot be a coincidence
sample = dsn.nlargest(8, "tests")[COLS].astype({"quadkey": str}).reset_index(drop=True)
keys = sample["quadkey"].tolist()

candidates = []
for typ in ["mobile", "fixed"]:
    years = [i.base_name for i in s3.get_file_info(pafs.FileSelector(f"{BASE}/type={typ}"))]
    for y in sorted(years, reverse=True):
        for q in sorted([i.base_name for i in s3.get_file_info(pafs.FileSelector(f"{BASE}/type={typ}/{y}"))],
                        reverse=True):
            for f in s3.get_file_info(pafs.FileSelector(f"{BASE}/type={typ}/{y}/{q}")):
                if f.path.endswith(".parquet"):
                    candidates.append((typ, y, q, f.path))
print(f"{len(candidates)} candidate releases; newest: {candidates[0][1:3]}")

limit = int(sys.argv[1]) if len(sys.argv) > 1 else 12          # newest N quarters per type
found = []
for typ in ["mobile", "fixed"]:
    for typ_, y, q, path in [c for c in candidates if c[0] == typ][:limit]:
        t = ds.dataset(path, filesystem=s3, format="parquet").to_table(
            columns=COLS, filter=ds.field("quadkey").isin(keys)).to_pandas()
        m = sample.merge(t, on="quadkey", suffixes=("_dsn", "_ookla"))
        exact = sum(all(r[f"{c}_dsn"] == r[f"{c}_ookla"] for c in COLS[1:]) for _, r in m.iterrows())
        print(f"{typ:6s} {y} {q}: {len(m)}/{len(keys)} quadkeys present, {exact} exact matches", flush=True)
        if exact == len(keys):
            found.append((typ, y, q, path))
            m.assign(release=f"{typ} {y} {q}", path=path).to_csv(TABLES / "ookla_release.csv", index=False)
            break
    if found:
        break
print("MATCH:", found if found else "none in the quarters searched")
