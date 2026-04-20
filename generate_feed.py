import subprocess, json, os, re
from datetime import datetime, timezone
from xml.etree.ElementTree import Element, SubElement, tostring
import xml.dom.minidom, requests

BASE_URL = "https://www.abc.net.au/triplej/programs/house-party"
API_URL = "https://api.abc.net.au/v2/page/collection?path=/triplej/programs/house-party&size=10"

def get_episodes():
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(API_URL, headers=headers, timeout=15)
        data = r.json()
        episodes = []
        for item in data.get("collection", []):
            url = item.get("canonicalURL", "")
            if url:
                episodes.append("https://www.abc.net.au" + url if url.startswith("/") else url)
        return episodes[:10]
    except Exception as e:
        print(f"API fout: {e}")
        return []

def get_audio_info(url):
    try:
        r = subprocess.run(
            ["yt-dlp", "-j", "--no-playlist", "--no-warnings", url],
            capture_output=True, text=True, timeout=60
        )
        if r.returncode == 0:
            d = json.loads(r.stdout)
            return {
                "url": d.get("url"),
                "title": d.get("title", "House Party"),
                "description": d.get("description", ""),
                "date": d.get("upload_date"),
            }
        else:
            print(f"yt-dlp fout: {r.stderr[:200]}")
    except Exception as e:
        print(f"Error: {e}")
    return None

def build_rss(episodes):
    rss = Element("rss", version="2.0")
    rss.set("xmlns:itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")
    ch = SubElement(rss, "channel")
    SubElement(ch, "title").text = "Triple J House Party"
    SubElement(ch, "link").text = BASE_URL
    SubElement(ch, "description").text = "Triple J House Party DJ mix show"
    SubElement(ch, "language").text = "en-au"
    for ep in episodes:
        item = SubElement(ch, "item")
        SubElement(item, "title").text = ep["title"]
        SubElement(item, "link").text = ep["page_url"]
        SubElement(item, "guid", isPermaLink="false").text = ep["page_url"]
        SubElement(item, "description").text = ep.get("description", "")[:500]
        if ep.get("date"):
            try:
                dt = datetime.strptime(ep["date"], "%Y%m%d").replace(tzinfo=timezone.utc)
                SubElement(item, "pubDate").text = dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
            except: pass
        if ep.get("url"):
            enc = SubElement(item, "enclosure")
            enc.set("url", ep["url"])
            enc.set("type", "audio/mpeg")
            enc.set("length", "0")
    return xml.dom.minidom.parseString(tostring(rss, encoding="unicode")).toprettyxml(indent="  ")

if __name__ == "__main__":
    os.makedirs("docs", exist_ok=True)
    print("Afleveringen ophalen via ABC API...")
    eps = get_episodes()
    print(f"Gevonden: {len(eps)} afleveringen")
    data = []
    for url in eps:
        print(f"Verwerken: {url}")
        info = get_audio_info(url)
        if info:
            info["page_url"] = url
            data.append(info)
            print(f"  OK: {info['title']}")
        else:
            print(f"  OVERGESLAGEN")
    print(f"Feed bouwen met {len(data)} afleveringen...")
    with open("docs/feed.xml", "w", encoding="utf-8") as f:
        f.write(build_rss(data))
    print("Klaar: docs/feed.xml")
