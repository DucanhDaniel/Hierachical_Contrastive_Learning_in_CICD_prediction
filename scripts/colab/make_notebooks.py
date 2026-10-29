"""Sinh notebook Colab chạy 5 fold trên p3-log-data, đẩy kết quả lên dataset Kaggle riêng tư sau mỗi fold (28/10/2026).

    python scripts/colab/make_notebooks.py   # -> scripts/colab/p3_v10_oom.ipynb, p3_bert_oom.ipynb
"""
import json
from pathlib import Path

HERE = Path(__file__).parent

SETUP = r'''import os, json, subprocess
import pandas as pd
from google.colab import userdata
os.environ["KAGGLE_API_TOKEN"] = userdata.get("KAGGLE_API_TOKEN")
subprocess.run("pip install -q -U kaggle", shell=True)
D, OUT, SLUG = "/content/p3data", "/content/out", "__SLUG__"
os.makedirs(OUT, exist_ok=True)
r = subprocess.run(f"kaggle datasets download ducanhpham2k5/p3-log-data -p {D} --unzip", shell=True, capture_output=True, text=True)
print(r.stdout[-300:], r.stderr[-300:])
runs = pd.read_parquet(f"{D}/runs.parquet")
print(len(runs), "run | crash:", (runs.leaf == "crash").sum(), "| quality:", (runs.leaf == "quality").sum())
assert __CHECK__, "dataset vẫn là nhãn cũ: chờ bản p3-log-data mới"
json.dump({"title": SLUG, "id": f"ducanhpham2k5/{SLUG}", "licenses": [{"name": "other"}]},
          open(f"{OUT}/dataset-metadata.json", "w"))'''

RUN = r'''script = """
export PYTHONPATH=D/project3_code.pyz PYTHONIOENCODING=utf-8
up() { kaggle datasets version -p OUT -m "$1" -r zip -q || kaggle datasets create -p OUT -r zip -q; }
for f in __FOLDS__; do
  echo "=== fold $f $(date)" >> OUT/train.log
  __CMD__ >> OUT/train.log 2>&1 || echo "fold $f LOI" >> OUT/train.log
  up "fold $f" >> OUT/upload.log 2>&1
done
echo "XONG $(date)" >> OUT/train.log
""".replace("OUT", OUT).replace("D/", D + "/").replace("{D}", D)
open("/content/run.sh", "w").write(script)
proc = subprocess.Popen(["bash", "/content/run.sh"])
print("pid", proc.pid)'''

PROGRESS = r'''import re
log = open(f"{OUT}/train.log", encoding="utf-8", errors="replace").read().splitlines()
keep = [l for l in log if re.search(r"===|test full|test masked|epoch|step \d+000 |LOI|XONG|Traceback|Error", l)]
print("đang chạy" if proc.poll() is None else f"đã dừng, mã {proc.returncode}")
print("\n".join(keep[-15:]))
print(sorted(os.listdir(OUT)))'''


def notebook(name: str, title: str, slug: str, cmd: str, folds: str = "0 1 2 3 4",
             check: str = '(runs.leaf == "crash").sum() > 2900', gpu: str = "L4") -> Path:
    md = (f"# {title}\n\nDữ liệu: dataset Kaggle `ducanhpham2k5/p3-log-data` . Kết quả đẩy lên dataset "
          f"riêng tư `ducanhpham2k5/{slug}` sau mỗi fold.\n\nCần: Runtime GPU (L4), secret `KAGGLE_API_TOKEN` (biểu tượng "
          "chìa khoá). Chạy lần lượt các ô; ô 3 chạy nền, ô 4 xem tiến độ. Giữ tab mở đến khi log có dòng XONG.")
    code = ['import subprocess\nprint(subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv"], '
            'capture_output=True, text=True).stdout)',
            SETUP.replace("__SLUG__", slug).replace("__CHECK__", check), RUN.replace("__CMD__", cmd).replace("__FOLDS__", folds), PROGRESS]
    cells = [{"cell_type": "markdown", "metadata": {}, "source": md}] + [
        {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": c} for c in code]
    doc = {"cells": cells, "metadata": {"accelerator": "GPU", "colab": {"gpuType": gpu, "provenance": []},
                                        "kernelspec": {"name": "python3", "display_name": "Python 3"}},
           "nbformat": 4, "nbformat_minor": 0}
    p = HERE / name
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


V10 = ("python -m project3.model.train --data {D} --fold $f --variants soft --feats all --chunks error "
       "--max-tokens 512 --window 1600 --out OUT/results_fold$f.json")
# 29/10 chiều: nhãn 2026-10-29b-doc (doc tăng từ 197 lên ~320 run), 2 tab A100 song song
DOC_CHECK = '(runs.leaf == "doc").sum() > 280 and (runs.leaf == "crash").sum() > 3010'  # bản lỗi 17:31 có crash 3000

if __name__ == "__main__":
    print(notebook("p3_v10_doc_a.ipynb", "v10 soft: fold 0-2, nhãn 2026-10-29b-doc", "p3-colab-v10-doc-a", V10, "0 1 2", DOC_CHECK, "A100"))
    print(notebook("p3_v10_doc_b.ipynb", "v10 soft: fold 3-4, nhãn 2026-10-29b-doc", "p3-colab-v10-doc-b", V10, "3 4", DOC_CHECK, "A100"))
    print(notebook("p3_v10_oom.ipynb", "v10 soft: 5 fold, nhãn mới", "p3-colab-v10-oom",
                   "python -m project3.model.train --data {D} --fold $f --variants soft --feats all --chunks error "
                   "--max-tokens 512 --window 1600 --out OUT/results_fold$f.json"))
    print(notebook("p3_bert_oom.ipynb", "B2 BERT 512 token cuối (ICSE 2024 poster): 5 fold, nhãn mới", "p3-colab-bert-oom",
                   "mkdir -p OUT/fold$f && python -m project3.model.ladder --data {D} --out OUT/fold$f --models bert "
                   "--folds $f"))
