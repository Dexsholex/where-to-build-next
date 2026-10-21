"""
03 - A 1 km equal-area grid over Nigeria carrying everything the siting needs.

For each 1 km cell:
  pop        people (Meta population CSV, summed from ~31 m pixels whose centres fall in the cell)
  smod       GHSL degree-of-urbanisation class at the cell centre; urban = classes 21-30
  rwi        Meta Relative Wealth Index of the nearest wealth tile within 3 km (none if further)
  lga        index into admin2 (OCHA), by the cell centre
  d_ok_km    distance to the nearest Ookla tile that meets the National Broadband Plan speed for its
             own setting (25 Mbps urban, 10 Mbps rural) and has at least MIN_TESTS tests
  d_any_km   distance to the nearest Ookla tile of any speed (is there any evidence at all?)

The Ookla tiles keep their own threshold class, read from GHSL at the tile centre, and are saved
with that flag for the maps and the dashboard.
"""
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import shapely
from pyproj import Transformer
from rasterio.features import rasterize
from rasterio.transform import from_origin
from scipy.spatial import cKDTree

from config import (ADMIN0, ADMIN2, CELL_M, CRS_EQUAL_AREA, CRS_WGS84, MIN_TESTS, OOKLA_GPKG, OOKLA_LAYER,
                    POP_CSV_ZIP, POP_PIXEL_MAX, PROCESSED, RURAL_MIN_KBPS, RWI_CSV, SMOD_URBAN, SMOD_ZIP, URBAN_MIN_KBPS)

# ----------------------------------------------------------------- grid
nga_ea = gpd.read_file(ADMIN0).to_crs(CRS_EQUAL_AREA)
minx, miny, maxx, maxy = nga_ea.total_bounds
x0, y1 = np.floor(minx / CELL_M) * CELL_M, np.ceil(maxy / CELL_M) * CELL_M
ncol, nrow = int(np.ceil((maxx - x0) / CELL_M)), int(np.ceil((y1 - miny) / CELL_M))
transform = from_origin(x0, y1, CELL_M, CELL_M)
cx = x0 + (np.arange(ncol) + 0.5) * CELL_M
cy = y1 - (np.arange(nrow) + 0.5) * CELL_M
XX, YY = np.meshgrid(cx, cy)
inside = rasterize([(g, 1) for g in nga_ea.geometry], out_shape=(nrow, ncol), transform=transform, fill=0) == 1
print(f"grid {nrow} x {ncol}, {inside.sum():,} cells inside Nigeria")

# ----------------------------------------------------------------- population
nga_ll = gpd.read_file(ADMIN0).to_crs(CRS_WGS84).geometry.union_all()
shapely.prepare(nga_ll)
to_ea = Transformer.from_crs(CRS_WGS84, CRS_EQUAL_AREA, always_xy=True)
pop = np.zeros((nrow, ncol))
n_pix = 0
n_bad, pop_bad = 0, 0.0
for ch in pd.read_csv(POP_CSV_ZIP, chunksize=3_000_000):
    lon, lat = ch["longitude"].to_numpy(), ch["latitude"].to_numpy()
    v = pd.to_numeric(ch[ch.columns[2]], errors="coerce").to_numpy()
    keep = shapely.contains_xy(nga_ll, lon, lat) & np.isfinite(v)
    bad = keep & (v > POP_PIXEL_MAX)                      # artefact pixels, see config
    n_bad += int(bad.sum()); pop_bad += float(v[bad].sum())
    keep &= ~bad
    X, Y = to_ea.transform(lon[keep], lat[keep])
    c = np.floor((X - x0) / CELL_M).astype(int)
    r = np.floor((y1 - Y) / CELL_M).astype(int)
    ok = (r >= 0) & (r < nrow) & (c >= 0) & (c < ncol)
    np.add.at(pop, (r[ok], c[ok]), v[keep][ok])
    n_pix += int(keep.sum())
print(f"population {pop.sum() / 1e6:.2f} M from {n_pix:,} pixels; excluded {n_bad} artefact pixels ({pop_bad:,.0f} people)")

# ----------------------------------------------------------------- GHSL settlement class
tif = "zip://" + str(SMOD_ZIP).replace("\\", "/") + "!/GHS_SMOD_E2020_GLOBE_R2023A_54009_1000_V2_0.tif"
with rasterio.open(tif) as src:
    to_moll = Transformer.from_crs(CRS_EQUAL_AREA, src.crs, always_xy=True)
    # read Nigeria's window once (with a margin) and keep it in memory
    mx, my = to_moll.transform(XX[inside], YY[inside])
    rr, cc = (np.asarray(a) for a in rasterio.transform.rowcol(src.transform, mx, my))
    r0, c0 = rr.min() - 5, cc.min() - 5
    win = rasterio.windows.Window(c0, r0, cc.max() - c0 + 6, rr.max() - r0 + 6)
    smod_band, smod_tf = src.read(1, window=win), src.window_transform(win)


def smod_at(x, y):
    mx_, my_ = to_moll.transform(np.asarray(x), np.asarray(y))
    r_, c_ = (np.asarray(a) for a in rasterio.transform.rowcol(smod_tf, mx_, my_))
    return smod_band[r_, c_]


smod = np.zeros((nrow, ncol), dtype=np.int16)
smod[inside] = smod_at(XX[inside], YY[inside])
urban = np.isin(smod, list(SMOD_URBAN))

# ----------------------------------------------------------------- wealth
rwi = pd.read_csv(RWI_CSV)
rx, ry = to_ea.transform(rwi["longitude"].to_numpy(), rwi["latitude"].to_numpy())
dist, idx = cKDTree(np.c_[rx, ry]).query(np.c_[XX[inside], YY[inside]], distance_upper_bound=3000)
rwi_grid = np.full((nrow, ncol), np.nan)
vals = np.full(inside.sum(), np.nan)
hit = np.isfinite(dist)
vals[hit] = rwi["rwi"].to_numpy()[idx[hit]]
rwi_grid[inside] = vals

# ----------------------------------------------------------------- LGAs
adm2 = gpd.read_file(ADMIN2).to_crs(CRS_EQUAL_AREA).reset_index(drop=True)
lga = rasterize([(g, i + 1) for i, g in enumerate(adm2.geometry)], out_shape=(nrow, ncol), transform=transform,
                fill=0, dtype="int32") - 1                                        # -1 = no LGA

# ----------------------------------------------------------------- Ookla tiles
tiles = gpd.read_file(OOKLA_GPKG, layer=OOKLA_LAYER).to_crs(CRS_EQUAL_AREA)
tc = tiles.geometry.centroid
tiles["x"], tiles["y"] = tc.x.to_numpy(), tc.y.to_numpy()
tiles["smod"] = smod_at(tiles["x"], tiles["y"])
tiles["urban"] = tiles["smod"].isin(SMOD_URBAN)
tiles["min_kbps"] = np.where(tiles["urban"], URBAN_MIN_KBPS, RURAL_MIN_KBPS)
tiles["meets_plan"] = tiles["avg_d_kbps"] >= tiles["min_kbps"]


def nearest_km(mask):
    t = tiles[mask]
    d, _ = cKDTree(np.c_[t["x"], t["y"]]).query(np.c_[XX[inside], YY[inside]])
    out = np.full((nrow, ncol), np.nan)
    out[inside] = d / 1000
    return out


d_ok = nearest_km(tiles["meets_plan"] & (tiles["tests"] >= MIN_TESTS))
d_any = nearest_km(tiles["tests"] >= 1)

np.savez_compressed(PROCESSED / "grid.npz", x0=x0, y1=y1, cell=CELL_M, nrow=nrow, ncol=ncol, inside=inside, pop=pop,
                    smod=smod, urban=urban, rwi=rwi_grid, lga=lga, d_ok_km=d_ok, d_any_km=d_any,
                    excluded_pixels=n_bad, excluded_people=pop_bad)
tiles.drop(columns=["tile"]).to_file(PROCESSED / "ookla_tiles.gpkg", driver="GPKG")
adm2.to_file(PROCESSED / "admin2.gpkg", driver="GPKG")
print(f"Ookla tiles: {len(tiles):,}; urban {tiles['urban'].mean():.0%}; meeting the plan's speed {tiles['meets_plan'].mean():.0%}")
print(f"people with a qualifying tile within 2 km: {pop[(d_ok <= 2) & inside].sum() / 1e6:.1f} M of {pop.sum() / 1e6:.1f} M")
print(f"people with wealth data: {100 * pop[np.isfinite(rwi_grid)].sum() / pop.sum():.1f}%")
