#!/usr/bin/env python3
"""
Beverly Data — Pavement Address Index Builder
Matches every parcel address to its nearest pavement segment (by ss_id) and
writes pavement_address_index.json.

Source geometry:
  - City of Beverly GIS (BeverlyGIS), "streets_cyvl_update" FeatureServer,
    same service as fetch_pavement_data.py, queried here with geometry.

Method:
  - Parse each parcel address into house number + street name.
  - Restrict candidate segments to those sharing the parcel's normalized
    street name (segments citywide are grouped by streetname).
  - Pick the segment whose polyline is closest to the parcel's lat/lng
    (equirectangular approximation, adequate at Beverly's scale).
  - Addresses whose street isn't in the PCI inventory (state highways,
    private roads, unsurveyed streets) are left unmatched.

Usage:
    python3 build_pavement_address_index.py
"""

import json
import math
import re
import urllib.request
from datetime import datetime
from pathlib import Path

OUT_DIR = Path(__file__).parent

SEGMENTS_URL = (
    "https://services1.arcgis.com/IVwtHDf2UjOF6PcX/arcgis/rest/services/"
    "streets_cyvl_update/FeatureServer/0/query"
    "?where=1%3D1&outFields=streetname,ss_id&returnGeometry=true&f=geojson"
)

ADDR_RE = re.compile(
    r'^\s*\d+[A-Za-z]?(?:\s*-\s*\d+[A-Za-z]?)?\s+(?:REAR\s+|R\s+)?(.+?)\s*$',
    re.IGNORECASE,
)

# Beyond this, the nearest surveyed segment on the parcel's street is too far
# to be a trustworthy match (e.g. long streets with sparse coverage) — drop
# rather than show a misleading result.
MAX_MATCH_DIST_M = 150


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "BeverlyData/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def norm_street(s):
    return re.sub(r"\.", "", s or "").lower().strip()


def parse_addr(addr):
    m = ADDR_RE.match(addr or "")
    if not m:
        return None
    return norm_street(m.group(1))


def point_to_segment_dist_m(px, py, ax, ay, bx, by):
    """Distance in meters from point p to line segment a-b, all in local xy meters."""
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def make_projector(lat0):
    """Local equirectangular projection (meters) centered at lat0, adequate for Beverly's extent."""
    m_per_deg_lat = 111_320.0
    m_per_deg_lng = 111_320.0 * math.cos(math.radians(lat0))

    def project(lng, lat):
        return (lng * m_per_deg_lng, lat * m_per_deg_lat)

    return project


def nearest_segment(px, py, candidates):
    best_ss_id, best_dist = None, float("inf")
    for ss_id, coords in candidates:
        for i in range(len(coords) - 1):
            ax, ay = coords[i]
            bx, by = coords[i + 1]
            d = point_to_segment_dist_m(px, py, ax, ay, bx, by)
            if d < best_dist:
                best_dist, best_ss_id = d, ss_id
    return best_ss_id, best_dist


def main():
    print("\nBeverly Data — Pavement Address Index Builder\n")

    print("  Fetching segment geometry…")
    seg_data = fetch_json(SEGMENTS_URL)
    print(f"    Retrieved {len(seg_data['features'])} segments")

    project = make_projector(42.55)

    street_groups = {}
    for feat in seg_data["features"]:
        street = norm_street(feat["properties"]["streetname"])
        ss_id = feat["properties"]["ss_id"]
        coords = [project(lng, lat) for lng, lat in feat["geometry"]["coordinates"]]
        street_groups.setdefault(street, []).append((ss_id, coords))

    print("  Loading parcels…")
    parcels = json.load(open(OUT_DIR / "parcels.json"))
    print(f"    Loaded {len(parcels)} parcels")

    index = {}
    matched, unmatched = 0, 0
    for p in parcels:
        addr = p.get("addr")
        lat, lng = p.get("lat"), p.get("lng")
        if not addr or lat is None or lng is None:
            continue

        street = parse_addr(addr)
        if street is None:
            unmatched += 1
            continue

        candidates = street_groups.get(street)
        if candidates is None:
            street_noext = re.sub(r"\s+ext$", "", street)
            candidates = street_groups.get(street_noext)
        if candidates is None:
            unmatched += 1
            continue

        px, py = project(lng, lat)
        ss_id, dist_m = nearest_segment(px, py, candidates)
        if ss_id is None or dist_m > MAX_MATCH_DIST_M:
            unmatched += 1
            continue

        key = re.sub(r"\.", "", addr).lower().strip()
        key = re.sub(r"\s+", " ", key)
        index[key] = {"ss_id": ss_id, "dist_m": round(dist_m, 1)}
        matched += 1

    print(f"    Matched {matched} addresses, {unmatched} unmatched (dropped beyond {MAX_MATCH_DIST_M}m or off-inventory)")

    output = {
        "updated": datetime.now().strftime("%Y-%m-%d"),
        "address_count": len(index),
        "addresses": index,
    }

    path = OUT_DIR / "pavement_address_index.json"
    with open(path, "w") as f:
        json.dump(output, f, separators=(",", ":"))
    print(f"\n  Written to {path}")


if __name__ == "__main__":
    main()
