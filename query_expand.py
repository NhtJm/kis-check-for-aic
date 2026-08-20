#!/usr/bin/env python3
"""Nhan mot cau query thanh nhieu bien the de gop diem (prompt ensembling).

Uu tien goi LLM qua API de dich va dien dat lai; neu chua cau hinh API thi lui ve
mot bo bien the co san khong can mang.
"""
import json, os, re, urllib.request, urllib.error

SYS = (
    "Bạn giúp chuẩn bị truy vấn cho mô hình tìm kiếm ảnh theo mô tả (CLIP/SigLIP).\n"
    "Từ câu mô tả cảnh của người dùng, hãy tạo đúng {n} biến thể:\n"
    "  - ít nhất 2 bản dịch tiếng Anh, viết theo văn phong caption ảnh, ngắn gọn, cụ thể\n"
    "  - 1 bản tiếng Anh chỉ liệt kê các danh từ/vật thể chính, không cần thành câu\n"
    "  - phần còn lại là các cách diễn đạt lại bằng tiếng Việt\n"
    "Giữ nguyên ý nghĩa, không thêm chi tiết không có trong câu gốc.\n"
    'Chỉ trả về JSON: {{"variants": ["...", "..."]}}'
)


def fallback(query):
    """Khong co API thi van co vai bien the don gian, khong can mang."""
    q = query.strip().rstrip(".")
    return [q, f"a photo of {q}", f"{q}, khung hình từ bản tin truyền hình"]


def expand(query, n=6, log=lambda m: None):
    import api_backend
    try:
        base, key, model = api_backend.cfg()
    except Exception as e:
        log(f"  mo rong query: chua cau hinh API ({e}) -> dung bo bien the co san")
        return fallback(query)

    body = {"model": model, "temperature": 0.3, "max_tokens": 600,
            "messages": [{"role": "system", "content": SYS.format(n=n)},
                         {"role": "user", "content": query}]}
    req = urllib.request.Request(base + "/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + key})
    try:
        txt = json.loads(urllib.request.urlopen(req, timeout=90).read())["choices"][0]["message"]["content"]
    except Exception as e:
        log(f"  mo rong query that bai ({type(e).__name__}) -> dung bo bien the co san")
        return fallback(query)

    m = re.search(r'\{.*\}', txt, re.S)
    try:
        got = json.loads(m.group(0))["variants"]
        out = [query] + [v.strip() for v in got if isinstance(v, str) and v.strip()]
    except Exception:
        log("  khong doc duoc JSON bien the -> dung bo bien the co san")
        return fallback(query)

    seen, uniq = set(), []
    for v in out:
        if v.lower() not in seen:
            seen.add(v.lower()); uniq.append(v)
    log(f"  mo rong thanh {len(uniq)} bien the:")
    for v in uniq:
        log(f"    · {v}")
    return uniq


if __name__ == "__main__":
    import sys
    for v in expand(sys.argv[1] if len(sys.argv) > 1 else "bốn phi hành gia mặc áo đen", log=print):
        print(v)
