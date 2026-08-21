#!/usr/bin/env python3
"""Lop luu tru va chia viec cho nhieu nguoi cung kiem tra mot submission.

Bo cuc du lieu (tren GCS bucket, hoac mot thu muc o may khi chay local):

    submissions/{ten}.csv        CSV goc
    meta/{ten}.json              so dong, video, thoi diem nop, diem AI (neu co)
    assign/{ten}.json            phan cong: {nguoi: [ma_video, ...]}
    marks/{ten}/{nguoi}.json     danh dau cua rieng tung nguoi

Moi nguoi chi ghi vao dung file cua minh, nen KHONG bao gio co hai tien trinh ghi
cung mot file -- khong can transaction, khong can database.
"""
import csv, io, json, os, re, time, collections

# Giu chu Unicode (ten tieng Viet co dau) -- chi chan ky tu nguy hiem cho duong dan.
SAFE = re.compile(r"[^\w.-]+", re.UNICODE)


def slug(s, default="x"):
    s = SAFE.sub("-", (s or "").strip()).strip("-.")
    s = s.replace("..", ".")            # chan di nguoc thu muc
    return s[:64] or default


# ---------- luu tru ----------
class LocalStore:
    """Dung khi chay o may: mot thu muc thuong."""
    def __init__(self, root):
        self.root = root

    def _p(self, path):
        p = os.path.join(self.root, path)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        return p

    def read(self, path):
        p = os.path.join(self.root, path)
        return open(p, "rb").read() if os.path.exists(p) else None

    def write(self, path, data):
        open(self._p(path), "wb").write(data if isinstance(data, bytes) else data.encode())

    def list(self, prefix):
        d = os.path.join(self.root, prefix)
        return sorted(os.listdir(d)) if os.path.isdir(d) else []

    def delete(self, path):
        p = os.path.join(self.root, path)
        if os.path.exists(p):
            os.remove(p)


class GcsStore:
    """Dung khi deploy: ghi thang qua API cua GCS, khong qua mount."""
    def __init__(self, bucket):
        from google.cloud import storage
        self.bucket = storage.Client().bucket(bucket)

    def read(self, path):
        b = self.bucket.blob(path)
        return b.download_as_bytes() if b.exists() else None

    def write(self, path, data):
        self.bucket.blob(path).upload_from_string(
            data if isinstance(data, bytes) else data.encode(),
            content_type="application/json" if path.endswith(".json") else "text/csv")

    def list(self, prefix):
        pre = prefix if prefix.endswith("/") else prefix + "/"
        return sorted({b.name[len(pre):].split("/")[0]
                       for b in self.bucket.list_blobs(prefix=pre) if b.name != pre})

    def delete(self, path):
        b = self.bucket.blob(path)
        if b.exists():
            b.delete()


def make_store(bucket=None, local_root=None):
    if bucket:
        return GcsStore(bucket)
    return LocalStore(local_root or os.path.join(os.path.dirname(os.path.abspath(__file__)), "teamdata"))


# ---------- doc CSV ----------
def parse_csv(data):
    rows = []
    text = data.decode("utf-8-sig", errors="replace") if isinstance(data, bytes) else data
    for r in csv.reader(io.StringIO(text)):
        if len(r) >= 2 and r[0].strip():
            try:
                rows.append({"video": r[0].strip(), "frame": int(float(r[1]))})
            except ValueError:
                continue                      # dong header
    return rows


# ---------- chia viec ----------
def assign(rows, people):
    """Chia THEO VIDEO, can bang so dong.

    Doi video la thao tac dat nhat khi kiem tra (phai cho player nap lai), nen gom
    tron mot video cho mot nguoi giam han so lan nap. Do tren du lieu that: 100 dong
    / 11 video chia cho 5 nguoi -> moi nguoi mo 2-3 video thay vi 11.
    """
    people = [p for p in dict.fromkeys(slug(p) for p in people if p and p.strip())]
    if not people:
        return {}
    freq = collections.Counter(r["video"] for r in rows)
    load = {p: 0 for p in people}
    out = {p: [] for p in people}
    for vid, n in freq.most_common():          # video nang xep truoc
        p = min(people, key=lambda x: (load[x], x))
        out[p].append(vid)
        load[p] += n
    return out


def assignment_stats(rows, plan):
    freq = collections.Counter(r["video"] for r in rows)
    return {p: {"videos": len(vids), "rows": sum(freq[v] for v in vids)}
            for p, vids in plan.items()}


# ---------- submission ----------
def save_submission(store, name, csv_bytes, people=None):
    name = slug(name, "submission")
    rows = parse_csv(csv_bytes)
    if not rows:
        raise ValueError("khong doc duoc dong nao hop le trong CSV")
    store.write(f"submissions/{name}.csv", csv_bytes)
    meta = {"name": name, "rows": len(rows),
            "videos": sorted({r["video"] for r in rows}),
            "uploaded": time.time(), "scored": False}
    store.write(f"meta/{name}.json", json.dumps(meta, ensure_ascii=False))
    if people:
        set_assignment(store, name, rows, people)
    return meta


def load_rows(store, name):
    data = store.read(f"submissions/{slug(name)}.csv")
    return parse_csv(data) if data else None


def load_meta(store, name):
    d = store.read(f"meta/{slug(name)}.json")
    return json.loads(d) if d else None


def list_submissions(store):
    out = []
    for f in store.list("meta"):
        if f.endswith(".json"):
            d = store.read(f"meta/{f}")
            if d:
                out.append(json.loads(d))
    return sorted(out, key=lambda m: -m.get("uploaded", 0))


def set_assignment(store, name, rows, people):
    plan = assign(rows, people)
    store.write(f"assign/{slug(name)}.json", json.dumps(plan, ensure_ascii=False))
    return plan


def load_assignment(store, name):
    d = store.read(f"assign/{slug(name)}.json")
    return json.loads(d) if d else {}


# ---------- danh dau ----------
def save_marks(store, name, who, marks):
    """marks: {"<video>|<frame>": "ok"|"no"|"maybe"}. Moi nguoi mot file rieng."""
    store.write(f"marks/{slug(name)}/{slug(who, 'ai-do')}.json",
                json.dumps({"who": who, "at": time.time(), "marks": marks}, ensure_ascii=False))


def load_all_marks(store, name):
    name = slug(name)
    out = {}
    for f in store.list(f"marks/{name}"):
        if f.endswith(".json"):
            d = store.read(f"marks/{name}/{f}")
            if d:
                j = json.loads(d)
                out[j.get("who") or f[:-5]] = j
    return out


def key_of(video, frame):
    return f"{video}|{frame}"


def progress(store, name):
    """Gop danh dau cua moi nguoi, tra ve tien do tung nguoi va tong."""
    rows = load_rows(store, name) or []
    plan = load_assignment(store, name)
    allm = load_all_marks(store, name)
    freq = collections.Counter(r["video"] for r in rows)

    merged, conflicts = {}, []
    for who, j in allm.items():
        for k, v in (j.get("marks") or {}).items():
            if k in merged and merged[k][1] != v:
                conflicts.append({"key": k, "a": merged[k], "b": (who, v)})
            merged[k] = (who, v)

    per = {}
    for who in sorted(set(plan) | set(allm)):
        vids = plan.get(who, [])
        total = sum(freq[v] for v in vids) if vids else 0
        mine = (allm.get(who, {}).get("marks") or {})
        done = len(mine)
        per[who] = {"videos": len(vids), "total": total, "done": done,
                    "ok": sum(1 for v in mine.values() if v == "ok"),
                    "no": sum(1 for v in mine.values() if v == "no"),
                    "maybe": sum(1 for v in mine.values() if v == "maybe"),
                    "at": allm.get(who, {}).get("at")}
    return {"rows": len(rows), "done": len(merged), "per_person": per,
            "conflicts": conflicts[:20], "merged": {k: v[1] for k, v in merged.items()}}


def export_csv(store, name):
    """CSV cuoi cung: moi dong kem danh dau va nguoi danh dau."""
    rows = load_rows(store, name) or []
    plan = load_assignment(store, name)
    owner = {v: p for p, vids in plan.items() for v in vids}
    allm = load_all_marks(store, name)
    merged = {}
    for who, j in allm.items():
        for k, v in (j.get("marks") or {}).items():
            merged[k] = (who, v)

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["rank", "video", "frame", "danh_gia", "nguoi_cham", "phu_trach"])
    label = {"ok": "dung", "no": "sai", "maybe": "chua-chac"}
    for i, r in enumerate(rows, 1):
        who, v = merged.get(key_of(r["video"], r["frame"]), (None, None))
        w.writerow([i, r["video"], r["frame"], label.get(v, ""), who or "", owner.get(r["video"], "")])
    return buf.getvalue()
