import subprocess, json, os
from datetime import datetime, timezone
from xml.etree.ElementTree import Element, SubElement, tostring
import xml.dom.minidom

BASE_URL = "https://www.abc.net.au/triplej/programs/house-party"

def get_episodes_via_ytdlp():
    try:
        r = subprocess.run(
            ["yt-dlp", "--flat-playlist", "-j", "--no-warnings", "--playlist-end", "10", BASE_URL],
            capture_output=True, text=True, timeout=120
        )
        urls = []
        for line in r.stdout.strip().splitlines():
            try:
                d = json.loads(line)
                url = d.get("url") or d.get("webpage_url", "")
                if "house-party" in url:
                    if not url.startswith("http"):
                        url = "https://www.abc.net.au" + url
                    urls.append(url)
            except:
                pass
        print(f"Playlist: {len(urls)} URLs")
        return urls
    except Exception as e:
        print(f"Playlist fout: {e}")
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
        print(f"  fout: {r.stderr[:200]}")
    except Exception as e:
        print(f"  error: {e}")
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
            except:
                pass
        if ep.get("url"):
            enc = SubElement(item, "enclosure")
            enc.set("url", ep["url"])
            enc.set("type", "audio/mpeg")
            enc.set("length", "0")
    return xml.dom.minidom.parseString(tostring(rss, encoding="unicode")).toprettyxml(indent="  ")

FALLBACK_URLS = [
    "https://www.abc.net.au/triplej/programs/house-party/house-party/106555166",
    "https://www.abc.net.au/triplej/programs/house-party/house-party/106531936",
    "https://www.abc.net.au/triplej/programs/house-party/house-party/106507590",
    "https://www.abc.net.au/triplej/programs/house-party/house-party/106484466",
    "https://www.abc.net.au/triplej/programs/house-party/house-party/106482730",
    "https://www.abc.net.au/triplej/programs/house-party/house-party/106457968",
    "https://www.abc.net.au/triplej/programs/house-party/house-party/106456228",
    "https://www.abc.net.au/triplej/programs/house-party/house-party/106428746",
]

os.makedirs("docs", exist_ok=True)
episode_urls = get_episodes_via_ytdlp()
if not episode_urls:
    print("Fallback naar bekende URLs...")
    episode_urls = FALLBACK_URLS

data = []
for url in episode_urls:
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
print(f"Klaar: docs/feed.xml ({len(data)} items)")
