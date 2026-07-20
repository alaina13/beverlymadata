#!/usr/bin/env python3
"""
Beverly Data — Street Width Fetcher
Pulls Beverly's street pavement footprint polygons (width, lanes, pavement
type, sidewalk and curb info per segment) and writes street_width.geojson.

Source:
  - City of Beverly GIS (BeverlyGIS), "Combined_gdb" FeatureServer, layer 83
    (Street_MasterPoly).

Usage:
    python3 fetch_street_width.py
"""

import json
import urllib.request
from datetime import datetime
from pathlib import Path

OUT_DIR = Path(__file__).parent

SERVICE_URL = "https://services1.arcgis.com/IVwtHDf2UjOF6PcX/arcgis/rest/services/Combined_gdb/FeatureServer"
LAYER = 83

FIELDS = [
    "NAME", "FROM_STREE", "TO_STREET", "Width", "Length", "Lanes",
    "Pave_Type", "Sidewalk_O", "Sidewalk_E", "Odd_Curb_T", "Even_Curb_",
]

PAVE_TYPES = {"BC": "Bituminous Concrete", "GR": "Gravel"}


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "BeverlyData/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def title_or_none(v):
    if v is None:
        return None
    v = v.strip()
    return v.title() if v else None


def clean(feat):
    p = feat["properties"]
    feat["properties"] = {
        "name": title_or_none(p.get("NAME")),
        "from_street": title_or_none(p.get("FROM_STREE")),
        "to_street": title_or_none(p.get("TO_STREET")),
        "width": p.get("Width") or None,  # 0 is a data placeholder, not a real width
        "length": round(p["Length"]) if p.get("Length") else None,
        "lanes": p.get("Lanes") or None,
        "pave_type": PAVE_TYPES.get((p.get("Pave_Type") or "").strip()),
        "sidewalk_odd": title_or_none(p.get("Sidewalk_O")),
        "sidewalk_even": title_or_none(p.get("Sidewalk_E")),
        "curb_odd": title_or_none(p.get("Odd_Curb_T")),
        "curb_even": title_or_none(p.get("Even_Curb_")),
    }
    return feat


def main():
    print("\n Beverly Data — Street Width Fetcher")
    print(f"    {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    url = f"{SERVICE_URL}/{LAYER}/query?where=1=1&outFields={','.join(FIELDS)}&outSR=4326&f=geojson"
    print("  Fetching street pavement footprints…")
    raw = fetch_json(url)
    feats = [clean(f) for f in raw["features"] if f.get("geometry")]
    print(f"    Retrieved {len(feats)} segments ({sum(1 for f in feats if f['properties']['width'])} with width data)")

    output = {
        "type": "FeatureCollection",
        "updated": datetime.now().strftime("%Y-%m-%d"),
        "sources": {
            "street_width": "City of Beverly GIS (BeverlyGIS) — Combined_gdb/FeatureServer layer 83 (Street_MasterPoly)",
        },
        "features": feats,
    }

    path = OUT_DIR / "street_width.geojson"
    with open(path, "w") as f:
        json.dump(output, f)
    print(f"\n  Written to {path}")


if __name__ == "__main__":
    main()
