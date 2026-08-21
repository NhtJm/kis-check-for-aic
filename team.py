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


# ---------- thanh vien va vai tro ----------
import unicodedata

DEFAULT_USERS = {
    "nhat":     {"role": "admin"},
    "thanh":    {"role": "member"},
    "nhan":     {"role": "member"},
    "quynhanh": {"role": "member"},
    "tung":     {"role": "member"},
}


def norm_name(s):
    """Ten chuan: chu thuong, khong dau, khong khoang trang.

    'Quỳnh Anh' -> 'quynhanh'. Dung de so khop luc dang nhap.
    """
    s = unicodedata.normalize("NFD", (s or "").strip())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace("đ", "d").replace("Đ", "d")
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def load_users(store):
    d = store.read("users.json")
    if d:
        return json.loads(d)
    store.write("users.json", json.dumps(DEFAULT_USERS, ensure_ascii=False))
    return dict(DEFAULT_USERS)


def save_users(store, users):
    store.write("users.json", json.dumps(users, ensure_ascii=False))


def set_role(store, name, role):
    users = load_users(store)
    n = norm_name(name)
    if n not in users:
        raise ValueError(f"khong co thanh vien '{n}'")
    if role not in ("admin", "member"):
        raise ValueError("role phai la admin hoac member")
    users[n]["role"] = role
    save_users(store, users)
    return users


def add_user(store, name, role="member"):
    users = load_users(store)
    n = norm_name(name)
    if not n:
        raise ValueError("ten khong hop le")
    users.setdefault(n, {})["role"] = role if role in ("admin", "member") else "member"
    save_users(store, users)
    return users


def remove_user(store, name):
    users = load_users(store)
    n = norm_name(name)
    if n in users:
        if users[n].get("role") == "admin" and \
           sum(1 for u in users.values() if u.get("role") == "admin") <= 1:
            raise ValueError("khong the xoa admin cuoi cung")
        del users[n]
        save_users(store, users)
    return users


def is_admin(store, name):
    return load_users(store).get(norm_name(name), {}).get("role") == "admin"


# ---------- bo cau hoi ----------
def save_queries(store, qs, round_name="p1"):
    store.write(f"queries/{slug(round_name)}.json", json.dumps(qs, ensure_ascii=False))
    return qs


def load_queries(store, round_name="p1"):
    d = store.read(f"queries/{slug(round_name)}.json")
    return json.loads(d) if d else []


def list_rounds(store):
    return sorted(f[:-5] for f in store.list("queries") if f.endswith(".json"))


def assign_queries(qids, people):
    """Chia deu cau hoi cho thanh vien, vong tron theo thu tu."""
    people = [p for p in dict.fromkeys(norm_name(p) for p in people if norm_name(p))]
    if not people:
        return {}
    out = {p: [] for p in people}
    for i, q in enumerate(qids):
        out[people[i % len(people)]].append(q)
    return out


def save_query_assignment(store, plan, round_name="p1"):
    store.write(f"qassign/{slug(round_name)}.json", json.dumps(plan, ensure_ascii=False))
    return plan


def load_query_assignment(store, round_name="p1"):
    d = store.read(f"qassign/{slug(round_name)}.json")
    return json.loads(d) if d else {}


def link_submission(store, query_id, sub_name, round_name="p1"):
    """Gan mot CSV submission vao mot cau hoi."""
    m = load_meta(store, sub_name)
    if not m:
        raise ValueError(f"khong co submission '{sub_name}'")
    m["query_id"] = query_id
    m["round"] = round_name
    store.write(f"meta/{slug(sub_name)}.json", json.dumps(m, ensure_ascii=False))
    return m


def submissions_by_query(store):
    out = {}
    for m in list_submissions(store):
        if m.get("query_id"):
            out.setdefault(m["query_id"], []).append(m["name"])
    return out


# ---------- vong thi ----------
# Vong hien tai la mot gia tri TOAN CUC: admin doi thi moi nguoi doi theo.
ROUNDS = [
    {"id": "thu-nghiem", "label": "Vòng thử nghiệm"},
    {"id": "vong-1",     "label": "Vòng 1"},
    {"id": "vong-2",     "label": "Vòng 2"},
    {"id": "vong-3",     "label": "Vòng 3"},
]
ROUND_IDS = [r["id"] for r in ROUNDS]


def load_settings(store):
    d = store.read("settings.json")
    return json.loads(d) if d else {"round": ROUND_IDS[0]}


def save_settings(store, st):
    store.write("settings.json", json.dumps(st, ensure_ascii=False))
    return st


def current_round(store):
    r = load_settings(store).get("round")
    return r if r in ROUND_IDS else ROUND_IDS[0]


def set_round(store, r):
    if r not in ROUND_IDS:
        raise ValueError(f"vong '{r}' khong hop le")
    st = load_settings(store)
    st["round"] = r
    save_settings(store, st)
    return r


def round_status(store):
    """Tinh trang tung vong: da nap bao nhieu cau, da chia chua, co bao nhieu CSV."""
    subs = {}
    for m in list_submissions(store):
        subs.setdefault(m.get("round") or ROUND_IDS[0], []).append(m["name"])
    out = []
    for r in ROUNDS:
        qs = load_queries(store, r["id"])
        plan = load_query_assignment(store, r["id"])
        out.append({**r, "queries": len(qs),
                    "assigned": sum(len(v) for v in plan.values()),
                    "subs": len(subs.get(r["id"], []))})
    return out


# ---------- nhan ZIP nhieu CSV ----------
# Ten file submission cua AIC thuong trung ma cau hoi: query-p1-7-kis.csv
QID_RE = re.compile(r"(query[-_][A-Za-z0-9]+[-_]\d+[-_](?:kis|qa|trake))", re.I)
NUMKIND_RE = re.compile(r"(\d+)[-_]?(kis|qa|trake)", re.I)


def match_query(filename, known_ids):
    """Doan xem mot file CSV thuoc cau hoi nao, dua vao TEN FILE.

    Tra ve (query_id, cach_khop). query_id co the la cau chua duoc nap -- van luu,
    de khi nap bo cau hoi sau thi tu noi vao (khong phu thuoc thu tu ai lam truoc).
    """
    base = os.path.basename(filename)
    lower = {k.lower(): k for k in known_ids}

    m = QID_RE.search(base)
    if m:
        cand = m.group(1).replace("_", "-").lower()
        return lower.get(cand, cand), ("ten-file" if cand in lower else "ten-file-chua-co-cau")

    # Khong co ma day du -> thu ghep theo so + loai, vd "7_kis.csv" hoac "kis-7.csv"
    m = NUMKIND_RE.search(base)
    if m:
        num, kind = m.group(1), m.group(2).lower()
        for k in known_ids:
            km = re.search(r"[-_](\d+)[-_](kis|qa|trake)$", k, re.I)
            if km and km.group(1) == num and km.group(2).lower() == kind:
                return k, "so+loai"
    return None, "khong-doan-duoc"


def ingest_zip(store, data, round_name=None, people=None, log=lambda m: None):
    """Giai nen ZIP, luu tung CSV thanh mot submission va gan vao cau hoi tuong ung."""
    import io as _io, zipfile
    round_name = round_name or ROUND_IDS[0]
    known = [q["id"] for q in load_queries(store, round_name)]

    try:
        zf = zipfile.ZipFile(_io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ValueError("file khong phai ZIP hop le")

    matched, unmatched, failed = [], [], []
    for info in zf.infolist():
        name = info.filename
        if info.is_dir() or not name.lower().endswith(".csv"):
            continue
        if "__MACOSX" in name or os.path.basename(name).startswith("."):
            continue          # rac macOS tao ra khi nen
        raw = zf.read(info)
        qid, how = match_query(name, known)
        sub = slug(os.path.splitext(os.path.basename(name))[0], "submission")
        try:
            meta = save_submission(store, sub, raw, people or None)
        except ValueError as e:
            failed.append({"file": name, "error": str(e)}); continue
        if qid:
            link_submission(store, qid, meta["name"], round_name)
            rec = {"file": name, "sub": meta["name"], "query_id": qid,
                   "rows": meta["rows"], "how": how,
                   "known": qid in known}
            matched.append(rec)
            log(f"  {os.path.basename(name)} -> {qid} ({meta['rows']} dong, {how})")
        else:
            unmatched.append({"file": name, "sub": meta["name"], "rows": meta["rows"]})
            log(f"  {os.path.basename(name)} -> KHONG doan duoc cau hoi")

    have = {r["query_id"] for r in matched}
    missing = [q for q in known if q not in have]
    return {"matched": matched, "unmatched": unmatched, "failed": failed,
            "missing_queries": missing, "round": round_name,
            "queries_loaded": len(known)}
