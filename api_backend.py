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

PROMPT = (
    "Bạn đang kiểm tra kết quả tìm kiếm video. Dưới đây là một khung hình và một câu mô tả.\n"
    "Chấm mức độ khớp giữa khung hình và câu mô tả trên thang 0-100:\n"
    "  0   = hoàn toàn không liên quan\n"
    "  50  = có vài yếu tố khớp nhưng thiếu ý chính\n"
    "  100 = khớp hoàn toàn, đúng cảnh được mô tả\n"
    "Chỉ trả về JSON: {\"score\": <số 0-100>, \"reason\": \"<1 câu ngắn>\"}\n\n"
    "Câu mô tả: "
)


def cfg():
    base  = os.environ.get("KIS_API_BASE", "").rstrip("/")
    key   = os.environ.get("KIS_API_KEY", "")
    model = os.environ.get("KIS_API_MODEL", "")
    missing = [n for n, v in [("KIS_API_BASE", base), ("KIS_API_KEY", key), ("KIS_API_MODEL", model)] if not v]
    if missing:
        raise RuntimeError("Thieu bien moi truong: " + ", ".join(missing))
    return base, key, model


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
            {"type": "image_url", "image_url": {"url": to_data_uri(img)}},
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


def score_images(images, query, concurrency=6, log=lambda m: None):
    """Tra ve (probs, notes) song song voi danh sach anh dau vao."""
    base, key, model = cfg()
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


def selftest():
    """Kiem tra cau hinh va goi thu mot anh mau."""
    import numpy as np
    base, key, model = cfg()
    print(f"base  = {base}\nmodel = {model}\nkey   = {'*' * 8}{key[-4:]} (do dai {len(key)})")
    img = np.zeros((64, 64, 3), dtype="uint8"); img[:, :, 0] = 220   # o vuong do
    p, note = _one(img, "một ô vuông màu đỏ", base, key, model)
    print("ket qua:", p, note or "OK")
    return p is not None


if __name__ == "__main__":
    sys.exit(0 if selftest() else 1)
