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

# The City Council RSS feed above is empty on the city's side, so council
# agendas are also read from the City Council section of the Agenda Center page.
AGENDA_CENTER_URL  = "https://www.beverlyma.gov/AgendaCenter"
AGENDA_CENTER_BASE = "https://www.beverlyma.gov"
COUNCIL_CATEGORY   = 49

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

def extract_doc_id(url: str):
    """Trailing numeric AgendaCenter document ID from a beverlyma.gov URL, or None."""
    m = re.search(r"(\d+)/?$", url)
    return int(m.group(1)) if m else None

AGENDA_DOWNLOAD_RE = re.compile(r'class="agendaDownload"[^>]*href="([^"]*)"')

def fetch_event_agenda_doc_id(event_link: str):
    """Scrape an event's Calendar.aspx page for its 'Download Agenda' link, if posted."""
    try:
        req = urllib.request.Request(event_link, headers={"User-Agent": "BeverlyData/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        m = AGENDA_DOWNLOAD_RE.search(html)
        return extract_doc_id(m.group(1)) if m else None
    except Exception:
        return None

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
                "docId":    extract_doc_id(link),
            })

    print("  Fetching City Council section of Agenda Center …")
    try:
        have = {(x["docId"], x["type"]) for x in items if x["docId"] is not None}
        council = [x for x in fetch_council_agendas()
                   if x["docId"] is None or (x["docId"], x["type"]) not in have]
        items.extend(council)
        print(f"  → {len(council)} City Council items from Agenda Center")
    except Exception as e:
        print(f"  ⚠️  Failed: {e}")

    # Sort newest first
    items.sort(key=lambda x: x["pubDate"], reverse=True)
    print(f"  → {len(items)} agenda/minutes items")
    return items

def parse_posted(text: str) -> str:
    """Agenda Center 'Posted Sep 21, 2026 2:52 PM' (Eastern) -> ISO string."""
    from zoneinfo import ZoneInfo
    try:
        dt = datetime.strptime(text, "%b %d, %Y %I:%M %p")
        return dt.replace(tzinfo=ZoneInfo("America/New_York")).isoformat()
    except ValueError:
        return ""

def fetch_council_agendas() -> list:
    """Scrape the City Council section of the Agenda Center page."""
    req = urllib.request.Request(AGENDA_CENTER_URL, headers={"User-Agent": "BeverlyData/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    start = html.find(f'id="category-panel-{COUNCIL_CATEGORY}"')
    if start < 0:
        raise ValueError("City Council section not found on Agenda Center page")
    end = html.find('id="category-panel-', start + 30)
    section = html[start:end if end > 0 else None]

    items = []
    for row in re.findall(r'<tr[^>]*class="catAgendaRow".*?</tr>', section, re.S):
        text   = re.sub(r"<[^>]+>", " ", row)
        text   = re.sub(r"\s+", " ", text.replace("&thinsp;", " ").replace("&mdash;", " "))
        posted = re.search(r"Posted (\w{3} \d{1,2}, \d{4} \d{1,2}:\d{2} [AP]M)", text)
        agenda = re.search(r'<p>\s*<a[^>]*href="/AgendaCenter/ViewFile/Agenda/_\d+-(\d+)"[^>]*>(.*?)</a>', row, re.S)
        if not agenda:
            continue
        doc_id   = int(agenda.group(1))
        title    = clean_title(re.sub(r"\s+", " ", agenda.group(2)))
        pub_date = parse_posted(posted.group(1)) if posted else ""
        items.append({
            "title":   title,
            "link":    f"{AGENDA_CENTER_BASE}/AgendaCenter/PreviousVersions/{doc_id}",
            "pubDate": pub_date,
            "desc":    "",
            "board":   "City Council",
            "type":    "agenda",
            "docId":   doc_id,
        })
        minutes = re.search(r'href="(/AgendaCenter/ViewFile/Minutes/[^"]+)"', row)
        if minutes:
            items.append({
                "title":   title.replace("Agenda", "Minutes") if "Agenda" in title else f"{title} Minutes",
                "link":    AGENDA_CENTER_BASE + minutes.group(1),
                "pubDate": pub_date,
                "desc":    "",
                "board":   "City Council",
                "type":    "minutes",
                "docId":   None,
            })
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
            "title":       title,
            "link":        link,
            "pubDate":     parse_date(pub_date),
            "eventDate":   event_date,
            "eventTime":   event_time,
            "location":    location,
            "board":       board,
            "sortDate":    sort_dt.isoformat(),
            "agendaDocId": fetch_event_agenda_doc_id(link) if link else None,
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
