#!/usr/bin/env python3
"""
Generate Triple J House Party RSS feed with date & presenter in the title.
Uses direct HTTP requests + __NEXT_DATA__ parsing (no yt-dlp needed).
"""

import json, os, re, sys
from datetime import datetime, timezone
from xml.etree.ElementTree import Element, SubElement, tostring
import xml.dom.minidom
import requests

# ----------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------
BASE_URL = "https://www.abc.net.au/triplej/programs/house-party"
COLLECTION_API = (
    "https://api.abc.net.au/v2/page/collection?"
    "path=/triplej/programs/house-party&size=20"
)
FALLBACK_URLS = [
    "https://www.abc.net.au/triplej/programs/house-party/house-party/106555166",
    "https://www.abc.net.au/triplej/programs/house-party/house-party/106531936",
    "https://www.abc.net.au/triplej/programs/house-party/house-party/106507590",
    "https://www.abc.net.au/triplej/programs/house-party/house-party/106484466",
    "https://www.abc.net.au/triplej/programs/house-party/house-party/106482730",
    "https://www.abc.net.au/triplej/programs/house-party/house-party/106457968",
]

# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------
def get_collection():
    """Try to get the episode list from the ABC API."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/124.0.0.0 Safari/537.36"
    }
    try:
        r = requests.get(COLLECTION_API, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        urls = []
        for block in data.get("blocks", []):
            for promo in block.get("promos", []):
                url = promo.get("url")
                if url and "/house-party/" in url:
                    if url.startswith("/"):
                        url = "https://www.abc.net.au" + url
                    urls.append(url)
        # deduplicate while preserving order
        seen = set()
        uniq = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                uniq.append(u)
        return uniq
    except Exception as e:
        print(f"FOUT bij ophalen collectie: {e}")
        return []


def extract_episode_info(page_url):
    """Return dict with audio_url, upload_date, presenter_name, presenter_url."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/124.0.0.0 Safari/537.36"
    }
    try:
        r = requests.get(page_url, headers=headers, timeout=15)
        r.raise_for_status()
        html = r.text

        # --- locate __NEXT_DATA__ JSON ---
        m = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">([^<]+)</script>',
            html,
        )
        if not m:
            print(f"  GEEN __NEXT_DATA__ in {page_url}")
            return None
        data = json.loads(m.group(1))

        props = data.get("props", {}).get("pageProps", {})

        # ----- audio URL -----
        try:
            renditions = props["data"]["documentProps"]["renditions"]
            if renditions and isinstance(renditions, list):
                # pick the first entry that looks like an audio file
                for rend in renditions:
                    url = rend.get("url")
                    if url and (url.endswith(".aac") or ".m3u8" in url):
                        audio_url = url
                        break
                else:
                    audio_url = renditions[0].get("url")
            else:
                audio_url = None
        except (KeyError, TypeError, IndexError):
            audio_url = None

        # ----- upload date -----
        upload_date = None
        doc = props.get("data", {}).get("documentProps", {})
        for key in ("firstPublished", "datePublished", "uploadDate", "publishDate"):
            if doc.get(key):
                upload_date = doc[key]
                break
        # fallback: search recursively for a string that looks like YYYYMMDD
        if not upload_date:
            def find_date(obj):
                if isinstance(obj, dict):
                    for v in obj.values():
                        if isinstance(v, str) and re.fullmatch(r"\d{8}", v):
                            return v
                        res = find_date(v)
                        if res:
                            return res
                elif isinstance(obj, list):
                    for v in obj:
                        res = find_date(v)
                        if res:
                            return res
                return None
            upload_date = find_date(props)

        # ----- presenter -----
        presenter_name = ""
        presenter_url = ""
        try:
            prep = props.get("presentersProps", {}).get("linkPrepared", [])
            if prep and isinstance(prep, list) and len(prep) > 0:
                item = prep[0]
                presenter_name = item.get("label", {}).get("full", "").strip()
                presenter_url = item.get("canonicalURL", "")
                if presenter_url and presenter_url.startswith("/"):
                    presenter_url = "https://www.abc.net.au" + presenter_url
        except Exception:
            pass

        return {
            "audio_url": audio_url,
            "upload_date": upload_date,
            "presenter_name": presenter_name,
            "presenter_url": presenter_url,
        }
    except Exception as e:
        print(f"  FOUT bij verwerken {page_url}: {e}")
        return None


def format_date(upload_date_str):
    """Convert YYYYMMDD → 'Sat 21 Mar 2026 at 8:00am' (fixed 08:00 am)."""
    try:
        dt = datetime.strptime(upload_date_str, "%Y%m%d").replace(tzinfo=timezone.utc)
        day_name = dt.strftime("%a")
        day = dt.strftime("%d").lstrip("0")
        month = dt.strftime("%b")
        year = dt.strftime("%Y")
        return f"{day_name} {day} {month} {year} at 8:00am"
    except Exception:
        return ""


def build_rss(items):
    """Build RSS feed with iTunes namespace."""
    rss = Element("rss", version="2.0")
    rss.set("xmlns:itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")
    ch = SubElement(rss, "channel")
    SubElement(ch, "title").text = "Triple J House Party"
    SubElement(ch, "link").text = BASE_URL
    SubElement(ch, "description").text = "Triple J House Party DJ mix show"
    SubElement(ch, "language").text = "en-au"
    for ep in items:
        it = SubElement(ch, "item")
        SubElement(it, "title").text = ep["title"]
        SubElement(it, "link").text = ep["page_url"]
        SubElement(it, "guid", isPermaLink="false").text = ep["page_url"]
        SubElement(it, "description").text = ep.get("description", "")[:500]
        if ep.get("date"):
            try:
                dt = datetime.strptime(ep["date"], "%Y%m%d").replace(tzinfo=timezone.utc)
                SubElement(it, "pubDate").text = dt.strftime(
                    "%a, %d %b %Y %H:%M:%S +0000"
                )
            except:
                pass
        if ep.get("url"):
            enc = SubElement(it, "enclosure")
            enc.set("url", ep["url"])
            enc.set("type", "audio/mpeg")
            enc.set("length", "0")
    return xml.dom.minidom.parseString(tostring(rss, encoding="unicode")).toprettyxml(
        indent="  "
    )


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
if __name__ == "__main__":
    os.makedirs("docs", exist_ok=True)
    print("Ophalen afleveringenlijst …")
    page_urls = get_collection()
    if not page_urls:
        print("WAARSCHUWLING: Geen afleveringen gevonden via API, gebruik vaste lijst.")
        page_urls = FALLBACK_URLS

    data = []
    for url in page_urls:
        print(f"Verwerken: {url}")
        info = extract_episode_info(url)
        if not info or not info.get("audio_url"):
            print("  OVERGESLAGEN (geen audio‑info)")
            continue

        audio_url = info["audio_url"]
        upload_date = info["upload_date"]
        date_str = format_date(upload_date) if upload_date else ""

        presenter_name = info["presenter_name"]
        presenter_url = info["presenter_url"]
        if presenter_name:
            presenter_part = (
                f"[{presenter_name}]({presenter_url})" if presenter_url else presenter_name
            )
        else:
            presenter_part = ""

        # Build title: <date> – House Party [Presenter](URL)
        parts = []
        if date_str:
            parts.append(date_str)
        parts.append("– House Party")
        if presenter_part:
            parts.append(f"[{presenter_part}]")
        title = " ".join(parts)

        data.append(
            {
                "title": title,
                "url": audio_url,
                "page_url": url,
                "date": upload_date,
                "description": "",  # optional
            }
        )
        print(f"  OK: {title}")

    print(f"Feed bouwen met {len(data)} afleveringen …")
    with open("docs/feed.xml", "w", encoding="utf-8") as f:
        f.write(build_rss(data))
    print(f"Klaar: docs/feed.xml ({len(data)} items)")
