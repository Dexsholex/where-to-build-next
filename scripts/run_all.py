"""
Rebuild Where to Build Next from the raw data, in order.

    python scripts/run_all.py            # everything (02 and 02b read Ookla's public bucket; skip them with --from 03)
    python scripts/run_all.py --from 04  # resume from a step

Boundaries, the cleaned facility list and the Ookla tiles ship in data/input; 01 fetches the rest.
The integrity check (08) runs last and fails loudly if any printed number disagrees with the data.
"""
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STEPS = [
    ("01", "01_download.py", "download wealth, settlement, schools and population; verify checksums"),
    ("02", "02_identify_ookla_release.py", "identify DSN's Ookla release against Ookla's public files"),
    ("02b", "02b_ookla_all_year.py", "fetch Ookla Q1-Q3 2024 for the all-year check; compare Q4 with DSN's file"),
    ("03", "03_build_grid.py", "1 km grid: population, settlement, wealth, LGA, distance to speed tests"),
    ("04", "04_siting.py", "triage every cell, choose sites, sensitivity"),
    ("05", "05_make_maps.py", "figures and the web-map layer"),
    ("06", "06_dashboard.py", "the interactive tool (HTML)"),
    ("07", "07_report.py", "the two-page PDF"),
    ("08", "08_integrity_check.py", "independent recomputation of the printed numbers"),
]


def main():
    start = sys.argv[sys.argv.index("--from") + 1] if "--from" in sys.argv else STEPS[0][0]
    ids = [s[0] for s in STEPS]
    if start not in ids:
        sys.exit(f"Unknown step {start}. Steps: {', '.join(ids)}")
    for step, script, what in STEPS[ids.index(start):]:
        print(f"\n=== {step}  {script}  ({what})", flush=True)
        t0 = time.time()
        if subprocess.run([sys.executable, script], cwd=HERE).returncode != 0:
            sys.exit(f"Step {step} failed after {time.time() - t0:.0f} s. Fix it, then resume with --from {step}")
        print(f"--- {step} done in {time.time() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    main()
