#!/usr/bin/env python3
"""
Beverly Data — Meeting Summarizer
Fetches City Council videos from BevCam's YouTube channel,
pulls transcripts, summarizes with Claude, and writes summaries.json.

Usage:
    ANTHROPIC_API_KEY=sk-... python3 summarize.py
    ANTHROPIC_API_KEY=sk-... python3 summarize.py --max 5
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import anthropic
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound

# ── Config ────────────────────────────────────────────────────────────────────

CHANNEL_ID   = "UCsloEZrieQqRUqra1diSk1w"   # BevCam Government
CHANNEL_RSS  = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
OUTPUT_FILE  = Path(__file__).parent / "summaries.json"
CLAUDE_MODEL = "claude-haiku-4-5-20251001"   # fast + cheap for summarization

# Only include videos whose title matches one of these governing bodies
BODY_FILTERS = [
    ("City Council",     re.compile(r"city council", re.IGNORECASE)),
    ("School Committee", re.compile(r"school committee", re.IGNORECASE)),
]

def detect_body(title: str) -> str | None:
    for name, pattern in BODY_FILTERS:
        if pattern.search(title):
            return name
    return None

def parse_summary(raw: str) -> dict:
    """Parse Claude's markdown response into structured fields."""
    headline = ""
    bullets  = []
    votes    = []
    current  = None

    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        low = stripped.lower()

        # Section headings (## Headline, ## Key Topics, ## Key Votes)
        if re.match(r"^#{1,3}\s*headline", low):
            current = "headline"
            continue
        if re.match(r"^#{1,3}\s*(key topics|topics|decisions|key topics)", low):
            current = "bullets"
            continue
        if re.match(r"^#{1,3}\s*key votes", low):
            current = "votes"
            continue

        # Skip date lines like **June 25, 2026**
        if re.match(r"^\*{1,2}[A-Z][a-z]+ \d{1,2},? \d{4}\*{1,2}$", stripped):
            continue

        # Capture content by current section
        if current == "headline" and not headline:
            headline = re.sub(r"^\*+|\*+$", "", stripped).strip()
        elif current in ("bullets", "votes"):
            if stripped.startswith(("- ", "• ", "* ")) or re.match(r"^[\-\•]\s", stripped):
                text = re.sub(r"^[-•*]\s*", "", stripped).strip()
                text = re.sub(r"^\*\*(.+?)\*\*\s*[–—-]\s*", r"\1: ", text)
                (votes if current == "votes" else bullets).append(text)
            # Handle markdown table rows (| col | col | col |)
            elif current == "votes" and stripped.startswith("|") and not re.match(r"^\|[-| ]+\|$", stripped):
                cols = [c.strip() for c in stripped.strip("|").split("|")]
                cols = [re.sub(r"\*+", "", c).strip() for c in cols if c.strip()]
                if len(cols) >= 2 and not cols[0].lower().startswith("order"):
                    # "Item — Result" or just skip header row
                    item_name = cols[1] if len(cols) > 2 else cols[0]
                    result    = cols[-1]
                    votes.append(f"{item_name} — {result}")

    return {"headline": headline, "bullets": bullets, "votes": votes, "raw": raw}


SUMMARY_PROMPT = """\
You are summarizing a Beverly, MA {body} meeting for residents who want a quick overview.

Below is the auto-generated transcript. Please produce:
1. A one-sentence headline (what was the most significant thing that happened?)
2. 4–6 bullet points covering the key topics discussed, decisions made, and votes taken
3. A "Key votes" section (if any formal votes occurred) listing what passed/failed

Keep language plain and accessible. Omit procedural filler (roll calls, adjournments).
Flag anything uncertain with "(unclear from transcript)".

TRANSCRIPT:
{transcript}
"""

# ── Helpers ───────────────────────────────────────────────────────────────────

def fetch_channel_videos(max_videos: int) -> list[dict]:
    """Return list of {video_id, title, published, url, body} from channel RSS."""
    print(f"  Fetching channel RSS feed…")
    req = urllib.request.Request(CHANNEL_RSS, headers={"User-Agent": "BeverlyData/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read()

    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "yt":   "http://www.youtube.com/xml/schemas/2015",
        "media":"http://search.yahoo.com/mrss/",
    }
    root = ET.fromstring(raw)
    videos = []
    for entry in root.findall("atom:entry", ns):
        video_id  = entry.findtext("yt:videoId",   namespaces=ns, default="")
        title     = entry.findtext("atom:title",    namespaces=ns, default="")
        published = entry.findtext("atom:published", namespaces=ns, default="")
        url       = f"https://www.youtube.com/watch?v={video_id}"
        body = detect_body(title)
        if body:
            videos.append({"video_id": video_id, "title": title,
                           "published": published, "url": url, "body": body})
        if len(videos) >= max_videos:
            break

    print(f"  Found {len(videos)} matching video(s) in feed")
    return videos


def fetch_transcript(video_id: str):
    """Return the transcript as a single string, or None if unavailable."""
    try:
        api = YouTubeTranscriptApi()
        segments = api.fetch(video_id)
        return " ".join(s.text for s in segments)
    except (TranscriptsDisabled, NoTranscriptFound):
        return None
    except Exception as e:
        print(f"    ⚠️  Transcript error: {e}")
        return None


def summarize(client: anthropic.Anthropic, transcript: str, body: str) -> dict:
    """Call Claude and return {headline, bullets, votes}."""
    # Truncate very long transcripts to avoid huge token bills
    words = transcript.split()
    if len(words) > 12000:
        transcript = " ".join(words[:12000]) + "\n\n[transcript truncated]"

    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": SUMMARY_PROMPT.format(transcript=transcript, body=body),
        }],
    )
    raw = message.content[0].text
    return parse_summary(raw)


def load_existing(path: Path) -> dict:
    """Load existing summaries so we can skip already-processed videos."""
    if path.exists():
        with open(path) as f:
            data = json.load(f)
        return {item["video_id"]: item for item in data}
    return {}


def save(path: Path, summaries: dict):
    items = sorted(summaries.values(), key=lambda x: x["published"], reverse=True)
    with open(path, "w") as f:
        json.dump(items, f, indent=2)
    print(f"\n✅  Wrote {len(items)} summar{'y' if len(items)==1 else 'ies'} to {path}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Summarize Beverly City Council meetings")
    parser.add_argument("--max", type=int, default=10,
                        help="Max number of videos to process (default: 10)")
    parser.add_argument("--force", action="store_true",
                        help="Re-summarize even if already in summaries.json")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌  Set ANTHROPIC_API_KEY environment variable first.", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    existing = {} if args.force else load_existing(OUTPUT_FILE)

    print(f"\n🎬  Beverly Data — Meeting Summarizer")
    print(f"    Channel : BevCam Government")
    print(f"    Max     : {args.max} video(s)")
    print(f"    Model   : {CLAUDE_MODEL}\n")

    videos = fetch_channel_videos(args.max)
    if not videos:
        print("No matching videos found. Exiting.")
        return

    summaries = dict(existing)
    new_count  = 0

    for i, video in enumerate(videos, 1):
        vid = video["video_id"]
        print(f"[{i}/{len(videos)}] {video['title']}")

        if vid in summaries and not args.force:
            print("    ✓ Already summarized — skipping\n")
            continue

        print("    Fetching transcript…")
        transcript = fetch_transcript(vid)
        if not transcript:
            print("    ⚠️  No transcript available — skipping\n")
            summaries[vid] = {**video, "error": "no transcript available",
                               "headline": "", "bullets": [], "votes": [], "raw": ""}
            continue

        word_count = len(transcript.split())
        print(f"    Transcript: {word_count:,} words")
        print("    Summarizing with Claude…")

        result = summarize(client, transcript, video["body"])
        summaries[vid] = {**video, **result}
        new_count += 1

        print(f"    ✓ {result['headline'] or '(no headline parsed)'}\n")

        # Be polite to the API
        if i < len(videos):
            time.sleep(0.5)

    save(OUTPUT_FILE, summaries)
    print(f"    {new_count} new, {len(existing)} cached")


if __name__ == "__main__":
    main()
