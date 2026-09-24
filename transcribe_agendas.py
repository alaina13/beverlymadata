#!/usr/bin/env python3
"""
Open Beverly: Agenda Transcriber
The city's agenda PDFs are scanned images with no text layer. This script
downloads each meeting's agenda listed in meetings.json, has Claude read the scan,
and writes the text to agenda_text.json (keyed by docId).

Usage:
    ANTHROPIC_API_KEY=sk-... python3 transcribe_agendas.py
    ANTHROPIC_API_KEY=sk-... python3 transcribe_agendas.py --max 5
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from pypdf import PdfReader, PdfWriter

# ── Config ────────────────────────────────────────────────────────────────────

ROOT          = Path(__file__).parent
MEETINGS_FILE = ROOT / "meetings.json"
OUTPUT_FILE   = ROOT / "agenda_text.json"
CLAUDE_MODEL  = "claude-haiku-4-5-20251001"
USER_AGENT    = "Mozilla/5.0 (OpenBeverly agenda transcriber)"
MAX_PDF_BYTES = 60 * 1024 * 1024   # skip oversized files
AGENDA_PAGES  = 10                 # packets (agenda + all backup) are trimmed to this many front pages

PROMPT = """\
This PDF is a scanned meeting agenda from the City of Beverly, Massachusetts.
Some boards post the full meeting packet, where the agenda is followed by
supporting documents. Transcribe only the agenda itself, including any
committee agendas that directly follow it. Stop as soon as supporting
documents begin (letters, memos, legal notices, orders, applications,
reports, plans, minutes) and include nothing from them.

Rules:
- Keep the original wording, spelling, numbering, and line breaks.
- Use plain text only. No markdown, no commentary, no summary.
- Skip clerk "received and recorded" stamps, page numbers, and signatures.
- If a word is illegible, write [illegible].
- Output only the transcription."""


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def front_pages(pdf: bytes) -> tuple[bytes, int]:
    """Trim a long packet to its first AGENDA_PAGES pages. Returns (pdf, original page count)."""
    reader = PdfReader(io.BytesIO(pdf))
    total = len(reader.pages)
    if total <= AGENDA_PAGES:
        return pdf, total
    writer = PdfWriter()
    for page in reader.pages[:AGENDA_PAGES]:
        writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue(), total


def transcribe(client: anthropic.Anthropic, pdf: bytes) -> str:
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=8000,
        messages=[{
            "role": "user",
            "content": [
                {"type": "document", "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": base64.standard_b64encode(pdf).decode(),
                }},
                {"type": "text", "text": PROMPT},
            ],
        }],
    )
    return message.content[0].text.strip()


def load_existing() -> dict:
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE) as f:
            return json.load(f)
    return {}


def save(data: dict):
    with open(OUTPUT_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Transcribe scanned Beverly agendas")
    parser.add_argument("--max", type=int, default=25,
                        help="Max number of new agendas to transcribe (default: 25)")
    parser.add_argument("--force", action="store_true",
                        help="Re-transcribe agendas already in agenda_text.json")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌  Set ANTHROPIC_API_KEY environment variable first.", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    with open(MEETINGS_FILE) as f:
        docs = [d for d in json.load(f) if d.get("agenda") and d.get("docId") is not None]

    existing = load_existing()
    todo = [d for d in docs
            if args.force or not existing.get(str(d["docId"]), {}).get("text")][: args.max]
    print(f"\n📄  Open Beverly: Agenda Transcriber")
    print(f"    Agendas in feed : {len(docs)}")
    print(f"    To transcribe   : {len(todo)}")
    print(f"    Model           : {CLAUDE_MODEL}\n")

    for i, doc in enumerate(todo, 1):
        key = str(doc["docId"])
        print(f"[{i}/{len(todo)}] {doc['title']} ({key})")
        entry = {
            "title": doc["title"],
            "board": doc.get("board", ""),
            "date": doc.get("date", ""),
            "transcribed": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "model": CLAUDE_MODEL,
        }
        try:
            url = doc["agenda"]
            pdf = fetch(url)
            if not pdf.startswith(b"%PDF"):
                raise ValueError("download was not a PDF")
            if len(pdf) > MAX_PDF_BYTES:
                raise ValueError(f"PDF too large ({len(pdf) // 1024 // 1024} MB)")
            pdf, pages = front_pages(pdf)
            entry["pages"] = pages
            entry["pdf"] = url
            entry["text"] = transcribe(client, pdf)
            print(f"    ✓ {len(entry['text'].split())} words\n")
        except Exception as e:
            entry["error"] = str(e)
            print(f"    ⚠️  {e}\n")
        existing[key] = entry
        save(existing)

    ok = sum(1 for v in existing.values() if v.get("text"))
    print(f"✅  agenda_text.json: {ok} transcribed, {len(existing) - ok} errors")


if __name__ == "__main__":
    main()
