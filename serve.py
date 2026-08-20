#!/usr/bin/env python3
"""Server local cho KIS Submission Checker.

Phuc vu file tinh, va mo them mot API de UI gui CSV + cau query len cham diem.
Model chi chay o may ban -- ban tren GitHub Pages la trang tinh nen o query se
tu an di.

    python3 serve.py [--port 8777]
Roi mo http://localhost:8777/
"""
import argparse, json, os, sys, threading, traceback
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

import score_query
import api_backend

api_backend.load_dotenv()      # nap .env ngay khi khoi dong

ROOT = os.path.dirname(os.path.abspath(__file__))
_lock = threading.Lock()          # model khong an toan da luong -> cham diem tuan tu

# Cau hinh khi deploy. Tren host nho: KIS_BACKENDS=api va KIS_FETCH=1
BACKENDS = [b.strip() for b in os.environ.get("KIS_BACKENDS", "siglip,hybrid,api").split(",") if b.strip()]
FETCH    = os.environ.get("KIS_FETCH", "0") not in ("0", "", "false", "False")
VIDEODIR = os.environ.get("KIS_VIDEO_DIR", os.path.join(ROOT, "videos"))
# Tren host CPU, mot request qua lon se chay lau hon gateway timeout. Chan truoc
# va noi ro cach thu nho, thay vi de nguoi dung ngoi cho roi an loi 502.
MAXFRAMES = int(os.environ.get("KIS_MAX_FRAMES", "0"))     # 0 = khong gioi han


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=ROOT, **kw)

    def log_message(self, fmt, *a):
        if "/api/" in (self.path or ""):
            sys.stderr.write("  %s\n" % (fmt % a))

    def _json(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.split("?")[0] == "/api/status":
            vids = sorted(f[:-4] for f in os.listdir(VIDEODIR)
                          if f.endswith(".mp4")) if os.path.isdir(VIDEODIR) else []
            api_ok = all(os.environ.get(k) for k in ("KIS_API_BASE", "KIS_API_KEY", "KIS_API_MODEL"))
            allowed = [b for b in BACKENDS if b == "siglip" or api_ok]
            return self._json(200, {"ok": True, "videos": vids, "model": score_query.MODEL_ID,
                                    "api": api_ok, "api_model": os.environ.get("KIS_API_MODEL", ""),
                                    "backends": allowed, "fetch": FETCH,
                                    "max_frames": MAXFRAMES})
        return super().do_GET()

    def do_POST(self):
        if self.path.split("?")[0] != "/api/score":
            return self._json(404, {"ok": False, "error": "khong co endpoint nay"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n) or b"{}")
            query = (req.get("query") or "").strip()
            rows  = [{"video": r[0], "frame": int(r[1])} for r in req.get("rows", [])]
            if not query:
                return self._json(400, {"ok": False, "error": "thieu cau query"})
            if not rows:
                return self._json(400, {"ok": False, "error": "khong co dong nao de cham"})

            window  = int(req.get("window", 90))
            step    = max(1, int(req.get("step", 30)))
            backend = req.get("backend", BACKENDS[0] if BACKENDS else "siglip")
            if backend not in BACKENDS:
                return self._json(400, {"ok": False,
                                        "error": f"backend '{backend}' khong duoc bat tren server nay"})
            topk    = int(req.get("topk", 20))
            per = (window * 2 // step + 1) if window > 0 else 1
            nframes = len(rows) * per
            if MAXFRAMES and nframes > MAXFRAMES:
                return self._json(400, {"ok": False, "error":
                    f"Yeu cau {nframes} frame, vuot gioi han {MAXFRAMES} cua server nay. "
                    f"Thu nho cua so (vd ±{step}) hoac tang buoc de giam so frame."})
            sys.stderr.write(f"\n[score] {len(rows)} dong · {nframes} frame · window ±{window} "
                             f"· step {step} · backend={backend} · query={query!r}\n")

            with _lock:
                res, offsets = score_query.run(rows, query, window, step, VIDEODIR,
                                               backend=backend, topk=topk,
                                               log=lambda m: sys.stderr.write(m + "\n"),
                                               fetch_missing=FETCH, root=ROOT)
            return self._json(200, {
                "ok": True, "query": query, "offsets": offsets,
                "rows": [[r["video"], r["frame"], r["score"], r["best_off"],
                          r["best_score"], r["mean_score"], r["cos"], r["note"],
                          r.get("rank_final"), r.get("rr")] for r in res]})
        except Exception as e:
            traceback.print_exc()
            return self._json(500, {"ok": False, "error": f"{type(e).__name__}: {e}"})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8777)))
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    a = ap.parse_args()
    print(f"KIS Checker: http://{a.host}:{a.port}/   (Ctrl+C de dung)")
    print(f"Backends bat: {', '.join(BACKENDS)} · tai video theo yeu cau: {'co' if FETCH else 'khong'}")
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()
