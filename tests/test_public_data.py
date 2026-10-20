"""Checks on the committed public-data layer (data/public/, SPEC §10)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tools.models import Area

PUBLIC = Path(__file__).resolve().parent.parent / "data" / "public"

# Fields that carry a value only when a real dataset backs them.
DATA_FIELDS = [
    "residents",
    "age_shares",
    "income_shares",
    "daytime_proxy",
    "station_traffic_monthly",
    "food_outlets",
    "rent_psf_month_sgd",
    "centroid",
]


@pytest.fixture(scope="module")
def areas() -> list[Area]:
    raw = json.loads((PUBLIC / "areas.json").read_text())
    return [Area.model_validate(a) for a in raw]


@pytest.fixture(scope="module")
def geo() -> dict:
    return json.loads((PUBLIC / "planning_areas.geojson").read_text())


def test_areas_validate_and_unique(areas):
    ids = [a.id for a in areas]
    assert len(ids) == len(set(ids))
    assert len(areas) >= 50


def test_ids_match_geojson(areas, geo):
    geo_ids = {f["properties"]["id"] for f in geo["features"]}
    assert {a.id for a in areas} == geo_ids
    for f in geo["features"]:
        p = f["properties"]
        assert set(p) == {"id", "name", "region"}
        assert p["id"] == p["id"].upper()
        assert f["geometry"]["type"] in ("Polygon", "MultiPolygon")


def test_geojson_size_and_precision(geo):
    assert (PUBLIC / "planning_areas.geojson").stat().st_size <= 1_600_000

    def coords(g):
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        for poly in polys:
            for ring in poly:
                assert ring[0] == ring[-1] and len(ring) >= 4
                yield from ring

    for f in geo["features"]:
        for lng, lat in coords(f["geometry"]):
            assert 103.5 < lng < 104.2 and 1.1 < lat < 1.5
            assert round(lng, 5) == lng and round(lat, 5) == lat


def test_shares_sum_to_one(areas):
    for a in areas:
        for shares in (a.age_shares, a.income_shares):
            if shares:
                assert abs(sum(shares.values()) - 1.0) < 0.002, a.id
                assert all(0.0 <= v <= 1.0 for v in shares.values())
        if a.age_shares:
            assert set(a.age_shares) == {"0-19", "20-39", "40-59", "60+"}
        if a.income_shares:
            assert set(a.income_shares) == {"<4k", "4k-8k", "8k-12k", "12k+"}


def test_no_negative_counts(areas):
    for a in areas:
        for v in (a.residents, a.food_outlets, a.station_traffic_monthly):
            assert v is None or v >= 0, a.id
        assert a.daytime_proxy is None or 0.0 <= a.daytime_proxy <= 1.0


def test_every_value_has_a_source(areas):
    for a in areas:
        for field in DATA_FIELDS:
            value = getattr(a, field)
            if value not in (None, {}, []):
                assert a.sources.get(field), f"{a.id}.{field} has no source"


def test_only_real_data(areas):
    assert all(a.simulated_fields == [] for a in areas)


def test_centroids_inside_singapore(areas):
    for a in areas:
        assert a.centroid is not None
        lat, lng = a.centroid
        assert 1.1 < lat < 1.5 and 103.5 < lng < 104.2


def test_stations_file(areas):
    st = json.loads((PUBLIC / "stations.json").read_text())
    assert set(st["areas"]) == {a.id for a in areas}
    names = [s["name"] for ss in st["areas"].values() for s in ss]
    assert len(names) == len(set(names)) and len(names) > 100
    for ss in st["areas"].values():
        for s in ss:
            assert 1.1 < s["lat"] < 1.5 and 103.5 < s["lng"] < 104.2


def test_checksums_cover_outputs():
    lines = (PUBLIC / "checksums.txt").read_text().splitlines()
    sums = dict(reversed(line.split("  ", 1)) for line in lines)
    for name in ("areas.json", "planning_areas.geojson", "stations.json"):
        assert sums[name] == hashlib.sha256((PUBLIC / name).read_bytes()).hexdigest()
