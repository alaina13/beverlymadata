#!/usr/bin/env python3
"""
Beverly Data — Data Fetcher
Pulls the Agenda Center page and calendar RSS feed from beverlyma.gov and writes:
  - meetings.json   (one item per meeting, with agenda and minutes links)
  - calendar.json   (upcoming events)

Run this on a schedule (cron, GitHub Actions, etc.) to keep data fresh.
Usage:
    python3 fetch_data.py
"""

import html as html_lib
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

OUT_DIR = Path(__file__).parent

# The Agenda Center page lists every board's meetings, each with its agenda
# and (once posted) minutes. It is the source for the archive; the city's RSS
# feeds report minutes under the agenda's title and link, which is misleading.
AGENDA_CENTER_URL  = "https://www.beverlyma.gov/AgendaCenter"
AGENDA_CENTER_BASE = "https://www.beverlyma.gov"

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

def clean_title(title: str) -> str:
    return re.sub(r"\s*\(PDF\)", "", title, flags=re.I).strip()

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

# ── Meeting archive fetcher ────────────────────────────────────────────────────

def board_name(category: str) -> str:
    """City category names are index-style ('Health, Board of'); put them in natural order."""
    name = html_lib.unescape(category).strip()
    head, sep, tail = name.rpartition(", ")
    if sep and (re.search(r"\b(of|on)$", tail) or tail == "Salem and Beverly"):
        return f"{tail} {head}"
    return name

def meeting_title(raw: str, board: str) -> str:
    """Drop the word 'Agenda' and any trailing date; the card shows the meeting date."""
    title = clean_title(html_lib.unescape(re.sub(r"\s+", " ", raw)))
    title = re.sub(r"\s+(for\s+)?\d{1,2}/\d{1,2}/\d{2,4}$", "", title)
    title = re.sub(r"\s*-\s*[A-Z][a-z]+ \d{1,2}, \d{4}$", "", title)
    title = re.sub(r"\bagenda\b", "", title, flags=re.I)
    title = re.sub(r"(\s*-\s*)+", " - ", title)
    title = re.sub(r"\s+", " ", title).strip(" -")
    return title or f"{board} Meeting"

def parse_posted(text: str) -> str:
    """Agenda Center 'Posted Sep 21, 2026 2:52 PM' (Eastern) -> ISO string."""
    from zoneinfo import ZoneInfo
    try:
        dt = datetime.strptime(text, "%b %d, %Y %I:%M %p")
        return dt.replace(tzinfo=ZoneInfo("America/New_York")).isoformat()
    except ValueError:
        return ""

def parse_row(row: str, board: str):
    agenda = re.search(r'<p>\s*<a[^>]*href="(/AgendaCenter/ViewFile/Agenda/_(\d{8})-(\d+))"[^>]*>(.*?)</a>', row, re.S)
    if not agenda:
        return None
    href, mmddyyyy, doc_id, raw_title = agenda.groups()
    text    = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", row))
    posted  = re.search(r"Posted (\w{3} \d{1,2}, \d{4} \d{1,2}:\d{2} [AP]M)", text)
    minutes = re.search(r'href="(/AgendaCenter/ViewFile/Minutes/[^"]+)"', row)
    return {
        "title":   meeting_title(raw_title, board),
        "board":   board,
        "date":    f"{mmddyyyy[4:]}-{mmddyyyy[:2]}-{mmddyyyy[2:4]}",
        "posted":  parse_posted(posted.group(1)) if posted else "",
        "docId":   int(doc_id),
        "agenda":  AGENDA_CENTER_BASE + href,
        "minutes": AGENDA_CENTER_BASE + minutes.group(1) if minutes else None,
    }

def fetch_archive() -> list:
    """One item per meeting, from every board section of the Agenda Center page."""
    req = urllib.request.Request(AGENDA_CENTER_URL, headers={"User-Agent": "BeverlyData/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        html = resp.read().decode("utf-8", errors="replace")

    categories = re.findall(r'aria-controls="category-panel-(\d+)">\s*([^<]+)', html)
    items, seen = [], set()
    for cid, category in categories:
        start = html.find(f'id="category-panel-{cid}"')
        end   = html.find('id="category-panel-', start + 30)
        section = html[start:end if end > 0 else None]
        board = board_name(category)
        for row in re.findall(r'<tr[^>]*class="catAgendaRow".*?</tr>', section, re.S):
            item = parse_row(row, board)
            if item and item["docId"] not in seen:
                seen.add(item["docId"])
                items.append(item)

    items.sort(key=lambda x: (x["date"], x["posted"]), reverse=True)
    print(f"  → {len(items)} meetings across {len(categories)} boards, "
          f"{sum(1 for x in items if x['minutes'])} with minutes")
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
    meetings = fetch_archive()
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
