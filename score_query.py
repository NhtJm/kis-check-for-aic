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
def read_frames_dir(frames_dir, vid, indices):
    """Doc frame da trich san (extract_frames.py). Nhanh hon va khong can file video."""
    import cv2
    out = {}
    for i in indices:
        p = os.path.join(frames_dir, f"{vid}_{i}.jpg")
        if os.path.exists(p):
            img = cv2.imread(p)
            if img is not None:
                out[i] = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return out



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
import scorers

MODEL_ID = scorers.SIGLIP


def score_images(images, queries, model_id=MODEL_ID, agg="mean_emb"):
    """Tra ve (probs, cosines, kind). queries: mot chuoi hoac danh sach bien the."""
    if isinstance(queries, str):
        queries = [queries]
    return scorers.score(images, queries, model_id, agg)


# ---------- pipeline ----------
def read_submission(path):
    """TRAKE co nhieu moc moi dong (video,f1,f2,f3) -- tach thanh tung moc rieng
    de cham diem, kem nhan E1/E2/E3."""
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.reader(f):
            if len(r) < 2 or not r[0].strip():
                continue
            fs = []
            for cell in r[1:]:
                cell = cell.strip()
                if not cell:
                    continue
                try:
                    fs.append(int(float(cell)))
                except ValueError:
                    fs = []; break          # dong header
            for i, fr in enumerate(fs):
                rows.append({"video": r[0].strip(), "frame": fr,
                             "ev": f"E{i+1}" if len(fs) > 1 else ""})
    return rows


def run(rows, query, window=90, step=30, video_dir=VIDEO_DIR, model_id=MODEL_ID,
        backend="siglip", topk=20, log=print, fetch_missing=False, root=".",
        agg="mean_emb", rerank=None, rerank_topk=30, rerank_window=None,
        provider="default", frames_dir=None, translate=False):
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
        # Uu tien frame da trich san: khong can video, khong dung toi YouTube.
        if frames_dir and os.path.isdir(frames_dir):
            got = read_frames_dir(frames_dir, vid, need[vid])
            if got:
                frames[vid], totals[vid] = got, 0
                log(f"  {vid}: {len(got)}/{len(need[vid])} frame (da trich san)")
                if len(got) == len(need[vid]):
                    continue
        path = os.path.join(video_dir, vid + ".mp4")
        if not os.path.exists(path) and fetch_missing:
            import video_cache
            path = video_cache.ensure(vid, video_dir, root, keep=need.keys(), log=log) or path
        if not os.path.exists(path):
            if vid not in frames:
                log(f"  {vid}: THIEU ca frame trich san lan file video, bo qua")
                frames[vid], totals[vid] = {}, 0
            continue
        got, total = read_frames(path, need[vid])
        frames.setdefault(vid, {}).update(got)
        totals[vid] = total
        log(f"  {vid}: doc {len(got)}/{len(need[vid])} frame tu video")

    # cham diem mot lan cho toan bo frame
    flat = [(v, i, frames[v][i]) for v in frames for i in sorted(frames[v])]
    log(f"Cham diem {len(flat)} frame · backend={backend} · query={query!r}")

    # TRAKE: query co the la dict {"E1": "...", "E2": "..."} -- moi moc cham theo
    # dung su kien cua no. Cham ca 3 moc bang chung mot doan mo ta la sai hinh:
    # E2 khong bao gio "giong" mo ta cua E1.
    per_event = isinstance(query, dict)
    if per_event:
        ev_text = dict(query)
        queries = [next(iter(query.values()))]
    else:
        queries = [query] if isinstance(query, str) else list(query)
    if translate:
        # Dich sang tieng Anh truoc khi cham: do thuc te cho thay query tieng Anh
        # tach diem tot hon han tieng Viet (29.77/23.44/0.17 so voi 99.9/100/99.7).
        import query_expand
        queries = [query_expand.translate(q, provider, log)[0] for q in queries]
    if backend == "api":
        import api_backend
        probs, _ = api_backend.score_images([f[2] for f in flat], queries[0], log=log,
                                            provider=provider)
        cosines, kind = [None] * len(flat), "absolute"
    elif per_event:
        # Gan moi frame vao su kien cua moc sinh ra no, roi cham theo tung nhom
        owner = {}
        for r in rows:
            ev = r.get("ev") or ""
            for o in offsets:
                owner.setdefault((r["video"], r["frame"] + o), ev)
        import collections as _c
        groups = _c.defaultdict(list)
        for i, (v, idx, _) in enumerate(flat):
            groups[owner.get((v, idx), "")].append(i)
        probs = [0.0] * len(flat); cosines = [0.0] * len(flat); kind = "absolute"
        for ev, idxs in groups.items():
            txt = ev_text.get(ev) or ev_text.get("") or next(iter(ev_text.values()))
            log(f"  {ev or '(chung)'}: {len(idxs)} frame · {txt[:60]}")
            p_, c_, kind = score_images([flat[i][2] for i in idxs], [txt], model_id, agg)
            for k, i in enumerate(idxs):
                probs[i], cosines[i] = p_[k], c_[k]
    else:
        probs, cosines, kind = score_images([f[2] for f in flat], queries, model_id, agg)

    P = {(v, i): (None if p is None else float(p), None if c is None else float(c))
         for (v, i, _), p, c in zip(flat, probs, cosines)}

    out = []
    for r in rows:
        v, fr = r["video"], r["frame"]
        pts = [(o, P[(v, fr + o)][0], P[(v, fr + o)][1]) for o in offsets
               if (v, fr + o) in P and P[(v, fr + o)][0] is not None]
        if not pts:
            out.append({**r, "score": None, "cos": None, "best_off": None,
                        "best_score": None, "mean_score": None,
                        "rr": None, "rr_off": None, "rr_at0": None,
                        "note": "khong doc duoc frame"})
            continue
        exact = next((p for o, p, c in pts if o == 0), None)
        ecos  = next((c for o, p, c in pts if o == 0), None)
        bo, bp, _ = max(pts, key=lambda x: x[1])
        out.append({**r,
                    "score": exact, "cos": ecos,
                    "best_off": bo, "best_score": bp,
                    "mean_score": sum(p for _, p, _ in pts) / len(pts),
                    "window": [{"off": o, "p": p} for o, p, c in pts],
                    "rr": None, "rr_off": None, "rr_at0": None,
                    "note": ""})

    if backend == "hybrid" and not rerank:      # hybrid = rerank bang VLM qua API
        rerank, rerank_topk = "api", topk

    if rerank:
        out = _rerank(out, offsets, frames, queries, rerank, rerank_topk, agg, log,
                      rerank_window=rerank_window, provider=provider)
    _set_final_rank(out, bool(rerank))
    return out, offsets


def _set_final_rank(out, reranked):
    """Thu tu chuan cuoi cung. Khi co rerank, nhom da rerank luon dung tren nhom con lai --
    tron diem cua hai model khac thang do voi nhau la sai."""
    def key(t):
        i, r = t
        grp = 0 if (reranked and r.get("rr") is not None) else 1
        val = r["rr"] if (reranked and r.get("rr") is not None) else \
              (r["score"] if r["score"] is not None else -1)
        return (grp, -val, -(r["cos"] or 0), i)
    for pos, (i, r) in enumerate(sorted(enumerate(out), key=key), 1):
        r["rank_final"] = pos


def _rerank(out, offsets, frames, queries, rerank_id, topk, agg, log, rerank_window=None,
            provider="default"):
    """Cho model thu hai xep lai topk dong dau ma model thu nhat loc ra.

    rerank_id = 'api' thi dung VLM qua agent router (KIS_API_MODEL).
    Mac dinh VLM chi cham dung frame do (offset 0) cho nhanh va re; model chay local
    thi quet ca cua so."""
    use_api = rerank_id == "api"
    if rerank_window is None:
        rr_offsets = [0] if use_api else offsets
    else:
        rr_offsets = [o for o in offsets if abs(o) <= rerank_window] or [0]

    short = sorted([r for r in out if r["score"] is not None],
                   key=lambda r: (-r["score"], -(r["cos"] or 0)))[:topk]
    if not short:
        return out
    jobs = [(r, o, r["frame"] + o) for r in short for o in rr_offsets
            if (r["frame"] + o) in frames.get(r["video"], {})]
    imgs = [frames[r["video"]][i] for r, o, i in jobs]
    log(f"Rerank bang {rerank_id}: {len(short)} dong / {len(jobs)} frame")

    if use_api:
        import api_backend
        probs, _ = api_backend.score_images(imgs, queries[0], log=log, provider=provider)
        cos = [p if p is not None else -1.0 for p in probs]
    else:
        _, cos, _ = score_images(imgs, queries, rerank_id, agg)

    got = {}
    for (r, o, _), c in zip(jobs, cos):
        got.setdefault(id(r), []).append((o, float(c)))
    for r in short:
        pts = got.get(id(r))
        if not pts:
            continue
        r["rr"]      = max(c for _, c in pts)          # lay diem cao nhat trong cua so
        r["rr_off"]  = max(pts, key=lambda x: x[1])[0]
        r["rr_at0"]  = next((c for o, c in pts if o == 0), None)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--query", required=True)
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--window", type=int, default=90, help="so frame truoc/sau (mac dinh 90 = +-3s)")
    ap.add_argument("--step", type=int, default=30, help="buoc nhay trong cua so (mac dinh 30 = 1s)")
    ap.add_argument("--videos", default=VIDEO_DIR)
    ap.add_argument("--frames", default="frames",
                    help="thu muc frame da trich san (extract_frames.py); uu tien hon video")
    ap.add_argument("--model", default=MODEL_ID)
    ap.add_argument("--backend", default="siglip", choices=["siglip", "api", "hybrid"],
                    help="siglip=local mien phi · api=VLM cham het · hybrid=SigLIP loc roi VLM cham topk")
    ap.add_argument("--topk", type=int, default=20, help="so dong VLM cham lai o che do hybrid")
    ap.add_argument("--fetch", action="store_true", help="tu tai video con thieu")
    ap.add_argument("--expand", type=int, default=0,
                    help="nho LLM dich/dien dat lai thanh N bien the roi gop diem (0 = tat)")
    ap.add_argument("--agg", default="mean_emb", choices=["mean_emb", "max", "mean"],
                    help="cach gop nhieu bien the: mean_emb (gop vector, kinh dien) | max | mean")
    ap.add_argument("--rerank", default=None,
                    help="xep lai vong hai: 'api' (VLM qua agent router) hoac jinaai/jina-clip-v2")
    ap.add_argument("--rerank-topk", type=int, default=30, dest="rerank_topk")
    ap.add_argument("--rerank-window", type=int, default=None, dest="rerank_window",
                    help="chi rerank cac frame lech <= N (mac dinh: api=0, model local=ca cua so)")
    ap.add_argument("--translate", action="store_true",
                    help="tu dich query sang tieng Anh bang API truoc khi cham")
    ap.add_argument("--provider", default="default",
                    help="provider API: openai (KIS_API_*) hoac ar (KIS_AR_*)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    rows = read_submission(a.csv)
    print(f"{len(rows)} dong tu {a.csv}")

    queries = [a.query]
    if a.expand:
        import query_expand
        queries = query_expand.expand(a.query, a.expand, log=print)

    res, offsets = run(rows, queries, a.window, a.step, a.videos, a.model, a.backend, a.topk,
                       fetch_missing=a.fetch, agg=a.agg,
                       rerank=a.rerank, rerank_topk=a.rerank_topk,
                       rerank_window=a.rerank_window, provider=a.provider,
                       frames_dir=a.frames, translate=a.translate)

    base = a.out or os.path.splitext(os.path.basename(a.csv))[0] + "-scored"
    payload = {"query": a.query, "queries": queries, "fps": a.fps, "window": a.window,
               "step": a.step, "offsets": offsets, "model": a.model, "backend": a.backend,
               "agg": a.agg, "rerank": a.rerank,
               "rows": [[r["video"], r["frame"], r["score"], r["best_off"],
                         r["best_score"], r["mean_score"], r["cos"], r["rank_final"]] for r in res]}
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

    # submission da xep lai hang theo diem model, dung dinh dang <video_id>,<frame_id>
    order = sorted(range(len(res)), key=lambda i: res[i]["rank_final"])
    with open(base + "-reranked.csv", "w", newline="", encoding="utf-8") as f:
        for i in order:
            f.write(f"{res[i]['video']},{res[i]['frame']}\n")
    print(f"Da ghi {base}-reranked.csv (submission xep lai theo diem)")

    print(f"\nDa ghi {base}.json va {base}.csv")
    hdr = f"\n{'moi':>4} {'goc':>4} {'video':11s} {'frame':>7s} {'khop%':>7s} {'lech':>6s} {'cos':>8s}"
    if a.rerank:
        hdr += f" {'rerank':>8s}"
    print(hdr)
    for i in order[:15]:
        r = res[i]
        line = (f"{r['rank_final']:>4} {i+1:>4} {r['video']:11s} {r['frame']:>7d} "
                f"{(r['score'] or 0)*100:>6.1f}% {(r['best_off'] or 0):>+6d} {(r['cos'] or 0):>+8.4f}")
        if a.rerank:
            line += f" {r['rr']:>+8.4f}" if r["rr"] is not None else f" {'-':>8s}"
        print(line)


if __name__ == "__main__":
    main()
