#!/usr/bin/env python3
"""Kiem tra cau hinh API voi chi phi toi thieu.

Chi goi DUNG MOT anh, roi doc truong `usage` that trong response de tinh chi phi
that thay vi doan. Chay cai nay truoc khi cham ca submission.

    python3 deploy/test_api.py            # test model trong .env
    python3 deploy/test_api.py --list     # xem model nao dung duoc
    python3 deploy/test_api.py --model gpt-4o-mini
"""
import argparse, json, os, sys, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import api_backend

# Gia tham khao USD/1M token. Chi de uoc tinh -- kiem tra lai bang bang gia that.
PRICE = {
    "gpt-4o-mini":   (0.15,  0.60),
    "gpt-4.1-mini":  (0.40,  1.60),
    "gpt-4.1-nano":  (0.10,  0.40),
    "gpt-4o":        (2.50, 10.00),
}


def req(url, key, body=None, timeout=90):
    r = urllib.request.Request(url, data=json.dumps(body).encode() if body else None,
                               headers={"Content-Type": "application/json",
                                        "Authorization": "Bearer " + key})
    return json.loads(urllib.request.urlopen(r, timeout=timeout).read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--model", default=None)
    a = ap.parse_args()

    api_backend.load_dotenv()
    base, key, model = api_backend.cfg()
    model = a.model or model
    print(f"base  = {base}\nmodel = {model}\nkey   = ***{key[-4:]}\n")

    if a.list:
        try:
            ids = sorted(m["id"] for m in req(base + "/models", key)["data"])
        except urllib.error.HTTPError as e:
            sys.exit(f"khong lay duoc danh sach model: HTTP {e.code} {e.read()[:200].decode()}")
        print(f"{len(ids)} model:")
        for i in ids:
            tag = "  <- co bang gia, nhin duoc anh" if i in PRICE else ""
            print(f"  {i}{tag}")
        return

    # mot anh 64x64 mau do, nho nhat co the
    import numpy as np
    img = np.zeros((64, 64, 3), dtype="uint8"); img[:, :, 0] = 220
    body = {"model": model, "temperature": 0, "max_tokens": 60,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": 'What color is this image? Reply JSON: {"color":"..."}'},
                {"type": "image_url", "image_url": {"url": api_backend.to_data_uri(img)}}]}]}
    try:
        r = req(base + "/chat/completions", key, body)
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read()[:400].decode()}")

    print("tra loi:", r["choices"][0]["message"]["content"][:120])
    u = r.get("usage") or {}
    pt, ct = u.get("prompt_tokens", 0), u.get("completion_tokens", 0)
    print(f"token : prompt={pt} completion={ct}")

    if model in PRICE and pt:
        pin, pout = PRICE[model]
        one = pt * pin / 1e6 + ct * pout / 1e6
        print(f"\nchi phi mot frame : ${one:.6f}")
        for n, label in [(30, "rerank top 30 (window 0)"),
                         (140, "hybrid ~140 frame"),
                         (700, "cham het 100 dong, cua so ±90")]:
            print(f"  {label:32s} ~${one*n:.3f}")
    else:
        print("\n(khong co bang gia cho model nay -- nhan token o tren de tu tinh)")


if __name__ == "__main__":
    main()
