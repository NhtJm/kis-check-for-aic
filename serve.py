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

ROOT = os.path.dirname(os.path.abspath(__file__))
_lock = threading.Lock()          # model khong an toan da luong -> cham diem tuan tu


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
            vids = sorted(f[:-4] for f in os.listdir(os.path.join(ROOT, "videos"))
                          if f.endswith(".mp4")) if os.path.isdir(os.path.join(ROOT, "videos")) else []
            api_ok = all(os.environ.get(k) for k in ("KIS_API_BASE", "KIS_API_KEY", "KIS_API_MODEL"))
            return self._json(200, {"ok": True, "videos": vids, "model": score_query.MODEL_ID,
                                    "api": api_ok, "api_model": os.environ.get("KIS_API_MODEL", "")})
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
            backend = req.get("backend", "siglip")
            topk    = int(req.get("topk", 20))
            sys.stderr.write(f"\n[score] {len(rows)} dong · window ±{window} · step {step} · query={query!r}\n")

            with _lock:
                res, offsets = score_query.run(rows, query, window, step,
                                               os.path.join(ROOT, "videos"),
                                               backend=backend, topk=topk,
                                               log=lambda m: sys.stderr.write(m + "\n"))
            return self._json(200, {
                "ok": True, "query": query, "offsets": offsets,
                "rows": [[r["video"], r["frame"], r["score"], r["best_off"],
                          r["best_score"], r["mean_score"], r["cos"], r["note"]] for r in res]})
        except Exception as e:
            traceback.print_exc()
            return self._json(500, {"ok": False, "error": f"{type(e).__name__}: {e}"})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8777)
    a = ap.parse_args()
    print(f"KIS Checker: http://localhost:{a.port}/   (Ctrl+C de dung)")
    print(f"Model: {score_query.MODEL_ID}")
    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()
