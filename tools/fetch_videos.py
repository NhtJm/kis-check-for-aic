#!/usr/bin/env python3
"""Tai video 360p (video-only, khong can ffmpeg merge) cho cac video co trong submission CSV."""
import csv, json, os, subprocess, sys

CSV_PATH  = sys.argv[1] if len(sys.argv) > 1 else "/Users/nhatnguyen/Downloads/submission-kis-1.csv"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA_DIR = os.path.join(ROOT, "data", "media-info")
OUT_DIR   = os.path.join(ROOT, "data", "videos")
FMT       = os.environ.get("KIS_FMT", "134")   # 134 = 640x360 avc1, mot file

os.makedirs(OUT_DIR, exist_ok=True)
wanted = []
with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
    for row in csv.reader(f):
        if len(row) >= 2 and row[0].strip() and row[0].strip() not in wanted:
            try:
                int(float(row[1]))
            except ValueError:
                continue
            wanted.append(row[0].strip())

ok, fail = [], []
for i, vid in enumerate(wanted, 1):
    dest = os.path.join(OUT_DIR, vid + ".mp4")
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        print(f"[{i}/{len(wanted)}] {vid}: da co, bo qua"); ok.append(vid); continue
    meta_path = os.path.join(MEDIA_DIR, vid + ".json")
    if not os.path.exists(meta_path):
        print(f"[{i}/{len(wanted)}] {vid}: THIEU media-info"); fail.append((vid, "thieu media-info")); continue
    url = json.load(open(meta_path, encoding="utf-8"))["watch_url"]
    print(f"[{i}/{len(wanted)}] {vid}: tai ...", flush=True)
    r = subprocess.run([sys.executable, "-m", "yt_dlp", "-f", FMT, "--no-part", "-q",
                        "-o", os.path.join(OUT_DIR, vid + ".%(ext)s"), url],
                       capture_output=True, text=True)
    if r.returncode == 0 and os.path.exists(dest):
        print(f"    OK  {os.path.getsize(dest)/1e6:.0f} MB"); ok.append(vid)
    else:
        why = (r.stderr or "").strip().splitlines()
        why = why[-1][:150] if why else "loi khong ro"
        print(f"    THAT BAI: {why}"); fail.append((vid, why))

print(f"\nXong: {len(ok)} tai duoc, {len(fail)} that bai")
for v, why in fail:
    print(f"  {v}: {why}")

import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
