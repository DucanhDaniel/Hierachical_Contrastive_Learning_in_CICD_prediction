import torch


def seg_softmax_pool(x: torch.Tensor, score: torch.Tensor, seg: torch.Tensor, n: int):
    """Attention pooling theo nhóm: phần tử i thuộc nhóm seg[i]; softmax của score trong từng nhóm.
    Trả về (vector gộp của n nhóm, trọng số của từng phần tử trong nhóm)."""
    x, score = x.float(), score.float()
    mx = torch.full((n,), -1e9, device=x.device).scatter_reduce(0, seg, score, "amax")
    e = torch.exp(score - mx[seg])
    s = torch.zeros(n, device=x.device).index_add(0, seg, e)
    w = e / s[seg]
    return torch.zeros(n, x.shape[1], device=x.device).index_add(0, seg, w.unsqueeze(1) * x), w
