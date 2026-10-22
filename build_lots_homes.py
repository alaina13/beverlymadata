#!/usr/bin/env python3
"""
Open Beverly: Lots and Homes Over Time builder
Summarizes Beverly's single-family properties by decade built, lot size, and
assessed value, and writes lots_homes.json for lots-homes.html.

Source:
  City of Beverly GIS (BeverlyGIS), Combined_gdb FeatureServer, layer 5
  (Parcels). Fields used: LUC (land use code), LAND_ACRE, FIN_AREA (finished
  living area), YR_BUILT, ZONE_1, TOTAL_VAL, LAND_VAL, BLDG_VAL. Values are the
  City's FY2026 assessments.

Method:
  - Single-family = land use code 101. Lot size = LAND_ACRE x 43,560 sq ft.
  - Home size = finished living area (FIN_AREA), not gross building area.
  - Decades group YR_BUILT; everything before 1900 is one group.
  - Medians are reported in cells of at least MIN_N homes; smaller cells are
    left blank so one house cannot drive a figure.
  - Regression: OLS of log(finished area) on decade built (1950s as the
    baseline), log(lot size), and zone dummies for zones with 50+ homes,
    with heteroskedasticity-robust (HC1) standard errors.

Requires: numpy

Usage:
    python3 build_lots_homes.py
"""

import collections
import json
import statistics as st
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

import numpy as np

OUT = Path(__file__).parent / "lots_homes.json"
SERVICE_URL = "https://services1.arcgis.com/IVwtHDf2UjOF6PcX/arcgis/rest/services/Combined_gdb/FeatureServer/5/query"
FIELDS = "LOC_ID,ZONE_1,LAND_ACRE,FIN_AREA,YR_BUILT,TOTAL_VAL,LAND_VAL,BLDG_VAL"
SQ_FT_PER_ACRE = 43560
MIN_N = 30
BASE_DECADE = "1950s"

BANDS = [("Under 5,000", 0, 5000), ("5,000 to 9,999", 5000, 10000),
         ("10,000 to 19,999", 10000, 20000), ("20,000 and over", 20000, float("inf"))]
DECADES = ["Before 1900"] + [f"{d}s" for d in range(1900, 2030, 10)]
VALUE_BIN_TOP = 30000     # 1,000 sq ft bins up to here, then one "and over" bin


def fetch():
    rows, offset = [], 0
    while True:
        q = urllib.parse.urlencode({
            "where": "LUC='101'", "outFields": FIELDS, "returnGeometry": "false", "f": "json",
            "resultOffset": offset, "resultRecordCount": 2000, "orderByFields": "OBJECTID",
        })
        req = urllib.request.Request(f"{SERVICE_URL}?{q}", headers={"User-Agent": "OpenBeverly/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            page = [f["attributes"] for f in json.loads(resp.read().decode("utf-8"))["features"]]
        rows += page
        if len(page) < 2000:
            return rows
        offset += 2000


def decade_of(year):
    return "Before 1900" if year < 1900 else f"{year // 10 * 10}s"


def band_of(sf):
    return next(i for i, (_, lo, hi) in enumerate(BANDS) if lo <= sf < hi)


def median_or_none(values):
    return round(st.median(values)) if len(values) >= MIN_N else None


def regression(homes):
    zones = [z for z, n in collections.Counter(h["zone"] for h in homes).items() if z and n >= 50]
    decades = [d for d in DECADES if d != BASE_DECADE]
    X = np.array([[1.0] + [float(h["decade"] == d) for d in decades] + [np.log(h["lot"])]
                  + [float(h["zone"] == z) for z in zones[1:]] for h in homes])
    y = np.log(np.array([h["fin"] for h in homes], dtype=float))
    # QR solve and einsum products: avoids spurious BLAS warnings seen with np.matmul on macOS
    Q, R = np.linalg.qr(X)
    beta = np.linalg.solve(R, np.einsum("ij,i->j", Q, y))
    resid = y - np.einsum("ij,j->i", X, beta)
    n, k = X.shape
    Rinv = np.linalg.inv(R)
    bread = np.einsum("ij,kj->ik", Rinv, Rinv)
    meat = np.einsum("ij,i,ik->jk", X, resid ** 2, X)
    cov = np.einsum("ij,jk,kl->il", bread, meat, bread) * n / (n - k)
    se = np.sqrt(np.diag(cov))
    out = []
    for i, d in enumerate(decades, start=1):
        pct = lambda c: round(100 * (np.exp(c) - 1), 1)
        out.append({"decade": d, "pct": pct(beta[i]), "lo": pct(beta[i] - 1.96 * se[i]), "hi": pct(beta[i] + 1.96 * se[i])})
    r2 = 1 - resid.var() / y.var()
    return {"base": BASE_DECADE, "n": n, "r2": round(float(r2), 3), "zones": zones, "rows": out}


def main():
    print("\n🏡  Open Beverly: Lots and Homes Over Time")
    raw = fetch()
    print(f"  {len(raw)} single-family parcels")
    homes = [{"zone": r["ZONE_1"], "lot": r["LAND_ACRE"] * SQ_FT_PER_ACRE, "fin": r["FIN_AREA"],
              "year": r["YR_BUILT"], "total": r["TOTAL_VAL"], "land": r["LAND_VAL"], "bldg": r["BLDG_VAL"]}
             for r in raw if r["LAND_ACRE"]]
    for h in homes:
        h["band"] = band_of(h["lot"])
        h["decade"] = decade_of(h["year"]) if h["year"] else None

    dated = [h for h in homes if h["decade"] and h["fin"]]

    decades = []
    for d in DECADES:
        grp = [h for h in dated if h["decade"] == d]
        counts = collections.Counter(h["band"] for h in grp)
        decades.append({
            "decade": d, "n": len(grp),
            "med_fin": median_or_none([h["fin"] for h in grp]),
            "avg_fin": round(st.mean(h["fin"] for h in grp)),
            "med_lot": round(st.median(h["lot"] for h in grp)),
            "band_n": [counts.get(i, 0) for i in range(len(BANDS))],
            "med_total": median_or_none([h["total"] for h in grp if h["total"]]),
        })

    strat = []
    for d in DECADES:
        cells = []
        for i in range(len(BANDS)):
            grp = [h["fin"] for h in dated if h["decade"] == d and h["band"] == i]
            cells.append({"n": len(grp), "med": median_or_none(grp)})
        strat.append({"decade": d, "cells": cells})

    valued = [h for h in homes if h["total"]]
    value_bins = []
    for lo in range(1000, VALUE_BIN_TOP, 1000):
        grp = [h for h in valued if lo <= h["lot"] < lo + 1000]
        if len(grp) >= MIN_N:
            value_bins.append({"label": f"{lo:,} to {lo + 999:,}", "lo": lo, "n": len(grp),
                               "med_total": round(st.median(h["total"] for h in grp)),
                               "med_land": round(st.median(h["land"] for h in grp)),
                               "med_bldg": round(st.median(h["bldg"] for h in grp))})
    grp = [h for h in valued if h["lot"] >= VALUE_BIN_TOP]
    value_bins.append({"label": f"{VALUE_BIN_TOP:,} and over", "lo": VALUE_BIN_TOP, "n": len(grp),
                       "med_total": round(st.median(h["total"] for h in grp)),
                       "med_land": round(st.median(h["land"] for h in grp)),
                       "med_bldg": round(st.median(h["bldg"] for h in grp))})

    value_bands = []
    for i, (name, _, _) in enumerate(BANDS):
        grp = [h for h in valued if h["band"] == i]
        sized = [h for h in grp if h["fin"]]
        value_bands.append({"band": name, "n": len(grp),
                            "med_total": round(st.median(h["total"] for h in grp)),
                            "med_land": round(st.median(h["land"] for h in grp)),
                            "med_bldg": round(st.median(h["bldg"] for h in grp)),
                            "med_per_sf": round(st.median(h["total"] / h["fin"] for h in sized))})

    result = {
        "updated": datetime.now().strftime("%Y-%m-%d"),
        "homes": len(homes), "dated": len(dated), "no_year": sum(1 for h in homes if not h["year"]),
        "med_fin_all": round(st.median(h["fin"] for h in homes if h["fin"])),
        "bands": [b[0] for b in BANDS], "min_n": MIN_N,
        "decades": decades, "strat": strat, "regression": regression(dated),
        "value_bins": value_bins, "value_bands": value_bands,
    }
    with open(OUT, "w") as fh:
        json.dump(result, fh, separators=(",", ":"))
    print(f"  ✅  Written to {OUT}")


if __name__ == "__main__":
    main()
