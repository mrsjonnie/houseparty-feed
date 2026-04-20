#!/usr/bin/env python3
"""
Generate Triple J House Party RSS feed with date & presenter in the title.
"""

import subprocess, json, os, re, sys
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
    """Probeer de afleveringenlijst op te halen via de ABC‑API."""
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


def get_info_with_ytdlp(page_url):
    """
    Gebruik yt-dlp om:
    - directe audio‑URL
    - titel (als fallback)
    - upload_date (YYYYMMDD)
    Retourneert een dict met keys: url, title, upload_date.
    """
    cmd = [
        "yt-dlp",
        "-j",
        "--no-playlist",
        "--no-warnings",
        "--geo-bypass",
        page_url,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            print(f"  yt-dlp fout: {result.stderr[:120]}")
            return None
        data = json.loads(result.stdout)
        return {
            "url": data.get("url"),
            "title": data.get("title", "House Party"),
            "upload_date": data.get("upload_date"),
        }
    except Exception as e:
        print(f"  yt-dlp exception: {e}")
        return None


def get_presenter(page_url):
    """
    Probeer de presentator (bijv. Latifa Tee) en diens ABC‑profiel‑URL
    uit de afleveringspagina te halen.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/124.0.0.0 Safari/537.36"
    }
    try:
        r = requests.get(page_url, headers=headers, timeout=15)
        r.raise_for_status()
        html = r.text

        # Zoek naar een label zoals "Presenter" of "Host"
        patterns = [
            r'Presenter[^>]*>[^<]*<[^>]*>([^<]+)',
            r'Host[^>]*>[^<]*<[^>]*>([^<]+)',
            r'"presenter"\s*:\s*"([^"]+)"',
            r'"host"\s*:\s*"([^"]+)"',
        ]
        for pat in patterns:
            m = re.search(pat, html, re.I)
            if m:
                name = m.group(1).strip()
                # Probeer een link naar de presentator‑pagina te vinden
                link_m = re.search(
                    rf'href="([^"]*{re.escape(name)}[^"]*)"', html, re.I
                )
                presenter_url = link_m.group(1) if link_m else ""
                if presenter_url and presenter_url.startswith("/"):
                    presenter_url = "https://www.abc.net.au" + presenter_url
                return name, presenter_url
        # Fallback: zoek naar een <meta name="author"> tag
        meta = re.search(
            r'<meta[^>]+name=["\']author["\'][^>]+content=["\']([^"\']+)["\']',
            html,
            re.I,
        )
        if meta:
            name = meta.group(1).strip()
            return name, ""
        return "", ""
    except Exception as e:
        print(f"  FOUT bij ophalen presenter: {e}")
        return "", ""


def format_date(upload_date_str):
    """
    Zet YYYYMMDD om naar "Sat 21 Mar 2026 at 8:00am".
    (We gebruiken een vaste tijdstip 08:00 am omdat de exacte tijd
    niet altijd beschikbaar is in de metadata.)
    """
    try:
        dt = datetime.strptime(upload_date_str, "%Y%m%d").replace(tzinfo=timezone.utc)
        day_name = dt.strftime("%a")
        day = dt.strftime("%d").lstrip("0")   # verwijder leading zero
        month = dt.strftime("%b")
        year = dt.strftime("%Y")
        time_str = "8:00am"
        return f"{day_name} {day} {month} {year} at {time_str}"
    except Exception:
        return ""


def build_rss(items):
    """Bouwt een RSS‑feed met iTunes‑namespace."""
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
        info = get_info_with_ytdlp(url)
        if not info or not info.get("url"):
            print("  OVERGESLAGEN (geen audio‑info)")
            continue

        audio_url = info["url"]
        raw_title = info.get("title", "House Party")
        upload_date = info.get("upload_date")
        date_str = format_date(upload_date) if upload_date else ""

        presenter_name, presenter_url = get_presenter(url)
        if presenter_name:
            presenter_part = (
                f"[{presenter_name}]({presenter_url})" if presenter_url else presenter_name
            )
        else:
            presenter_part = ""

        # Bouw de titel zoals gewenst
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
                "description": "",  # optioneel
            }
        )
        print(f"  OK: {title}")

    print(f"Feed bouwen met {len(data)} afleveringen …")
    with open("docs/feed.xml", "w", encoding="utf-8") as f:
        f.write(build_rss(data))
    print(f"Klaar: docs/feed.xml ({len(data)} items)")
