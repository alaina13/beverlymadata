#!/usr/bin/env python3
"""
Beverly Data — Pavement Condition Fetcher
Pulls Beverly's citywide Pavement Condition Index (PCI) inventory and writes
pavement_pci.json.

Source:
  - City of Beverly GIS (BeverlyGIS), "streets_cyvl_update" FeatureServer,
    embedded in the public "Beverly Streets" ArcGIS web app.

Usage:
    python3 fetch_pavement_data.py
"""

import json
import urllib.request
from datetime import datetime
from pathlib import Path

OUT_DIR = Path(__file__).parent

SERVICE_URL = "https://services1.arcgis.com/IVwtHDf2UjOF6PcX/arcgis/rest/services/streets_cyvl_update/FeatureServer/0/query"

FIELDS = [
    "streetname", "fromstreetname", "tostreetname", "ss_id",
    "pci", "class", "ward", "functional_class", "length_ft",
    "pci_2017", "pci_2019", "pci_2021", "pci_2022", "pci_2023", "pci_2024",
    "survey_date",
]

CONDITION_RANGES = {
    "Excellent": (86, 100),
    "Good": (71, 85),
    "Fair": (56, 70),
    "Poor": (41, 55),
    "Very Poor": (26, 40),
    "Serious": (17, 25),
}


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "BeverlyData/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_all_segments():
    print("  Fetching Beverly citywide PCI inventory…")
    params = f"?where=1=1&outFields={','.join(FIELDS)}&returnGeometry=false&f=json"
    data = fetch_json(SERVICE_URL + params)
    feats = [f["attributes"] for f in data.get("features", [])]
    print(f"    Retrieved {len(feats)} segments")
    return feats


def title_case(name):
    name = name.strip() if name else name
    return name.title() if name else None


def clean_segment(a):
    return {
        "ss_id": a.get("ss_id"),
        "street": title_case(a.get("streetname")),
        "from": title_case(a.get("fromstreetname")),
        "to": title_case(a.get("tostreetname")),
        "pci": a.get("pci"),
        "condition": a.get("class"),
        "ward": a.get("ward"),
        "functional_class": a.get("functional_class"),
        "length_ft": a.get("length_ft"),
        "pci_history": {
            "2017": a.get("pci_2017"),
            "2019": a.get("pci_2019"),
            "2021": a.get("pci_2021"),
            "2022": a.get("pci_2022"),
            "2023": a.get("pci_2023"),
            "2024": a.get("pci_2024"),
        },
    }


def main():
    print("\n🛣️   Beverly Data — Pavement Condition Fetcher")
    print(f"    {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    raw = fetch_all_segments()
    segments = [clean_segment(a) for a in raw if a.get("streetname")]

    output = {
        "updated": datetime.now().strftime("%Y-%m-%d"),
        "segment_count": len(segments),
        "current_pci_year": 2024,
        "condition_ranges": CONDITION_RANGES,
        "segments": segments,
        "sources": {
            "pci_inventory": "City of Beverly GIS (BeverlyGIS), Beverly Streets ArcGIS web app — streets_cyvl_update FeatureServer",
        },
    }

    path = OUT_DIR / "pavement_pci.json"
    with open(path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  ✅  Written to {path}")


if __name__ == "__main__":
    main()
