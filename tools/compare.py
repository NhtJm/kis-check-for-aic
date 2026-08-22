#!/usr/bin/env python3
"""So sanh cac cau hinh cham diem tren cung mot submission.

    python3 compare.py --csv sub.csv --query "..." [--truth L21_V015,25725]

Neu cho --truth (dong dung), script bao thu hang cua no o tung cau hinh --
day moi la con so noi len chat luong, chu khong phai diem %.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import argparse, json, sys
import score_query as sq
import scorers

def rank_of(res, truth):
    if not truth:
        return None
    v, f = truth.split(",")
    for r in res:
        if r["video"] == v and r["frame"] == int(f):
            return r["rank_final"]
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--query", required=True)
    ap.add_argument("--en", default=None, help="ban dich tieng Anh (neu khong goi API)")
    ap.add_argument("--truth", default=None, help="dong dung, dang L21_V015,25725")
    ap.add_argument("--window", type=int, default=90)
    ap.add_argument("--step", type=int, default=30)
    ap.add_argument("--expand", type=int, default=0)
    a = ap.parse_args()

    rows = sq.read_submission(a.csv)
    vi = a.query
    en = a.en or vi
    multi = [vi, en]
    if a.expand:
        import query_expand
        multi = query_expand.expand(vi, a.expand, log=print)

    configs = [
        ("SigLIP · chi tieng Viet",      dict(query=[vi],   model_id=scorers.SIGLIP)),
        ("SigLIP · chi tieng Anh",       dict(query=[en],   model_id=scorers.SIGLIP)),
        ("SigLIP · gop bien the",        dict(query=multi,  model_id=scorers.SIGLIP)),
        ("Jina v2 · gop bien the",       dict(query=multi,  model_id=scorers.JINA)),
        ("SigLIP loc -> Jina rerank 30", dict(query=multi,  model_id=scorers.SIGLIP,
                                              rerank=scorers.JINA, rerank_topk=30)),
    ]

    print(f"\n{len(rows)} dong · cua so ±{a.window} buoc {a.step}")
    print(f"query VI: {vi}\nquery EN: {en}")
    if len(multi) > 2:
        print(f"bien the: {len(multi)}")
    if a.truth:
        print(f"dong dung: {a.truth}")

    results = {}
    for name, kw in configs:
        res, _ = sq.run(rows, window=a.window, step=a.step, log=lambda m: None, **kw)
        results[name] = res
        top = sorted(res, key=lambda r: r["rank_final"])[:5]
        rk = rank_of(res, a.truth)
        print(f"\n=== {name} ===")
        if rk:
            print(f"  >>> DONG DUNG dung hang {rk}/{len(rows)}")
        for r in top:
            mark = "  <<< DUNG" if a.truth and f"{r['video']},{r['frame']}" == a.truth else ""
            print(f"   {r['rank_final']:>3}. {r['video']:11s} {r['frame']:>6d} "
                  f"cos={(r['cos'] or 0):+.4f}{mark}")

    if a.truth:
        print("\n=== TONG KET: hang cua dong dung ===")
        for name in results:
            rk = rank_of(results[name], a.truth)
            print(f"  {rk:>3}  {name}" if rk else f"    -  {name}")

if __name__ == "__main__":
    main()
