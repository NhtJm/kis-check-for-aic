#!/usr/bin/env python3
"""Cham diem do khop giua mot cau query va cac frame trong submission KIS.

Dung SigLIP da luyen da ngu (ho tro tieng Viet). SigLIP duoc huan luyen bang
sigmoid loss nen cho ra xac suat khop **tuyet doi** cho tung cap (anh, cau chu) --
khac CLIP von chi so sanh tuong doi duoc.

    python3 score_query.py --csv submission.csv --query "bon phi hanh gia ao den"

Voi moi dong trong CSV, script lay them vai frame truoc/sau (mac dinh +-90 frame
= +-3 giay, moi 30 frame) roi bao: diem tai dung frame do, diem cao nhat trong
cua so va lech bao nhieu frame.
"""
import argparse, csv, json, os, sys, math
import numpy as np

MODEL_ID  = "google/siglip-base-patch16-256-multilingual"
VIDEO_DIR = "videos"


# ---------- doc frame ----------
def read_frames(video_path, indices):
    """Doc cac frame theo chi so. Doc tuan tu khi gan nhau, seek khi xa -- nhanh hon seek moi lan."""
    import cv2
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {}, 0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    out, pos = {}, -1
    for idx in sorted(set(indices)):
        if idx < 0 or idx >= total:
            continue
        if pos < 0 or idx < pos or idx - pos > 60:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            pos = idx
        else:
            while pos < idx:                      # doc luot toi, re hon seek
                cap.grab(); pos += 1
        ok, img = cap.read()
        pos += 1
        if ok:
            out[idx] = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    cap.release()
    return out, total


# ---------- model ----------
_cache = {}

def get_model(model_id=MODEL_ID):
    if model_id in _cache:
        return _cache[model_id]
    import torch
    from transformers import AutoModel, AutoProcessor
    dev = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
    model = AutoModel.from_pretrained(model_id).to(dev).eval()
    proc  = AutoProcessor.from_pretrained(model_id)
    _cache[model_id] = (model, proc, dev)
    return _cache[model_id]


def score_images(images, query, model_id=MODEL_ID, batch=24):
    """Tra ve xac suat khop (0..1) cua tung anh voi cau query."""
    import torch
    model, proc, dev = get_model(model_id)
    with torch.no_grad():
        t = proc(text=[query], padding="max_length", truncation=True, return_tensors="pt").to(dev)
        tf = model.get_text_features(**t)
        tf = tf / tf.norm(dim=-1, keepdim=True)

        sims = []
        for i in range(0, len(images), batch):
            im = proc(images=images[i:i+batch], return_tensors="pt").to(dev)
            f = model.get_image_features(**im)
            f = f / f.norm(dim=-1, keepdim=True)
            sims.append((f @ tf.T).squeeze(-1).float().cpu())
        if not sims:
            return np.zeros(0), np.zeros(0)
        cos = torch.cat(sims)
        # SigLIP: sigmoid(scale * cos + bias) -> xac suat khop da hieu chuan
        logits = model.logit_scale.exp().float().cpu() * cos + model.logit_bias.float().cpu()
        return torch.sigmoid(logits).numpy(), cos.numpy()


# ---------- pipeline ----------
def read_submission(path):
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.reader(f):
            if len(r) < 2 or not r[0].strip():
                continue
            try:
                rows.append({"video": r[0].strip(), "frame": int(float(r[1]))})
            except ValueError:
                continue          # dong header
    return rows


def run(rows, query, window=90, step=30, video_dir=VIDEO_DIR, model_id=MODEL_ID,
        backend="siglip", topk=20, log=print, fetch_missing=False, root="."):
    """backend: 'siglip' (local, mien phi) | 'api' (VLM qua router) | 'hybrid' (loc bang
    SigLIP roi cho VLM cham lai topk dong dau -- re va chinh xac nhat)."""
    offsets = list(range(-window, window + 1, step)) if window > 0 else [0]
    if 0 not in offsets:
        offsets.append(0); offsets.sort()

    # gom cac frame can doc theo tung video (co gop trung)
    need = {}
    for i, r in enumerate(rows):
        need.setdefault(r["video"], set()).update(r["frame"] + o for o in offsets)

    frames, totals = {}, {}
    for vid in sorted(need):
        path = os.path.join(video_dir, vid + ".mp4")
        if not os.path.exists(path) and fetch_missing:
            import video_cache
            path = video_cache.ensure(vid, video_dir, root, keep=need.keys(), log=log) or path
        if not os.path.exists(path):
            log(f"  {vid}: THIEU file video, bo qua")
            frames[vid], totals[vid] = {}, 0
            continue
        got, total = read_frames(path, need[vid])
        frames[vid], totals[vid] = got, total
        log(f"  {vid}: doc {len(got)}/{len(need[vid])} frame")

    # cham diem mot lan cho toan bo frame
    flat = [(v, i, frames[v][i]) for v in frames for i in sorted(frames[v])]
    log(f"Cham diem {len(flat)} frame · backend={backend} · query={query!r}")

    if backend == "api":
        import api_backend
        probs, _ = api_backend.score_images([f[2] for f in flat], query, log=log)
        cosines = [None] * len(flat)
    else:
        probs, cosines = score_images([f[2] for f in flat], query, model_id)

    P = {(v, i): (None if p is None else float(p), None if c is None else float(c))
         for (v, i, _), p, c in zip(flat, probs, cosines)}

    out = []
    for r in rows:
        v, fr = r["video"], r["frame"]
        pts = [(o, P[(v, fr + o)][0], P[(v, fr + o)][1]) for o in offsets
               if (v, fr + o) in P and P[(v, fr + o)][0] is not None]
        if not pts:
            out.append({**r, "score": None, "cos": None, "best_off": None,
                        "best_score": None, "mean_score": None, "note": "khong doc duoc frame"})
            continue
        exact = next((p for o, p, c in pts if o == 0), None)
        ecos  = next((c for o, p, c in pts if o == 0), None)
        bo, bp, _ = max(pts, key=lambda x: x[1])
        out.append({**r,
                    "score": exact, "cos": ecos,
                    "best_off": bo, "best_score": bp,
                    "mean_score": sum(p for _, p, _ in pts) / len(pts),
                    "window": [{"off": o, "p": p} for o, p, c in pts],
                    "note": ""})

    if backend == "hybrid":
        out = _refine_with_api(out, offsets, frames, query, topk, log)
    return out, offsets


def _refine_with_api(out, offsets, frames, query, topk, log):
    """Lay topk dong diem cao nhat theo SigLIP roi cho VLM cham lai cho chac."""
    import api_backend
    ranked = sorted([r for r in out if r["score"] is not None],
                    key=lambda r: (-r["score"], -(r["cos"] or 0)))[:topk]
    if not ranked:
        return out
    jobs = [(r, o, r["frame"] + o) for r in ranked for o in offsets
            if (r["frame"] + o) in frames.get(r["video"], {})]
    log(f"Hybrid: SigLIP loc con {len(ranked)} dong -> VLM cham lai {len(jobs)} frame")
    probs, _ = api_backend.score_images([frames[r["video"]][i] for r, o, i in jobs], query, log=log)

    got = {}
    for (r, o, _), p in zip(jobs, probs):
        if p is not None:
            got.setdefault(id(r), []).append((o, p))
    for r in ranked:
        pts = got.get(id(r))
        if not pts:
            r["note"] = "VLM khong cham duoc, giu diem SigLIP"; continue
        r["siglip_score"] = r["score"]
        r["score"] = next((p for o, p in pts if o == 0), max(p for _, p in pts))
        bo, bp = max(pts, key=lambda x: x[1])
        r["best_off"], r["best_score"] = bo, bp
        r["mean_score"] = sum(p for _, p in pts) / len(pts)
        r["note"] = "VLM cham lai"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--query", required=True)
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--window", type=int, default=90, help="so frame truoc/sau (mac dinh 90 = +-3s)")
    ap.add_argument("--step", type=int, default=30, help="buoc nhay trong cua so (mac dinh 30 = 1s)")
    ap.add_argument("--videos", default=VIDEO_DIR)
    ap.add_argument("--model", default=MODEL_ID)
    ap.add_argument("--backend", default="siglip", choices=["siglip", "api", "hybrid"],
                    help="siglip=local mien phi · api=VLM cham het · hybrid=SigLIP loc roi VLM cham topk")
    ap.add_argument("--topk", type=int, default=20, help="so dong VLM cham lai o che do hybrid")
    ap.add_argument("--fetch", action="store_true", help="tu tai video con thieu")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    rows = read_submission(a.csv)
    print(f"{len(rows)} dong tu {a.csv}")
    res, offsets = run(rows, a.query, a.window, a.step, a.videos, a.model, a.backend, a.topk,
                       fetch_missing=a.fetch)

    base = a.out or os.path.splitext(os.path.basename(a.csv))[0] + "-scored"
    payload = {"query": a.query, "fps": a.fps, "window": a.window, "step": a.step,
               "offsets": offsets, "model": a.model, "backend": a.backend,
               "rows": [[r["video"], r["frame"], r["score"], r["best_off"],
                         r["best_score"], r["mean_score"], r["cos"]] for r in res]}
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    with open(base + ".csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["rank", "video", "frame", "khop_%", "tot_nhat_%", "lech_frame",
                    "trung_binh_%", "cosine", "ghi_chu"])
        for i, r in enumerate(res, 1):
            pc = lambda x: "" if x is None else f"{x*100:.1f}"
            w.writerow([i, r["video"], r["frame"], pc(r["score"]), pc(r["best_score"]),
                        "" if r["best_off"] is None else r["best_off"], pc(r["mean_score"]),
                        "" if r["cos"] is None else f"{r['cos']:.4f}", r["note"]])

    ranked = sorted([r for r in res if r["score"] is not None],
                    key=lambda r: (-r["score"], -(r["cos"] or 0)))
    print(f"\nDa ghi {base}.json va {base}.csv")
    print(f"\n{'#':>4} {'video':11s} {'frame':>7s} {'khop%':>7s} {'tot nhat%':>10s} {'lech':>6s} {'cos':>8s}")
    for r in ranked[:15]:
        print(f"{rows.index({'video':r['video'],'frame':r['frame']})+1:>4} {r['video']:11s} {r['frame']:>7d} "
              f"{r['score']*100:>6.1f}% {r['best_score']*100:>9.1f}% {r['best_off']:>+6d} {r['cos']:>+8.4f}")


if __name__ == "__main__":
    main()
