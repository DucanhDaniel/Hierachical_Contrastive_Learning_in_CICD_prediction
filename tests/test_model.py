"""Phần lõi của project3.model: cây nhãn, metric, văn bản, chia fold, loss, sampler, đóng gói mã."""
import ast
import tempfile
import unittest
import zipfile
from pathlib import Path

import numpy as np

from project3.model import kaggle, llm
from project3.model.data import fold_split, mix50, train_folds
from project3.model.labels import LabelTree, leaf_of
from project3.model.metrics import hier_scores
from project3.model.pack import bundle_code
from project3.model.text import clip_chunk, mask_text

TREE = LabelTree.from_dict({
    "l1": ["build", "test", "env"], "l2": ["compile", "test", "infra"],
    "group": {"compile": "build", "test": "test", "infra": "env"},
    "l3": ["javac", "kotlinc", "testfailure"],
    "parent": {"javac": "compile", "kotlinc": "compile", "testfailure": "test", "infra": "infra", "rare": "test"},
    "min_leaf": 50})


class LabelTreeTest(unittest.TestCase):
    def test_structure(self):
        self.assertEqual(TREE.children(), {"compile": [0, 1], "test": [2], "infra": []})
        self.assertEqual(TREE.leaf_parent_index(), [0, 0, 1])
        self.assertEqual(TREE.tier2("rare"), "test")
        self.assertEqual(TREE.to_dict()["min_leaf"], 50)
        self.assertEqual(leaf_of(float("nan"), "infra"), "infra")

    def test_build_drops_rare_leaves(self):
        t = LabelTree.build({"compile": "build", "test": "test"}, {"javac": "compile", "rare": "test"},
                            {"javac": 80, "rare": 3}, min_leaf=50)
        self.assertEqual(t.l3, ["javac"])
        self.assertEqual(t.parent["rare"], "test")
        self.assertEqual(t.extra["dropped_leaves"], {"rare": 3})


class MetricsTest(unittest.TestCase):
    def test_unknown_prediction_is_wrong_at_every_level(self):
        s = hier_scores(["javac", "kotlinc", "testfailure"], ["kotlinc", "?", "testfailure"], TREE.parent, TREE.group)
        self.assertAlmostEqual(s["acc_l3"], 1 / 3)
        self.assertAlmostEqual(s["macroF1_l2"], (2 / 3 + 1) / 2)  # compile: P=1, R=1/2; test: 1
        self.assertEqual(s["n"], 3)


class TextTest(unittest.TestCase):
    def test_mask_and_clip(self):
        self.assertEqual(mask_text("a\nERROR x\nb", "ERROR x"), "a\nb")
        self.assertEqual(mask_text("a\nb", ""), "a\nb")
        c = clip_chunk("head\n" + "y" * 2000, n=10)
        self.assertEqual(c, "head\n" + "y" * 10)


class SplitTest(unittest.TestCase):
    def test_fold_split(self):
        folds = np.array([0, 1, 2, 3, 4, 0, 1])
        tr, va, te = fold_split(folds, 4)
        self.assertEqual(te.tolist(), [4])
        self.assertEqual(va.tolist(), [0, 5])  # val = fold 0 khi test = 4
        self.assertEqual(tr.tolist(), [1, 2, 3, 6])
        self.assertEqual(train_folds(4), [1, 2, 3])

    def test_mix50_deterministic(self):
        a = mix50(range(1000))
        self.assertEqual(a, mix50(range(1000)))
        self.assertTrue(400 < sum(a.values()) < 600)


class TorchTest(unittest.TestCase):
    def setUp(self):
        try:
            import torch  # noqa: F401
        except ImportError:
            self.skipTest("không có torch")

    def test_losses_and_memory(self):
        import torch
        import torch.nn.functional as F
        from project3.model.nn.losses import MemoryBank, hcl_loss, soft_supcon_mem, supcon_mem
        torch.manual_seed(0)
        feat = F.normalize(torch.randn(6, 8), dim=1)
        lab = torch.tensor([[0, 0, 0], [0, 0, 0], [0, 0, 1], [1, 1, 2], [1, 1, 2], [1, 1, -1]])
        empty_f, empty_l = torch.zeros(0, 8), torch.zeros(0, 3, dtype=torch.long)
        for loss in (supcon_mem(feat, lab[:, 2], empty_f, empty_l[:, 2], 0.1), hcl_loss(feat, lab, empty_f, empty_l, 0.1),
                     soft_supcon_mem(feat, lab, empty_f, empty_l, 0.1, 0.4)):
            self.assertTrue(torch.isfinite(loss) and loss > 0)
        # không có cặp dương nào -> 0
        self.assertEqual(float(supcon_mem(feat[:2], torch.tensor([0, 1]), empty_f, empty_l[:, 0], 0.1)), 0.0)
        mem = MemoryBank(4, 8, 3, "cpu")
        self.assertEqual(len(mem.get(0, 0)[0]), 0)
        mem.push(feat, lab)
        self.assertEqual(len(mem.get(10, 50)[0]), 0)  # chưa hết warmup
        self.assertTrue(torch.equal(mem.get(60, 50)[1], lab[:4]))

    def test_mpc_sampler_gives_pairs(self):
        from project3.model.nn.samplers import MPCSampler
        tr = np.arange(40)
        leaf = np.array(["a"] * 30 + ["b"] * 9 + ["c"])
        batches = list(MPCSampler(tr, leaf)(np.random.default_rng(0), 6))
        self.assertEqual(len(batches), 40 // 6)
        for b in batches:
            self.assertEqual(len(b), 6)
            _, counts = np.unique(leaf[b], return_counts=True)
            self.assertTrue((counts % 2 == 0).all())


class PackagingTest(unittest.TestCase):
    def test_bundle_contains_model_package(self):
        with tempfile.TemporaryDirectory() as d:
            names = zipfile.ZipFile(bundle_code(Path(d))).namelist()
        for f in ("project3/__init__.py", "project3/model/train.py", "project3/model/nn/net.py"):
            self.assertIn(f, names)

    def test_kernel_config_substitution(self):
        with tempfile.TemporaryDirectory() as d:
            old, kaggle.OUT = kaggle.OUT, Path(d)
            try:
                k = kaggle.make_kernel("p3-test", [1], ["soft"], ["--tfidf"], 5.0, "NvidiaTeslaT4")
            finally:
                kaggle.OUT = old
            text = (k / "run.py").read_text(encoding="utf-8")
            self.assertIn('CONFIG = {"folds": [1], "variants": ["soft"], "budget_h": 5.0, "extra": ["--tfidf"]}', text)
            ast.parse(text)

    def test_llm_task_leaves_match(self):
        for f in Path("scripts/kaggle/llm_baseline").glob("task*.py"):
            tree = ast.parse(f.read_text(encoding="utf-8"))
            leaves = next(ast.literal_eval(n.value) for n in tree.body
                          if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "LEAVES")
            self.assertEqual(leaves, llm.LEAVES, f.name)


if __name__ == "__main__":
    unittest.main()
