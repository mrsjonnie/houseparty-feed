import subprocess, json, os, re, sys
from datetime import datetime, timezone
from xml.etree.ElementTree import Element, SubElement, tostring
import xml.dom.minidom
import requests

BASE_URL = "https://www.abc.net.au/triplej/programs/house-party"
COLLECTION_API = "https://api.abc.net.au/v2/page/collection?path=/triplej/programs/house-party&size=20"

def get_collection():
    """Haalt de lijst met afleveringen op van de ABC‑API."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    try:
        r = requests.get(COLLECTION_API, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        items = []
        for block in data.get("blocks", []):
            for promo in block.get("promos", []):
                url = promo.get("url")
                if url and "/house-party/" in url:
                    # Maak de URL absoluut indien nodig
                    if url.startswith("/"):
                        url = "https://www.abc.net.au" + url
                    items.append(url)
        # Dubbels verwijderen terwijl volgorde behouden blijft
        seen = set()
        uniq = []
        for u in items:
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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    try:
        r = requests.get(page_url, headers=headers, timeout=15)
        r.raise_for_status()
        # Zoek het __NEXT_DATA__‑blok
        m = re.search(r'<script id="__NEXT_DATA__" type="application/json">([^<]+)</script>', r.text)
        if not m:
            print(f"  GEEN __NEXT_DATA__ in {page_url}")
            return None
        data = json.loads(m.group(1))
        # Navigeer naar de renditions (structuur observed in de aflevering)
        try:
            renditions = data["props"]["pageProps"]["data"]["documentProps"]["renditions"]
            if renditions and isinstance(renditions, list):
                # Neem de eerste beschikbare URL (meestal .aac)
                audio_url = renditions[0].get("url")
                if audio_url:
                    return audio_url
        except (KeyError, TypeError, IndexError):
            pass
        # Fallback: zoek elke URL die eindigt op .aac of .mp4 in de hele JSON
        def find_media(obj):
            if isinstance(obj, dict):
                for v in obj.values():
                    if isinstance(v, str) and (v.endswith(".aac") or v.endswith(".mp4") or ".m3u8" in v):
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
                SubElement(it, "pubDate").text = dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
            except:
                pass
        if ep.get("url"):
            enc = SubElement(it, "enclosure")
            enc.set("url", ep["url"])
            enc.set("type", "audio/mpeg")
            enc.set("length", "0")
    return xml.dom.minidom.parseString(tostring(rss, encoding="unicode")).toprettyxml(indent="  ")

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
        if audio_url:
            # Probeer titel en datum uit de pagina te halen (eenvoudig)
            try:
                r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                title_match = re.search(r'<title>([^<]+)</title>', r.text)
                title = title_match.group(1).strip() if title_match else "House Party"
                # Verwijder eventuele "‑ Triple J" of dergelijke suffix
                title = re.sub(r"\s*[-–]\s*Triple J.*$", "", title, flags=re.I).strip()
                date_match = re.search(r'"uploadDate"\s*:\s*"(\d{8})', r.text)
                upload_date = date_match.group(1) if date_match else None
            except:
                title = "House Party"
                upload_date = None
            data.append({
                "title": title,
                "url": audio_url,
                "page_url": url,
                "date": upload_date,
                "description": ""  # beschrijving optioneel
            })
            print(f"  OK: {title} → {audio_url}")
        else:
            print("  OVERGESLAGEN")
    print(f"Feed bouwen met {len(data)} afleveringen …")
    with open("docs/feed.xml", "w", encoding="utf-8") as f:
        f.write(build_rss(data))
    print(f"Klaar: docs/feed.xml ({len(data)} items)")
