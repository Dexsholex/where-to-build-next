"""
01 - Fetch the external datasets and check every byte against the recorded checksum.

Files land in data/raw/<folder>/. data/raw/PROVENANCE.csv records the URL, licence, size and SHA-256 of each
one. A file that is already present is verified, not downloaded again; a download whose checksum disagrees
with the record stops the run, so nobody rebuilds the analysis on different data by accident. No account is
needed for any file.
"""
import csv
import hashlib
import sys
import urllib.request
from datetime import datetime, timezone

from config import RAW

HDX = "https://data.humdata.org/dataset"
DOWNLOADS = [
    ("rwi", "Meta Relative Wealth Index, Nigeria", "CC BY-NC 4.0",
     f"{HDX}/76f2a2ea-ba50-40f5-b79c-db95d668b843/resource/b112d3f9-7a9d-4798-b27d-a505219186aa/download/"
     "nga_relative_wealth_index.csv", "nga_relative_wealth_index.csv"),
    ("ghsl_smod", "GHSL degree of urbanisation (SMOD) E2020 R2023A, 1 km, Mollweide", "CC BY 4.0",
     "https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_SMOD_GLOBE_R2023A/"
     "GHS_SMOD_E2020_GLOBE_R2023A_54009_1000/V2-0/GHS_SMOD_E2020_GLOBE_R2023A_54009_1000_V2_0.zip",
     "GHS_SMOD_E2020_GLOBE_R2023A_54009_1000_V2_0.zip"),
    ("grid3_education", "GRID3 NGA Education Facilities (NGA_Education, 2021 upload)", "CC BY",
     f"{HDX}/ec228c18-8edc-4f3c-94c9-a6b946af7229/resource/1a064a21-ffcf-4fb8-a0a6-5cf811d94664/download/"
     "nga_education.zip", "nga_education.zip"),
    ("meta_population", "Meta High Resolution Population Density Maps, Nigeria, general population 2020 (CSV)", "CC BY",
     f"{HDX}/62ec6c48-2f23-476b-8c1e-e924ad79908d/resource/ec1ac1b2-616e-43a7-ba8c-29eaf3479f24/download/"
     "nga_general_2020_csv.zip", "nga_general_2020_csv.zip"),
]

prov_path = RAW / "PROVENANCE.csv"
FIELDS = ["folder", "dataset", "licence", "url", "file", "bytes", "sha256", "downloaded_utc"]
records = {r["file"]: r for r in csv.DictReader(open(prov_path, newline=""))} if prov_path.exists() else {}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


problems = []
for folder, name, licence, url, fname in DOWNLOADS:
    rel = f"{folder}/{fname}"
    out = RAW / folder / fname
    out.parent.mkdir(parents=True, exist_ok=True)
    if not out.exists():
        print(f"downloading {name} ...", flush=True)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=600) as r, open(out, "wb") as o:
            while block := r.read(1 << 20):
                o.write(block)
    digest, size = sha256(out), out.stat().st_size
    if rel in records:
        ok = records[rel]["sha256"] == digest
        print(f"{'OK      ' if ok else 'MISMATCH'} {rel} ({size:,} bytes)")
        if not ok:
            problems.append(rel)
    else:
        records[rel] = dict(folder=folder, dataset=name, licence=licence, url=url, file=rel, bytes=size, sha256=digest,
                            downloaded_utc=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        print(f"RECORDED {rel} ({size:,} bytes)")

with open(prov_path, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=FIELDS)
    w.writeheader()
    w.writerows(records.values())
if problems:
    sys.exit(f"Checksum mismatch for {', '.join(problems)}: the source has changed since this analysis was run.")
