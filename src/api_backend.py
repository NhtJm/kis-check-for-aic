#!/usr/bin/env python3
"""Cham diem frame bang mot VLM qua API kieu OpenAI (OpenRouter / agent router / ...).

Doc cau hinh tu bien moi truong -- khong bao gio ghi khoa vao file:

    export KIS_API_BASE=https://openrouter.ai/api/v1     # hoac router cua ban
    export KIS_API_KEY=sk-...
    export KIS_API_MODEL=google/gemini-2.5-flash          # model nao co thi nhin anh

Model phai nhan duoc anh (vision). Moi frame la mot request, nen dung ket hop
voi buoc loc SigLIP o local cho re -- xem che do "hybrid" trong score_query.py.
"""
import base64, io, json, os, re, sys
from concurrent.futures import ThreadPoolExecutor
import urllib.request, urllib.error

# Prompt viet bang tieng Anh, khong phai vi model hieu tieng Anh tot hon, ma vi
# mot so router (Agent Router) tra ve "content-blocked" cho noi dung tieng Viet.
# Tien the: do thuc te cho thay query tieng Anh cung xep hang tot hon tieng Viet.
PROMPT = (
    "You are verifying a video search result. Below are one video frame and one "
    "scene description.\n"
    "Rate how well the frame matches the description on a 0-100 scale:\n"
    "  0   = completely unrelated\n"
    "  50  = some elements match but the main subject is missing\n"
    "  100 = a full match, exactly the scene described\n"
    'Reply with JSON only: {"score": <0-100>, "reason": "<one short sentence>"}\n\n'
    "Scene description: "
)


def load_dotenv(path=None):
    """Doc file .env canh script vao os.environ. Khong ghi de bien da co san."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = path or os.path.join(root, ".env")
    if not os.path.exists(path):
        return False
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:      # bien moi truong that luon thang .env
                os.environ[k] = v
    return True


# Cho phep cau hinh nhieu provider cung luc trong mot file .env:
#   KIS_API_*  = provider mac dinh
#   KIS_AR_*   = Agent Router
PREFIXES = {"default": "KIS_API", "openai": "KIS_API", "ar": "KIS_AR"}


def cfg(provider="default"):
    load_dotenv()
    pre = PREFIXES.get(provider, provider)
    base  = os.environ.get(pre + "_BASE", "").rstrip("/")
    key   = os.environ.get(pre + "_KEY", "")
    model = os.environ.get(pre + "_MODEL", "")
    missing = [pre + s for s, v in [("_BASE", base), ("_KEY", key), ("_MODEL", model)] if not v]
    if missing:
        raise RuntimeError("Thieu cau hinh: " + ", ".join(missing)
                           + " -- dat trong file .env hoac bien moi truong")
    return base, key, model


def available():
    """Liet ke provider da cau hinh du ba gia tri."""
    load_dotenv()
    out = {}
    for name in ("openai", "ar"):
        try:
            b, k, m = cfg(name)
            out[name] = {"base": b, "model": m}
        except RuntimeError:
            pass
    return out


def to_data_uri(img_rgb, quality=80, max_w=512):
    from PIL import Image
    im = Image.fromarray(img_rgb)
    if im.width > max_w:
        im = im.resize((max_w, round(im.height * max_w / im.width)))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=quality)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _one(img, query, base, key, model, timeout=90):
    body = {
        "model": model,
        "temperature": 0,
        "max_tokens": 120,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": PROMPT + query},
            # detail=low: chi phi giam ~3 lan ma cau tra loi khong doi (do thuc te
            # tren gpt-4o-mini: 8532 -> 2865 token, cung cho ket qua nhu nhau).
            {"type": "image_url", "image_url": {"url": to_data_uri(img), "detail": "low"}},
        ]}],
    }
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
    )
    try:
        raw = urllib.request.urlopen(req, timeout=timeout).read()
        txt = json.loads(raw)["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read()[:160].decode(errors='replace')}"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"

    m = re.search(r'"score"\s*:\s*([0-9]+(?:\.[0-9]+)?)', txt) or re.search(r'\b([0-9]{1,3})\b', txt)
    if not m:
        return None, "khong doc duoc diem tu: " + txt[:120]
    return max(0.0, min(1.0, float(m.group(1)) / 100.0)), ""


def score_images(images, query, concurrency=6, log=lambda m: None, provider="default"):
    """Tra ve (probs, notes) song song voi danh sach anh dau vao."""
    base, key, model = cfg(provider)
    log(f"  API: {model} qua {base} · {len(images)} frame · {concurrency} luong")
    out = [None] * len(images)
    notes = [""] * len(images)

    def work(i):
        out[i], notes[i] = _one(images[i], query, base, key, model)

    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        list(ex.map(work, range(len(images))))

    bad = [n for n in notes if n]
    if bad:
        log(f"  API: {len(bad)}/{len(images)} frame loi, vd: {bad[0]}")
    return out, notes


def selftest(provider="default"):
    """Kiem tra cau hinh va goi thu mot anh mau."""
    import numpy as np
    base, key, model = cfg(provider)
    print(f"base  = {base}\nmodel = {model}\nkey   = {'*' * 8}{key[-4:]} (do dai {len(key)})")
    img = np.zeros((64, 64, 3), dtype="uint8"); img[:, :, 0] = 220   # o vuong do
    p, note = _one(img, "a solid red square", base, key, model)
    print("ket qua:", p, note or "OK")
    return p is not None


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "default"
    print("provider da cau hinh:", ", ".join(available()) or "(chua co cai nao)")
    print(f"--- thu provider: {which} ---")
    sys.exit(0 if selftest(which) else 1)
