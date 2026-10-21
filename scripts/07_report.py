"""
07 - The two-page submission PDF (submission/DSN_Geospatial_WhereToBuildNext_OluwasolaOyinloye.pdf).

Page 1: the four needs, the map, the problem and the steps. Page 2: external datasets, insights with
recommendations, priority communities, the first ten sites, limitations and references. Every number is read from outputs/tables; none is typed in.
"""
import json

import pandas as pd
from fpdf import FPDF
from PIL import Image

import config as C

AUTHOR, EMAIL = "Oluwasola Oyinloye", "o.oyin1115@gmail.com"
TOOL_URL = "https://dexsholex.github.io/where-to-build-next/"
H = json.load(open(C.TABLES / "headline.json"))
B = pd.read_csv(C.TABLES / "budgets.csv").set_index("sites")
S = pd.DataFrame(H["sensitivity"]).set_index("setting")
import numpy as np  # noqa: E402
G = np.load(C.PROCESSED / "grid.npz")
pc, pp = H["people_by_class_m"], H["people_by_class_pct"]
b100 = B.loc[100]
fb = H["facilities_by_class"]
sb = H["schools_by_class"]
_bh = pd.read_csv(C.TABLES / "budgets_by_host.csv")
clin100 = int(_bh[(_bh["sites"] == 100) & (_bh["hosts"] == "clinics") & (_bh["objective"] == "efficiency")]["people"].iloc[0])
PL = pd.DataFrame(H["priority_lgas"])
thin_lgas = int((PL["best_site_poorer"] < H["eq_site100_poorer"]).sum())

INK, MUTED, ACCENT = (20, 32, 27), (86, 100, 94), (166, 38, 110)
COLORS = {"served": (27, 158, 119), "capacity": (217, 139, 31), "measure": (74, 120, 208), "coverage": (166, 38, 110)}
LM = 12
W = 210 - 2 * LM


def clean(s):
    for k, v in {"–": "-", "—": "-", "’": "'", "‘": "'", "“": '"', "”": '"', "≥": ">=", "…": "..."}.items():
        s = s.replace(k, v)
    return s.encode("latin-1", "replace").decode("latin-1")


class R(FPDF):
    def footer(self):
        self.set_y(-9); self.set_font("Helvetica", "", 7); self.set_text_color(*MUTED)
        self.cell(0, 4, clean(f"Where to Build Next  |  {AUTHOR}  |  page {self.page_no()} of 2"), align="R")

    def head(self, text, size=10.5):
        self.set_x(LM); self.set_font("Helvetica", "B", size); self.set_text_color(*ACCENT)
        self.multi_cell(W, 5.2, clean(text)); self.set_text_color(*INK)

    def para(self, text, size=8.6, lh=4.0, style=""):
        self.set_x(LM); self.set_font("Helvetica", style, size); self.set_text_color(*INK)
        self.multi_cell(W, lh, clean(text)); self.ln(0.6)

    def item(self, num, head, text, size=8.6, lh=4.0):
        y = self.get_y()
        self.set_xy(LM, y); self.set_font("Helvetica", "B", size); self.set_text_color(*ACCENT)
        self.cell(6, lh, str(num))
        self.set_xy(LM + 6, y); self.set_text_color(*INK); self.set_font("Helvetica", "", size)
        self.multi_cell(W - 6, lh, clean(f"**{head}** {text}"), markdown=True); self.ln(0.8)


pdf = R(format="A4"); pdf.set_auto_page_break(True, margin=11); pdf.set_margins(LM, 10, LM)
pdf.set_title("Where to Build Next"); pdf.set_author(AUTHOR)
pdf.set_subject("DSN AI Bootcamp 2026, Geospatial Track: Mapping Nigeria's Digital Divide")

# ================================================================= page 1
pdf.add_page()
pdf.set_font("Helvetica", "B", 23); pdf.set_text_color(*INK); pdf.set_x(LM)
pdf.cell(W, 10, "Where to Build Next", new_x="LMARGIN", new_y="NEXT")
pdf.set_font("Helvetica", "", 10.5); pdf.set_text_color(*MUTED)
pdf.multi_cell(W, 5, clean("Not every connectivity gap needs a tower. This siting tool sorts every square kilometre of "
                           "Nigeria by what it needs, then picks the clinics and schools that should host new sites."))
pdf.set_font("Helvetica", "", 8.2)
pdf.set_x(LM); pdf.cell(W, 4.5, clean(f"{AUTHOR}  |  {EMAIL}  |  DSN AI Bootcamp 2026, Geospatial Track: Mapping "
                                      "Nigeria's Digital Divide"), new_x="LMARGIN", new_y="NEXT")
pdf.set_font("Helvetica", "B", 8.6); pdf.set_text_color(*ACCENT); pdf.set_x(LM)
pdf.cell(W, 5, clean(f"Interactive tool: {TOOL_URL}"), link=TOOL_URL, new_x="LMARGIN", new_y="NEXT")
pdf.ln(1.5)

labels = {"served": "Served", "capacity": "Slow: upgrade", "measure": "Unmeasured town", "coverage": "Rural, no tests"}
bw, gap = (W - 3 * 3) / 4, 3
y0 = pdf.get_y()
for i, k in enumerate(["served", "capacity", "measure", "coverage"]):
    x = LM + i * (bw + gap)
    pdf.set_fill_color(*COLORS[k]); pdf.rect(x, y0, 2.2, 13, "F")
    pdf.set_xy(x + 4, y0 + 0.5); pdf.set_font("Helvetica", "B", 13); pdf.set_text_color(*INK)
    pdf.cell(bw - 4, 6, f"{pc[k]:.1f} M")
    pdf.set_xy(x + 4, y0 + 6.8); pdf.set_font("Helvetica", "", 7.6); pdf.set_text_color(*MUTED)
    pdf.cell(bw - 4, 4, clean(f"{labels[k]}, {pp[k]:.0f}% of people"))
pdf.set_y(y0 + 15.5)

img = C.FIGS / "fig_triage_map.png"
iw, ih = Image.open(img).size
wm = W - 14                                   # narrower so page 1 holds the steps
mh = wm * ih / iw
pdf.image(str(img), x=LM + 4, y=pdf.get_y(), w=wm, h=mh)
pdf.set_y(pdf.get_y() + mh + 1)
pdf.para(f"Figure 1. What each 1 km of Nigeria needs, from {H['tests']:,} Ookla mobile speed tests (Q4 2024) against the "
      "National Broadband Plan's speeds, with the first 100 sites (clinics and schools), chosen poorest first to close rural gaps.",
      size=7.6, lh=3.5, style="I")
pdf.head("The problem")
pdf.para(f"Nigeria's broadband plan set a 2025 target of 25 Mbps in urban areas and 10 Mbps in rural areas, with 4G for 90% of "
      f"people (FMoCDE 2020). In the Ookla data, only {H['served_rural_pct']}% of rural residents live within 2 km of a test at the plan's "
      f"speed, against {H['served_urban_pct']}% in towns. Where people do test, the average download is "
      f"{H['down_mbps_urban']} Mbps in towns and {H['down_mbps_rural']} Mbps in rural areas (weighted by tests; latency "
      f"{H['latency_ms_urban']:.0f} and {H['latency_ms_rural']:.0f} ms), but only {H['tiles_rural']:,} of the {H['tiles']:,} tiles are rural. "
      "The question this tool answers: which communities are poorly "
      "connected relative to their population, settlement and need, what does each place need, and where should the "
      "next sites go?")

pdf.head("Steps")
steps = [
    ("Identify the data.", f"DSN's file states neither type nor period. Matching tiles to Ookla's public release on AWS "
                          f"identified it exactly: mobile, Q4 2024 (all {H['dsn_tiles_identical']:,} tiles identical)."),
    ("Build a 1 km grid.", f"{H['population_m']:.1f} million people from Meta's 2020 population map, each cell tagged urban "
                           "or rural (GHSL), with a wealth score (Meta RWI) and its LGA (OCHA). "
                           f"{int(G['excluded_pixels'])} pixels where Meta's layer piles a census count onto a few "
                           f"buildings ({G['excluded_people'] / 1e6:.2f} million people) are excluded as unplaceable."),
    ("Sort every cell by need.", "Served: a test within 2 km meets the plan's speed for its setting. Slow: tests nearby, "
                                 "all too slow. Unmeasured town: urban, no test within 2 km. Rural gap: rural, "
                                 "no test within 2 km."),
    ("Choose the sites.", f"For rural gaps only, a maximal covering search (Church and ReVelle 1974) picks hosts from "
                          f"{H['facilities']:,} registered clinics and {H['schools']:,} schools (GRID3; public and private, all levels), one per km², that "
                          "reach the most people within 5 km, one at a time; greedy selection reaches at least 63% of the "
                          "optimum (Nemhauser et al. 1978). It runs twice: reach the most people, and poorest first (the "
                          "poorer 40% by wealth score). JAMB centres were left out: there is no official list with locations."),
]
for i, (hd, tx) in enumerate(steps, 1):
    pdf.item(i, hd, tx, size=8.3, lh=3.8)

# ================================================================= page 2
pdf.add_page()
pdf.head("External datasets integrated with the Ookla tiles")
rows = [("Meta population 2020", "people per ~31 m pixel, summed to 1 km", "Facebook and CIESIN 2021"),
        ("Meta Relative Wealth Index", "need: poorer 40% of people", "Chi et al. 2022"),
        ("GHSL degree of urbanisation 2020", "urban or rural, sets the speed threshold", "Schiavina et al. 2023"),
        ("GRID3 health facilities v3.0, v2.0", f"{H['facilities']:,} candidate clinic hosts", "CIESIN 2026, 2024"),
        ("GRID3 education facilities 2020", f"{H['schools']:,} candidate school hosts", "GRID3 2020"),
        ("OCHA boundaries; Broadband Plan", "LGAs; speed and coverage benchmarks", "OCHA FISS 2026; FMoCDE 2020")]
cw = [58, 78, W - 136]
pdf.set_font("Helvetica", "", 7.8)
for r in rows:
    y = pdf.get_y()
    for j, (wd, t) in enumerate(zip(cw, r)):
        pdf.set_xy(LM + sum(cw[:j]), y); pdf.set_font("Helvetica", "B" if j == 0 else "", 7.8)
        pdf.cell(wd, 4.1, clean(t))
    pdf.set_y(y + 4.1)
pdf.ln(1.5)

pdf.head("Insights and recommendations")
ins = [
    ("Rural Nigeria is nearly invisible in the speed data, and its gap is a poverty gap.",
     f"Towns log {H['tests_per_10k_urban']} tests per 10,000 people, rural areas {H['tests_per_10k_rural']}. "
     f"{pc['coverage']:.1f} million rural people have no test within 2 km, and {H['coverage_gap_poorer_pct']:.0f}% of "
     "them are in the poorer 40%. The LGAs holding most of them (table below) are thinly settled: "
     f"{PL['poorer_per_km2'].min()} to {PL['poorer_per_km2'].max()} poorer people per km² of gap, against "
     f"{H['poorer_per_km2_under_eq100']} under the 100 chosen sites, so in {thin_lgas} of the 5 even the best site "
     "reaches fewer people than the 100th site chosen.",
     "Universal Service Provision Fund: give these LGAs a budget line of their own, as each needs several sites."),
    ("Most gaps need upgrades or measurement, not new towers.",
     f"{pc['capacity']:.1f} million people live near tests that are too slow (only {H['tiles_meeting_plan_pct_urban']}% of "
     f"town tiles reach 25 Mbps), and {pc['measure']:.1f} million live in "
     f"towns with no test at all; {H['lgas_with_no_tile']} of 774 LGAs ({H['pop_in_lgas_with_no_tile_m']:.1f} million "
     "people) had none.",
     "Operators: add capacity where tests are slow. Nigerian Communications Commission: measure untested towns first."),
    ("Clinics and schools can share the new sites, and choosing the poorest first costs little reach.",
     f"{fb['coverage']:,} clinics and {sb['coverage']:,} schools sit in rural gaps. 100 sites at either "
     f"reach {b100['eff_people'] / 1e6:.2f} million people, against {clin100 / 1e6:.2f} million with clinics alone. "
     f"Chosen poorest first, they reach {b100['eq_people'] / 1e6:.2f} million: "
     f"{b100['poorer_gained_by_equity'] / 1e3:,.0f} thousand more people in the poorer 40% "
     f"({100 * b100['poorer_gained_by_equity'] / b100['eff_poorer']:.0f}% more) for "
     f"{b100['people_given_up_for_equity'] / 1e3:,.0f} thousand fewer overall; {H['eq100_sites_at_schools']} of them are "
     f"schools, and {H['eq100_multi_host_cells']} of the 100 squares hold two or more possible hosts.",
     "NPHCDA, state primary health care and universal basic education boards, and the Fund: host new sites at these "
     "clinics and schools, chosen poorest first, towards the plan's target of connecting 80% of primary health centres."),
]
for i, (hd, tx, act) in enumerate(ins, 1):
    pdf.item(i, hd, tx, size=8.6, lh=3.9)
    pdf.set_x(LM + 6); pdf.set_font("Helvetica", "", 8.6); pdf.set_text_color(*INK)
    pdf.multi_cell(W - 6, 3.9, clean(f"**Action.** {act}"), markdown=True); pdf.ln(1.0)

# ---- communities to prioritise: the brief's own three criteria, then the two other needs
pdf.head("Communities to prioritise (LGAs, people in thousands)", size=9.5)
LG = pd.read_csv(C.TABLES / "lga_summary.csv")
groups = [("Rural, poorer 40%, no broadband evidence", "coverage_poorer"), ("Towns to measure first", "measure"),
          ("Slow networks to upgrade", "capacity")]
colw = W / 3
y0 = pdf.get_y()
for j, (title, col) in enumerate(groups):
    x = LM + j * colw
    pdf.set_xy(x, y0); pdf.set_font("Helvetica", "B", 7.8); pdf.set_text_color(*MUTED)
    pdf.cell(colw - 2, 3.8, clean(title))
    pdf.set_font("Helvetica", "", 7.8); pdf.set_text_color(*INK)
    for k, (_, r) in enumerate(LG.nlargest(5, col).iterrows()):
        pdf.set_xy(x, y0 + 4.0 + k * 3.6)
        pdf.cell(colw - 16, 3.6, clean(f"{k + 1}. {r['lga']}, {r['state']}"))
        pdf.cell(12, 3.6, f"{r[col] / 1e3:,.0f}", align="R")
pdf.set_y(y0 + 4.0 + 5 * 3.6 + 1.5)

img2 = C.FIGS / "fig_reach.png"
iw, ih = Image.open(img2).size
w2 = 86
h2 = w2 * ih / iw
y = pdf.get_y()
pdf.image(str(img2), x=LM, y=y, w=w2, h=h2)
pdf.set_xy(LM + w2 + 4, y + 2); pdf.set_font("Helvetica", "B", 8.4); pdf.set_text_color(*ACCENT)
pdf.multi_cell(W - w2 - 4, 4, "How sure are we?")
pdf.set_x(LM + w2 + 4); pdf.set_font("Helvetica", "", 7.7); pdf.set_text_color(*INK)
pdf.multi_cell(W - w2 - 4, 3.6, clean(
    f"Reach depends on assumptions, so the tool reports ranges. With 100 sites: {S.loc['site reach 3 km', 'reached_100_m']:.1f} "
    f"to {S.loc['site reach 10 km', 'reached_100_m']:.1f} million people for a site reach of 3 to 10 km. The rural gap is "
    f"{S['coverage_gap_m'].min():.1f} to {S['coverage_gap_m'].max():.1f} million across a 1 to 5 km serving distance and a "
    f"3-test minimum. The gaps last all year: {H['allyear_gap_untested_pct']}% of people in rural gaps had no test within 2 km "
    f"in any quarter of 2024 ({H['allyear_eq100_untested_pct']}% of those the first 100 sites reach). "
    "Figure 2: people reached as sites are added."))
pdf.ln(1.5)
pdf.set_x(LM + w2 + 4); pdf.set_font("Helvetica", "B", 8.4); pdf.set_text_color(*ACCENT)
pdf.multi_cell(W - w2 - 4, 4, "In the tool")
pdf.set_x(LM + w2 + 4); pdf.set_font("Helvetica", "", 7.7); pdf.set_text_color(*INK)
pdf.multi_cell(W - w2 - 4, 3.6, clean(
    "Change the number of sites, the priority and the hosts; read the full ranked list or copy it as CSV; rank "
    "LGAs by each need; and turn on 2023 satellite imagery to zoom in on any site and check the ground before building."))
assert pdf.get_y() <= y + h2 + 1, "the notes beside Figure 2 run past the chart"
pdf.set_y(y + h2 + 1)

pdf.head("The first 10 sites, chosen poorest first (full list and both runs in the tool)", size=9.5)
top = pd.read_csv(C.TABLES / "sites_equity.csv").head(10)
cols = [("#", 7), ("Host", 74), ("LGA, state", 48), ("People reached", 28), ("In poorer 40%", W - 157)]
pdf.set_font("Helvetica", "B", 7.6); pdf.set_text_color(*MUTED)
x = LM
for name, wd in cols:
    pdf.set_xy(x, pdf.get_y()); pdf.cell(wd, 3.8, name, align="R" if name.startswith(("People", "In ")) else "L"); x += wd
pdf.ln(3.9); pdf.set_text_color(*INK); pdf.set_font("Helvetica", "", 7.6)
for _, r in top.iterrows():
    y, x = pdf.get_y(), LM
    nm, tag = clean(str(r["name"])), f" ({r['host']})"          # shorten the name, never the host type
    if pdf.get_string_width(nm + tag) > cols[1][1] - 2:
        while pdf.get_string_width(nm + "..." + tag) > cols[1][1] - 2:
            nm = nm[:-1]
        nm = nm.rstrip() + "..."
    vals = [str(r["rank"]), nm + tag, f"{r['lga']}, {r['state']}", f"{r['people_reached']:,}",
            f"{r['poorer_reached']:,}"]
    for (name, wd), v in zip(cols, vals):
        pdf.set_xy(x, y); pdf.cell(wd, 3.6, clean(v), align="R" if name.startswith(("People", "In ")) else "L")
        x += wd
    pdf.set_y(y + 3.6)
pdf.ln(1.5)

pdf.head("Limitations", size=9.5)
pdf.para("No test means no evidence, not no signal: gaps are inferred from where people test, not from operator "
      "coverage maps or mast locations, and tests are crowdsourced and sparse. The needs use Q4 2024 alone (Q1 to Q3 only "
      "test that gaps persist; newer quarters exist). A 5 km site reach and 2 km serving distance are assumptions, tested above. Wealth estimates "
      "date from 2021. A registered facility is not always a working one, and towers need power, backhaul and security "
      "that this tool does not model.", size=7.7, lh=3.5)
pdf.head("References", size=9.5)
pdf.para("Chi, G. et al. (2022) PNAS 119(3) e2113658119. Church, R. and ReVelle, C. (1974) Papers of the Regional Science "
      "Association 32, 101-118. GRID3 (2020) NGA Education Facilities, HDX. CIESIN (2024, "
      "2026) GRID3 NGA Health Facilities v2.0, v3.0, doi:10.7916/kv1n-0743, "
      "10.7916/s6cq-1q98. Facebook and CIESIN (2021) High Resolution Settlement Layer. FMoCDE (2020) Nigerian National "
      "Broadband Plan 2020-2025. Nemhauser, G., Wolsey, L. and Fisher, M. (1978) Mathematical Programming 14, 265-294. "
      "OCHA FISS (2026) Nigeria subnational boundaries. Schiavina, M., Melchiorri, M. and Pesaresi, M. (2023) GHS-SMOD "
      "R2023A, JRC, doi:10.2905/A0DF7A6F-49DE-46EA-9BDE-563437A6E2BA. Speedtest® by Ookla® Global Fixed and Mobile "
      "Network Performance Maps, supplied by DSN and matched to the release on AWS on 20 October 2026; based on "
      f"{AUTHOR}'s analysis of these maps for Q4 2024; Ookla trademarks used under license and reprinted with permission "
      "(CC BY-NC-SA 4.0; maps here shared under the same licence).",
      size=7.0, lh=3.2)

out = C.SUBMISSION / "DSN_Geospatial_WhereToBuildNext_OluwasolaOyinloye.pdf"
assert pdf.page_no() == 2, f"the brief allows 2 pages; this build has {pdf.page_no()}"
pdf.output(str(out))
print(f"saved {out}, {pdf.page_no()} pages")
