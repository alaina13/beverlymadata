#!/usr/bin/env python3
"""
Open Beverly: Zoning Comparison (RHD) builder
Compares every lot in the RHD Multifamily High Density district against the
district's dimensional requirements and writes zoning_rhd.geojson.

Sources:
  - City of Beverly GIS (BeverlyGIS), Combined_gdb FeatureServer:
      layer 5  Parcels (zone, units, stories)
      layer 70 Roofprint (building footprints)
      layer 83 Street_MasterPoly (street pavement polygons)
  - zoning.geojson (MBTA Communities Overlay boundary; see fetch_zoning_data.py)
  - Beverly Zoning Ordinance Ch. 300: § 300-37 (RHD), § 300-140 (MBTA overlay),
    Article II definitions ("Frontage", "Setback", "Yard, front")

Method (estimates, not surveys):
  - Condo records stacked on one lot polygon are combined by LOC_ID.
  - Principal building = largest roofprint whose interior point is on the lot.
  - Frontage = longest unbroken lot edge that is not shared with another parcel
    and lies within 15 m of street pavement.
  - Corner lots: either street may be the front yard (Art. II), so each street
    is tested and the more favorable result is kept.
  - Tolerance: roofprints include eaves while setbacks are measured to the
    foundation, so results within 3 ft (5% for lot area) are "close".

Requires: geopandas, shapely 2.x

Usage:
    python3 build_zoning_rhd.py
"""

import json
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely import STRtree
from shapely.geometry import LineString
from shapely.ops import linemerge, unary_union

OUT_DIR = Path(__file__).parent
SERVICE_URL = "https://services1.arcgis.com/IVwtHDf2UjOF6PcX/arcgis/rest/services/Combined_gdb/FeatureServer"
MASS_STATE_PLANE = 26986  # meters

FT = 3.28084
TOL_FT = 3.0
TOL_AREA = 0.05

# § 300-37 (base) and § 300-140 (MBTA Communities Overlay), RHD
FRONTAGE_FT = 50
FRONT_FT = 15
SIDE_FT = 10
SIDE_OVER_3_STORIES_FT = 15
REAR_FT = 20
BASE_LOT_SF = 6000
BASE_PER_UNIT_OVER_TWO_SF = 3000
MBTA_MAX_UNITS = 9

RULES = ["area", "frontage", "front", "side", "rear"]


def fetch_layer(layer_id, fields, order_field="OBJECTID"):
    feats, offset = [], 0
    while True:
        q = urllib.parse.urlencode({
            "where": "1=1", "outFields": fields, "outSR": MASS_STATE_PLANE, "f": "geojson",
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


def main():
    print("\n🏘️   Open Beverly: Zoning Comparison (RHD)")
    print(f"    {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    print("  Fetching parcels, roofprints, streets…")
    parcels = fetch_layer(5, "LOC_ID,ZONE_1,ASSESSOR_ADD,LUC,UNIT,STORY")
    roofs = fetch_layer(70, "OBJECTID")
    streets = fetch_layer(83, "NAME", order_field="OBJECTID_1")
    parcels["geometry"] = parcels.geometry.buffer(0)

    zoning = gpd.read_file(OUT_DIR / "zoning.geojson").to_crs(MASS_STATE_PLANE)
    mbta = unary_union(zoning[(zoning.kind == "overlay") & (zoning.code == "MBTA")].geometry)

    # Every distinct lot polygon citywide, for finding lot lines shared with neighbors
    all_lots = parcels.drop_duplicates("LOC_ID")
    all_geoms, all_ids = list(all_lots.geometry), list(all_lots.LOC_ID)
    lot_tree = STRtree(all_geoms)
    street_geoms, street_names = list(streets.geometry), list(streets.NAME)
    street_tree = STRtree([g.buffer(15) for g in street_geoms])

    rhd = pd.DataFrame(parcels[parcels.ZONE_1 == "RHD"])
    rhd["story_n"] = pd.to_numeric(rhd.STORY.astype(str).str.extract(r"([\d.]+)")[0], errors="coerce")
    is_condo = rhd.LUC.astype(str) == "102"
    rhd["addr"] = rhd.ASSESSOR_ADD.where(~is_condo, rhd.ASSESSOR_ADD.str.replace(r"\s+(UNIT\s*)?#?\w{1,4}$", "", regex=True))
    lots = rhd.groupby("LOC_ID").agg(
        geometry=("geometry", "first"), addr=("addr", "first"),
        units=("UNIT", "sum"), story=("story_n", "max"),
    ).reset_index()
    lots = gpd.GeoDataFrame(lots, geometry="geometry", crs=MASS_STATE_PLANE)
    print(f"    {len(rhd)} RHD records → {len(lots)} lots")

    roofs["area"] = roofs.geometry.area
    joined = gpd.sjoin(roofs.set_geometry(roofs.geometry.representative_point()), lots[["geometry"]], predicate="within")
    joined = joined[~joined.index.duplicated()]
    roofs["lot_idx"] = joined["index_right"]
    roofs_by_lot = roofs.groupby("lot_idx")

    features = []
    for i, lot in lots.iterrows():
        g = lot.geometry
        boundary = g.boundary
        in_mbta = bool(mbta.contains(g.representative_point()))
        units = max(int(lot.units or 0), 1)
        story = None if pd.isna(lot.story) else float(lot.story)
        area_sf = g.area * FT * FT
        req_area = BASE_LOT_SF if in_mbta else BASE_LOT_SF + BASE_PER_UNIT_OVER_TWO_SF * max(0, units - 2)
        req_side = SIDE_OVER_3_STORIES_FT if (story or 0) > 3 else SIDE_FT

        neighbors = [all_geoms[k] for k in lot_tree.query(g.buffer(1)) if all_ids[k] != lot.LOC_ID]
        open_edge = boundary.difference(unary_union([n.buffer(0.75) for n in neighbors])) if neighbors else boundary
        nearby = street_tree.query(g.buffer(2))
        fronts = {}
        for piece in line_parts(open_edge):
            if piece.length * FT < 3 or not len(nearby):
                continue
            dist, name = min((street_geoms[k].distance(piece.centroid), street_names[k] or "") for k in nearby)
            if dist <= 15:
                fronts.setdefault(name, []).append(piece)
        frontage_ft = max((p.length for pieces in fronts.values() for p in pieces), default=0) * FT

        area_tier = "meets" if area_sf >= req_area else ("close" if area_sf >= (1 - TOL_AREA) * req_area else "short")
        props = {
            "addr": lot.addr, "units": units, "stories": story, "mbta": in_mbta,
            "lot_sf": round(area_sf), "req_lot_sf": req_area,
            "frontage_ft": round(frontage_ft, 1) if fronts else None,
            "req_side_ft": req_side,
            "over_unit_cap": in_mbta and units > MBTA_MAX_UNITS,
            "corner": len(fronts) > 1,
            "t_area": area_tier,
            "t_frontage": tier(frontage_ft, FRONTAGE_FT, TOL_FT) if fronts else None,
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
                tiers = (tier(f, FRONT_FT, TOL_FT), tier(s, req_side, TOL_FT), tier(r, REAR_FT, TOL_FT))
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

    out = gpd.GeoDataFrame(features, geometry="geometry", crs=MASS_STATE_PLANE).to_crs(4326)
    measured = out[out.measured]

    summary = {"lots": len(out), "measured": int(measured.shape[0]), "mbta": int(out.mbta.sum()),
               "over_unit_cap": int(out.over_unit_cap.sum()), "rules": {}}
    medians = {"area": out.lot_sf.median(), "frontage": out.frontage_ft.median(),
               "front": measured.front_ft.median(), "side": measured.side_ft.median(), "rear": measured.rear_ft.median()}
    for k in RULES:
        counts = out[f"t_{k}"].value_counts()
        summary["rules"][k] = {"median": round(float(medians[k]), 1),
                               **{t: int(counts.get(t, 0)) for t in ("meets", "close", "short")}}
    all_ok = measured[[f"t_{k}" for k in RULES]].isin(["meets", "close"]) | measured[[f"t_{k}" for k in RULES]].isna()
    summary["meets_all_within_tolerance"] = int(all_ok.all(axis=1).sum())

    geo = json.loads(out.to_json(drop_id=True))
    for feat in geo["features"]:
        feat["geometry"]["coordinates"] = json.loads(json.dumps(feat["geometry"]["coordinates"]), parse_float=lambda x: round(float(x), 6))
    geo["updated"] = datetime.now().strftime("%Y-%m-%d")
    geo["summary"] = summary
    path = OUT_DIR / "zoning_rhd.geojson"
    with open(path, "w") as fh:
        json.dump(geo, fh, separators=(",", ":"))
    print(f"\n  {json.dumps(summary, indent=2)}")
    print(f"\n  ✅  Written to {path}")


if __name__ == "__main__":
    main()
