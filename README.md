# Where to Build Next

**Live tool:** https://dexsholex.github.io/where-to-build-next/ · **Two-page summary:** [`submission/`](submission/DSN_Geospatial_WhereToBuildNext_OluwasolaOyinloye.pdf)

Nigeria's broadband plan set minimum speeds of 25 Mbps in towns and 10 Mbps in rural areas, but money for new sites is scarce and the gaps are not all the same. This project sorts every populated square kilometre of Nigeria by what it needs, using Ookla's mobile speed tests for October to December 2024, and then chooses which existing clinics and schools should host new connectivity sites so that each one reaches as many unconnected people as possible.

Oluwasola Oyinloye, for the DSN AI Bootcamp 2026 Geospatial Track ("Mapping Nigeria's Digital Divide").

## What it finds

Of 205.6 million people:

| Need | People | What it calls for |
|---|---:|---|
| Served: a test at the plan's speed within 2 km | 53.0 M | nothing new |
| Slow signal: tests nearby, all below the plan's speed | 22.1 M | more capacity on existing networks |
| Town to measure: urban, no test within 2 km | 64.6 M | measurement before investment |
| Rural gap: rural, no test within 2 km | 66.0 M | new sites |

- Where people do test, the average mobile download is 52.2 Mbps in towns and 22.9 Mbps in rural areas (weighted by tests), but only 628 of the 9,234 tiles are rural.
- 80% of the people in rural gaps are in Nigeria's poorer 40% by Meta's Relative Wealth Index, and the gaps last: 95.9% of these people had no test within 2 km in any quarter of 2024.
- Chosen to reach the most people, 100 sites hosted at clinics and schools reach 3.12 million of them (47 of the 100 at schools); clinics alone reach 3.04 million. How far one site reaches matters most: the same 100 sites reach 1.7 million at 3 km and 8.0 million at 10 km.
- Choosing the poorest first, which the tool opens on, reaches 398,000 more people in the poorer 40% for 251,000 fewer people overall.
- The LGAs with the most poorer rural people and no test (Ningi, Fune, Wasagu/Danko, Ganjuwa, Gamawa) are thinly settled, so a straight ranking passes them over: in four of the five, even the best single site reaches fewer people than the 100th site chosen. They need a budget line of their own.

## Repository

```
index.html            the interactive tool (served by GitHub Pages)
scripts/              the pipeline, numbered in run order; config.py holds every assumption
data/input/           inputs small enough to ship: Ookla tiles (Q4 2024 from DSN; Q1-Q3 2024 for the all-year check),
                      OCHA boundaries, cleaned GRID3 health facilities
data/raw/             downloads (not committed); PROVENANCE.csv records URL, licence, size and SHA-256 of each
outputs/tables/       site rankings, budgets, LGA table, sensitivity runs, integrity check
outputs/figures/      the two figures in the PDF
submission/           the two-page PDF
docs/research_log.md  decisions, problems found and how they were fixed, dated
```

## Rebuild it

Python 3.14 and the packages in `requirements.txt`:

```bash
python -m pip install -r requirements.txt
python scripts/run_all.py
```

Step 01 downloads about 210 MB from HDX and the JRC and stops if any file's checksum differs from `data/raw/PROVENANCE.csv`. Steps 02 and 02b read Ookla's public bucket on AWS: 02 confirms which release DSN's tiles came from, and 02b fetches January to September 2024 for the all-year check (its output ships in `data/input/`). Skip both with `--from 03`. After the downloads, a full run takes about five minutes on a laptop and ends with the integrity check.

| Step | Script | Does |
|---|---|---|
| 01 | `01_download.py` | wealth index, GHSL settlement layer, GRID3 schools, Meta population; checksums verified |
| 02 | `02_identify_ookla_release.py` | matches the tiles to Ookla's public release (mobile, Q4 2024) |
| 02b | `02b_ookla_all_year.py` | fetches Q1-Q3 2024 for Nigeria; confirms all 9,234 of DSN's tiles are identical to the public Q4 file |
| 03 | `03_build_grid.py` | 1 km grid: people, urban or rural, wealth, LGA, distance to the nearest speed test |
| 04 | `04_siting.py` | sorts every cell by need, chooses sites, runs the sensitivity tests |
| 05 | `05_make_maps.py` | figures and the web-map layer |
| 06 | `06_dashboard.py` | the interactive tool |
| 07 | `07_report.py` | the two-page PDF |
| 08 | `08_integrity_check.py` | recomputes the published numbers by independent routes |

## Data

| Layer | Source | Licence |
|---|---|---|
| Mobile speed tests | Speedtest by Ookla Global Fixed and Mobile Network Performance Maps, mobile, Q4 2024 | CC BY-NC-SA 4.0 |
| Population | Meta High Resolution Population Density Maps, 2020 (Facebook and CIESIN 2021) | CC BY |
| Wealth | Meta Relative Wealth Index (Chi et al. 2022, PNAS 119(3)) | CC BY-NC 4.0 |
| Settlement type | GHSL GHS-SMOD R2023A, 2020 (Schiavina, Melchiorri and Pesaresi 2023) | CC BY 4.0 |
| Clinics | GRID3 NGA Health Facilities v3.0 and v2.0 (CIESIN 2026, 2024) | CC BY 4.0 |
| Schools | GRID3 NGA Education Facilities, 2020 | CC BY |
| Boundaries | OCHA subnational administrative boundaries (COD-AB) | CC BY-IGO |
| Speed targets | Nigerian National Broadband Plan 2020–2025, pp. 36, 38 and 40 | public document |
| Satellite layer (tool only) | EOxCloudless 2023 by EOX IT Services GmbH (contains modified Copernicus Sentinel data 2023) | CC BY-NC-SA 4.0 |

The clinic list in `data/input/` keeps GRID3 v3.0 for its 24 states and v2.0 for the other 13, and drops records without coordinates, records flagged as duplicates, and facilities marked Not-Functional or Closed. DSN supplied the Ookla tiles and the population file. All 9,234 tiles are identical to Ookla's public mobile file for Q4 2024 (`outputs/tables/ookla_all_year.csv`), and the population file is byte-for-byte identical to the one on HDX (same SHA-256). Because Ookla's licence is ShareAlike and non-commercial, the maps and tables here are shared under CC BY-NC-SA 4.0.

Speedtest® by Ookla® Global Fixed and Mobile Network Performance Maps were supplied by DSN and matched to the release on AWS on 20 October 2026. Based on Oluwasola Oyinloye's analysis of Speedtest® by Ookla® Global Fixed and Mobile Network Performance Maps for Q4 2024. Ookla trademarks used under license and reprinted with permission.

## Method

A cell is served if an Ookla tile within 2 km reaches the plan's speed for its setting (GHSL classes 21 to 30 count as urban). Rural cells with no tile at all within 2 km are rural gaps: no evidence of broadband, which is not proof of no signal. For those cells only, the maximal covering location problem (Church and ReVelle 1974) is solved by lazy greedy selection over 75,124 candidate squares holding 54,732 clinics and 204,355 schools, with a 5 km site reach; coverage is submodular, so greedy reaches at least 1 − 1/e of the optimum (Nemhauser, Wolsey and Fisher 1978). Hosts in the same square kilometre are interchangeable, so one is kept per cell, a clinic first. "Poorest first" weights only people in the poorer 40% when choosing, while counting everyone covered.

## Checks

`scripts/08_integrity_check.py` recomputes the key results without reusing the pipeline's own code: tile counts from the raw file, urban labels with a different raster sampler, the classification of 3,000 random cells using great-circle distances, the people covered by the chosen sites by brute force, speeds and latency from the raw file, the priority-LGA figures from every raw host inside each LGA polygon, the all-year check by great-circle distances on a sample, and every number printed in the PDF and embedded in the tool. The current run passes 38 of 38.

## Limits

A missing test is missing evidence, not proof of no signal: tests are crowdsourced, sparse and mostly urban (2.99 per 10,000 people in towns, 0.31 in rural areas), and 231 of 774 LGAs logged none this quarter. Gaps come from where people test, not from operator coverage maps or mast locations; the all-year check (95.9% of people in rural gaps untested in every quarter of 2024) makes chance an unlikely explanation, but it is still not proof of no signal. The 2 km serving distance and 5 km site reach are assumptions, tested in `outputs/tables/sensitivity.csv`. The wealth estimates date from 2021, and a registered clinic or school is not always a working one. New sites also need power, backhaul and security, which this does not model. JAMB exam centres were considered as hosts but left out because no official list with locations is published. 256 population pixels where Meta's layer places a census count on a few buildings (0.55 million people) are excluded.

## Citation

Oyinloye, O. (2026). *Where to Build Next: connectivity siting for Nigeria.* DSN AI Bootcamp 2026, Geospatial Track. https://github.com/Dexsholex/where-to-build-next

Code: MIT licence (`LICENSE`). Data and derived maps and tables: the licences above.
