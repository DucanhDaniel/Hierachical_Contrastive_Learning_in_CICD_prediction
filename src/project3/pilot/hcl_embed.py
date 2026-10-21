"""Bước 1 của pilot HCL: embed từng hunk của diff bằng UniXcoder đóng băng, lưu cache.

Mỗi commit lấy tối đa MAX_HUNKS hunk, chia vòng tròn giữa các file (file nào cũng có mặt trước khi lấy hunk thứ hai).
Input của một hunk: đường dẫn file + header @@ + các dòng ngữ cảnh/thêm/xoá (giữ dấu +/-), tối đa MAX_TOKENS token.
Kết quả data/processed/hcl_pilot/emb.npz:
  emb [n_hunk, 768] float16, hunk_file [n_hunk] (chỉ số file toàn cục), file_commit [n_file], shas [n_commit]

    uv run --group exp python -m project3.pilot.hcl_embed
"""
import argparse
import gzip
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from transformers import AutoModel, AutoTokenizer

from .experiment import read_diff

MODEL = "microsoft/unixcoder-base"
MAX_HUNKS = 32
MAX_TOKENS = 256
MAX_HUNK_CHARS = 3000


def hunks_of(path: str) -> list[list[str]]:
    """[[text hunk của file 1...], [file 2...]] theo thứ tự trong diff."""
    files, cur, name, hunk = [], None, None, None
    for line in read_diff(path).splitlines():
        if line.startswith("diff --git "):
            name = line.split(" b/", 1)[-1]
            cur = []
            files.append(cur)
            hunk = None
        elif line.startswith("@@") and cur is not None:
            hunk = [name, line]
            cur.append(hunk)
        elif hunk is not None and line[:1] in "+- " and not line.startswith(("+++", "---")):
            hunk.append(line)
    return [["\n".join(h)[:MAX_HUNK_CHARS] for h in f] for f in files if f]


def pick(files: list[list[str]], k: int) -> list[tuple[int, str]]:
    out, depth = [], 0
    while len(out) < k and any(depth < len(f) for f in files):
        for i, f in enumerate(files):
            if depth < len(f) and len(out) < k:
                out.append((i, f[depth]))
        depth += 1
    return sorted(out, key=lambda x: x[0])  # gom hunk cùng file liền nhau


def collect(diffs_csv: Path, max_hunks: int) -> dict:
    d = pd.read_csv(diffs_csv)
    d = d[d.ok.astype(str) == "True"].drop_duplicates("head_sha").reset_index(drop=True)
    texts, hunk_file, file_commit, shas = [], [], [], []
    for _, r in d.iterrows():
        chosen = pick(hunks_of(r.path), max_hunks)
        if not chosen:
            continue
        c = len(shas)
        shas.append(r.head_sha)
        local = {}
        for fi, text in chosen:
            if fi not in local:
                local[fi] = len(file_commit)
                file_commit.append(c)
            hunk_file.append(local[fi])
            texts.append(text)
    print(f"{len(shas)} commit, {len(file_commit)} file, {len(texts)} hunk", flush=True)
    return {"texts": texts, "hunk_file": hunk_file, "file_commit": file_commit, "shas": shas}


def embed(h: dict, out: Path, batch: int, max_tokens: int, fp16: bool) -> None:
    texts = h["texts"]
    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModel.from_pretrained(MODEL).cuda().eval()
    if fp16:  # T4 có Tensor Core; GTX 16xx thì fp16 chậm hơn fp32 ~3,5 lần nên để fp32
        model = model.half()
    order = np.argsort([len(t) for t in texts])  # gom độ dài gần nhau để ít padding
    emb = np.zeros((len(texts), model.config.hidden_size), dtype=np.float16)
    t0 = time.time()
    with torch.inference_mode():
        for i in range(0, len(order), batch):
            idx = order[i:i + batch]
            enc = tok([texts[j] for j in idx], padding=True, truncation=True, max_length=max_tokens,
                      return_tensors="pt").to("cuda")
            hs = model(**enc).last_hidden_state.float()
            m = enc["attention_mask"].unsqueeze(-1).float()
            emb[idx] = ((hs * m).sum(1) / m.sum(1)).cpu().numpy()
            if (i // batch) % 100 == 0:
                print(f"  {i + len(idx)}/{len(texts)} ({time.time() - t0:.0f}s)", flush=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez(out, emb=emb, hunk_file=np.array(h["hunk_file"]), file_commit=np.array(h["file_commit"]),
             shas=np.array(h["shas"], dtype="U40"))
    print(f"Đã lưu {out} ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--diffs", type=Path, default=Path("data/processed/pilot_diffs.csv"))
    ap.add_argument("--hunks", type=Path, help="đọc hunk đã gom sẵn (json.gz) thay vì đọc diff")
    ap.add_argument("--pack", type=Path, help="chỉ gom hunk rồi ghi ra json.gz (để upload lên GPU từ xa)")
    ap.add_argument("--out", type=Path, default=Path("data/processed/hcl_pilot/emb.npz"))
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--max-hunks", type=int, default=MAX_HUNKS)
    ap.add_argument("--max-tokens", type=int, default=MAX_TOKENS)
    ap.add_argument("--fp16", action="store_true")
    a = ap.parse_args()
    if a.hunks:
        h = json.loads(gzip.decompress(a.hunks.read_bytes()))
    else:
        h = collect(a.diffs, a.max_hunks)
    if a.pack:
        a.pack.parent.mkdir(parents=True, exist_ok=True)
        a.pack.write_bytes(gzip.compress(json.dumps(h).encode()))
        print(f"Đã lưu {a.pack}")
    else:
        embed(h, a.out, a.batch, a.max_tokens, a.fp16)
