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

# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------
def get_collection():
    """Haalt de lijst met afleverings‑URL’s op van de ABC‑API."""
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


def get_audio_url(page_url):
    """Gegeven een afleverings‑pagina, retourneer de directe audio‑URL."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/124.0.0.0 Safari/537.36"
    }
    try:
        r = requests.get(page_url, headers=headers, timeout=15)
        r.raise_for_status()
        m = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">([^<]+)</script>',
            r.text,
        )
        if not m:
            print(f"  GEEN __NEXT_DATA__ in {page_url}")
            return None
        data = json.loads(m.group(1))
        try:
            renditions = data["props"]["pageProps"]["data"]["documentProps"]["renditions"]
            if renditions and isinstance(renditions, list):
                audio_url = renditions[0].get("url")
                if audio_url:
                    return audio_url
        except (KeyError, TypeError, IndexError):
            pass

        # Fallback: zoek elke .aac/.mp4/.m3u8 URL in de JSON
        def find_media(obj):
            if isinstance(obj, dict):
                for v in obj.values():
                    if isinstance(v, str) and (
                        v.endswith(".aac")
                        or v.endswith(".mp4")
                        or ".m3u8" in v
                    ):
                        return v
                    res = find_media(v)
                    if res:
                        return res
            elif isinstance(obj, list):
                for v in obj:
                    res = find_media(v)
                    if res:
                        return res
            return None

        audio_url = find_media(data)
        if audio_url:
            return audio_url
        print(f"  GEEN AUDIO‑URL gevonden in {page_url}")
        return None
    except Exception as e:
        print(f"  FOUT bij verwerken {page_url}: {e}")
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

        # Zoek naar een label zoals "Presenter" of "Host" gevolgd door een naam
        # Voorbeeld: <span>Presenter</span><span>Latifa Tee</span>
        # of <div class="presenter">Latifa Tee</div>
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
                # Maak de URL absoluut indien nodig
                if presenter_url and presenter_url.startswith("/"):
                    presenter_url = "https://www.abc.net.au" + presenter_url
                return name, presenter_url
        # Als geen specifieke label gevonden, kijk naar een bekende auteur‑meta
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
    Converteert YYYYMMDD → "Sat 21 Mar 2026 at 8:00am".
    Als de tijd onbekend is, gebruiken we een vaste tijdstip 08:00 am.
    """
    try:
        dt = datetime.strptime(upload_date_str, "%Y%m%d").replace(tzinfo=timezone.utc)
        # Dagnaam, dag, maand, jaar
        day_name = dt.strftime("%a")
        day = dt.strftime("%d").lstrip("0")  # verwijder leading zero
        month = dt.strftime("%b")
        year = dt.strftime("%Y")
        # vaste tijd (kan later verfijnd worden indien tijd beschikbaar komt)
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
        page_urls = [
            "https://www.abc.net.au/triplej/programs/house-party/house-party/106555166",
            "https://www.abc.net.au/triplej/programs/house-party/house-party/106531936",
            "https://www.abc.net.au/triplej/programs/house-party/house-party/106507590",
            "https://www.abc.net.au/triplej/programs/house-party/house-party/106484466",
            "https://www.abc.net.au/triplej/programs/house-party/house-party/106482730",
            "https://www.abc.net.au/triplej/programs/house-party/house-party/106457968",
        ]

    data = []
    for url in page_urls:
        print(f"Verwerken: {url}")
        audio_url = get_audio_url(url)
        if not audio_url:
            print("  OVERGESLAGEN (geen audio)")
            continue

        # Datum en presenter
        # Probeer eerst datum uit yt-dlp (via upload_date) – we halen het nog even op
        # zodat we een consistente datum hebben voor de titel.
        # We maken een aparte yt-dlp call alleen voor datum/presentator info.
        # Dit is efficiënt genoeg omdat we maar enkele afleveringen per run hebben.
        yt_info = None
        try:
            yt_proc = subprocess.run(
                ["yt-dlp", "-j", "--no-playlist", "--no-warnings", "--geo-bypass", url],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if yt_proc.returncode == 0:
                yt_info = json.loads(yt_proc.stdout)
        except Exception:
            yt_info = None

        upload_date = yt_info.get("upload_date") if yt_info else None
        date_str = format_date(upload_date) if upload_date else ""

        presenter_name, presenter_url = get_presenter(url)
        # Als we geen presenter vinden, val terug op lege string
        if presenter_name:
            # Markdown‑achtige link zoals gewenst: [Latifa Tee](URL)
            presenter_part = f"[{presenter_name}]({presenter_url})" if presenter_url else presenter_name
        else:
            presenter_part = ""

        # Titel opbouwen
        base_title = "House Party"
        if date_str and presenter_part:
            title = f"{date_str} – {base_title} [{presenter_part}]"
        elif date_str:
            title = f"{date_str} – {base_title}"
        elif presenter_part:
            title = f"{base_title} [{presenter_part}]"
        else:
            title = base_title

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
