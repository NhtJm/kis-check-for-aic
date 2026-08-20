#!/usr/bin/env python3
"""Hai bo cham diem anh-chu, chung mot giao dien.

SigLIP  -- co hieu chuan sigmoid nen cho xac suat khop TUYET DOI, nhung bao hoa o dinh.
JinaCLIP v2 -- khong co hieu chuan, chi so sanh TUONG DOI duoc, bu lai xep hang thuong sac hon.

Ca hai deu nhan nhieu bien the cau query cung luc (prompt ensembling): gop cac
vector chu da chuan hoa lai roi chuan hoa lan nua -- cach gop kinh dien cua CLIP,
lam diu di cach dien dat cua tung cau.
"""
import numpy as np

SIGLIP = "google/siglip-base-patch16-256-multilingual"
JINA   = "jinaai/jina-clip-v2"
_cache = {}


def _device():
    import torch
    return "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")


def combine(embs, agg="mean_emb"):
    """Gop nhieu vector chu (da chuan hoa) thanh mot."""
    if len(embs) == 1 or agg != "mean_emb":
        return embs
    v = embs.mean(axis=0, keepdims=True)
    return v / (np.linalg.norm(v, axis=-1, keepdims=True) + 1e-9)


class SiglipScorer:
    kind = "absolute"
    name = SIGLIP

    def __init__(self, model_id=SIGLIP):
        import torch
        from transformers import AutoModel, AutoProcessor
        self.name = model_id
        self.dev = _device()
        self.model = AutoModel.from_pretrained(model_id).to(self.dev).eval()
        self.proc = AutoProcessor.from_pretrained(model_id)
        self.torch = torch

    def text_embed(self, texts):
        t = self.proc(text=list(texts), padding="max_length", truncation=True, return_tensors="pt").to(self.dev)
        with self.torch.no_grad():
            f = self.model.get_text_features(**t)
        f = f / f.norm(dim=-1, keepdim=True)
        return f.float().cpu().numpy()

    def image_embed(self, images, batch=24):
        out = []
        for i in range(0, len(images), batch):
            im = self.proc(images=images[i:i+batch], return_tensors="pt").to(self.dev)
            with self.torch.no_grad():
                f = self.model.get_image_features(**im)
            out.append((f / f.norm(dim=-1, keepdim=True)).float().cpu().numpy())
        return np.concatenate(out) if out else np.zeros((0, 1))

    def prob(self, cos):
        """sigmoid(scale*cos + bias) -- xac suat khop da hieu chuan cua SigLIP."""
        scale = float(self.model.logit_scale.exp())
        bias  = float(self.model.logit_bias)
        return 1.0 / (1.0 + np.exp(-(scale * cos + bias)))


class JinaScorer:
    kind = "relative"
    name = JINA

    def __init__(self, model_id=JINA):
        import torch
        from transformers import AutoModel
        self.name = model_id
        self.dev = _device()
        self.model = AutoModel.from_pretrained(model_id, trust_remote_code=True).to(self.dev).eval()
        self.torch = torch

    def text_embed(self, texts):
        v = np.asarray(self.model.encode_text(list(texts)), dtype="float32")
        if v.ndim == 1:
            v = v[None, :]
        return v / (np.linalg.norm(v, axis=-1, keepdims=True) + 1e-9)

    def image_embed(self, images, batch=16):
        from PIL import Image
        pil = [Image.fromarray(im) for im in images]
        out = []
        for i in range(0, len(pil), batch):
            v = np.asarray(self.model.encode_image(pil[i:i+batch]), dtype="float32")
            if v.ndim == 1:
                v = v[None, :]
            out.append(v / (np.linalg.norm(v, axis=-1, keepdims=True) + 1e-9))
        return np.concatenate(out) if out else np.zeros((0, 1))

    def prob(self, cos):
        """Khong co hieu chuan -- tra ve None, ben goi se tu chuan hoa tuong doi."""
        return None


def get(model_id):
    if model_id not in _cache:
        _cache[model_id] = JinaScorer(model_id) if "jina" in model_id.lower() else SiglipScorer(model_id)
    return _cache[model_id]


def score(images, queries, model_id=SIGLIP, agg="mean_emb"):
    """Tra ve (probs, cosines, kind). queries la mot hoac nhieu bien the cau hoi."""
    sc = get(model_id)
    temb = combine(sc.text_embed(queries), agg)          # (k, d)
    iemb = sc.image_embed(images)                        # (n, d)
    if len(iemb) == 0:
        return np.zeros(0), np.zeros(0), sc.kind
    sims = iemb @ temb.T                                 # (n, k)
    cos = sims.max(axis=1) if agg == "max" else sims.mean(axis=1)
    p = sc.prob(cos)
    if p is None:                                        # chuan hoa tuong doi trong tap ung vien
        lo, hi = float(cos.min()), float(cos.max())
        p = (cos - lo) / (hi - lo) if hi > lo else np.full_like(cos, 0.5)
    return np.asarray(p), np.asarray(cos), sc.kind
