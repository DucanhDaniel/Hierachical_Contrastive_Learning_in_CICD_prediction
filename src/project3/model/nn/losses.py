"""Loss so sánh theo cây nhãn và bộ nhớ đặc trưng.

lab có 3 cột (tầng 1, tầng 2, lá); lá -1 = lá bị bỏ vì ít mẫu (không học ở tầng 3).
"""
import numpy as np
import torch
import torch.nn.functional as F


def class_weights(y: torch.Tensor, idx: np.ndarray, k: int) -> torch.Tensor:
    """Căn bậc hai nghịch tần suất trên tập train (chỉ số idx), chuẩn hoá trung bình 1; bỏ nhãn -1."""
    c = np.bincount(y[idx][y[idx] >= 0].cpu().numpy(), minlength=k).astype(float)
    w = np.sqrt(c.sum() / (k * np.maximum(c, 1)))
    return torch.tensor(w / w.mean(), dtype=torch.float32, device=y.device)


class MemoryBank:
    """Đặc trưng + nhãn của các batch trước (mới nhất ở đầu), dùng làm mẫu so sánh thêm."""

    def __init__(self, size: int, dim: int, levels: int, device):
        self.size = size
        self.feat = torch.zeros(0, dim, device=device)
        self.lab = torch.zeros(0, levels, dtype=torch.long, device=device)

    def get(self, step: int, warmup: int):
        k = len(self.feat) if step >= warmup else 0
        return self.feat[:k], self.lab[:k]

    def push(self, feat: torch.Tensor, lab: torch.Tensor) -> None:
        self.feat = torch.cat([feat.detach(), self.feat])[:self.size]
        self.lab = torch.cat([lab, self.lab])[:self.size]


def _self_mask(sim: torch.Tensor, n: int) -> torch.Tensor:
    m = torch.zeros_like(sim, dtype=torch.bool)
    m[:, :n] = torch.eye(n, dtype=torch.bool, device=sim.device)
    return m


def supcon_mem(feat, lab, mfeat, mlab, tau: float):
    """SupCon một tầng (lab 1 chiều), so với batch + bộ nhớ; bỏ nhãn -1."""
    keys, kl = torch.cat([feat, mfeat]), torch.cat([lab, mlab])
    n = len(lab)
    sim = feat @ keys.T / tau
    self_ = _self_mask(sim, n)
    sim = sim.masked_fill(self_ | (kl < 0)[None, :], -1e9)
    logp = sim - torch.logsumexp(sim, 1, keepdim=True)
    pos = (lab[:, None] == kl[None, :]) & (kl >= 0)[None, :] & ~self_
    ok = (lab >= 0) & (pos.sum(1) > 0)
    if not ok.any():
        return feat.sum() * 0
    return -((logp * pos).sum(1)[ok] / pos.sum(1)[ok]).mean()


def hcl_loss(feat, lab, mfeat, mlab, tau: float):
    """HCL: tổng SupCon của 3 tầng."""
    return sum(supcon_mem(feat, lab[:, lv], mfeat, mlab[:, lv], tau) for lv in range(lab.shape[1]))


def soft_supcon_mem(feat, lab, mfeat, mlab, tau: float, sib_w, hard=None, hard_w: float = 1.0):
    """SupCon một loss, trọng số dương theo cây: cùng lá 1, cùng cha khác lá sib_w (lá -1 coi theo tầng 2), khác 0.
    sib_w: số, hoặc tensor theo loại tầng 2 của anchor. hard: ma trận bool [lá, lá] cặp dễ nhầm; mẫu âm thuộc cặp đó
    được tính hard_w lần trong mẫu số (phạt mạnh hơn)."""
    keys, kl = torch.cat([feat, mfeat]), torch.cat([lab, mlab])
    n = len(lab)
    sim = feat @ keys.T / tau
    self_ = _self_mask(sim, n)
    sim = sim.masked_fill(self_, -1e9)
    same3 = (lab[:, None, 2] == kl[None, :, 2]) & (lab[:, None, 2] >= 0)
    same2 = lab[:, None, 1] == kl[None, :, 1]
    if hard is not None:
        a3, k3 = lab[:, 2].clamp(min=0), kl[:, 2].clamp(min=0)
        hn = hard[a3][:, k3] & (lab[:, None, 2] >= 0) & (kl[None, :, 2] >= 0) & ~same3
        sim_den = sim + hn.float() * float(np.log(hard_w))
    else:
        sim_den = sim
    logp = sim - torch.logsumexp(sim_den, 1, keepdim=True)
    sw = sib_w[lab[:, 1]][:, None] if torch.is_tensor(sib_w) else sib_w
    w = torch.where(same3, 1.0, torch.where(same2, sw, 0.0)).masked_fill(self_, 0.0)
    ok = w.sum(1) > 0
    if not ok.any():
        return feat.sum() * 0
    return -((logp * w).sum(1)[ok] / w.sum(1)[ok]).mean()


def instance_nce(feat, views: int, tau: float):
    """InfoNCE theo run (SimCLR/KnowLog): batch = [góc nhìn 1 của n run, góc nhìn 2, ...]; dương = góc nhìn khác của cùng run."""
    n = len(feat) // views
    sim = (feat @ feat.T / tau).masked_fill(torch.eye(len(feat), dtype=torch.bool, device=feat.device), -1e9)
    pos = torch.arange(len(feat), device=feat.device) % n
    same = (pos[:, None] == pos[None, :]) & ~torch.eye(len(feat), dtype=torch.bool, device=feat.device)
    logp = sim - torch.logsumexp(sim, 1, keepdim=True)
    return -((logp * same).sum(1) / same.sum(1)).mean()


def proxy_loss(feat, lab, proxy_parent, proxy_delta, leaf_parent, tau: float, parent_w: float):
    """Kéo run về nguyên mẫu lá (= nguyên mẫu cha + độ lệch; softmax trên mọi lá) + nguyên mẫu cha (trọng số parent_w)."""
    pl = F.normalize(proxy_parent[leaf_parent] + proxy_delta, dim=1)
    pp = F.normalize(proxy_parent, dim=1)
    loss = parent_w * F.cross_entropy(feat @ pp.T / tau, lab[:, 1])
    if (lab[:, 2] >= 0).any():
        loss = loss + F.cross_entropy(feat @ pl.T / tau, lab[:, 2], ignore_index=-1)
    return loss
