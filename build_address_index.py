#!/usr/bin/env python3
"""
Beverly Data — Address Index Builder
Extracts a lightweight address -> lat/lng lookup from parcels.json for
client-side address search (e.g. the parking map's destination search).

Unlike build_pavement_address_index.py, this doesn't match to any other
dataset, it's just parcels.json stripped down to what a search box needs,
so pages don't have to fetch the full 3.7MB parcels file just to geocode
an address the user typed.

Usage:
    python3 build_address_index.py
"""

import json
import re
from datetime import datetime
from pathlib import Path

OUT_DIR = Path(__file__).parent


def normalize(addr):
    key = re.sub(r"\.", "", addr).lower().strip()
    return re.sub(r"\s+", " ", key)


def main():
    print("\nBeverly Data — Address Index Builder\n")

    parcels = json.load(open(OUT_DIR / "parcels.json"))
    print(f"  Loaded {len(parcels)} parcels")

    index = {}
    skipped = 0
    for p in parcels:
        addr = p.get("addr")
        lat, lng = p.get("lat"), p.get("lng")
        if not addr or lat is None or lng is None:
            skipped += 1
            continue
        index[normalize(addr)] = {"lat": lat, "lng": lng}

    print(f"  Indexed {len(index)} addresses, {skipped} skipped (missing address or coordinates)")

    output = {
        "updated": datetime.now().strftime("%Y-%m-%d"),
        "address_count": len(index),
        "addresses": index,
    }

    path = OUT_DIR / "address_index.json"
    with open(path, "w") as f:
        json.dump(output, f, separators=(",", ":"))
    print(f"\n  Written to {path}")


if __name__ == "__main__":
    main()
