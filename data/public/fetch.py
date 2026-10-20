"""Fetch and process the public-data layer (SPEC §6.2, §10).

Downloads real, sourced public datasets into ``data/public/raw/`` (gitignored), then derives:

- ``planning_areas.geojson``  URA MP2019 planning-area boundaries, simplified, WGS84
- ``stations.json``           MRT/LRT stations per planning area (from LTA station exits)
- ``areas.json``              one ``tools.models.Area`` per planning area
- ``checksums.txt``           SHA-256 of every raw file and every output

No number is invented or estimated: a field without a real source stays null and the gap is
recorded in SOURCES.md.

Usage::

    python -m data.public.fetch             # download (cached), then process
    python -m data.public.fetch --refresh   # re-download everything
    python -m data.public.fetch --offline   # reprocess from raw/ only, no network

``LTA_ACCOUNT_KEY`` (LTA DataMall) enables station passenger volumes; without it
``station_traffic_monthly`` stays null.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import sys
import time
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
RETRIEVED = "2026-10-19"

DGS_META = "https://api-production.data.gov.sg/v2/public/api/datasets/{id}/metadata"
DGS_POLL = "https://api-open.data.gov.sg/v1/public/api/datasets/{id}/poll-download"
DGS_INIT = "https://api-open.data.gov.sg/v1/public/api/datasets/{id}/initiate-download"
ONEMAP_SEARCH = "https://www.onemap.gov.sg/api/common/elastic/search"
LTA_PV_TRAIN = "https://datamall2.mytransport.sg/ltaodataservice/PV/Train"

# key -> (data.gov.sg dataset id, title, publisher, as-of, raw filename)
DATASETS: dict[str, dict[str, str]] = {
    "boundaries": {
        "id": "d_4765db0e87b9c86336792efe8a1f7a66",
        "title": "Master Plan 2019 Planning Area Boundary (No Sea)",
        "publisher": "Urban Redevelopment Authority",
        "as_of": "MP2019 (approved 2019-11-18; coverage from 2019-12-23)",
        "file": "mp2019_planning_area_boundary.geojson",
    },
    "income": {
        "id": "d_4e150bbd35c3145ea43019212c7b46c2",
        "title": "Resident Households by Planning Area of Residence and Monthly Household Income from "
        "Work (Census of Population 2020)",
        "publisher": "Singapore Department of Statistics",
        "as_of": "Census of Population 2020 (dataset revised 2026-06-30)",
        "file": "census2020_households_pa_income.csv",
    },
    "workplace": {
        "id": "d_22063c84778e6535b92b4d8f93fd2525",
        "title": "Employed Residents Aged 15 Years and Over by Planning Area of Workplace, Age Group "
        "and Sex (Census of Population 2020)",
        "publisher": "Singapore Department of Statistics",
        "as_of": "Census of Population 2020 (reference date 2020-06-30)",
        "file": "census2020_employed_pa_workplace.csv",
    },
    "eating": {
        "id": "d_227473e811b09731e64725f140b77697",
        "title": "List of NEA Licensed Eating Establishments",
        "publisher": "National Environment Agency",
        "as_of": "coverage 2015-06-11 to 2016-09-06",
        "file": "nea_licensed_eating_establishments.csv",
    },
    "station_exits": {
        "id": "d_b39d3a0871985372d7e1637193335da5",
        "title": "LTA MRT Station Exit (GEOJSON)",
        "publisher": "Land Transport Authority",
        "as_of": "dataset updated 2026-10-18",
        "file": "lta_mrt_station_exit.geojson",
    },
    "station_codes": {
        "id": "d_d312a5b127e1ae74299b8ae664cedd4e",
        "title": "Train Station Chinese Names",
        "publisher": "Land Transport Authority",
        "as_of": "coverage 2017-06-27 (dataset updated 2024-06-06)",
        "file": "lta_train_station_names.csv",
    },
}

LICENCE = "Singapore Open Data Licence v1.0"

# SingStat's Population Trends page; not on data.gov.sg. The newest June release is used.
SINGSTAT_PAGE = (
    "https://www.singstat.gov.sg/find-data/explore-data-themes/population/geographic-distribution/"
    "latest-news-data"
)
SINGSTAT_TITLE = "Singapore Residents by Planning Area / Subzone, Age Group, Sex and Type of Dwelling"
POPULATION = {
    "id": "singstat:respopagesextod",
    "title": SINGSTAT_TITLE,
    "publisher": "Singapore Department of Statistics",
    "zip": "singstat_respopagesextod.zip",
    "source_file": "singstat_respopagesextod.source.json",
}

# ----------------------------------------------------------------- network helpers


def _client():  # imported lazily so --offline needs no network libraries
    import httpx

    return httpx.Client(timeout=120, headers={"User-Agent": "waypoint-public-data/1.0"})


def _get_json(client, url: str, params: dict | None = None, headers: dict | None = None) -> Any:
    for attempt in range(10):
        r = client.get(url, params=params, headers=headers)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(min(60, 6 * (attempt + 1)))
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"giving up on {url} after repeated 429/5xx")


def dgs_download(client, dataset_id: str, dest: Path) -> None:
    """Download a data.gov.sg dataset file via poll-download (initiating it if needed)."""
    url = None
    for attempt in range(12):
        body = _get_json(client, DGS_POLL.format(id=dataset_id))
        data = body.get("data") or {}
        url = data.get("url")
        if url and data.get("status", "DOWNLOAD_SUCCESS") == "DOWNLOAD_SUCCESS":
            break
        if attempt == 0:
            _get_json(client, DGS_INIT.format(id=dataset_id))
        time.sleep(5)
        url = None
    if not url:
        raise RuntimeError(f"data.gov.sg did not produce a download for {dataset_id}")
    r = client.get(url, follow_redirects=True)
    r.raise_for_status()
    dest.write_bytes(r.content)
    time.sleep(1.5)


def dgs_metadata(client, dataset_id: str) -> dict:
    body = _get_json(client, DGS_META.format(id=dataset_id))
    time.sleep(1.0)
    return body.get("data") or {}


POSTAL_RE = re.compile(r"SINGAPORE\s*(\d{6})\s*$")


def eating_postal_codes(path: Path) -> list[str]:
    codes = set()
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            m = POSTAL_RE.search(row["premises_address"].strip())
            if m:
                codes.add(m.group(1))
    return sorted(codes)


# Hawker and market stalls in the NEA list have no postal code, e.g.
# "BEDOK NORTH ST 4 BLK 85 Stall No 01-21" or "AMOY STREET FOOD CENTRE Stall No 01-01".
ROAD_ABBR = {
    "ST": "STREET", "RD": "ROAD", "AVE": "AVENUE", "LOR": "LORONG", "DR": "DRIVE", "CRES": "CRESCENT",
    "CTRL": "CENTRAL", "PL": "PLACE", "NTH": "NORTH", "STH": "SOUTH", "UPP": "UPPER", "BT": "BUKIT",
    "JLN": "JALAN", "TG": "TANJONG", "CL": "CLOSE", "GDNS": "GARDENS", "PK": "PARK", "HTS": "HEIGHTS",
    "TER": "TERRACE", "CTR": "CENTRE", "CT": "COURT",
}  # fmt: skip


def _norm_words(s: str) -> list[str]:
    return [ROAD_ABBR.get(w, w) for w in re.sub(r"[^A-Z0-9 ]", " ", s.upper()).split()]


def stall_query(address: str) -> str | None:
    """Query key for an address without a postal code: 'BLK|<blk>|<road>' or 'NAME|<building>'."""
    a = re.sub(r"\([^)]*\)", " ", address)
    a = re.split(r"\s+Stall No\b", re.sub(r"\s+", " ", a).strip(), flags=re.I)[0].strip().upper()
    if not a:
        return None
    m = re.match(r"^(?P<road>.+?) BLK (?P<blk>\w+)$", a) or re.match(r"^BLK (?P<blk>\w+) (?P<road>.+)$", a)
    if m:
        return f"BLK|{m['blk']}|{m['road']}"
    return f"NAME|{a}"


def _stall_hit_ok(query: str, hit: dict) -> bool:
    kind, *parts = query.split("|")
    if kind == "BLK":
        blk, road = parts
        # same block number and the same road words (order-free: "TOA PAYOH LOR 8" = "LORONG 8 TOA PAYOH")
        return hit.get("BLK_NO", "").upper() == blk and sorted(
            _norm_words(hit.get("ROAD_NAME", ""))
        ) == sorted(_norm_words(road))
    name = _norm_words(parts[0])
    return name in (_norm_words(hit.get("SEARCHVAL", "")), _norm_words(hit.get("BUILDING", "")))


def eating_stall_queries(path: Path) -> list[str]:
    qs = set()
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            addr = row["premises_address"].strip()
            if not POSTAL_RE.search(addr):
                q = stall_query(addr)
                if q:
                    qs.add(q)
    return sorted(qs)


def onemap_geocode_stalls(client, queries: list[str], cache_path: Path) -> dict[str, Any]:
    """Geocode stall addresses with OneMap; keep a hit only if it matches strictly (no fuzzy).

    Cache value: {"latlng": [lat, lng], "matched": <OneMap ADDRESS>} or null.
    """
    cache: dict[str, Any] = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    todo = [q for q in queries if q not in cache]
    print(f"  onemap stalls: {len(queries)} addresses, {len(todo)} to geocode", flush=True)
    for q in todo:
        kind, *parts = q.split("|")
        text = f"{parts[0]} {parts[1]}" if kind == "BLK" else parts[0]
        for attempt in range(20):
            time.sleep(1.05)
            r = client.get(
                ONEMAP_SEARCH,
                params={"searchVal": text, "returnGeom": "Y", "getAddrDetails": "Y", "pageNum": 1},
            )
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(min(60, 2 * (attempt + 1)))
                continue
            r.raise_for_status()
            break
        else:
            cache_path.write_text(json.dumps(cache, sort_keys=True, indent=0))
            raise RuntimeError("OneMap kept rate-limiting; re-run to resume")
        hits = [h for h in r.json().get("results", []) if _stall_hit_ok(q, h)]
        cache[q] = (
            {
                "latlng": [float(hits[0]["LATITUDE"]), float(hits[0]["LONGITUDE"])],
                "matched": hits[0]["ADDRESS"],
            }
            if hits
            else None
        )
    cache_path.write_text(json.dumps(cache, sort_keys=True, indent=0))
    return cache


def onemap_geocode(client, postals: list[str], cache_path: Path) -> dict[str, Any]:
    """Geocode postal codes with OneMap's public search API. Cached and resumable.

    Cache value: [lat, lng] for a hit whose POSTAL equals the query, or null when OneMap has no
    exact match (no fuzzy matches are used).
    """
    cache: dict[str, Any] = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    todo = [p for p in postals if p not in cache]
    print(f"  onemap: {len(postals)} postal codes, {len(todo)} to geocode", flush=True)
    throttled = 0
    next_at = 0.0
    for i, pc in enumerate(todo, 1):
        for attempt in range(20):
            time.sleep(max(0.0, next_at - time.monotonic()))
            next_at = time.monotonic() + 1.05  # OneMap's public search allows about one call per second
            r = client.get(
                ONEMAP_SEARCH,
                params={"searchVal": pc, "returnGeom": "Y", "getAddrDetails": "Y", "pageNum": 1},
            )
            if r.status_code == 429 or r.status_code >= 500:
                throttled += 1
                time.sleep(min(60, 2 * (attempt + 1)))
                continue
            r.raise_for_status()
            break
        else:
            cache_path.write_text(json.dumps(cache, sort_keys=True))
            raise RuntimeError("OneMap kept rate-limiting; re-run to resume")
        hits = [h for h in r.json().get("results", []) if h.get("POSTAL") == pc]
        cache[pc] = [float(hits[0]["LATITUDE"]), float(hits[0]["LONGITUDE"])] if hits else None
        if i % 100 == 0:
            cache_path.write_text(json.dumps(cache, sort_keys=True))
            print(f"  onemap: {i}/{len(todo)} (throttled {throttled}x)", flush=True)
    cache_path.write_text(json.dumps(cache, sort_keys=True))
    return cache


def lta_passenger_volume(client, key: str, dest_dir: Path) -> list[Path]:
    """Download LTA DataMall 'Passenger Volume by Train Stations' (latest month available).

    DataMall serves only the last three months. Returns the CSV paths written.
    """
    body = _get_json(client, LTA_PV_TRAIN, headers={"AccountKey": key, "accept": "application/json"})
    links = [v.get("Link") for v in body.get("value", []) if v.get("Link")]
    out = []
    for link in links:
        r = client.get(link, follow_redirects=True)
        r.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            for name in z.namelist():
                if name.lower().endswith(".csv"):
                    p = dest_dir / f"lta_pv_train_{Path(name).name}"
                    p.write_bytes(z.read(name))
                    out.append(p)
    return out


def singstat_population(client, dest_dir: Path) -> None:
    """Find the newest 'June YYYY in csv' link under SINGSTAT_TITLE and download it."""
    r = client.get(SINGSTAT_PAGE, follow_redirects=True)
    r.raise_for_status()
    page = r.text
    start = page.find(SINGSTAT_TITLE)
    if start < 0:
        raise RuntimeError(f"SingStat page no longer lists {SINGSTAT_TITLE!r}")
    links = re.findall(r'<a[^>]*href="(/files/[^"]+\.zip)"[^>]*>(.*?)</a>', page[start:], re.S)
    for href, label in links:
        text = re.sub(r"<[^>]+>", "", label)
        m = re.search(r"June (\d{4}) in csv", text)
        if m:
            year = m.group(1)
            url = "https://www.singstat.gov.sg" + href
            z = client.get(url, follow_redirects=True)
            z.raise_for_status()
            (dest_dir / POPULATION["zip"]).write_bytes(z.content)
            (dest_dir / POPULATION["source_file"]).write_text(
                json.dumps({"url": url, "reference": f"June {year}", "page": SINGSTAT_PAGE}, indent=1)
            )
            return
    raise RuntimeError("no 'June YYYY in csv' link found on the SingStat page")


def download(refresh: bool = False) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    meta_path = RAW / "metadata.json"
    meta: dict[str, Any] = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    with _client() as client:
        for key, ds in DATASETS.items():
            dest = RAW / ds["file"]
            if refresh or not dest.exists():
                print(f"download {key}: {ds['id']}", flush=True)
                dgs_download(client, ds["id"], dest)
            if refresh or ds["id"] not in meta:
                m = dgs_metadata(client, ds["id"])
                meta[ds["id"]] = {
                    k: m.get(k)
                    for k in (
                        "name",
                        "lastUpdatedAt",
                        "coverageStart",
                        "coverageEnd",
                        "managedBy",
                        "description",
                    )
                }
                meta_path.write_text(json.dumps(meta, indent=1, sort_keys=True))
        if refresh or not (RAW / POPULATION["zip"]).exists():
            print("download SingStat residents by planning area (latest June release)", flush=True)
            singstat_population(client, RAW)
        print("geocode eating establishments via OneMap", flush=True)
        onemap_geocode(
            client, eating_postal_codes(RAW / DATASETS["eating"]["file"]), RAW / "onemap_postal_geocode.json"
        )
        onemap_geocode_stalls(
            client, eating_stall_queries(RAW / DATASETS["eating"]["file"]), RAW / "onemap_stall_geocode.json"
        )
        key = os.environ.get("LTA_ACCOUNT_KEY")
        if key:
            print("download LTA DataMall passenger volume by train station", flush=True)
            lta_passenger_volume(client, key, RAW)
        else:
            print("LTA_ACCOUNT_KEY not set: station_traffic_monthly stays null", flush=True)


# ----------------------------------------------------------------- geometry (pure Python)

Ring = list[tuple[float, float]]  # (lng, lat)


def _polygons(geom: dict) -> list[list[Ring]]:
    """GeoJSON Polygon/MultiPolygon -> list of polygons, each [outer, *holes], 2-D only."""
    if geom["type"] == "Polygon":
        polys = [geom["coordinates"]]
    elif geom["type"] == "MultiPolygon":
        polys = geom["coordinates"]
    else:
        raise ValueError(f"unexpected geometry {geom['type']}")
    return [[[(float(p[0]), float(p[1])) for p in ring] for ring in poly] for poly in polys]


def _in_ring(x: float, y: float, ring: Ring) -> bool:
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


class AreaShape:
    def __init__(self, area_id: str, polys: list[list[Ring]]):
        self.id = area_id
        self.polys = polys
        xs = [p[0] for poly in polys for p in poly[0]]
        ys = [p[1] for poly in polys for p in poly[0]]
        self.bbox = (min(xs), min(ys), max(xs), max(ys))

    def contains(self, lng: float, lat: float) -> bool:
        x0, y0, x1, y1 = self.bbox
        if not (x0 <= lng <= x1 and y0 <= lat <= y1):
            return False
        for outer, *holes in self.polys:
            if _in_ring(lng, lat, outer) and not any(_in_ring(lng, lat, h) for h in holes):
                return True
        return False

    def centroid(self) -> tuple[float, float]:
        """Area-weighted centroid (lat, lng) of all outer rings minus holes (planar, in degrees)."""
        a_sum = cx = cy = 0.0
        for poly in self.polys:
            for k, ring in enumerate(poly):
                signed = gx = gy = 0.0
                for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1], strict=True):
                    cross = x0 * y1 - x1 * y0
                    signed += cross
                    gx += (x0 + x1) * cross
                    gy += (y0 + y1) * cross
                if signed == 0:
                    continue
                signed /= 2
                weight = abs(signed) * (1.0 if k == 0 else -1.0)  # holes subtract
                cx += gx / (6 * signed) * weight
                cy += gy / (6 * signed) * weight
                a_sum += weight
        return (cy / a_sum, cx / a_sum)


def find_area(shapes: list[AreaShape], lng: float, lat: float) -> str | None:
    for s in shapes:
        if s.contains(lng, lat):
            return s.id
    return None


def _dp(points: Ring, tol: float) -> Ring:
    """Douglas-Peucker on an open polyline (iterative)."""
    import numpy as np

    pts = np.asarray(points, dtype=float)
    n = len(pts)
    if n < 3:
        return list(points)
    keep = np.zeros(n, dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = pts[i], pts[j]
        seg = pts[i + 1 : j]
        d = b - a
        norm = math.hypot(d[0], d[1])
        if norm == 0:
            dist = np.hypot(seg[:, 0] - a[0], seg[:, 1] - a[1])
        else:
            dist = np.abs(d[0] * (seg[:, 1] - a[1]) - d[1] * (seg[:, 0] - a[0])) / norm
        k = int(np.argmax(dist))
        if dist[k] > tol:
            m = i + 1 + k
            keep[m] = True
            stack.append((i, m))
            stack.append((m, j))
    return [tuple(p) for p in pts[keep]]


def simplify_ring(ring: Ring, tol: float) -> Ring | None:
    closed = ring[0] == ring[-1]
    core = ring[:-1] if closed else ring
    if len(core) < 4:
        out = core
    else:
        # split at the point farthest from the first so DP sees two open chains
        x0, y0 = core[0]
        far = max(range(len(core)), key=lambda i: (core[i][0] - x0) ** 2 + (core[i][1] - y0) ** 2)
        a = _dp(core[: far + 1], tol)
        b = _dp(core[far:] + [core[0]], tol)
        out = a[:-1] + b[:-1]
    out = [(round(x, 5), round(y, 5)) for x, y in out]
    dedup: Ring = []
    for p in out:
        if not dedup or dedup[-1] != p:
            dedup.append(p)
    if len(dedup) < 3:  # too small to simplify: keep the rounded original
        dedup = []
        for p in ((round(x, 5), round(y, 5)) for x, y in core):
            if not dedup or dedup[-1] != p:
                dedup.append(p)
    if dedup and dedup[0] == dedup[-1]:
        dedup.pop()
    if len(set(dedup)) < 3:  # a sub-metre sliver that vanishes at 5 dp
        return None
    return dedup + [dedup[0]]


# ----------------------------------------------------------------- processing


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _src(ds: dict[str, str]) -> str:
    return f"{ds['id']} · {ds['title']} · {ds['as_of']}"


def _int(v: str) -> int:
    v = v.strip().replace(",", "")
    if v in ("", "-", "na", "NA"):
        return 0
    return int(float(v))


def load_boundaries() -> tuple[dict, list[AreaShape]]:
    g = json.loads((RAW / DATASETS["boundaries"]["file"]).read_text())
    shapes = [
        AreaShape(f["properties"]["PLN_AREA_N"].strip(), _polygons(f["geometry"])) for f in g["features"]
    ]
    return g, shapes


def write_geojson(g: dict, out: Path, tol: float) -> None:
    feats = []
    for f in g["features"]:
        p = f["properties"]
        pid = p["PLN_AREA_N"].strip()
        polys = []
        for poly in _polygons(f["geometry"]):
            rings = [simplify_ring(r, tol) for r in poly]
            if rings[0] is None:  # outer ring collapsed: drop the sliver polygon
                continue
            polys.append([r for r in rings if r is not None])
        geom = (
            {"type": "Polygon", "coordinates": polys[0]}
            if len(polys) == 1
            else {"type": "MultiPolygon", "coordinates": polys}
        )
        feats.append(
            {
                "type": "Feature",
                "properties": {"id": pid, "name": title_case(pid), "region": title_case(p["REGION_N"])},
                "geometry": geom,
            }
        )
    feats.sort(key=lambda f: f["properties"]["id"])
    fc = {
        "type": "FeatureCollection",
        "source": _src(DATASETS["boundaries"]),
        "simplification": f"Douglas-Peucker tolerance {tol} deg, coordinates rounded to 5 dp",
        "features": feats,
    }
    out.write_text(json.dumps(fc, separators=(",", ":")))


def title_case(s: str) -> str:
    return " ".join(
        w.capitalize() if "-" not in w else "-".join(x.capitalize() for x in w.split("-"))
        for w in s.strip().lower().split()
    )


AGE_BANDS = {"0-19": (0, 19), "20-39": (20, 39), "40-59": (40, 59), "60+": (60, 999)}


def _age_low(ag: str) -> int:
    return int(re.match(r"(\d+)", ag).group(1))  # "0_to_4", "90_and_Over"


def load_population() -> tuple[dict[str, int], dict[str, dict[str, float]], str]:
    src = json.loads((RAW / POPULATION["source_file"]).read_text())
    with zipfile.ZipFile(RAW / POPULATION["zip"]) as z:
        name = next(
            n for n in z.namelist() if n.lower().endswith(".csv") and not n.lower().startswith("notes")
        )
        text = z.read(name).decode("utf-8-sig")
    totals: dict[str, int] = defaultdict(int)
    bands: dict[str, dict[str, int]] = defaultdict(lambda: dict.fromkeys(AGE_BANDS, 0))
    for row in csv.DictReader(io.StringIO(text)):
        pa = row["PA"].strip().upper()
        n = _int(row["Pop"])
        low = _age_low(row["AG"])
        band = next(b for b, (lo, hi) in AGE_BANDS.items() if lo <= low <= hi)
        totals[pa] += n
        bands[pa][band] += n
    shares = {
        pa: {b: round(v / totals[pa], 4) for b, v in bs.items()} for pa, bs in bands.items() if totals[pa] > 0
    }
    as_of = f"{src['reference']} ({src['url']})"
    return dict(totals), shares, as_of


INCOME_BANDS = {
    "<4k": ["NoEmployedPerson", "Below_1_000", "1_000_1_999", "2_000_2_999", "3_000_3_999"],
    "4k-8k": ["4_000_4_999", "5_000_5_999", "6_000_6_999", "7_000_7_999"],
    "8k-12k": ["8_000_8_999", "9_000_9_999", "10_000_10_999", "11_000_11_999"],
    "12k+": [
        "12_000_12_999",
        "13_000_13_999",
        "14_000_14_999",
        "15_000_17_499",
        "17_500_19_999",
        "20_000andOver",
    ],
}


def load_income() -> dict[str, dict[str, float]]:
    out = {}
    with (RAW / DATASETS["income"]["file"]).open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    cols = set(rows[0].keys())
    mapped = {c for cs in INCOME_BANDS.values() for c in cs}
    missing = mapped - cols
    extra = cols - mapped - {"Number", "Total"}
    if missing or extra:
        raise RuntimeError(f"income bins changed: missing={missing} extra={extra}")
    for row in rows:
        pa = row["Number"].strip().upper()
        if pa in ("TOTAL", "OTHERS"):
            continue
        total = _int(row["Total"])
        counts = {b: sum(_int(row[c]) for c in cs) for b, cs in INCOME_BANDS.items()}
        binned = sum(counts.values())
        if total <= 0 or binned <= 0:
            continue
        # SingStat rounds each cell, so bins can differ from the total by a few households
        if abs(binned - total) > max(5, 0.001 * total):
            raise RuntimeError(f"income bins do not add up for {pa}: {binned} vs {total}")
        out[pa] = {b: round(v / binned, 4) for b, v in counts.items()}
    return out


def load_workplace() -> dict[str, int]:
    out = {}
    with (RAW / DATASETS["workplace"]["file"]).open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            pa = row["Number"].strip().upper()
            if pa in (
                "TOTAL",
                "OTHER PLANNING AREAS OR OUTSIDE SINGAPORE",
                "NO FIXED LOCATION FOR WORK",
                "WORKS FROM HOME",
            ):
                continue
            out[pa] = _int(row["Total_Total"])
    return out


def load_stations(shapes: list[AreaShape]) -> list[dict]:
    g = json.loads((RAW / DATASETS["station_exits"]["file"]).read_text())
    exits: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for f in g["features"]:
        name = f["properties"]["STATION_NA"].strip().upper()
        lng, lat = f["geometry"]["coordinates"][:2]
        exits[name].append((float(lng), float(lat)))
    codes: dict[str, list[str]] = defaultdict(list)
    with (RAW / DATASETS["station_codes"]["file"]).open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            codes[row["mrt_station_english"].strip().upper()].append(row["stn_code"].strip().upper())
    stations = []
    for name, pts in sorted(exits.items()):
        lng = sum(p[0] for p in pts) / len(pts)
        lat = sum(p[1] for p in pts) / len(pts)
        m = re.match(r"(.*) (MRT|LRT) STATION$", name)
        base, kind = (m.group(1), m.group(2)) if m else (name, None)
        stations.append(
            {
                "name": title_case(base) + (f" {kind}" if kind else ""),
                "dataset_name": name,
                "type": kind,
                "lat": round(lat, 6),
                "lng": round(lng, 6),
                "exits": len(pts),
                "codes": sorted(set(codes.get(base, []))),
                "area_id": find_area(shapes, lng, lat),
            }
        )
    return stations


def load_station_traffic(stations: list[dict]) -> tuple[dict[str, int], str] | None:
    """Monthly tap-ins + tap-outs per planning area from LTA DataMall PV/Train CSVs in raw/."""
    files = sorted(RAW.glob("lta_pv_train_*.csv"))
    if not files:
        return None
    code_area: dict[str, str] = {}
    for s in stations:
        for c in s["codes"]:
            if s["area_id"]:
                code_area[c] = s["area_id"]
    by_month: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    unmatched: set[str] = set()
    for path in files:
        with path.open(newline="", encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                pt_codes = [c.strip().upper() for c in row["PT_CODE"].split("/") for c in c.split("-")]
                areas = {code_area[c] for c in pt_codes if c in code_area}
                if len(areas) != 1:
                    unmatched.add(row["PT_CODE"])
                    continue
                vol = _int(row["TOTAL_TAP_IN_VOLUME"]) + _int(row["TOTAL_TAP_OUT_VOLUME"])
                by_month[row["YEAR_MONTH"].strip()][areas.pop()] += vol
    if unmatched:
        print(
            f"  warning: {len(unmatched)} LTA station codes not matched to an area: {sorted(unmatched)[:10]}"
        )
    month = max(by_month)
    return dict(by_month[month]), month


def load_food_outlets(shapes: list[AreaShape]) -> tuple[dict[str, int], dict[str, int]]:
    postal = json.loads((RAW / "onemap_postal_geocode.json").read_text())
    stall_path = RAW / "onemap_stall_geocode.json"
    stalls = json.loads(stall_path.read_text()) if stall_path.exists() else {}
    counts: dict[str, int] = defaultdict(int)
    stats = {
        "rows": 0,
        "by_postal_code": 0,
        "by_stall_address": 0,
        "no_exact_match": 0,
        "outside_areas": 0,
        "counted": 0,
    }
    ll_area: dict[tuple[float, float], str | None] = {}
    with (RAW / DATASETS["eating"]["file"]).open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            stats["rows"] += 1
            addr = row["premises_address"].strip()
            m = POSTAL_RE.search(addr)
            if m:
                key, cache, kind = m.group(1), postal, "by_postal_code"
            else:
                key, cache, kind = stall_query(addr), stalls, "by_stall_address"
            if key is not None and key not in cache:
                raise RuntimeError(f"{key!r} not geocoded yet; run without --offline")
            hit = cache.get(key) if key is not None else None
            if hit is None:
                stats["no_exact_match"] += 1
                continue
            lat, lng = hit["latlng"] if isinstance(hit, dict) else hit
            if (lat, lng) not in ll_area:
                ll_area[(lat, lng)] = find_area(shapes, lng, lat)
            area = ll_area[(lat, lng)]
            if area is None:
                stats["outside_areas"] += 1
                continue
            counts[area] += 1
            stats[kind] += 1
            stats["counted"] += 1
    return dict(counts), stats


def process() -> None:
    sys.path.insert(0, str(HERE.parent.parent))
    from tools.models import Area

    g, shapes = load_boundaries()
    regions = {
        f["properties"]["PLN_AREA_N"].strip(): title_case(f["properties"]["REGION_N"]) for f in g["features"]
    }

    tol = 0.00001  # ~1 m
    out_geo = HERE / "planning_areas.geojson"
    write_geojson(g, out_geo, tol)

    residents, age_shares, pop_as_of = load_population()
    income = load_income()
    workplace = load_workplace()
    stations = load_stations(shapes)
    food, food_stats = load_food_outlets(shapes)
    traffic = load_station_traffic(stations)

    unknown = (set(residents) | set(income) | set(workplace)) - set(regions)
    if unknown:
        raise RuntimeError(f"planning areas not in the boundary file: {sorted(unknown)}")

    max_work = max(workplace.values())
    pop_src = f"{POPULATION['id']} · {POPULATION['title']} · {pop_as_of}"
    food_src = (
        f"{_src(DATASETS['eating'])}; geocoded with OneMap search API by postal code, or block + road "
        f"for stalls (retrieved {RETRIEVED}); point-in-polygon on {DATASETS['boundaries']['id']}"
    )
    st_src = (
        f"{_src(DATASETS['station_exits'])}; station point = mean of its exits; point-in-polygon on "
        f"{DATASETS['boundaries']['id']}"
    )

    areas = []
    for s in sorted(shapes, key=lambda s: s.id):
        pid = s.id
        src: dict[str, str] = {
            "id": _src(DATASETS["boundaries"]),
            "name": _src(DATASETS["boundaries"]),
            "region": _src(DATASETS["boundaries"]),
            "centroid": f"computed: area-weighted polygon centroid of {DATASETS['boundaries']['id']}",
        }
        a: dict[str, Any] = {"id": pid, "name": title_case(pid), "region": regions[pid]}
        if pid in residents:
            a["residents"] = residents[pid]
            src["residents"] = pop_src
        if pid in age_shares:
            a["age_shares"] = age_shares[pid]
            src["age_shares"] = pop_src
        if pid in income:
            a["income_shares"] = income[pid]
            src["income_shares"] = _src(DATASETS["income"])
        if pid in workplace:
            a["daytime_proxy"] = round(workplace[pid] / max_work, 4)
            src["daytime_proxy"] = (
                f"{_src(DATASETS['workplace'])}; employed residents working in the area / max over areas"
            )
        if traffic is not None:
            vols, month = traffic
            a["station_traffic_monthly"] = vols.get(pid, 0)
            src["station_traffic_monthly"] = (
                f"LTA DataMall PV/Train · Passenger Volume by Train Stations · {month}; "
                "tap-ins + tap-outs at stations inside the area"
            )
        a["food_outlets"] = food.get(pid, 0)
        src["food_outlets"] = food_src
        lat, lng = s.centroid()
        a["centroid"] = (round(lat, 6), round(lng, 6))
        a["sources"] = src
        a["simulated_fields"] = []
        areas.append(Area.model_validate(a).model_dump(mode="json"))

    by_area: dict[str, list[dict]] = defaultdict(list)
    for st in stations:
        if st["area_id"]:
            by_area[st["area_id"]].append(
                {k: st[k] for k in ("name", "lat", "lng", "type", "codes", "exits")}
            )
    for a in areas:
        a["sources"]["stations"] = st_src
    stations_out = {
        "source": st_src,
        "station_codes_source": _src(DATASETS["station_codes"]),
        "unassigned": [s["name"] for s in stations if not s["area_id"]],
        "areas": {
            s.id: sorted(by_area.get(s.id, []), key=lambda x: x["name"])
            for s in sorted(shapes, key=lambda s: s.id)
        },
    }
    (HERE / "stations.json").write_text(json.dumps(stations_out, indent=1, ensure_ascii=False) + "\n")
    (HERE / "areas.json").write_text(json.dumps(areas, indent=1, ensure_ascii=False) + "\n")

    print(f"food outlets: {food_stats}")
    print(f"stations: {len(stations)} total, {len(stations_out['unassigned'])} outside every area")
    write_checksums()


def write_checksums() -> None:
    raw_files = sorted(p for p in RAW.iterdir() if p.is_file() and not p.name.startswith("."))
    outs = [HERE / n for n in ("planning_areas.geojson", "stations.json", "areas.json")]
    lines = [f"{sha256(p)}  {p.relative_to(HERE)}" for p in raw_files + outs]
    (HERE / "checksums.txt").write_text("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="reprocess from raw/ without network")
    ap.add_argument("--refresh", action="store_true", help="re-download every raw file")
    args = ap.parse_args(argv)
    if not args.offline:
        download(refresh=args.refresh)
    process()


if __name__ == "__main__":
    main()
