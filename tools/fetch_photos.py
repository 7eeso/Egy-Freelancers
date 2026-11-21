"""Download free-licence photos (Pexels API) into static/img and write static/img/CREDITS.md.

Usage:  PEXELS_API_KEY=xxxx python tools/fetch_photos.py
Pexels licence allows free commercial use without attribution; we still record credits.
Images are saved LOCALLY because the site's CSP only allows images from itself
(no hotlinking = no third-party tracking of your visitors).
"""
import io, json, os, sys, urllib.parse, urllib.request
from pathlib import Path
from PIL import Image

KEY = os.environ.get("PEXELS_API_KEY") or sys.exit("Set PEXELS_API_KEY (free at pexels.com/api)")
OUT = Path(__file__).resolve().parent.parent / "static" / "img"
QUERIES = {  # file name -> search query
    "cat-design.webp": "graphic designer workspace", "cat-development.webp": "web developer laptop code",
    "cat-writing.webp": "writing notebook desk", "cat-marketing.webp": "social media marketing phone",
    "cat-video.webp": "video editing timeline", "cat-business.webp": "business meeting office",
    "showcase-branding.webp": "brand identity design", "showcase-website.webp": "website design mockup",
    "showcase-video.webp": "video production camera", "showcase-content.webp": "content creator desk",
}

def get(url, headers=None):
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=30).read()

credits = ["# Photo credits\n"]
for name, q in QUERIES.items():
    data = json.loads(get("https://api.pexels.com/v1/search?" + urllib.parse.urlencode({"query": q, "per_page": 1, "orientation": "landscape"}), {"Authorization": KEY}))
    if not data["photos"]: print("no result for", q); continue
    ph = data["photos"][0]
    im = Image.open(io.BytesIO(get(ph["src"]["large"]))).convert("RGB")
    w, h = (640, 400) if name.startswith("cat-") else (800, 520)
    im.thumbnail((w * 2, h * 2)); im = im.resize((w, h)) if im.size != (w, h) else im
    im.save(OUT / name, "WEBP", quality=80)
    credits.append(f"- {name}: photo by {ph['photographer']} on Pexels ({ph['url']})")
    print("saved", name)
(OUT / "CREDITS.md").write_text("\n".join(credits) + "\n")
