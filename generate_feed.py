import subprocess
import json
import os
import re
from datetime import datetime, timezone
from xml.etree.ElementTree import Element, SubElement, tostring
import xml.dom.minidom
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.abc.net.au/triplej/programs/house-party"
OUTPUT_DIR = "docs"

def get_episodes():
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(BASE_URL, headers=headers, timeout=15)
    soup = BeautifulSoup(r.text, "html.parser")
    links = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.search(r"/house-party/house-party/\d+", href):
            full = "https://www.abc.net.au" + href if href.startswith("/") else href
            if full not in seen:
                seen.add(full)
                links.append(full)
    return links[:10]

def get_audio_info(episode_url):
    try:
        result = subprocess.run(
            ["yt-dlp", "-j", "--no-playlist", "--no-warnings", episode_url],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return {
                "url": data.get("url"),
                "title": data.get("title", "House Party"),
                "description": data.get("description", ""),
                "date": data.get("upload_date"),
                "duration": data.get("duration", 0),
            }
    except Exception as e:
        print(f"Error: {e}")
    return None

def build_rss(episodes_data):
    rss = Element("rss", version="2.0")
    rss.set("xmlns:itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = "Triple J House Party"
    SubElement(channel, "link").text = BASE_URL
    SubElement(channel, "description").text = "Triple J House Party DJ mix show"
    SubElement(channel, "language").text = "en-au"

    for ep in episodes_data:
        item = SubElement(channel, "item")
        SubElement(item, "title").text = ep["title"]
        SubElement(item, "link").text = ep["page_url"]
        SubElement(item, "guid", isPermaLink="false").text = ep["page_url"]
        SubElement(item, "description").text = ep.get("description", "")[:500]
        if ep.get("date"):
            try:
                dt = datetime.strptime(ep["date"], "%Y%m%d").replace(tzinfo=timezone.utc)
                SubElement(item, "pubDate").text = dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
            except:
                pass
        if ep.get("url"):
            enc = SubElement(item, "enclosure")
            enc.set("url", ep["url"])
            enc.set("type", "audio/mpeg")
            enc.set("length", "0")

    xml_str = xml.dom.minidom.parseString(tostring(rss, encoding="unicode")).toprettyxml(indent="  ")
    return xml_str

if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("Fetching episode list...")
    episode_urls = get_episodes()
    print(f"Found {len(episode_urls)} episodes")
    episodes_data = []
    for url in episode_urls:
        print(f"Fetching: {url}")
        info = get_audio_info(url)
        if info:
            info["page_url"] = url
            episodes_data.append(info)
            print(f"  OK: {info['title']}")
    print(f"Building feed with {len(episodes_data)} episodes...")
    rss_xml = build_rss(episodes_data)
    output_path = os.path.join(OUTPUT_DIR, "feed.xml")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(rss_xml)
    print(f"Done: {output_path}")
