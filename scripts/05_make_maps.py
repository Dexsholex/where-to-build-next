"""
05 - Figures for the PDF, and the triage layer for the web map.

  fig_triage_map.png   every 1 km cell coloured by what it needs, with the first 100 sites chosen poorest first
                       (the order the report recommends), state borders and a few cities for orientation
  fig_reach.png        people reached as sites are added, efficiency against equity
  triage_webmap.png    the triage layer reprojected to Web Mercator for the dashboard, with its bounds

Palette (checked with the dataviz validator, all pairs, light surface: CVD dE >= 8.9, normal >= 20.2):
served #1B9E77, capacity #D98B1F, measure #4A78D0, coverage #A6266E. Amber is below 3:1 on white,
so every class is also named in the legend.
"""
import json

import geopandas as gpd
import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from matplotlib.colors import ListedColormap
from matplotlib.lines import Line2D
from PIL import Image
from rasterio.transform import from_origin
from rasterio.warp import Resampling, calculate_default_transform, reproject

import config as C

COLORS = ["#1B9E77", "#D98B1F", "#4A78D0", "#A6266E"]
LABELS = ["Served: broadband-speed test nearby", "Slow: tests nearby, below the plan's speed",
          "Measure first: town, no test within 2 km", "Rural gap: no test within 2 km"]
# Cities for orientation (lon, lat, state). Each point is checked against the OCHA state polygon below.
CITIES = [("Lagos", 3.39, 6.46, "Lagos"), ("Ibadan", 3.93, 7.38, "Oyo"), ("Abuja", 7.49, 9.06, "Federal Capital Territory"),
          ("Kano", 8.52, 12.00, "Kano"), ("Kaduna", 7.44, 10.52, "Kaduna"), ("Port Harcourt", 7.03, 4.82, "Rivers"),
          ("Enugu", 7.51, 6.45, "Enugu"), ("Maiduguri", 13.16, 11.85, "Borno"), ("Sokoto", 5.24, 13.06, "Sokoto")]
plt.rcParams["font.family"] = "DejaVu Sans"

H = json.load(open(C.TABLES / "headline.json"))
g = np.load(C.PROCESSED / "grid.npz")
cls = np.load(C.PROCESSED / "triage.npz")["cls"]
x0, y1, cell, nrow, ncol = float(g["x0"]), float(g["y1"]), float(g["cell"]), int(g["nrow"]), int(g["ncol"])
extent = [x0, x0 + ncol * cell, y1 - nrow * cell, y1]
adm1 = gpd.read_file(C.ADMIN1).to_crs(C.CRS_EQUAL_AREA)
nga = gpd.read_file(C.ADMIN0).to_crs(C.CRS_EQUAL_AREA)
eff = pd.read_csv(C.TABLES / "sites_efficiency.csv")
equ = pd.read_csv(C.TABLES / "sites_equity.csv")
budgets = pd.read_csv(C.TABLES / "budgets.csv")


def to_ea(df):
    return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs=C.CRS_WGS84).to_crs(
        C.CRS_EQUAL_AREA)


# ----------------------------------------------------------------- triage map
fig, ax = plt.subplots(figsize=(11, 9.2))
img = np.ma.masked_less(cls, 0)
ax.imshow(img, cmap=ListedColormap(COLORS), vmin=0, vmax=3, extent=extent, interpolation="nearest", zorder=1)
adm1.boundary.plot(ax=ax, color="#8c8c8c", linewidth=0.45, zorder=2)        # grey reads on colour and on white
nga.boundary.plot(ax=ax, color="#222222", linewidth=1.0, zorder=3)
s100 = to_ea(equ.head(100))
for host, mk in [("clinic", "o"), ("school", "s")]:
    s = s100[s100["host"] == host]
    ax.scatter(s.geometry.x, s.geometry.y, s=26, marker=mk, facecolor="white", edgecolor="#111111", linewidth=1.1,
               zorder=5)
s10 = s100.head(10)
ax.scatter(s10.geometry.x, s10.geometry.y, s=150, marker="*", facecolor="#FFD23F", edgecolor="#111111",
           linewidth=0.9, zorder=6)
city = gpd.GeoDataFrame({"name": [c[0] for c in CITIES], "state": [c[3] for c in CITIES]},
                        geometry=gpd.points_from_xy([c[1] for c in CITIES], [c[2] for c in CITIES]), crs=C.CRS_WGS84)
city = city.to_crs(C.CRS_EQUAL_AREA)
where = gpd.sjoin(city, adm1[["state", "geometry"]].rename(columns={"state": "in_state"}), predicate="within")
assert (where["state"] == where["in_state"]).all() and len(where) == len(city), "a city label falls outside its state"
ax.scatter(city.geometry.x, city.geometry.y, s=14, color="#111111", zorder=7)
for _, c in city.iterrows():
    ax.annotate(c["name"], (c.geometry.x, c.geometry.y), xytext=(4, 3), textcoords="offset points", fontsize=9.5,
                fontweight="bold", color="#111111", zorder=8, path_effects=[pe.withStroke(linewidth=2.6, foreground="white")])
ax.set_axis_off(); ax.set_aspect("equal")
pc = H["people_by_class_m"]
handles = [mpatches.Patch(facecolor=c, edgecolor="none",
                          label=f"{l}  ({pc[k]:.0f} M people)") for c, l, k in zip(COLORS, LABELS, pc)]
handles += [Line2D([], [], marker="o", ls="", markerfacecolor="white", markeredgecolor="#111111", markersize=7,
                   label="First 100 sites, poorest first: clinic"),
            Line2D([], [], marker="s", ls="", markerfacecolor="white", markeredgecolor="#111111", markersize=6.5,
                   label="First 100 sites, poorest first: school"),
            Line2D([], [], marker="*", ls="", markerfacecolor="#FFD23F", markeredgecolor="#111111", markersize=13,
                   label="First 10 sites (table on page 2)"),
            Line2D([], [], color="#8c8c8c", lw=1, label="State border")]
ax.legend(handles=handles, loc="lower right", fontsize=10.5, frameon=True, framealpha=0.95, edgecolor="#cccccc",
          title="What each 1 km of Nigeria needs", title_fontsize=11.5, alignment="left")
xmn, xmx = ax.get_xlim(); ymn, ymx = ax.get_ylim()
bx, by = xmn + 0.04 * (xmx - xmn), ymn + 0.05 * (ymx - ymn)
ax.plot([bx, bx + 200_000], [by, by], color="#222222", lw=3, solid_capstyle="butt")
ax.text(bx + 100_000, by + 12_000, "200 km", ha="center", va="bottom", fontsize=10)
ax.annotate("N", xy=(0.05, 0.93), xytext=(0.05, 0.86), xycoords="axes fraction", ha="center", fontsize=12,
            fontweight="bold", arrowprops=dict(arrowstyle="-|>", color="#222222", lw=1.6))
fig.text(0.01, 0.005, "Speedtest by Ookla, mobile, Q4 2024; Meta population 2020 and Relative Wealth Index; GHSL "
         "settlement classes 2020; GRID3 health and education facilities; OCHA boundaries. Speed benchmark: National Broadband Plan "
         "2020-2025 (25 Mbps urban, 10 Mbps rural). Albers equal-area. Analysis: Oluwasola Oyinloye.",
         fontsize=7, color="#555555", wrap=True)
fig.subplots_adjust(left=0.0, right=1.0, top=1.0, bottom=0.03)
fig.savefig(C.FIGS / "fig_triage_map.png", dpi=250, facecolor="white")
plt.close(fig)

# ----------------------------------------------------------------- reach curve
fig, ax = plt.subplots(figsize=(6.4, 3.6))
n = np.arange(1, len(eff) + 1)
ax.plot(n, eff["cum_people"] / 1e6, color="#222222", lw=2, label="Reach the most people: everyone reached")
ax.plot(n, eff["cum_poorer"] / 1e6, color="#222222", lw=2, ls=":", label="Reach the most people: poorer 40% reached")
ax.plot(n, equ["cum_people"] / 1e6, color="#A6266E", lw=2, label="Poorest first: everyone reached")
ax.plot(n, equ["cum_poorer"] / 1e6, color="#A6266E", lw=2, ls=":", label="Poorest first: poorer 40% reached")
b100 = budgets.set_index("sites").loc[100]
ax.axvline(100, color="#bbbbbb", lw=1, zorder=0)
ax.annotate(f"At 100 sites, poorest-first reaches\n{b100['poorer_gained_by_equity'] / 1e3:,.0f} thousand more poorer people\n"
            f"for {b100['people_given_up_for_equity'] / 1e3:,.0f} thousand fewer in total",
            xy=(100, b100["eq_poorer"] / 1e6), xytext=(108, 0.6), fontsize=8.5,
            arrowprops=dict(arrowstyle="-", color="#888888", lw=0.8))
ax.set_xlabel("Number of new sites (clinics and schools)", fontsize=9.5)
ax.set_ylabel("People reached (millions)", fontsize=9.5)
ax.grid(alpha=0.25); ax.spines[["top", "right"]].set_visible(False)
ax.legend(fontsize=7.6, frameon=False, loc="upper left")
ax.tick_params(labelsize=8.5)
fig.tight_layout()
fig.savefig(C.FIGS / "fig_reach.png", dpi=250, facecolor="white")
plt.close(fig)

# ----------------------------------------------------------------- web map layer
src_tf = from_origin(x0, y1, cell, cell)
dst_tf, w, h = calculate_default_transform(C.CRS_EQUAL_AREA, "EPSG:3857", ncol, nrow, *[extent[0], extent[2],
                                                                                        extent[1], extent[3]])
dst = np.full((h, w), -1, dtype=np.int8)
reproject(cls, dst, src_transform=src_tf, src_crs=C.CRS_EQUAL_AREA, dst_transform=dst_tf, dst_crs="EPSG:3857",
          resampling=Resampling.nearest, src_nodata=-1, dst_nodata=-1)
rgba = np.zeros((h, w, 4), dtype=np.uint8)
for k, c in enumerate(COLORS):
    rgba[dst == k] = [int(c[i:i + 2], 16) for i in (1, 3, 5)] + [215]
Image.fromarray(rgba).save(C.PROCESSED / "triage_webmap.png", optimize=True)
west, north = dst_tf * (0, 0)
east, south = dst_tf * (w, h)
from pyproj import Transformer  # noqa: E402

t = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
(lon0, lat0), (lon1, lat1) = t.transform(west, south), t.transform(east, north)
json.dump({"south": lat0, "west": lon0, "north": lat1, "east": lon1}, open(C.PROCESSED / "triage_webmap_bounds.json", "w"))
print("saved fig_triage_map.png, fig_reach.png, triage_webmap.png", (h, w))
