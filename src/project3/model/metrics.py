"""Chỉ số đánh giá theo cây nhãn."""
import numpy as np
from sklearn.metrics import f1_score


def hier_scores(true_leaf, pred_leaf, parent: dict, group: dict) -> dict:
    """acc + macro-F1 ở lá, tầng 2, tầng 1. Dự đoán ngoài cây (vd. '?' của quy tắc) tính là sai ở mọi tầng.
    macro-F1 lấy trung bình trên các nhãn có trong tập đúng."""
    t2 = [parent.get(x, x) for x in true_leaf]
    p2 = [parent.get(x, x) if x in parent or x in group else "?" for x in pred_leaf]
    t1, p1 = [group[x] for x in t2], [group.get(x, "?") for x in p2]
    labels3 = sorted(set(true_leaf))
    return {"n": len(true_leaf), "acc_l3": float(np.mean(np.array(true_leaf) == np.array(pred_leaf))),
            "macroF1_l3": f1_score(true_leaf, pred_leaf, labels=labels3, average="macro", zero_division=0),
            "macroF1_l2": f1_score(t2, p2, labels=sorted(set(t2)), average="macro", zero_division=0),
            "macroF1_l1": f1_score(t1, p1, labels=sorted(set(t1)), average="macro", zero_division=0),
            "F1_l3": dict(zip(labels3, map(float, f1_score(true_leaf, pred_leaf, labels=labels3, average=None,
                                                            zero_division=0))))}
