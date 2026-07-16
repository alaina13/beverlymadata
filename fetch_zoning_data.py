#!/usr/bin/env python3
"""
Beverly Data — Zoning Map Fetcher
Pulls Beverly's zoning districts and overlay/historic districts and writes
zoning.geojson.

Source:
  - City of Beverly GIS (BeverlyGIS), "Combined_gdb" FeatureServer, embedded
    in the public "Zoning Map" ArcGIS Instant App.

Usage:
    python3 fetch_zoning_data.py
"""

import json
import urllib.request
from datetime import datetime
from pathlib import Path

OUT_DIR = Path(__file__).parent

SERVICE_URL = "https://services1.arcgis.com/IVwtHDf2UjOF6PcX/arcgis/rest/services/Combined_gdb/FeatureServer"

# Layer 31 = base zoning districts (R6, CN, IG, etc.)
# Layer 21 = overlay + historic districts (WPOD, MBTA, NHL, LHD, etc.)
DISTRICT_LAYER = 31
OVERLAY_LAYER = 21


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "BeverlyData/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_layer_geojson(layer_id, out_fields):
    url = (
        f"{SERVICE_URL}/{layer_id}/query"
        f"?where=1=1&outFields={','.join(out_fields)}&outSR=4326&f=geojson"
    )
    return fetch_json(url)


def clean_district(feat):
    p = feat["properties"]
    feat["properties"] = {
        "kind": "district",
        "code": p.get("ZONE_"),
        "label": (p.get("Description") or "").title(),
    }
    return feat


def clean_overlay(feat):
    p = feat["properties"]
    feat["properties"] = {
        "kind": "overlay",
        "code": p.get("CATEGORY"),
        "label": (p.get("NAME_SITE") or "").title(),
        "classification": (p.get("CLASSIFICATION") or "").title(),
    }
    return feat


def main():
    print("\n🗺️   Beverly Data — Zoning Map Fetcher")
    print(f"    {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    print("  Fetching base zoning districts…")
    districts = fetch_layer_geojson(DISTRICT_LAYER, ["ZONE_", "Description"])
    district_feats = [clean_district(f) for f in districts["features"] if f.get("geometry")]
    print(f"    Retrieved {len(district_feats)} districts")

    print("  Fetching overlay + historic districts…")
    overlays = fetch_layer_geojson(OVERLAY_LAYER, ["CATEGORY", "NAME_SITE", "CLASSIFICATION"])
    overlay_feats = [clean_overlay(f) for f in overlays["features"] if f.get("geometry")]
    print(f"    Retrieved {len(overlay_feats)} overlay/historic districts")

    output = {
        "type": "FeatureCollection",
        "updated": datetime.now().strftime("%Y-%m-%d"),
        "sources": {
            "zoning": "City of Beverly GIS (BeverlyGIS), Zoning Map ArcGIS Instant App — Combined_gdb/FeatureServer layer 31",
            "overlay": "City of Beverly GIS (BeverlyGIS), Zoning Map ArcGIS Instant App — Combined_gdb/FeatureServer layer 21",
        },
        "features": district_feats + overlay_feats,
    }

    path = OUT_DIR / "zoning.geojson"
    with open(path, "w") as f:
        json.dump(output, f)
    print(f"\n  ✅  Written to {path}")


if __name__ == "__main__":
    main()
