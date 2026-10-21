"""
02b - The rest of 2024, for the all-year check.

The four needs are set from DSN's tiles for October to December 2024. One quarter with no test nearby could be
chance, so this step fetches Ookla's mobile tiles for January to September 2024 from the same public bucket
(ookla-open-data, no account) and keeps those that touch Nigeria, the rule that reproduces DSN's selection.
It also fetches October to December itself and compares it with DSN's file tile by tile.

Every Nigerian tile's quadkey starts with 1222 (Nigeria lies inside that zoom-4 tile), so only that slice of
each file is read. Outputs, small enough to ship with the code:
  data/input/ookla_mobile_2024q{1,2,3}_nigeria.parquet
  outputs/tables/ookla_all_year.csv      tiles and tests per quarter, and the Q4 comparison with DSN's file
"""
import geopandas as gpd
import pandas as pd
import pyarrow.dataset as ds
import pyarrow.fs as pafs
import shapely

import config as C

s3 = pafs.S3FileSystem(anonymous=True, region="us-west-2", connect_timeout=30, request_timeout=120)
BASE = "ookla-open-data/parquet/performance/type=mobile/year=2024"
FILES = {1: "2024-01-01", 2: "2024-04-01", 3: "2024-07-01", 4: "2024-10-01"}
KEEP = ["quadkey", "tile_x", "tile_y", "avg_d_kbps", "avg_u_kbps", "avg_lat_ms", "tests", "devices"]
VALUES = ["avg_d_kbps", "avg_u_kbps", "avg_lat_ms", "tests", "devices"]

nga = gpd.read_file(C.ADMIN0).to_crs(C.CRS_WGS84).union_all()
dsn = gpd.read_file(C.OOKLA_GPKG, layer=C.OOKLA_LAYER).astype({"quadkey": str})
rows = []
for q, day in FILES.items():
    path = f"{BASE}/quarter={q}/{day}_performance_mobile_tiles.parquet"
    t = ds.dataset(path, filesystem=s3, format="parquet").to_table(
        filter=(ds.field("quadkey") >= "1222") & (ds.field("quadkey") < "1223")).to_pandas()
    full = t[KEEP]
    t = t[shapely.intersects(shapely.from_wkt(t["tile"].to_numpy()), nga)][KEEP].reset_index(drop=True)
    row = dict(quarter=f"2024 Q{q}", source=f"s3://{path}", tiles=len(t), tests=int(t["tests"].sum()))
    if q == 4:
        m = dsn.merge(full, on="quadkey", suffixes=("_dsn", "_ookla"))   # every DSN tile, wherever it sits
        same = (m[[f"{c}_dsn" for c in VALUES]].to_numpy() == m[[f"{c}_ookla" for c in VALUES]].to_numpy()).all(axis=1)
        row.update(dsn_tiles=len(dsn), dsn_tiles_identical=int(same.sum()),
                   rule_extra=len(set(t["quadkey"]) - set(dsn["quadkey"])),
                   rule_missing=len(set(dsn["quadkey"]) - set(t["quadkey"])))
    else:
        t.to_parquet(C.INPUT / f"ookla_mobile_2024q{q}_nigeria.parquet", index=False)
    rows.append(row)
    print(row, flush=True)
pd.DataFrame(rows).to_csv(C.TABLES / "ookla_all_year.csv", index=False)
