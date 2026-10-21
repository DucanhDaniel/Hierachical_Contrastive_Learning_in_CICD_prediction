"""Chọn batch huấn luyện (chỉ số run)."""
import numpy as np


def random_batches(rng: np.random.Generator, tr: np.ndarray, batch: int):
    order = rng.permutation(tr)
    yield from (order[i:i + batch] for i in range(0, len(order), batch))


class MPCSampler:
    """Batch = batch/2 lá x 2 run, lá chọn theo xác suất ~ căn bậc hai số run train; SupCon luôn có cặp dương."""

    def __init__(self, tr: np.ndarray, leaf: np.ndarray):
        leaf_tr = leaf[tr]
        self.pools = {l: tr[leaf_tr == l] for l in np.unique(leaf_tr)}
        self.leaves = np.array(list(self.pools))
        w = np.sqrt([len(self.pools[l]) for l in self.leaves])
        self.p = w / w.sum()
        self.n_train = len(tr)

    def __call__(self, rng: np.random.Generator, batch: int):
        k = max(1, batch // 2)
        for _ in range(self.n_train // batch):
            pick = rng.choice(len(self.leaves), size=min(k, len(self.leaves)), replace=False, p=self.p)
            yield np.concatenate([rng.choice(self.pools[self.leaves[c]], size=2, replace=len(self.pools[self.leaves[c]]) < 2)
                                  for c in pick])
