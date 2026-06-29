#!/usr/bin/env python3
"""
Beverly Data — Civic Data Fetcher
Pulls publicly available data for Beverly, MA and writes civic_data.json.

Sources:
  - Beverly City Assessors page (tax rates)
  - MA DESE profiles (school enrollment, per-pupil spending)

Run this on a schedule alongside fetch_data.py.
Usage:
    python3 fetch_civic_data.py
"""

import json
import re
import urllib.request
from datetime import datetime
from pathlib import Path

OUT_DIR = Path(__file__).parent

BEVERLY_DISTRICT_CODE = "00300000"

def fetch_html(url):
    req = urllib.request.Request(url, headers={"User-Agent": "BeverlyData/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")

def strip_tags(html):
    return re.sub(r"<[^>]+>", " ", html)

def collapse(text):
    return re.sub(r"\s+", " ", text).strip()

# ── Tax rates ──────────────────────────────────────────────────────────────────

def fetch_tax_rates():
    print("  Fetching tax rates from Beverly Assessors page…")
    try:
        html = fetch_html("https://www.beverlyma.gov/391/City-Assessors")
        text = collapse(strip_tags(html))

        rates = {}
        # Look for "FY YYYY Tax Rates" section
        fy_match = re.search(r"Fiscal Year (\d{4}) Tax Rates?", text, re.I)
        if fy_match:
            rates["fiscal_year"] = int(fy_match.group(1))

        # Residential rate — format: "Residential - $10.81" or "Residential: $10.81"
        res = re.search(r"Residential\s*[-:]\s*\$?([\d.]+)", text, re.I)
        if res:
            rates["residential"] = float(res.group(1))

        # Commercial rate
        com = re.search(r"Commercial\s*[-:]\s*\$?([\d.]+)", text, re.I)
        if com:
            rates["commercial"] = float(com.group(1))

        if rates:
            print(f"    FY{rates.get('fiscal_year','?')}: Residential ${rates.get('residential','?')}, Commercial ${rates.get('commercial','?')}")
            return rates
    except Exception as e:
        print(f"    ⚠️  Failed: {e}")

    # Fallback to known FY2026 values
    print("    Using fallback FY2026 rates")
    return {"fiscal_year": 2026, "residential": 10.81, "commercial": 20.98, "fallback": True}

# ── School enrollment ──────────────────────────────────────────────────────────

def fetch_enrollment(year):
    """year = last two digits of school year end, e.g. 2025 = 2024-25"""
    url = (
        f"https://profiles.doe.mass.edu/statereport/enrollmentbygrade.aspx"
        f"?mode=districtSchool&year={year}&orderBy=&district={BEVERLY_DISTRICT_CODE}"
        f"&school=0&grade=0&reportType=1"
    )
    try:
        html = fetch_html(url)
        text = collapse(strip_tags(html))
        # Row format: "Beverly 00300000 <grade counts> <total>"
        m = re.search(r"Beverly\s+00300000(?:\s+[\d,]+){14,}\s+([\d,]+)", text)
        if m:
            return int(m.group(1).replace(",", ""))
    except Exception as e:
        print(f"    ⚠️  Enrollment {year} failed: {e}")
    return None

def fetch_school_data():
    print("  Fetching school enrollment from DESE…")
    current_year = datetime.now().year
    # DESE page always returns current year regardless of year param
    for yr in range(current_year, current_year - 2, -1):
        n = fetch_enrollment(yr)
        if n:
            school_year = f"{yr-1}–{str(yr)[2:]}"
            print(f"    {school_year}: {n:,}")
            return {"school_year": school_year, "enrollment": n}
    return None

# ── Per-pupil spending ─────────────────────────────────────────────────────────

def fetch_per_pupil():
    print("  Fetching per-pupil spending from DESE…")
    current_year = datetime.now().year
    for yr in range(current_year - 1, current_year - 4, -1):
        url = (
            f"https://profiles.doe.mass.edu/statereport/ppx.aspx"
            f"?mode=districtSchool&year={yr}&orderBy=&district={BEVERLY_DISTRICT_CODE}&school=0"
        )
        try:
            html = fetch_html(url)
            text = collapse(strip_tags(html))
            # Row format: "Beverly 00300000 $TOTAL FTEs $PER_PUPIL ..."
            m = re.search(r"Beverly\s+00300000\s+\$[\d,]+\.\d+\s+[\d,.]+\s+\$([\d,]+\.\d+)", text, re.I)
            if m:
                cost = float(m.group(1).replace(",", ""))
                print(f"    FY{yr}: ${cost:,.0f}/pupil in-district")
                return {"fiscal_year": yr, "per_pupil_in_district": cost}
        except Exception as e:
            print(f"    ⚠️  PPX {yr} failed: {e}")
    # Fallback to known value
    print("    Using fallback FY2024 per-pupil value")
    return {"fiscal_year": 2024, "per_pupil_in_district": 18595, "fallback": True}

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("\n📊  Beverly Data — Civic Data Fetcher")
    print(f"    {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    tax = fetch_tax_rates()
    enrollment = fetch_school_data()
    per_pupil = fetch_per_pupil()

    output = {
        "updated": datetime.now().strftime("%Y-%m-%d"),
        "tax_rates": tax,
        "school_enrollment": enrollment or {},
        "per_pupil_spending": per_pupil,
        "sources": {
            "tax_rates": "Beverly City Assessors Office — beverlyma.gov/391/City-Assessors",
            "school_data": "MA DESE School and District Profiles — profiles.doe.mass.edu",
            "budget": "Beverly Finance Department — beverlyma.gov/309/Fiscal-Budgets",
        },
        "budget_links": [
            {"label": "FY2026 Budget (ClearGov)", "url": "https://city-beverly-ma-budget-book.cleargov.com/20282/introduction/transmittal-letter"},
            {"label": "FY2025 Budget (ClearGov)", "url": "https://city-beverly-ma-budget-book.cleargov.com/15295/introduction/transmittal-letter"},
            {"label": "FY2027 Proposed Budget (PDF)", "url": "https://www.beverlyma.gov/DocumentCenter/View/7440/Proposed-FY-2027-City-Budget"},
            {"label": "FY2024 Budget (PDF)", "url": "https://www.beverlyma.gov/DocumentCenter/View/4555/Proposed-Fiscal-Year-2024-Budget"},
        ],
    }

    path = OUT_DIR / "civic_data.json"
    with open(path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  ✅  Written to {path}")

if __name__ == "__main__":
    main()
