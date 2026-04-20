import subprocess, json, os, re
from datetime import datetime, timezone
from xml.etree.ElementTree import Element, SubElement, tostring
import xml.dom.minidom, requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.abc.net.au/triplej/programs/house-party"

def get_episodes():
    r = requests.get(BASE_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    links, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.search(r"/house-party/house-party/\d+", href):
            full = "https://www.abc.net.au" + href if href.startswith("/") else href
            if full not in seen:
                seen.add(full)
                links.append(full)
    return links[:10]

def get_audio_info(url):
    try:
        r = subprocess.run(["yt-dlp", "-j", "--no-playlist", "--no-warnings", url],
                           capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            d = json.loads(r.stdout)
            return {"url": d.get("url"), "title": d.get("title", "House Party"),
                    "description": d.get("description", ""), "date": d.get("upload_date")}
    except Exception as e:
        print(f"Error: {e}")
    return None

def build_rss(episodes):
    rss = Element("rss", version="2.0")
    ch = SubElement(rss, "channel")
    SubElement(ch, "title").text = "Triple J House Party"
    SubElement(ch, "link").text = BASE_URL
    SubElement(ch, "description").text = "Triple J House Party DJ mix show"
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
            enc.set("url", ep["url"]); enc.set("type", "audio/mpeg"); enc.set("length", "0")
    return xml.dom.minidom.parseString(tostring(rss, encoding="unicode")).toprettyxml(indent="  ")

if __name__ == "__main__":
    os.makedirs("docs", exist_ok=True)
    eps = get_episodes()
    print(f"Found {len(eps)} episodes")
    data = []
    for url in eps:
        info = get_audio_info(url)
        if info:
            info["page_url"] = url
            data.append(info)
            print(f"OK: {info['title']}")
    with open("docs/feed.xml", "w", encoding="utf-8") as f:
        f.write(build_rss(data))
    print("Done: docs/feed.xml")
