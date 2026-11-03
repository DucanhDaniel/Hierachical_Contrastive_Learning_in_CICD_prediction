"""Đóng gói demo cho Colab (03/11/2026): dataset Kaggle riêng tư ducanhpham2k5/p3-demo. Chỉ CPU, không chạy mô hình.

  label_tree.json, norm.json (trung bình / độ lệch đặc trưng theo tập train của từng fold, như model.train.load_feats),
  repo_fold.json (repo -> fold của dữ liệu), config.json (ngưỡng entropy MC Dropout, fold mặc định cho repo mới),
  examples/*.json.gz (run mẫu: log lấy từ dữ liệu crawl ở máy nên chạy được cả khi log GitHub đã hết hạn),
  p3demo_code.zip (src/project3 + configs/label_rules.json). Weight lấy từ dataset p3-c-weights.

    python -m project3.demo.export        # -> data/demo_bundle/ rồi: kaggle datasets version -p data/demo_bundle -r zip
"""
import gzip
import json
import shutil
import sys
import zipfile
from pathlib import Path

import pandas as pd

from project3.model.config import PACK
from project3.model.data import fold_split
from project3.model.train import load_feats
from .check import UNK, local_record

OUT = Path("data/demo_bundle")
DEFAULT_FOLD = 3  # macro-F1 lá cao nhất trong 5 mô hình seed 0 (0,813)
EXAMPLES = {  # run_id -> mô tả ngắn hiện trên giao diện
    30617913741: "quy tắc không gán được, lỗi SpotBugs",
    32067356556: "quy tắc không gán được, lỗi git",
    29479365127: "quy tắc không gán được, mô hình không chắc",
    30343630798: "lỗi không phải do build (kiểm tra changelog)",
    31179342930: "quy tắc gán được: lỗi biên dịch",
    30110353847: "quy tắc gán được: unit test lỗi",
}


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "examples").mkdir(parents=True)
    shutil.copy(PACK / "label_tree.json", OUT)
    runs = pd.read_parquet(PACK / "runs.parquet")  # như model.train.main: không khử trùng trước khi tính chuẩn hoá
    norm = {}
    for k in range(5):
        _, (mu, sd) = load_feats(PACK / "features.parquet", runs, "all", fold_split(runs.repo_fold.values, k)[0])
        norm[k] = {"mu": mu.tolist(), "sd": sd.tolist()}
    (OUT / "norm.json").write_text(json.dumps(norm))
    unk = pd.read_parquet(UNK / "runs.parquet")
    both = pd.concat([runs, unk])
    (OUT / "repo_fold.json").write_text(json.dumps(both.drop_duplicates("repository").set_index("repository")
                                                   .repo_fold.astype(int).to_dict()))
    mc = json.loads(Path("data/results/mc/summary.json").read_text(encoding="utf-8"))
    thr = -mc["run ?, sau rà lại"]["ngưỡng_cv"]["MC −entropy"]["thr_median"]  # điểm = −entropy
    (OUT / "config.json").write_text(json.dumps({"thr_entropy": thr, "default_fold": DEFAULT_FOLD, "mc_passes": 20}))
    feats = pd.concat([pd.read_parquet(p / "features.parquet") for p in (PACK, UNK)]).drop_duplicates("run_id").set_index("run_id")
    meta = both.drop_duplicates("run_id").set_index("run_id")
    for rid, note in EXAMPLES.items():
        r = meta.loc[rid]
        rec = local_record(r.repository, rid, r.event)
        rec.update(url=f"https://github.com/{r.repository}/actions/runs/{rid}", note=note,
                   diff={"vector": [float(v) for v in feats.loc[rid, "diff"]]})
        (OUT / "examples" / f"{rid}.json.gz").write_bytes(gzip.compress(json.dumps(rec).encode("utf-8")))
    with zipfile.ZipFile(OUT / "p3demo_code.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(Path("src/project3").rglob("*")):
            if f.suffix in (".py", ".html", ".json") and "__pycache__" not in f.parts:
                z.write(f, f.as_posix())
        z.write("configs/label_rules.json")
    (OUT / "dataset-metadata.json").write_text(json.dumps(
        {"title": "p3-demo", "id": "ducanhpham2k5/p3-demo", "licenses": [{"name": "other"}]}))
    print(f"-> {OUT}: ngưỡng entropy {thr:.3f}, {len(EXAMPLES)} run mẫu, "
          f"{sum(f.stat().st_size for f in OUT.rglob('*') if f.is_file()) / 1e6:.1f} MB")


SETUP = r'''import os, sys, glob, subprocess, zipfile
from google.colab import userdata
os.environ["KAGGLE_API_TOKEN"] = userdata.get("KAGGLE_API_TOKEN")
subprocess.run("pip install -q -U kaggle gradio pyngrok duckdb", shell=True)
for ds, d in [("p3-demo", "/content/p3demo"), ("p3-c-weights", "/content/p3w"), ("p3-gh-token", "/content/p3tok")]:
    r = subprocess.run(f"kaggle datasets download ducanhpham2k5/{ds} -p {d} --unzip --force", shell=True,
                       capture_output=True, text=True)
    print(ds, r.stdout[-120:], r.stderr[-200:])
for z in glob.glob("/content/p3demo/*.zip"):  # Kaggle thường tự giải nén; nếu chưa thì giải nén ở đây
    zipfile.ZipFile(z).extractall("/content/p3demo/" + os.path.basename(z)[:-4])
sys.path.insert(0, "/content/p3demo/p3demo_code/src")
os.environ["GITHUB_TOKEN"] = open(glob.glob("/content/p3tok/**/gh_token.txt", recursive=True)[0]).read().strip()
print(sorted(os.listdir("/content/p3demo")), sorted(os.listdir("/content/p3w")))'''

LAUNCH = r'''from project3.demo.app import launch
url = launch("/content/p3demo", "/content/p3w/C_s0_fold{fold}.model_soft0.pt", ngrok_token=userdata.get("NGROK_AUTHTOKEN"))
print("Mở demo tại:", url)'''

CHECK = r'''# kiểm tra nhanh: dự đoán 6 run mẫu (không qua giao diện)
from project3.demo.app import load_examples
from project3.demo.predict import Predictor
p = Predictor("/content/p3demo", "/content/p3w/C_s0_fold{fold}.model_soft0.pt")
for rid, (note, rec) in load_examples("/content/p3demo").items():
    o = p.predict(rec)
    print(rid, note, "->", o["pred"]["leaf"], f'{o["pred"]["p_leaf"]:.3f}', "| entropy", round(o["mc"]["entropy"], 2),
          "| trả lời" if o["mc"]["answered"] else "| không chắc", "| dòng 1:", o["lines"][0]["text"][:80], f'({o["seconds"]}s)')'''


def notebook(path: Path = Path("scripts/colab/p3_demo.ipynb")) -> None:
    md = ("# Demo: phân loại nguyên nhân lỗi build CI\n\nCần: Runtime GPU (T4 là đủ), secret `KAGGLE_API_TOKEN` và "
          "`NGROK_AUTHTOKEN` (biểu tượng chìa khoá). Chạy lần lượt các ô; ô 3 in link ngrok để mở demo. Giữ tab mở trong "
          "lúc demo; xong thì Runtime → Disconnect and delete runtime để không tốn compute unit.")
    cells = [{"cell_type": "markdown", "metadata": {}, "source": md}] + [
        {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": c}
        for c in ('import subprocess\nprint(subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv"], '
                  'capture_output=True, text=True).stdout)', SETUP, LAUNCH, CHECK)]
    doc = {"cells": cells, "metadata": {"accelerator": "GPU", "colab": {"gpuType": "T4", "provenance": []},
                                        "kernelspec": {"name": "python3", "display_name": "Python 3"}},
           "nbformat": 4, "nbformat_minor": 0}
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print("->", path)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
    notebook()
