#!/usr/bin/env python3
"""Server local / Cloud Run cho KIS Submission Checker.

Phuc vu file tinh, cham diem bang model, va dieu phoi nhieu nguoi cung kiem tra
mot submission (nop CSV -> chia viec theo video -> gop ket qua).

    python3 serve.py [--port 8777]

Bien moi truong dang chu y:
    KIS_PASSWORD     mat khau chung; bo trong = khong chan ai
    KIS_BUCKET       bucket GCS de luu submission/marks; bo trong = luu o teamdata/
    KIS_BACKENDS     backend cham diem duoc phep (siglip,hybrid,api)
    KIS_MAX_FRAMES   chan request qua lon (0 = khong gioi han)
"""
import argparse, hashlib, hmac, json, os, sys, threading, traceback, urllib.parse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

import score_query
import api_backend
import team

api_backend.load_dotenv()

ROOT = os.path.dirname(os.path.abspath(__file__))
_lock = threading.Lock()          # model khong an toan da luong -> cham diem tuan tu

BACKENDS = [b.strip() for b in os.environ.get("KIS_BACKENDS", "siglip,hybrid,api").split(",") if b.strip()]
FETCH    = os.environ.get("KIS_FETCH", "0") not in ("0", "", "false", "False")
VIDEODIR = os.environ.get("KIS_VIDEO_DIR", os.path.join(ROOT, "videos"))
FRAMEDIR = os.environ.get("KIS_FRAME_DIR", os.path.join(ROOT, "frames"))
MAXFRAMES = int(os.environ.get("KIS_MAX_FRAMES", "0"))
PASSWORD = os.environ.get("KIS_PASSWORD", "")
BUCKET   = os.environ.get("KIS_BUCKET", "")
MAX_UPLOAD = 8 * 1024 * 1024      # CSV submission khong bao gio lon the nay

_store = None
def store():
    global _store
    if _store is None:
        _store = team.make_store(BUCKET or None)
    return _store


def token_for(pw):
    """Token gui kem moi request. Khong phai session that -- du cho team noi bo."""
    return hashlib.sha256(("kis:" + pw).encode()).hexdigest()

EXPECTED = token_for(PASSWORD) if PASSWORD else ""


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, fmt, *a):
        if "/api/" in (self.path or ""):
            sys.stderr.write("  %s\n" % (fmt % a))

    # ---------- tien ich ----------
    def _json(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def _text(self, code, body, ctype="text/csv; charset=utf-8", filename=None):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(b)

    def _authed(self):
        if not PASSWORD:
            return True
        got = self.headers.get("X-KIS-Auth", "")
        return bool(got) and hmac.compare_digest(got, EXPECTED)

    def _need_auth(self):
        self._json(401, {"ok": False, "error": "can mat khau", "auth": True})

    def _body(self, limit=MAX_UPLOAD):
        n = int(self.headers.get("Content-Length", 0))
        if n > limit:
            return None
        return self.rfile.read(n) if n else b""

    def _q(self):
        parts = urllib.parse.urlparse(self.path)
        return parts.path, {k: v[0] for k, v in urllib.parse.parse_qs(parts.query).items()}

    # ---------- GET ----------
    def do_GET(self):
        path, q = self._q()

        if path == "/api/status":
            # Cong khai, nhung chi noi du de UI biet co phai hoi mat khau khong.
            vids = sorted(f[:-4] for f in os.listdir(VIDEODIR)
                          if f.endswith(".mp4")) if os.path.isdir(VIDEODIR) else []
            if os.path.isdir(FRAMEDIR):
                vids = sorted(set(vids) | {f.rsplit("_", 1)[0] for f in os.listdir(FRAMEDIR)
                                           if f.endswith(".jpg")})
            api_ok = all(os.environ.get(k) for k in ("KIS_API_BASE", "KIS_API_KEY", "KIS_API_MODEL"))
            return self._json(200, {
                "ok": True, "auth_required": bool(PASSWORD), "authed": self._authed(),
                "videos": vids, "model": score_query.MODEL_ID,
                "api": api_ok, "api_model": os.environ.get("KIS_API_MODEL", ""),
                "backends": [b for b in BACKENDS if b == "siglip" or api_ok],
                "fetch": FETCH, "max_frames": MAXFRAMES,
                "translate": api_ok, "team": True})

        if path.startswith("/api/"):
            if not self._authed():
                return self._need_auth()

            if path == "/api/submissions":
                return self._json(200, {"ok": True, "items": team.list_submissions(store())})

            if path == "/api/submission":
                name = q.get("name", "")
                rows = team.load_rows(store(), name)
                if rows is None:
                    return self._json(404, {"ok": False, "error": "khong co submission nay"})
                plan = team.load_assignment(store(), name)
                who = q.get("who", "")
                mine = plan.get(team.slug(who), []) if who else []
                marks = {}
                if who:
                    allm = team.load_all_marks(store(), name)
                    marks = (allm.get(who) or {}).get("marks", {})
                return self._json(200, {"ok": True, "name": team.slug(name),
                                        "rows": [[r["video"], r["frame"]] for r in rows],
                                        "assign": plan, "my_videos": mine,
                                        "my_marks": marks,
                                        "meta": team.load_meta(store(), name)})

            if path == "/api/progress":
                return self._json(200, {"ok": True, **team.progress(store(), q.get("name", ""))})

            if path == "/api/export":
                name = team.slug(q.get("name", ""))
                if team.load_rows(store(), name) is None:
                    return self._json(404, {"ok": False, "error": "khong co submission nay"})
                return self._text(200, team.export_csv(store(), name),
                                  filename=f"{name}-team-check.csv")

            return self._json(404, {"ok": False, "error": "khong co endpoint nay"})

        return super().do_GET()

    # ---------- POST ----------
    def do_POST(self):
        path, q = self._q()

        if path == "/api/login":
            body = self._body(4096) or b"{}"
            try:
                pw = (json.loads(body).get("password") or "")
            except Exception:
                pw = ""
            if not PASSWORD:
                return self._json(200, {"ok": True, "token": "", "auth_required": False})
            if hmac.compare_digest(token_for(pw), EXPECTED):
                return self._json(200, {"ok": True, "token": EXPECTED})
            return self._json(401, {"ok": False, "error": "mat khau khong dung"})

        if not self._authed():
            return self._need_auth()

        try:
            if path == "/api/upload":
                return self._upload(q)
            if path == "/api/marks":
                return self._marks()
            if path == "/api/assign":
                return self._assign()
            if path == "/api/score":
                return self._score()
            return self._json(404, {"ok": False, "error": "khong co endpoint nay"})
        except Exception as e:
            traceback.print_exc()
            return self._json(500, {"ok": False, "error": f"{type(e).__name__}: {e}"})

    # ---------- xu ly ----------
    def _upload(self, q):
        data = self._body()
        if data is None:
            return self._json(413, {"ok": False, "error": "file qua lon"})
        name = q.get("name") or "submission"
        people = [p for p in (q.get("people") or "").split(",") if p.strip()]
        try:
            meta = team.save_submission(store(), name, data, people or None)
        except ValueError as e:
            return self._json(400, {"ok": False, "error": str(e)})
        sys.stderr.write(f"\n[upload] {meta['name']}: {meta['rows']} dong · "
                         f"{len(meta['videos'])} video · chia cho {len(people)} nguoi\n")
        rows = team.load_rows(store(), meta["name"])
        plan = team.load_assignment(store(), meta["name"])
        return self._json(200, {"ok": True, "meta": meta, "assign": plan,
                                "stats": team.assignment_stats(rows, plan) if plan else {}})

    def _assign(self):
        req = json.loads(self._body(65536) or b"{}")
        name = req.get("name", "")
        rows = team.load_rows(store(), name)
        if rows is None:
            return self._json(404, {"ok": False, "error": "khong co submission nay"})
        plan = team.set_assignment(store(), name, rows, req.get("people") or [])
        return self._json(200, {"ok": True, "assign": plan,
                                "stats": team.assignment_stats(rows, plan)})

    def _marks(self):
        req = json.loads(self._body() or b"{}")
        name, who = req.get("name", ""), req.get("who", "")
        if not name or not who:
            return self._json(400, {"ok": False, "error": "thieu ten submission hoac ten nguoi cham"})
        team.save_marks(store(), name, who, req.get("marks") or {})
        return self._json(200, {"ok": True})

    def _score(self):
        req = json.loads(self._body(8 * 1024 * 1024) or b"{}")
        query = (req.get("query") or "").strip()
        rows  = [{"video": r[0], "frame": int(r[1])} for r in req.get("rows", [])]
        if not query:
            return self._json(400, {"ok": False, "error": "thieu cau query"})
        if not rows:
            return self._json(400, {"ok": False, "error": "khong co dong nao de cham"})

        window  = int(req.get("window", 90))
        step    = max(1, int(req.get("step", 30)))
        backend = req.get("backend", BACKENDS[0] if BACKENDS else "siglip")
        topk    = int(req.get("topk", 20))
        if backend not in BACKENDS:
            return self._json(400, {"ok": False,
                                    "error": f"backend '{backend}' khong duoc bat tren server nay"})

        per = (window * 2 // step + 1) if window > 0 else 1
        nframes = len(rows) * per
        if MAXFRAMES and nframes > MAXFRAMES:
            return self._json(400, {"ok": False, "error":
                f"Yeu cau {nframes} frame, vuot gioi han {MAXFRAMES} cua server nay. "
                f"Thu nho cua so (vd ±{step}) hoac tang buoc de giam so frame."})

        query_en, translated = query, False
        if req.get("translate"):
            import query_expand
            query_en, translated = query_expand.translate(
                query, log=lambda m: sys.stderr.write(m + "\n"))

        sys.stderr.write(f"\n[score] {len(rows)} dong · {nframes} frame · window ±{window} "
                         f"· step {step} · backend={backend} · query={query_en!r}\n")
        with _lock:
            res, offsets = score_query.run(rows, query_en, window, step, VIDEODIR,
                                           backend=backend, topk=topk,
                                           log=lambda m: sys.stderr.write(m + "\n"),
                                           fetch_missing=FETCH, root=ROOT,
                                           frames_dir=FRAMEDIR)
        return self._json(200, {
            "ok": True, "query": query, "query_en": query_en,
            "translated": translated, "offsets": offsets,
            "rows": [[r["video"], r["frame"], r["score"], r["best_off"],
                      r["best_score"], r["mean_score"], r["cos"], r["note"],
                      r.get("rank_final"), r.get("rr")] for r in res]})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8777)))
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    a = ap.parse_args()
    print(f"KIS Checker: http://{a.host}:{a.port}/   (Ctrl+C de dung)")
    print(f"Backends: {', '.join(BACKENDS)} · tai video theo yeu cau: {'co' if FETCH else 'khong'}")
    print(f"Mat khau chung: {'CO' if PASSWORD else 'khong dat (ai cung vao duoc)'}")
    print(f"Kho du lieu team: {'gs://' + BUCKET if BUCKET else 'teamdata/ (o may)'}")
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()
