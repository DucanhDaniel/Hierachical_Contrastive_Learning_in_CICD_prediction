"""Cây nhãn 3 tầng (26/10/2026, chốt 2 artifact; docs/cay-nhan-3-tang-2026-10-25.md, theo góp ý GVHD 23/10):
  tầng 1 (artifact chứa lỗi)   du_an (mã + cấu hình build) | moi_truong (runner, mạng, secrets, thiết lập CI)
  tầng 2 (thời điểm cần sửa)   viet_code, build_local, ci_merge (thuộc du_an) | cau_hinh_ci, chay_lai (thuộc moi_truong)
  lá (loại lỗi)                bảng II Rausch + network, flaky; lá `infra` = infra_other (hạ tầng không rõ loại)
Mỗi cha có ≥ 2 con. Mỗi lá đúng một cha -> artifact và thời điểm suy thẳng từ lá; kiểm chứng ở lá (pipeline.leaf_review).

Cây theo nguyên nhân 22/10 (change/external → code/buildsys/ci_infra/flaky → lá) giữ ở CAUSE_GROUP / CAUSE_PARENT để
tái lập v8–v11 (`--tree cause`).

Lưu ở label_tree.json trong gói dữ liệu; `parent` gồm mọi lá có trong dữ liệu (kể cả lá bị bỏ vì ít mẫu).

    python -m project3.model.labels --data data/kaggle_log_ds   # ghi lại label_tree.json theo cây này (giữ bản cũ *_v1)
"""
import argparse
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

GROUP = {"viet_code": "du_an", "build_local": "du_an", "ci_merge": "du_an",
         "cau_hinh_ci": "moi_truong", "chay_lai": "moi_truong"}  # tầng 2 -> tầng 1
PARENT = {"compile": "viet_code", "quality": "viet_code", "doc": "viet_code", "buildconfig": "viet_code",
          "testfailure": "build_local", "license": "build_local", "compatibility": "build_local",
          "dependency": "build_local", "itestfailure": "ci_merge", "flaky": "ci_merge",
          "git": "cau_hinh_ci", "androidsdk": "cau_hinh_ci", "infra": "cau_hinh_ci",
          "network": "chay_lai", "crash": "chay_lai"}  # lá -> tầng 2

CAUSE_GROUP = {"code": "change", "buildsys": "change", "ci_infra": "external", "flaky": "external"}
CAUSE_PARENT = {"compile": "code", "testfailure": "code", "itestfailure": "code", "quality": "code", "doc": "code",
                "license": "code", "compatibility": "code", "buildconfig": "buildsys", "dependency": "buildsys",
                "network": "ci_infra", "git": "ci_infra", "crash": "ci_infra", "androidsdk": "ci_infra",
                "infra": "ci_infra", "flaky": "flaky"}
TREES = {"artifact": (GROUP, PARENT), "cause": (CAUSE_GROUP, CAUSE_PARENT)}
# loại tầng 2 của bộ quy tắc (crawl.build_log_labels.GROUP, nhãn người 10/10) -> tầng 2 của cây NGUYÊN NHÂN; với cây
# artifact loại `test` cũ tách sang hai cha (testfailure/itestfailure) nên không ánh xạ được ở tầng 2
RULE_L2 = {"compile": "code", "test": "code", "lint": "code", "buildconfig": "buildsys", "dependency": "buildsys",
           "infra": "ci_infra", "flaky": "flaky"}


@dataclass
class LabelTree:
    l1: list
    l2: list
    l3: list
    group: dict                      # loại tầng 2 -> nhóm tầng 1
    parent: dict                     # lá -> loại tầng 2
    extra: dict = field(default_factory=dict)  # min_leaf, dropped_leaves (chỉ để ghi lại)

    @classmethod
    def from_dict(cls, d: dict) -> "LabelTree":
        core = ("l1", "l2", "l3", "group", "parent")
        return cls(*(d[k] for k in core), extra={k: v for k, v in d.items() if k not in core})

    @classmethod
    def load(cls, path: Path) -> "LabelTree":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def to_dict(self) -> dict:
        return {"l1": self.l1, "l2": self.l2, "group": self.group, "l3": self.l3, "parent": self.parent, **self.extra}

    @classmethod
    def build(cls, group: dict, parent: dict, leaf_counts: dict, min_leaf: int) -> "LabelTree":
        """Cây từ nhóm tầng 2 (tầng 2 -> tầng 1), cha của lá và số run mỗi lá."""
        return cls(l1=list(dict.fromkeys(group.values())), l2=list(group), group=group,
                   l3=sorted(l for l, n in leaf_counts.items() if n >= min_leaf),
                   parent={l: parent.get(l, l) for l in leaf_counts},
                   extra={"min_leaf": min_leaf,
                          "dropped_leaves": {l: int(n) for l, n in leaf_counts.items() if n < min_leaf}})

    def tier2(self, leaf: str) -> str:
        return self.parent.get(leaf, leaf)

    def children(self) -> dict:
        """Loại tầng 2 -> chỉ số các lá con trong l3."""
        return {c: [i for i, l in enumerate(self.l3) if self.tier2(l) == c] for c in self.l2}

    def leaf_parent_index(self) -> list:
        """Chỉ số loại cha (trong l2) của từng lá trong l3."""
        return [self.l2.index(self.tier2(l)) for l in self.l3]


def leaf_of(label_l3, label_l2) -> str:
    """Lá của một run: label_l3, hoặc label_l2 khi loại đó không có lá (infra)."""
    return label_l3 if isinstance(label_l3, str) else label_l2


def retree(data: Path, min_leaf: int, tree_name: str = "artifact") -> LabelTree:
    """Ghi lại label_tree.json của một gói đã có theo cây hiện hành (lá giữ nguyên nên runs/TF-IDF dùng tiếp được)."""
    import pandas as pd
    data = Path(data)
    old = data / "label_tree.json"
    if old.exists() and not (data / "label_tree_v1.json").exists():
        shutil.copy(old, data / "label_tree_v1.json")
    counts = pd.read_parquet(data / "runs.parquet", columns=["leaf"]).leaf.value_counts().to_dict()
    group, parent = TREES[tree_name]
    missing = set(counts) - set(parent)
    if missing:
        raise SystemExit(f"lá không có trong cây: {missing}")
    tree = LabelTree.build(group, parent, counts, min_leaf)
    old.write_text(json.dumps(tree.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    return tree


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--min-leaf", type=int, default=50)
    ap.add_argument("--tree", choices=list(TREES), default="artifact")
    a = ap.parse_args()
    t = retree(a.data, a.min_leaf, a.tree)
    print("tầng 1", t.l1, "| tầng 2", t.l2, "| lá", t.l3, "| bỏ", t.extra["dropped_leaves"])
