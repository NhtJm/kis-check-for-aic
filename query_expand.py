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


# ---------- dich sang tieng Anh ----------
TRANSLATE_SYS = (
    "You translate scene descriptions for an image-text retrieval model.\n"
    "Translate the user's text into English, written the way an image caption is "
    "written: concrete, visual, no filler.\n"
    "Keep every detail; do not add anything that is not in the original.\n"
    "If the text is already English, return it unchanged.\n"
    'Reply with JSON only: {"en": "..."}'
)

# Dau tieng Viet -- dung de biet co can dich khong
_VN = "àáảãạăằắẳẵặâầấẩẫậđèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ"


def is_vietnamese(text):
    t = text.lower()
    return any(c in _VN for c in t)


def translate(query, provider="default", log=lambda m: None):
    """Dich query sang tieng Anh. Tra ve nguyen van neu khong dich duoc."""
    if not is_vietnamese(query):
        return query, False

    import api_backend
    try:
        base, key, model = api_backend.cfg(provider)
    except Exception as e:
        log(f"  khong dich duoc (chua cau hinh API): {e}")
        return query, False

    body = {"model": model, "temperature": 0, "max_tokens": 300,
            "messages": [{"role": "system", "content": TRANSLATE_SYS},
                         {"role": "user", "content": query}]}
    req = urllib.request.Request(base + "/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + key})
    try:
        txt = json.loads(urllib.request.urlopen(req, timeout=60).read())["choices"][0]["message"]["content"]
    except Exception as e:
        log(f"  dich that bai ({type(e).__name__}) -- dung nguyen query goc")
        return query, False

    m = re.search(r'\{.*\}', txt, re.S)
    try:
        en = json.loads(m.group(0))["en"].strip()
    except Exception:
        en = txt.strip().strip('"')
    if not en:
        return query, False
    log(f"  dich: {query!r}")
    log(f"     -> {en!r}")
    return en, True


if __name__ == "__main__":
    import sys
    for v in expand(sys.argv[1] if len(sys.argv) > 1 else "bốn phi hành gia mặc áo đen", log=print):
        print(v)