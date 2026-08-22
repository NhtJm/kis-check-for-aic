#!/usr/bin/env python3
"""Dung UI kiem tra submission KIS.

Nhung toan bo index media-info vao mot file HTML tu chua, de UI co the nap
bat ky file CSV submission nao ngay trong trinh duyet.

    python3 build_viewer.py [media-info-dir] [output.html] [submission.csv]

Tham so thu 3 la tuy chon: neu co, CSV do duoc nap san khi mo trang.
Them --no-check de bo qua buoc hoi YouTube xem video con song khong.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import json, os, re, sys, csv, urllib.request, urllib.error

args      = [a for a in sys.argv[1:] if not a.startswith("--")]
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA_DIR = args[0] if len(args) > 0 else os.path.join(ROOT, "data", "media-info")
OUT_PATH  = args[1] if len(args) > 1 else os.path.join(ROOT, "web", "index.html")
INIT_CSV  = args[2] if len(args) > 2 else None
DEFAULT_FPS = 30


def build_index(media_dir):
    """Doc moi file media-info/*.json -> map {video_id: {yt,title,author,date,length,url}}."""
    index = {}
    for name in sorted(os.listdir(media_dir)):
        if not name.endswith(".json"):
            continue
        d = json.load(open(os.path.join(media_dir, name), encoding="utf-8"))
        m = re.search(r"v=([\w-]+)", d["watch_url"])
        index[name[:-5]] = {"yt": m.group(1) if m else None,
                            "title": d["title"],
                            "author": d["author"],
                            "date": d["publish_date"],
                            "length": d["length"],
                            "url": d["watch_url"]}
    return index


def read_submission(path):
    """Doc CSV submission -> list [video_id, frame]. Bo qua dong header neu co."""
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.reader(f):
            if len(row) < 2 or not row[0].strip():
                continue
            try:
                rows.append([row[0].strip(), int(float(row[1]))])
            except ValueError:
                continue          # dong header
    return rows


def probe(yt):
    """Hoi YouTube xem video con xem duoc khong. None = khong kiem tra duoc."""
    url = ("https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v="
           + yt + "&format=json")
    try:
        urllib.request.urlopen(url, timeout=15).read()
        return "ok"
    except urllib.error.HTTPError as e:
        return {401: "private", 403: "private", 404: "removed"}.get(e.code, "http-%d" % e.code)
    except Exception:
        return None


index = build_index(MEDIA_DIR)
initial, status = None, {}

if INIT_CSV:
    rows = read_submission(INIT_CSV)
    initial = {"source": os.path.basename(INIT_CSV), "rows": rows}
    missing = sorted({v for v, _ in rows if v not in index})
    if missing:
        print(f"  CANH BAO thieu media-info: {missing}")
    if "--no-check" not in sys.argv:
        for v in sorted({v for v, _ in rows if v in index}):
            st = probe(index[v]["yt"])
            if st and st != "ok":
                status[v] = st

payload = {"fps": DEFAULT_FPS, "media": index, "initial": initial, "status": status}

template = open(os.path.join(ROOT, "templates", "viewer_template.html"), encoding="utf-8").read()
html = template.replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
open(OUT_PATH, "w", encoding="utf-8").write(html)

# index gon mot file de server dung khi deploy (media-info/ khong len git)
with open(os.path.join(ROOT, "web", "media-index.json"), "w", encoding="utf-8") as f:
    json.dump(index, f, ensure_ascii=False, separators=(",", ":"))

print(f"Da tao {OUT_PATH}  ({len(html)/1024:.0f} KB)")
print(f"Da tao web/media-index.json  ({os.path.getsize(os.path.join(ROOT,'web','media-index.json'))/1024:.0f} KB)")
print(f"  index: {len(index)} video tu {MEDIA_DIR}/")
if initial:
    print(f"  nap san: {initial['source']} ({len(initial['rows'])} entry)")
if status:
    print(f"  video khong xem duoc: {status}")
