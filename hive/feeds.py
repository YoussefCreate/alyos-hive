"""Read RSS and Atom feeds (URLs or local files) into plain dicts."""

import html
import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ATOM = "{http://www.w3.org/2005/Atom}"
USER_AGENT = "alyos-hive/0.1 (+https://github.com/YoussefCreate/alyos-hive)"


def _clean(text, limit=1500):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    return text[:limit]


def read_source(url, timeout=30):
    if not url.startswith(("http://", "https://")):
        return Path(url).read_bytes()
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def parse(raw):
    root = ET.fromstring(raw)
    items = []
    for item in root.iter("item"):  # RSS 2.0
        items.append({
            "title": _clean(item.findtext("title"), 300),
            "url": (item.findtext("link") or item.findtext("guid") or "").strip(),
            "summary": _clean(item.findtext("description")),
        })
    for entry in root.iter(f"{ATOM}entry"):  # Atom
        link = entry.find(f"{ATOM}link")
        items.append({
            "title": _clean(entry.findtext(f"{ATOM}title"), 300),
            "url": (link.get("href") if link is not None else entry.findtext(f"{ATOM}id") or "").strip(),
            "summary": _clean(entry.findtext(f"{ATOM}content") or entry.findtext(f"{ATOM}summary")),
        })
    return [i for i in items if i["title"] and i["url"]]


def fetch(url):
    return parse(read_source(url))
