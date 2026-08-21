#!/usr/bin/env python3
"""Trich san cac frame ma mot submission can, ra JPEG.

Server cham diem chi can dung nhung frame do, khong can ca video. Voi
submission-kis-3: ~700 anh JPEG (~35MB) thay vi 2.2GB video -- va khong con
phu thuoc vao viec tai duoc tu YouTube.

    python3 extract_frames.py --csv sub.csv --window 90 --step 30 --out frames/

Trich o cua so rong nhat ban dinh dung; cua so hep hon khi cham la tap con.
"""
import argparse, csv, os, sys, collections

def read_submission(path):
    """Dung chung parser voi score_query -- truoc day moi file mot ban, sua cho nay
    quen cho kia va TRAKE bi mat moc E2/E3."""
    import score_query
    return [(r["video"], r["frame"]) for r in score_query.read_submission(path)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--window", type=int, default=90)
    ap.add_argument("--step", type=int, default=30)
    ap.add_argument("--videos", default="videos")
    ap.add_argument("--out", default="frames")
    ap.add_argument("--quality", type=int, default=85)
    a = ap.parse_args()

    import cv2
    offsets = list(range(-a.window, a.window + 1, a.step)) if a.window > 0 else [0]
    if 0 not in offsets: offsets.append(0); offsets.sort()

    rows = read_submission(a.csv)
    need = collections.defaultdict(set)
    for v, f in rows:
        need[v].update(f + o for o in offsets)

    os.makedirs(a.out, exist_ok=True)
    total = done = skipped = missing_vid = 0
    for vid in sorted(need):
        path = os.path.join(a.videos, vid + ".mp4")
        want = sorted(i for i in need[vid] if i >= 0)
        total += len(want)
        todo = [i for i in want if not os.path.exists(os.path.join(a.out, f"{vid}_{i}.jpg"))]
        skipped += len(want) - len(todo)
        if not todo:
            continue
        if not os.path.exists(path):
            print(f"  {vid}: THIEU video, bo qua {len(todo)} frame")
            missing_vid += 1
            continue

        cap = cv2.VideoCapture(path)
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        pos = -1
        got = 0
        for idx in todo:
            if idx >= n:
                continue
            if pos < 0 or idx < pos or idx - pos > 60:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx); pos = idx
            else:
                while pos < idx: cap.grab(); pos += 1
            ok, img = cap.read(); pos += 1
            if ok:
                cv2.imwrite(os.path.join(a.out, f"{vid}_{idx}.jpg"), img,
                            [cv2.IMWRITE_JPEG_QUALITY, a.quality])
                got += 1
        cap.release()
        done += got
        print(f"  {vid}: {got}/{len(todo)} frame")

    size = sum(os.path.getsize(os.path.join(a.out, f)) for f in os.listdir(a.out)) / 1e6
    print(f"\n{done} frame moi, {skipped} da co, {total} tong cong")
    if missing_vid:
        print(f"CANH BAO: {missing_vid} video khong co file -- chay fetch_videos.py truoc")
    print(f"{a.out}/: {len(os.listdir(a.out))} anh, {size:.0f} MB")


if __name__ == "__main__":
    main()
