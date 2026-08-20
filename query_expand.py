#!/usr/bin/env python3
"""Nhan mot cau query thanh nhieu bien the de gop diem (prompt ensembling).

Uu tien goi LLM qua API de dich va dien dat lai; neu chua cau hinh API thi lui ve
mot bo bien the co san khong can mang.
"""
import json, os, re, urllib.request, urllib.error

SYS = (
    "You prepare queries for an image-text retrieval model (CLIP/SigLIP).\n"
    "From the user's scene description, produce exactly {n} variants:\n"
    "  - at least 2 English translations written as image captions: short, concrete\n"
    "  - 1 English variant listing only the key objects/nouns, not a full sentence\n"
    "  - the rest: English rephrasings from different angles\n"
    "Keep the meaning; do not invent details absent from the original.\n"
    'Reply with JSON only: {{"variants": ["...", "..."]}}'
)


def fallback(query):
    """Khong co API thi van co vai bien the don gian, khong can mang."""
    q = query.strip().rstrip(".")
    return [q, f"a photo of {q}", f"{q}, a frame from a TV news broadcast"]


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
