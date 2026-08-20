#!/usr/bin/env python3
"""Kho video co gioi han dung luong, tai theo yeu cau.

Luon tai NGUYEN video chu khong cat doan: cat doan lam frame danh so lai tu 0 va
cho cat bam theo keyframe, nen chi so frame trong submission se lech -- dung cai
ma toan bo cong cu nay dua vao.
"""
import json, os, subprocess, sys, time

FMT = os.environ.get("KIS_VIDEO_FMT", "134")            # 640x360 avc1, mot file
CAP_MB = int(os.environ.get("KIS_VIDEO_CACHE_MB", "1500"))
_index = None


def index(root="."):
    """Map video_id -> thong tin, uu tien media-index.json roi den media-info/."""
    global _index
    if _index is not None:
        return _index
    p = os.path.join(root, "media-index.json")
    if os.path.exists(p):
        _index = json.load(open(p, encoding="utf-8"))
        return _index
    _index = {}
    d = os.path.join(root, "media-info")
    if os.path.isdir(d):
        import re
        for n in os.listdir(d):
            if n.endswith(".json"):
                j = json.load(open(os.path.join(d, n), encoding="utf-8"))
                m = re.search(r"v=([\w-]+)", j["watch_url"])
                _index[n[:-5]] = {"yt": m.group(1) if m else None, "url": j["watch_url"]}
    return _index


def _evict(video_dir, keep):
    """Xoa video cu nhat (theo lan dung gan nhat) cho den khi duoi han muc."""
    files = [(os.path.join(video_dir, f), os.path.getsize(os.path.join(video_dir, f)),
              os.path.getatime(os.path.join(video_dir, f)))
             for f in os.listdir(video_dir) if f.endswith(".mp4")]
    total = sum(s for _, s, _ in files)
    for path, size, _ in sorted(files, key=lambda x: x[2]):
        if total <= CAP_MB * 1e6:
            break
        if os.path.basename(path)[:-4] in keep:
            continue
        os.remove(path)
        total -= size
        sys.stderr.write(f"  cache: xoa {os.path.basename(path)} ({size/1e6:.0f} MB)\n")


def ensure(vid, video_dir, root=".", keep=(), log=lambda m: None):
    """Tra ve duong dan video, tai ve neu chua co. None neu that bai."""
    os.makedirs(video_dir, exist_ok=True)
    dest = os.path.join(video_dir, vid + ".mp4")
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        os.utime(dest, None)                    # danh dau vua dung
        return dest

    info = index(root).get(vid)
    if not info:
        log(f"  {vid}: khong co trong media-index"); return None

    _evict(video_dir, set(keep) | {vid})
    log(f"  {vid}: chua co, dang tai ...")
    t0 = time.time()
    r = subprocess.run([sys.executable, "-m", "yt_dlp", "-f", FMT, "--no-part", "-q",
                        "-o", os.path.join(video_dir, vid + ".%(ext)s"), info["url"]],
                       capture_output=True, text=True)
    if r.returncode == 0 and os.path.exists(dest):
        log(f"  {vid}: tai xong {os.path.getsize(dest)/1e6:.0f} MB trong {time.time()-t0:.0f}s")
        return dest
    why = (r.stderr or "").strip().splitlines()
    log(f"  {vid}: tai that bai -- {why[-1][:120] if why else 'khong ro'}")
    return None
