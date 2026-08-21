#!/usr/bin/env python3
"""Bo sung frame cho cac video ma server chua co.

Vi sao can buoc nay: YouTube chan tai tu IP datacenter, nen server tren cloud
KHONG tu lay video ve duoc. May ban thi tai binh thuong. Script nay chay o may:

    tai video  ->  trich frame  ->  day frame len bucket

Xem video khong can buoc nay (player phat thang tu YouTube trong trinh duyet);
chi CHAM DIEM moi can, vi cham diem can pixel that.

    python3 sync_frames.py submission.csv          # tu mot file CSV o may
    python3 sync_frames.py --from-server           # lay moi submission tren server
    python3 sync_frames.py --from-server --dry-run # chi xem thieu gi
"""
import argparse, csv, json, os, subprocess, sys, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.abspath(__file__))
BUCKET = os.environ.get("KIS_BUCKET", "kis-check-aic-videos")
URL = os.environ.get("KIS_URL", "https://kis-check-for-aic-850237628890.asia-southeast1.run.app")


def sh(cmd, **kw):
    return subprocess.run(cmd, shell=isinstance(cmd, str), text=True,
                          capture_output=True, **kw)


def videos_from_csv(path):
    out = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.reader(f):
            if len(r) >= 2 and r[0].strip():
                try:
                    int(float(r[1])); out.append(r[0].strip())
                except ValueError:
                    pass
    return out


def videos_from_server(log=print):
    pw = os.environ.get("KIS_PASSWORD")
    if not pw:
        sys.exit("Can KIS_PASSWORD de doc danh sach submission tren server.\n"
                 "  export KIS_PASSWORD='...'")
    def call(path, body=None, tok=None):
        h = {"Content-Type": "application/json"}
        if tok: h.update({"X-KIS-Auth": tok, "X-KIS-User": "nhat"})
        req = urllib.request.Request(URL + path,
                                     data=json.dumps(body).encode() if body else None,
                                     headers=h, method="POST" if body else "GET")
        return json.loads(urllib.request.urlopen(req, timeout=120).read())
    try:
        tok = call("/api/login", {"name": "nhat", "password": pw})["token"]
        items = call("/api/submissions", tok=tok)["items"]
    except urllib.error.HTTPError as e:
        sys.exit(f"khong doc duoc server: HTTP {e.code} {e.read()[:150].decode()}")
    log(f"  server co {len(items)} submission")
    vids = []
    for m in items:
        vids += m.get("videos") or []
    return vids


def have_on_bucket():
    r = sh(f"gcloud storage ls gs://{BUCKET}/frames/ 2>/dev/null")
    names = set()
    for line in r.stdout.splitlines():
        b = os.path.basename(line.strip())
        if b.endswith(".jpg") and "_" in b:
            names.add(b.rsplit("_", 1)[0])
    return names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="?")
    ap.add_argument("--from-server", action="store_true")
    ap.add_argument("--window", type=int, default=90)
    ap.add_argument("--step", type=int, default=30)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if not a.csv and not a.from_server:
        ap.error("cho mot file CSV, hoac dung --from-server")

    print("1) xem can nhung video nao")
    want = sorted(set(videos_from_csv(a.csv) if a.csv else videos_from_server()))
    print(f"   can {len(want)} video")

    print("2) xem bucket da co gi")
    have = have_on_bucket()
    missing = [v for v in want if v not in have]
    print(f"   bucket da co {len(have)} video · con thieu {len(missing)}")
    if not missing:
        print("\nKhong co gi de lam -- server da du frame cho toan bo danh sach.")
        return
    print("   thieu:", ", ".join(missing[:12]) + (" ..." if len(missing) > 12 else ""))
    if a.dry_run:
        print("\n(--dry-run: dung o day)")
        return

    print("\n3) tai video con thieu (chay o may, khong bi YouTube chan)")
    tmp = os.path.join(ROOT, ".sync-list.csv")
    with open(tmp, "w") as f:
        for v in missing:
            f.write(f"{v},0\n")
    r = subprocess.run([sys.executable, "fetch_videos.py", tmp], cwd=ROOT)
    if r.returncode != 0:
        print("   tai video that bai"); sys.exit(1)

    print("\n4) trich frame")
    src = a.csv or tmp
    r = subprocess.run([sys.executable, "extract_frames.py", "--csv", src,
                        "--window", str(a.window), "--step", str(a.step)], cwd=ROOT)
    if r.returncode != 0:
        print("   trich frame that bai"); sys.exit(1)

    print("\n5) day len bucket")
    r = subprocess.run(f"gcloud storage rsync frames gs://{BUCKET}/frames --recursive",
                       shell=True, cwd=ROOT)
    os.remove(tmp)
    if r.returncode != 0:
        print("   day len that bai"); sys.exit(1)

    after = have_on_bucket()
    print(f"\nXong. Bucket gio co {len(after)} video (them {len(after) - len(have)}).")
    print("Tai lai trang kiem tra la thay so 'cham diem duoc N video' tang.")


if __name__ == "__main__":
    main()
