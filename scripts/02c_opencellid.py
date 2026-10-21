"""
02c - OpenCelliD cell positions for Nigeria, as a second check on the rural gaps.

OpenCelliD (CC BY-SA 4.0) is a crowdsourced database of mobile cell positions. Its own site needs an account and
blocks some networks, so this step reads the public copy that the UN Smart Maps Group keeps on Source Cooperative
as one PMTiles archive (cellid.pmtiles, about 530 MB). Zoom 14 holds every cell (the build dropped points only at
lower zooms), and the archive is ordered so that neighbouring tiles sit together. The step reads the archive's
directories, works out which bytes hold Nigeria's zoom-14 tiles, and fetches only those.

Outputs:
  data/raw/opencellid/nigeria_cells.parquet   cells of Nigerian networks (MCC 621) inside Nigeria's box
  outputs/tables/opencellid_fetch.csv         source, its date, what was fetched, and a checksum of the cells file
"""
import bisect
import gzip
import hashlib
import math
import struct
import urllib.request

import pandas as pd
from pmtiles.tile import deserialize_directory, deserialize_header, zxy_to_tileid

import config as C

URL = "https://data.source.coop/smartmaps/opencellid/cellid.pmtiles"
Z = 14
BOX = (2.5, 4.0, 15.0, 14.2)                         # west, south, east, north: Nigeria with a margin
fetched = 0


def get(start, length):
    global fetched
    req = urllib.request.Request(URL, headers={"Range": f"bytes={start}-{start + length - 1}", "User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=300) as r:
        data, info = r.read(), r.headers
    assert len(data) == length, f"short read at {start}: {len(data)} of {length}"
    fetched += length
    return data, info


# ----------------------------------------------------------------- minimal Mapbox Vector Tile reader (points only)
def varint(b, i):
    out = shift = 0
    while True:
        c = b[i]
        i += 1
        out |= (c & 0x7F) << shift
        shift += 7
        if c < 0x80:
            return out, i


def fields(b):
    i = 0
    while i < len(b):
        key, i = varint(b, i)
        num, wire = key >> 3, key & 7
        if wire == 0:
            v, i = varint(b, i)
        elif wire == 2:
            n, i = varint(b, i)
            v, i = b[i:i + n], i + n
        elif wire == 1:
            v, i = struct.unpack_from("<d", b, i)[0], i + 8
        elif wire == 5:
            v, i = struct.unpack_from("<f", b, i)[0], i + 4
        else:
            raise ValueError(f"unexpected wire type {wire}")
        yield num, v


def packed(b):
    out, i = [], 0
    while i < len(b):
        v, i = varint(b, i)
        out.append(v)
    return out


def value(b):
    for num, v in fields(b):
        if num == 1:
            return v.decode()
        if num in (2, 3):
            return v
        if num in (4, 5):
            return v - (1 << 64) if v >= 1 << 63 else v
        if num == 6:
            return (v >> 1) ^ -(v & 1)
        if num == 7:
            return bool(v)


def points(tile, tx, ty):
    """Yield (properties, lon, lat) for each point that belongs to this tile (buffer copies are skipped)."""
    for num, layer in fields(tile):
        if num != 3:
            continue
        keys, vals, feats, extent = [], [], [], 4096
        for ln, lv in fields(layer):
            if ln == 3:
                keys.append(lv.decode())
            elif ln == 4:
                vals.append(value(lv))
            elif ln == 2:
                feats.append(lv)
            elif ln == 5:
                extent = lv
        for ft in feats:
            tags, geom = [], []
            for fn, fv in fields(ft):
                if fn == 2:
                    tags = packed(fv)
                elif fn == 4:
                    geom = packed(fv)
            props = {keys[tags[k]]: vals[tags[k + 1]] for k in range(0, len(tags), 2)}
            x = y = i = 0
            while i < len(geom):
                cmd, count = geom[i] & 7, geom[i] >> 3
                i += 1
                if cmd != 1:
                    break
                for _ in range(count):
                    dx, dy = geom[i], geom[i + 1]
                    i += 2
                    x += (dx >> 1) ^ -(dx & 1)
                    y += (dy >> 1) ^ -(dy & 1)
                    if 0 <= x < extent and 0 <= y < extent:
                        n = 1 << Z
                        lon = (tx + x / extent) / n * 360 - 180
                        lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (ty + y / extent) / n))))
                        yield props, lon, lat


# ----------------------------------------------------------------- directories, then only Nigeria's tiles
head, info = get(0, 127)
h = deserialize_header(head)
assert h["max_zoom"] >= Z, h["max_zoom"]
root, _ = get(h["root_offset"], h["root_length"])
leaves, _ = get(h["leaf_directory_offset"], h["leaf_directory_length"])
entries = []
for e in deserialize_directory(root):
    if e.run_length == 0:                             # a pointer to a leaf directory
        entries += deserialize_directory(leaves[e.offset:e.offset + e.length])
    else:
        entries.append(e)
entries.sort(key=lambda e: e.tile_id)
ids = [e.tile_id for e in entries]

n = 1 << Z
x0, x1 = (int((lon + 180) / 360 * n) for lon in (BOX[0], BOX[2]))
lat_y = lambda lat: int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
y0, y1 = lat_y(BOX[3]), lat_y(BOX[1])
wanted = {}                                           # (offset, length) -> tiles that use those bytes
for tx in range(x0, x1 + 1):
    for ty in range(y0, y1 + 1):
        tid = zxy_to_tileid(Z, tx, ty)
        k = bisect.bisect_right(ids, tid) - 1
        if k >= 0 and entries[k].tile_id <= tid < entries[k].tile_id + entries[k].run_length:
            wanted.setdefault((entries[k].offset, entries[k].length), []).append((tx, ty))
print(f"{len(wanted):,} zoom-{Z} tiles with cells in Nigeria's box", flush=True)

rows, spans = [], sorted(wanted)
i = 0
while i < len(spans):                                 # fetch neighbouring tiles in one request
    start, end, j = spans[i][0], spans[i][0] + spans[i][1], i + 1
    while j < len(spans) and spans[j][0] - end < 200_000 and spans[j][0] + spans[j][1] - start < 32_000_000:
        end = max(end, spans[j][0] + spans[j][1])
        j += 1
    blob, _ = get(h["tile_data_offset"] + start, end - start)
    for off, length in spans[i:j]:
        tile = gzip.decompress(blob[off - start:off - start + length])
        for tx, ty in wanted[(off, length)]:
            for props, lon, lat in points(tile, tx, ty):
                if props.get("mcc") == 621 and BOX[0] <= lon <= BOX[2] and BOX[1] <= lat <= BOX[3]:
                    rows.append({**props, "lon": lon, "lat": lat})
    i = j

cells = (pd.DataFrame(rows).drop_duplicates(["radio", "mcc", "net", "area", "cell"])
         [["radio", "mcc", "net", "area", "cell", "lon", "lat", "range", "samples", "created", "updated"]])
out = C.RAW / "opencellid" / "nigeria_cells.parquet"
out.parent.mkdir(parents=True, exist_ok=True)
cells.to_parquet(out, index=False)
upd = pd.to_datetime(cells["updated"], unit="s")
summary = dict(source=URL, last_modified=info.get("Last-Modified"), etag=info.get("ETag"), zoom=Z,
               tiles=len(wanted), bytes_fetched=fetched, cells=len(cells), lte_cells=int((cells["radio"] == "LTE").sum()),
               updated_min=str(upd.min().date()), updated_max=str(upd.max().date()),
               sha256=hashlib.sha256(out.read_bytes()).hexdigest())
pd.DataFrame([summary]).to_csv(C.TABLES / "opencellid_fetch.csv", index=False)
print(summary)
print(cells["radio"].value_counts().to_string())
