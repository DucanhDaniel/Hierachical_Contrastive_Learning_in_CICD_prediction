"""Cây nhãn 3 tầng: tầng 1 (build/test/env) -> tầng 2 (7 loại) -> tầng 3 (lá đủ mẫu).

Lưu ở label_tree.json trong gói dữ liệu; `parent` gồm mọi lá có trong dữ liệu (kể cả lá bị bỏ vì ít mẫu),
lá không có cha (vd. infra) trỏ về chính nó.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path


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
        """Cây từ nhóm tầng 2 (build_log_labels.GROUP), cha của lá (fine_labels.PARENT) và số run mỗi lá."""
        return cls(l1=["build", "test", "env"], l2=list(group), group=group,
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
