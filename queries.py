#!/usr/bin/env python3
"""Tach bo de AIC dan tho thanh danh sach cau hoi.

Van ban dan vao co dang:

    Textual Known Item Search (KIS)
    Câu `query-p1-1-kis`
    <mo ta, co the nhieu dong>
    Câu `query-p1-2-kis`
    ...

Ham parse() lay ra id, loai (kis/qa/trake), va phan mo ta; voi TRAKE thi tach
them cac moc su kien E1..En.
"""
import re

# Cac dong tieu de / rac cua trang web, khong thuoc mo ta cau hoi nao
JUNK = re.compile(
    r"^\s*(?:Textual Known Item Search.*|Question Answering.*|"
    r"Temporal Retrieval and Alignment.*|Bộ câu hỏi vòng thi.*|Tệp đính kèm.*|"
    r"Đăng xuất|Đề bài.*|AIC\d*|\[.*\]\(.*\)|\*\s*\[.*|\d{2}:\d{2}:\d{2}|"
    r"Thanh niên, sinh viên.*)\s*$", re.I)

MARKER = re.compile(r"^\s*C[âa]u\s+[`'\"]?(query-[A-Za-z0-9_-]+)[`'\"]?\s*$", re.M)
# Dau phan cach sau E1 co the la ":", "." hoac chi mot khoang trang --
# de thi viet ca hai kieu.
EVENT  = re.compile(r"^\s*(E\d+)\s*[:.\-]?\s+(.+)$", re.M)
CUT    = re.compile(r"^\s*Tệp đính kèm\s*$", re.M)


def kind_of(qid):
    tail = qid.rsplit("-", 1)[-1].lower()
    return tail if tail in ("kis", "qa", "trake") else "kis"


def clean(block):
    lines = [l.rstrip() for l in block.splitlines()]
    keep = [l for l in lines if l.strip() and not JUNK.match(l)]
    return "\n".join(keep).strip()


def parse(text):
    """Tra ve list {id, kind, text, events}. Giu nguyen thu tu xuat hien."""
    cut = CUT.search(text)
    if cut:
        text = text[:cut.start()]          # bo phan danh sach tep dinh kem

    marks = list(MARKER.finditer(text))
    out = []
    for i, m in enumerate(marks):
        qid = m.group(1)
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        body = clean(text[m.end():end])
        kind = kind_of(qid)
        events = []
        if kind == "trake":
            events = [{"id": e.group(1), "text": e.group(2).strip()}
                      for e in EVENT.finditer(body)]
        out.append({"id": qid, "kind": kind, "text": body, "events": events})

    # Bo trung id, giu ban dau tien
    seen, uniq = set(), []
    for q in out:
        if q["id"] not in seen:
            seen.add(q["id"]); uniq.append(q)
    return uniq


def summary(qs):
    from collections import Counter
    c = Counter(q["kind"] for q in qs)
    return {"total": len(qs), "by_kind": dict(c)}


if __name__ == "__main__":
    import sys, json
    data = open(sys.argv[1], encoding="utf-8").read() if len(sys.argv) > 1 else sys.stdin.read()
    qs = parse(data)
    print(json.dumps({"summary": summary(qs), "queries": qs}, ensure_ascii=False, indent=2))
