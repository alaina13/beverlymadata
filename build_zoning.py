#!/usr/bin/env python3
"""
Open Beverly: Zoning Comparison builder
Compares every lot in a residential district against the district's
dimensional requirements and writes zoning_<district>.geojson for each
district in DISTRICTS (currently RHD and RMD).

Sources:
  - City of Beverly GIS (BeverlyGIS), Combined_gdb FeatureServer:
      layer 5  Parcels (zone, units, stories, land use, garages)
      layer 70 Roofprint (building footprints)
      layer 79 Driveway_Poly, layer 80 Parking_Poly (paved areas)
      layer 83 Street_MasterPoly (street pavement polygons)
  - zoning.geojson (MBTA Communities Overlay boundary; see fetch_zoning_data.py)
  - Beverly Zoning Ordinance Ch. 300: § 300-36 (RMD), § 300-37 (RHD),
    § 300-140 (MBTA overlay), § 300-59 and § 300-64 (parking), Article II
    definitions ("Frontage", "Setback", "Yard, front")

Method (estimates, not surveys):
  - Condo records stacked on one lot polygon are combined by LOC_ID.
  - Principal building = largest roofprint whose interior point is on the lot.
  - Frontage = longest unbroken lot edge that is not shared with another parcel
    and lies within 15 m of street pavement.
  - Corner lots: either street may be the front yard (Art. II), so each street
    is tested and the more favorable result is kept.
  - Tolerance: roofprints include eaves while setbacks are measured to the
    foundation, so results within 3 ft (5% for lot area) are "close".
  - Parking (district totals only, not published per lot): mapped driveway and
    parking area on each lot converted to spaces at 162 sq ft per space (high)
    or 200 sq ft on driveways and 330 sq ft in parking lots (low), plus
    assessor-recorded garages at 250 sq ft per space.

Requires: geopandas, shapely 2.x

Usage:
    python3 build_zoning.py
"""

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely import STRtree
from shapely.geometry import LineString
from shapely.ops import linemerge, unary_union

OUT_DIR = Path(__file__).parent
SERVICE_URL = "https://services1.arcgis.com/IVwtHDf2UjOF6PcX/arcgis/rest/services/Combined_gdb/FeatureServer"
MASS_STATE_PLANE = 26986  # meters

FT = 3.28084
SQ_FT = FT * FT
TOL_FT = 3.0
TOL_AREA = 0.05

# Dimensional requirements. Base district rules come from Article VII; lots in
# the MBTA Communities Overlay use a flat lot area and a unit cap (§ 300-140).
DISTRICTS = {
    "RHD": {  # § 300-37
        "base_lot_sf": 6000, "per_unit_over_two_sf": 3000, "mbta_max_units": 9,
        "frontage": 50, "front": 15, "side": 10, "side_over_3_stories": 15, "rear": 20,
    },
    "RMD": {  # § 300-36
        "base_lot_sf": 8000, "per_unit_over_two_sf": 4000, "mbta_max_units": 8,
        "frontage": 65, "front": 20, "side": 10, "side_over_3_stories": 10, "rear": 20,
    },
}

RULES = ["area", "frontage", "front", "side", "rear"]

# § 300-59 Table E: 2 spaces per unit in RHD/RMD; rooming houses 1 per rental unit
PARKING_PER_UNIT = 2
ROOMING_HOUSE_LUC = "121"
STALL_SF = 162            # § 300-64: 9 ft x 18 ft
DRIVEWAY_SF_LOW = 200
LOT_SF_LOW = 330          # stall plus share of drive aisle
GARAGE_SF_PER_SPACE = 250


def fetch_layer(layer_id, fields, order_field="OBJECTID", where="1=1"):
    feats, offset = [], 0
    while True:
        q = urllib.parse.urlencode({
            "where": where, "outFields": fields, "outSR": MASS_STATE_PLANE, "f": "geojson",
            "resultOffset": offset, "resultRecordCount": 2000, "orderByFields": order_field,
        })
        req = urllib.request.Request(f"{SERVICE_URL}/{layer_id}/query?{q}", headers={"User-Agent": "OpenBeverly/1.0"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            page = json.loads(resp.read().decode("utf-8"))["features"]
        feats += page
        if len(page) < 2000:
            break
        offset += 2000
    gdf = gpd.GeoDataFrame.from_features(feats)
    return gdf.set_crs(MASS_STATE_PLANE, allow_override=True)


def line_parts(geom):
    if geom.is_empty:
        return []
    if geom.geom_type == "LineString":
        return [geom]
    if geom.geom_type == "MultiLineString":
        merged = linemerge(geom)
        return list(getattr(merged, "geoms", [merged]))
    return [g for part in getattr(geom, "geoms", []) for g in line_parts(part)]


def segments(geom):
    out = []
    for part in line_parts(geom):
        cs = list(part.coords)
        out += [LineString(cs[k:k + 2]) for k in range(len(cs) - 1)]
    return out


def tier(actual, required, tol):
    if actual is None:
        return None
    if actual >= required:
        return "meets"
    return "close" if actual >= required - tol else "short"


def garage_sf(row):
    detached = sum(int(a) * int(b) for a, b in re.findall(r"(\d+)\s*[xX]\s*(\d+)", str(row.DET_GARAGE or "")))
    attached = pd.to_numeric(row.ATT_GARAGE, errors="coerce")
    return detached + (0 if pd.isna(attached) else attached)


class CityData:
    """Citywide layers shared by every district."""

    def __init__(self):
        print("  Fetching parcels, roofprints, streets, paving…")
        self.parcels = fetch_layer(5, "LOC_ID,ZONE_1,ASSESSOR_ADD,LUC,UNIT,STORY,ATT_GARAGE,DET_GARAGE,BSMT_GAR")
        self.parcels["geometry"] = self.parcels.geometry.buffer(0)
        self.roofs = fetch_layer(70, "OBJECTID")
        self.roofs["area"] = self.roofs.geometry.area
        streets = fetch_layer(83, "NAME", order_field="OBJECTID_1")
        paving = pd.concat([fetch_layer(79, "Type", order_field="OID"), fetch_layer(80, "Type", order_field="OID")], ignore_index=True)
        paving = paving[paving.Type != "Parking Helliport"].copy()
        paving["kind"] = np.where(paving.Type.str.startswith("Parking"), "lot", "driveway")
        paving["geometry"] = paving.geometry.buffer(0)
        self.paving = gpd.GeoDataFrame(paving, geometry="geometry", crs=MASS_STATE_PLANE)

        zoning = gpd.read_file(OUT_DIR / "zoning.geojson").to_crs(MASS_STATE_PLANE)
        self.mbta = unary_union(zoning[(zoning.kind == "overlay") & (zoning.code == "MBTA")].geometry)

        all_lots = self.parcels.drop_duplicates("LOC_ID")
        self.all_geoms, self.all_ids = list(all_lots.geometry), list(all_lots.LOC_ID)
        self.lot_tree = STRtree(self.all_geoms)
        self.street_geoms, self.street_names = list(streets.geometry), list(streets.NAME)
        self.street_tree = STRtree([g.buffer(15) for g in self.street_geoms])


def build_district(code, rules, city):
    print(f"\n  {code}")
    recs = pd.DataFrame(city.parcels[city.parcels.ZONE_1 == code])
    recs["story_n"] = pd.to_numeric(recs.STORY.astype(str).str.extract(r"([\d.]+)")[0], errors="coerce")
    is_condo = recs.LUC.astype(str) == "102"
    recs["addr"] = recs.ASSESSOR_ADD.where(~is_condo, recs.ASSESSOR_ADD.str.replace(r"\s+(UNIT\s*)?#?\w{1,4}$", "", regex=True))
    recs["garage_sf"] = recs.apply(garage_sf, axis=1)
    recs["bsmt_gar"] = pd.to_numeric(recs.BSMT_GAR, errors="coerce").fillna(0)
    lots = recs.groupby("LOC_ID").agg(
        geometry=("geometry", "first"), addr=("addr", "first"), luc=("LUC", "first"),
        units=("UNIT", "sum"), story=("story_n", "max"),
        garage_sf=("garage_sf", "max"), bsmt_gar=("bsmt_gar", "max"),
    ).reset_index()
    lots = gpd.GeoDataFrame(lots, geometry="geometry", crs=MASS_STATE_PLANE)
    print(f"    {len(recs)} records → {len(lots)} lots")

    roofs = city.roofs
    joined = gpd.sjoin(roofs.set_geometry(roofs.geometry.representative_point()), lots[["geometry"]], predicate="within")
    joined = joined[~joined.index.duplicated()]
    roofs_by_lot = roofs.assign(lot_idx=joined["index_right"]).groupby("lot_idx")

    features = []
    for i, lot in lots.iterrows():
        g = lot.geometry
        boundary = g.boundary
        in_mbta = bool(city.mbta.contains(g.representative_point()))
        units = max(int(lot.units or 0), 1)
        story = None if pd.isna(lot.story) else float(lot.story)
        area_sf = g.area * SQ_FT
        req_area = rules["base_lot_sf"] if in_mbta else rules["base_lot_sf"] + rules["per_unit_over_two_sf"] * max(0, units - 2)
        req_side = rules["side_over_3_stories"] if (story or 0) > 3 else rules["side"]

        neighbors = [city.all_geoms[k] for k in city.lot_tree.query(g.buffer(1)) if city.all_ids[k] != lot.LOC_ID]
        open_edge = boundary.difference(unary_union([n.buffer(0.75) for n in neighbors])) if neighbors else boundary
        nearby = city.street_tree.query(g.buffer(2))
        # Assign each open edge segment to its nearest street, then rejoin
        # segments per street, so a corner lot's frontage isn't merged across
        # two streets at the corner.
        by_street = {}
        for seg in segments(open_edge) if len(nearby) else []:
            dist, name = min((city.street_geoms[k].distance(seg.centroid), city.street_names[k] or "") for k in nearby)
            if dist <= 15:
                by_street.setdefault(name, []).append(seg)
        fronts = {}
        for name, segs in by_street.items():
            pieces = [p for p in line_parts(linemerge(segs)) if p.length * FT >= 3]
            if pieces:
                fronts[name] = pieces
        frontage_ft = max((p.length for pieces in fronts.values() for p in pieces), default=0) * FT

        area_tier = "meets" if area_sf >= req_area else ("close" if area_sf >= (1 - TOL_AREA) * req_area else "short")
        props = {
            "addr": lot.addr, "units": units, "stories": story, "mbta": in_mbta,
            "lot_sf": round(area_sf), "req_lot_sf": req_area,
            "frontage_ft": round(frontage_ft, 1) if fronts else None,
            "req_frontage_ft": rules["frontage"], "req_front_ft": rules["front"],
            "req_side_ft": req_side, "req_rear_ft": rules["rear"],
            "over_unit_cap": in_mbta and units > rules["mbta_max_units"],
            "corner": len(fronts) > 1,
            "t_area": area_tier,
            "t_frontage": tier(frontage_ft, rules["frontage"], TOL_FT) if fronts else None,
            "front_ft": None, "side_ft": None, "rear_ft": None,
            "t_front": None, "t_side": None, "t_rear": None,
        }

        if i in roofs_by_lot.groups and fronts:
            bldgs = roofs_by_lot.get_group(i)
            b = bldgs.loc[bldgs.area.idxmax()].geometry
            best = None
            for name, pieces in fronts.items():
                front = unary_union(pieces)
                others = segments(boundary.difference(front.buffer(0.5)))
                depth = max((front.distance(s.centroid) for s in others), default=0)
                sides = [s for s in others if front.distance(s.centroid) < 0.6 * depth]
                rears = [s for s in others if front.distance(s.centroid) >= 0.6 * depth]
                f = b.distance(front) * FT
                s = min((b.distance(x) for x in sides), default=None)
                r = min((b.distance(x) for x in rears), default=None)
                s = None if s is None else s * FT
                r = None if r is None else r * FT
                tiers = (tier(f, rules["front"], TOL_FT), tier(s, req_side, TOL_FT), tier(r, rules["rear"], TOL_FT))
                score = sum({"short": 2, "close": 1}.get(t, 0) for t in tiers)
                if best is None or score < best[0]:
                    best = (score, f, s, r, tiers)
            _, f, s, r, tiers = best
            props.update(
                front_ft=round(f, 1), side_ft=None if s is None else round(s, 1), rear_ft=None if r is None else round(r, 1),
                t_front=tiers[0], t_side=tiers[1], t_rear=tiers[2],
            )

        props["n_short"] = sum(props[f"t_{k}"] == "short" for k in RULES)
        props["measured"] = props["t_front"] is not None
        features.append({"geometry": g, **props})

    out = gpd.GeoDataFrame(features, geometry="geometry", crs=MASS_STATE_PLANE)
    measured = out[out.measured]

    summary = {"district": code, "lots": len(out), "measured": int(measured.shape[0]), "mbta": int(out.mbta.sum()),
               "over_unit_cap": int(out.over_unit_cap.sum()), "rules": {}}
    medians = {"area": out.lot_sf.median(), "frontage": out.frontage_ft.median(),
               "front": measured.front_ft.median(), "side": measured.side_ft.median(), "rear": measured.rear_ft.median()}
    for k in RULES:
        counts = out[f"t_{k}"].value_counts()
        summary["rules"][k] = {"median": round(float(medians[k]), 1),
                               **{t: int(counts.get(t, 0)) for t in ("meets", "close", "short")}}
    tier_cols = measured[[f"t_{k}" for k in RULES]]
    summary["meets_all_within_tolerance"] = int((tier_cols.isin(["meets", "close"]) | tier_cols.isna()).all(axis=1).sum())
    summary["parking"] = parking_summary(lots, city.paving)
    print(f"  {json.dumps(summary, indent=2)}")

    geo = json.loads(out.to_crs(4326).to_json(drop_id=True))
    for feat in geo["features"]:
        feat["geometry"]["coordinates"] = json.loads(json.dumps(feat["geometry"]["coordinates"]), parse_float=lambda x: round(float(x), 6))
    geo["updated"] = datetime.now().strftime("%Y-%m-%d")
    geo["summary"] = summary
    path = OUT_DIR / f"zoning_{code.lower()}.geojson"
    with open(path, "w") as fh:
        json.dump(geo, fh, separators=(",", ":"))
    print(f"  ✅  Written to {path}")


def parking_summary(lots, paving):
    """District-level range of lots meeting the parking minimum. Per-lot counts
    are too uncertain to publish, so only totals leave this function."""
    lots = lots.assign(lot_i=range(len(lots)))
    clipped = gpd.overlay(lots[["lot_i", "geometry"]], paving[["kind", "geometry"]], how="intersection", keep_geom_type=True)
    clipped["sf"] = clipped.geometry.area * SQ_FT
    paved = clipped.pivot_table(index="lot_i", columns="kind", values="sf", aggfunc="sum")
    paved = paved.reindex(columns=["driveway", "lot"]).reindex(lots.lot_i).fillna(0)
    garage = np.floor(lots.garage_sf.fillna(0).values / GARAGE_SF_PER_SPACE) + lots.bsmt_gar.fillna(0).values
    high = np.floor(paved.driveway.values / STALL_SF) + np.floor(paved.lot.values / STALL_SF) + garage
    low = np.floor(paved.driveway.values / DRIVEWAY_SF_LOW) + np.floor(paved.lot.values / LOT_SF_LOW) + garage
    units = np.maximum(lots.units.fillna(0).astype(int).values, 1)
    required = np.where(lots.luc.astype(str) == ROOMING_HOUSE_LUC, units, PARKING_PER_UNIT * units)
    return {
        "required_spaces": int(required.sum()),
        "est_spaces_low": int(low.sum()), "est_spaces_high": int(high.sum()),
        "meets_low": int((low >= required).sum()), "meets_high": int((high >= required).sum()),
        "lots": len(lots),
    }


def main():
    print("\n🏘️   Open Beverly: Zoning Comparison")
    print(f"    {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    city = CityData()
    for code, rules in DISTRICTS.items():
        build_district(code, rules, city)


if __name__ == "__main__":
    main()
