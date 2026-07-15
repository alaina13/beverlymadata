#!/usr/bin/env python3
"""
Beverly Data — Street Paving Page Tracker
Fetches the City of Beverly's Street Paving update page and records a new
history entry in street_paving_history.json whenever the page text changes.

Source:
  - https://www.beverlyma.gov/195/Street-Paving

Usage:
    python3 fetch_street_paving.py
"""

import json
import urllib.request
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

OUT_DIR = Path(__file__).parent
URL = "https://www.beverlyma.gov/195/Street-Paving"
HISTORY_PATH = OUT_DIR / "street_paving_history.json"

SKIP_TAGS = {"script", "style"}


class PageContentExtractor(HTMLParser):
    """Pulls the visible text out of the CivicPlus main content div (id="page")."""

    def __init__(self):
        super().__init__()
        self.stack_depth = 0
        self.target_depth = None
        self.skip_depth = 0
        self.chunks = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "div":
            self.stack_depth += 1
            classes = attrs.get("class") or ""
            if (
                self.target_depth is None
                and attrs.get("id") == "page"
                and "moduleContentNew" in classes
            ):
                self.target_depth = self.stack_depth
        if tag in SKIP_TAGS:
            self.skip_depth += 1

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS and self.skip_depth > 0:
            self.skip_depth -= 1
        if tag == "div":
            if self.target_depth is not None and self.stack_depth == self.target_depth:
                self.target_depth = None
            self.stack_depth -= 1

    def handle_data(self, data):
        if self.target_depth is not None and self.skip_depth == 0:
            text = data.strip()
            if text:
                self.chunks.append(text)

    def get_text(self):
        return "\n".join(self.chunks)


def fetch_html(url):
    req = urllib.request.Request(url, headers={"User-Agent": "BeverlyData/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def load_history():
    if HISTORY_PATH.exists():
        with open(HISTORY_PATH) as f:
            return json.load(f)
    return {"url": URL, "last_checked": None, "history": []}


def main():
    print("\n🚧  Beverly Data — Street Paving Page Tracker")
    today = datetime.now().strftime("%Y-%m-%d")

    html = fetch_html(URL)
    parser = PageContentExtractor()
    parser.feed(html)
    text = parser.get_text()

    if not text:
        raise RuntimeError("Extracted page text was empty, page structure may have changed")

    data = load_history()
    data["last_checked"] = today

    last_text = data["history"][-1]["text"] if data["history"] else None
    if text != last_text:
        data["history"].append({"date": today, "text": text})
        print(f"  Change detected, recorded new snapshot for {today}")
    else:
        print("  No change since last snapshot")

    with open(HISTORY_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  ✅  Written to {HISTORY_PATH}")


if __name__ == "__main__":
    main()
