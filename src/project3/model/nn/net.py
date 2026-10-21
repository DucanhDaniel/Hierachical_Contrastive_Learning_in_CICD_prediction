"""Mạng đọc log: các đoạn log -> UniXcoder (đóng băng embeddings + N lớp dưới), trung bình token -> attention đoạn -> job
-> run (vector r); ngữ cảnh CI mã hoá cùng encoder -> 64 số; tuỳ chọn log xác suất TF-IDF -> 64 số; ghép -> MLP -> z (256).
Ba đầu phân loại (tầng 1, tầng 2, lá) + đầu so sánh 64 chiều (chỉ dùng khi huấn luyện).
"""
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from ..config import ENCODER
from ..labels import LabelTree
from .pooling import seg_softmax_pool


class LogNet(nn.Module):
    def __init__(self, tree: LabelTree, device, freeze_layers: int = 6, tfidf_dim: int = 0,
                 share_parent: bool = False, proxy: bool = False, encoder: str = ENCODER):
        from transformers import AutoModel, AutoTokenizer
        super().__init__()
        self.tok = AutoTokenizer.from_pretrained(encoder)
        self.enc = AutoModel.from_pretrained(encoder)
        for p in self.enc.embeddings.parameters():
            p.requires_grad = False
        for layer in self.enc.encoder.layer[:freeze_layers]:
            for p in layer.parameters():
                p.requires_grad = False
        d = self.enc.config.hidden_size
        n1, n2, n3 = len(tree.l1), len(tree.l2), len(tree.l3)
        self.att_c, self.att_j = nn.Linear(d, 1), nn.Linear(d, 1)
        self.ctx = nn.Sequential(nn.Linear(d, 64), nn.GELU())
        if tfidf_dim:
            self.tf = nn.Sequential(nn.Linear(tfidf_dim, 64), nn.GELU())
        self.body = nn.Sequential(nn.Dropout(0.1), nn.Linear(d + 64 + 64 * bool(tfidf_dim), 256), nn.GELU(), nn.Dropout(0.1))
        self.h1, self.h2, self.h3 = nn.Linear(256, n1), nn.Linear(256, n2), nn.Linear(256, n3)
        self.share_parent = share_parent
        if share_parent:  # h3.weight đóng vai độ lệch so với trọng số loại cha ở h2
            nn.init.zeros_(self.h3.weight)
        self.con = nn.Sequential(nn.Linear(256, 128), nn.GELU(), nn.Linear(128, 64))
        if proxy:  # nguyên mẫu cha (tầng 2) + độ lệch lá
            self.proxy_parent = nn.Parameter(torch.randn(n2, 64) * 0.1)
            self.proxy_delta = nn.Parameter(torch.zeros(n3, 64))
        self.leaf_parent = torch.tensor(tree.leaf_parent_index(), device=device)
        self.dev = device

    def embed(self, texts: list, max_len: int) -> torch.Tensor:
        e = self.tok(texts, padding=True, truncation=True, max_length=max_len, return_tensors="pt").to(self.dev)
        h = self.enc(**e).last_hidden_state
        m = e["attention_mask"].unsqueeze(-1).to(h.dtype)
        return ((h * m).sum(1) / m.sum(1)).float()

    def forward(self, texts: list, c2j: list, j2r: list, n_runs: int, ctx: list, tf=None,
                max_tokens: int = 256, keep: bool = False):
        """texts: các đoạn log của batch; c2j[i] = job của đoạn i; j2r[j] = run (trong batch) của job j;
        ctx: ngữ cảnh CI từng run; tf: mảng log xác suất TF-IDF từng run (nếu có).
        Trả về (logit tầng 1, tầng 2, lá, đặc trưng so sánh đã chuẩn hoá, extra); extra = {"w": trọng số từng đoạn trong
        cả run, "z": z} khi keep, ngược lại None."""
        h = self.embed(texts, max_tokens)
        c2j, j2r = torch.tensor(c2j, device=self.dev), torch.tensor(j2r, device=self.dev)
        j, wc = seg_softmax_pool(h, self.att_c(h).squeeze(1), c2j, len(j2r))
        r, wj = seg_softmax_pool(j, self.att_j(j).squeeze(1), j2r, n_runs)
        extra = {"w": (wc * wj[c2j]).detach().cpu().numpy()} if keep else None
        feats = [r, self.ctx(self.embed(ctx, 64))]
        if tf is not None:
            feats.append(self.tf(torch.tensor(tf, device=self.dev)))
        z = self.body(torch.cat(feats, 1))
        if keep:
            extra["z"] = z.detach().float().cpu().numpy().astype(np.float16)
        o3 = (z @ (self.h2.weight[self.leaf_parent] + self.h3.weight).T + self.h3.bias) if self.share_parent else self.h3(z)
        return self.h1(z), self.h2(z), o3, F.normalize(self.con(z), dim=1), extra


def decode(o1, o2, o3, tree: LabelTree):
    """Dự đoán nhất quán theo cây: tầng 2 = argmax log p1(nhóm) + log p2(loại); lá = argmax p3 trong các con của loại đó
    (loại không có lá con -> chính loại đó). Trả về (lá dự đoán, log xác suất 3 tầng ghép lại, float16)."""
    lp1, lp2, lp3 = (torch.log_softmax(o.float(), 1).cpu().numpy() for o in (o1, o2, o3))
    g = np.array([tree.l1.index(tree.group[c]) for c in tree.l2])
    s2 = lp1[:, g] + lp2
    children = tree.children()
    out = []
    for i, c in enumerate(s2.argmax(1)):
        ch = children[tree.l2[c]]
        out.append(tree.l3[ch[int(lp3[i, ch].argmax())]] if ch else tree.l2[c])
    return out, np.concatenate([lp1, lp2, lp3], 1).astype(np.float16)
