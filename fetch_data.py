#!/usr/bin/env python3
"""
Beverly Data — Data Fetcher
Pulls agenda and calendar RSS feeds from beverlyma.gov and writes:
  - meetings.json   (agendas & minutes)
  - calendar.json   (upcoming events)

Run this on a schedule (cron, GitHub Actions, etc.) to keep data fresh.
Usage:
    python3 fetch_data.py
"""

import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

OUT_DIR = Path(__file__).parent

AGENDA_FEEDS = [
    {"url": "https://beverlyma.gov/RSSFeed.aspx?ModID=65&CID=All-0",           "board": None},
    {"url": "https://beverlyma.gov/RSSFeed.aspx?ModID=65&CID=City-Council-49", "board": "City Council"},
]

CALENDAR_FEED = "https://beverlyma.gov/RSSFeed.aspx?ModID=58&CID=All-calendar.xml"

BOARD_RULES = [
    (re.compile(r"city council",            re.I), "City Council"),
    (re.compile(r"school committee",        re.I), "School Committee"),
    (re.compile(r"planning board",          re.I), "Planning Board"),
    (re.compile(r"finance committee",       re.I), "Finance Committee"),
    (re.compile(r"board of health",         re.I), "Board of Health"),
    (re.compile(r"conservation commission", re.I), "Conservation Commission"),
    (re.compile(r"zoning board",            re.I), "Zoning Board of Appeals"),
    (re.compile(r"affordable housing",      re.I), "Affordable Housing Trust"),
    (re.compile(r"library board|library trustee|board of trustees.*library", re.I), "Library Board of Trustees"),
    (re.compile(r"disabilities",            re.I), "Commission on Disabilities"),
    (re.compile(r"harbor",                  re.I), "Harbor Management Authority"),
    (re.compile(r"historic district",       re.I), "Historic District Commission"),
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def fetch_xml(url: str) -> ET.Element:
    req = urllib.request.Request(url, headers={"User-Agent": "BeverlyData/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return ET.fromstring(resp.read())

def detect_board(title: str) -> str:
    for pattern, name in BOARD_RULES:
        if pattern.search(title):
            return name
    return "Other"

def detect_type(title: str, desc: str) -> str:
    return "minutes" if re.search(r"minutes", title + " " + desc, re.I) else "agenda"

def clean_title(title: str) -> str:
    return re.sub(r"\s*\(PDF\)", "", title, flags=re.I).strip()

def clean_desc(raw_desc: str, title: str) -> str:
    clean = re.sub(r"\s*\(PDF\)", "", raw_desc, flags=re.I).strip()
    return clean if clean and clean != title else ""

def parse_date(date_str: str):
    """Return ISO date string or empty string."""
    if not date_str:
        return ""
    try:
        # RSS pubDate format: "Thu, 26 Jun 2026 00:00:00 -0500"
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(date_str).isoformat()
    except Exception:
        return date_str

# ── Agenda fetcher ─────────────────────────────────────────────────────────────

def fetch_agendas() -> list:
    seen = set()
    items = []

    for feed in AGENDA_FEEDS:
        print(f"  Fetching {feed['url'].split('CID=')[1]} …")
        try:
            root = fetch_xml(feed["url"])
        except Exception as e:
            print(f"  ⚠️  Failed: {e}")
            continue

        for item in root.findall(".//item"):
            raw_title = item.findtext("title") or ""
            title     = clean_title(raw_title)
            link      = (item.findtext("link") or "").strip() or \
                        (item.findtext("guid") or "").strip()
            pub_date  = item.findtext("pubDate") or ""
            raw_desc  = item.findtext("description") or ""
            desc      = clean_desc(raw_desc, title)
            board     = feed["board"] or detect_board(title)
            doc_type  = detect_type(title, desc)

            key = title + "|" + link
            if key in seen:
                continue
            seen.add(key)

            items.append({
                "title":    title,
                "link":     link,
                "pubDate":  parse_date(pub_date),
                "desc":     desc,
                "board":    board,
                "type":     doc_type,
            })

    # Sort newest first
    items.sort(key=lambda x: x["pubDate"], reverse=True)
    print(f"  → {len(items)} agenda/minutes items")
    return items

# ── Calendar fetcher ───────────────────────────────────────────────────────────

def fetch_calendar() -> list:
    print(f"  Fetching calendar …")
    try:
        root = fetch_xml(CALENDAR_FEED)
    except Exception as e:
        print(f"  ⚠️  Failed: {e}")
        return []

    now = datetime.now(timezone.utc)
    events = []

    for item in root.findall(".//item"):
        title    = (item.findtext("title") or "").strip()
        link     = (item.findtext("link") or "").strip() or \
                   (item.findtext("guid") or "").strip()
        pub_date = item.findtext("pubDate") or ""

        # Pull custom calendar fields (any namespace)
        def ns_text(tag):
            for el in item.iter():
                if el.tag.split("}")[-1] == tag:
                    return (el.text or "").strip()
            return ""

        event_date = ns_text("EventDates")
        event_time = ns_text("EventTimes").split(" - ")[0].split(" – ")[0].strip()
        location   = ns_text("Location")
        board      = detect_board(title)

        # Parse sort date
        sort_date_str = event_date or pub_date
        try:
            from email.utils import parsedate_to_datetime
            sort_dt = parsedate_to_datetime(sort_date_str) if not event_date \
                      else datetime.fromisoformat(event_date.replace("Z", "+00:00")) \
                           if "T" in event_date else datetime.strptime(event_date, "%B %d, %Y").replace(tzinfo=timezone.utc)
        except Exception:
            sort_dt = now

        # Skip past events (more than 1 day ago)
        if sort_dt.replace(tzinfo=timezone.utc if sort_dt.tzinfo is None else sort_dt.tzinfo) < \
           now.replace(tzinfo=timezone.utc) and (now - sort_dt.replace(tzinfo=timezone.utc if sort_dt.tzinfo is None else sort_dt.tzinfo)).days > 1:
            continue

        events.append({
            "title":      title,
            "link":       link,
            "pubDate":    parse_date(pub_date),
            "eventDate":  event_date,
            "eventTime":  event_time,
            "location":   location,
            "board":      board,
            "sortDate":   sort_dt.isoformat(),
        })

    events.sort(key=lambda x: x["sortDate"])
    print(f"  → {len(events)} upcoming events")
    return events

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("\n📡  Beverly Data — Data Fetcher")
    print(f"    {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    print("Agendas & Minutes:")
    meetings = fetch_agendas()
    meetings_path = OUT_DIR / "meetings.json"
    with open(meetings_path, "w") as f:
        json.dump(meetings, f, indent=2)
    print(f"  ✅  Written to {meetings_path}\n")

    print("Calendar:")
    events = fetch_calendar()
    calendar_path = OUT_DIR / "calendar.json"
    with open(calendar_path, "w") as f:
        json.dump(events, f, indent=2)
    print(f"  ✅  Written to {calendar_path}\n")

    print("Done. Run summarize.py to refresh AI meeting summaries.")

if __name__ == "__main__":
    main()
