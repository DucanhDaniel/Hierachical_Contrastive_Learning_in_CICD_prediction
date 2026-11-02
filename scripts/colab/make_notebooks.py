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
keep = [l for l in log if re.search(r"===|cấu hình|test full|test masked|epoch|step \d+000 |LOI|XONG|Traceback|Error", l)]
print("đang chạy" if proc.poll() is None else f"đã dừng, mã {proc.returncode}")
print("\n".join(keep[-15:]))
print(sorted(os.listdir(OUT)))'''


CODE_SETUP = r'''
r = subprocess.run("kaggle datasets download ducanhpham2k5/p3-code -p /content/p3code --unzip --force", shell=True,
                   capture_output=True, text=True)
import zipfile
print("mã mới:", len(zipfile.ZipFile("/content/p3code/project3_code.pyz").namelist()), "file")'''


def notebook(name: str, title: str, slug: str, cmd: str, folds: str = "0 1 2 3 4",
             check: str = '(runs.leaf == "crash").sum() > 2900', gpu: str = "L4", code: bool = False,
             extra: dict = None) -> Path:
    """code=True: lấy mã từ dataset p3-code (cập nhật mã không cần upload lại p3-log-data).
    extra: {dataset: thư mục} các dataset Kaggle tải thêm (vd. gói run `?`, weight đã lưu)."""
    md = (f"# {title}\n\nDữ liệu: dataset Kaggle `ducanhpham2k5/p3-log-data` . Kết quả đẩy lên dataset "
          f"riêng tư `ducanhpham2k5/{slug}` sau mỗi fold.\n\nCần: Runtime GPU (L4), secret `KAGGLE_API_TOKEN` (biểu tượng "
          "chìa khoá). Chạy lần lượt các ô; ô 3 chạy nền, ô 4 xem tiến độ. Giữ tab mở đến khi log có dòng XONG.")
    code = ['import subprocess\nprint(subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv"], '
            'capture_output=True, text=True).stdout)',
            SETUP.replace("__SLUG__", slug).replace("__CHECK__", check) + (CODE_SETUP if code else "")
            + "".join(f'\nprint(subprocess.run("kaggle datasets download ducanhpham2k5/{k} -p {v} --unzip", shell=True, '
                      f'capture_output=True, text=True).stdout[-200:])' for k, v in (extra or {}).items()),
            (RUN.replace("D/project3_code.pyz", "/content/p3code/project3_code.pyz") if code else RUN)
            .replace("__CMD__", cmd).replace("__FOLDS__", folds), PROGRESS]
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
    # seed 0 trên A100 lệch ±0.08/fold so với lần chạy T4 -> thêm seed 1 để lấy trung bình
    V10_S1 = V10.replace("--out", "--seed-start 1 --out")
    print(notebook("p3_v10_doc_s1_a.ipynb", "v10 soft seed 1: fold 0-2, nhãn 2026-10-29b-doc", "p3-colab-v10-doc-s1-a", V10_S1, "0 1 2", DOC_CHECK, "A100"))
    print(notebook("p3_v10_doc_s1_b.ipynb", "v10 soft seed 1: fold 3-4, nhãn 2026-10-29b-doc", "p3-colab-v10-doc-s1-b", V10_S1, "3 4", DOC_CHECK, "A100"))
    # 30/10: kiểm chứng attention có chỉ đúng đoạn log chứa dòng bằng chứng không -> lưu attention từng đoạn
    V10_ATTN = V10_S1.replace("--out", "--save-repr --repr-train 500 --out")
    print(notebook("p3_v10_attn_a.ipynb", "v10 seed 1 + attention: fold 0", "p3-colab-v10-attn-a", V10_ATTN, "0", DOC_CHECK, "A100"))
    # 30/10 chiều: chạy thử 3 cấu hình (A cửa sổ chia đôi, C + điểm từng dòng + loss chỉ dòng lỗi, B chỉ điểm từng dòng)
    TRAIN = ("python -m project3.model.train --data {D} --fold $f --variants soft --feats all --chunks error "
             "--max-tokens 512 --window 1600 --seed-start 1 --window-mode split")
    LINES = (TRAIN + " --smoke --epochs 1 --max-steps 5 --val-max 40 --line-attn --ev-loss 0.5 --out OUT/smoke.json "
             ">> OUT/train.log 2>&1 && for c in A C B; do case $c in A) X='';; B) X='--line-attn';; "
             "C) X='--line-attn --ev-loss 0.5';; esac; echo \"--- cấu hình $c\" >> OUT/train.log; "
             + TRAIN + " --save-repr --repr-train 500 $X --out OUT/${c}_fold$f.json >> OUT/train.log 2>&1; "
             "up \"$c fold $f\" >> OUT/upload.log 2>&1; done")
    print(notebook("p3_v10_lines_a.ipynb", "Thử cửa sổ chia đôi + điểm từng dòng: fold 0 (A, C, B)", "p3-colab-v10-lines-a",
                   LINES, "0", DOC_CHECK, "A100", code=True))
    print(notebook("p3_v10_lines_b.ipynb", "Thử cửa sổ chia đôi + điểm từng dòng: fold 3 (A, C, B)", "p3-colab-v10-lines-b",
                   LINES, "3", DOC_CHECK, "A100", code=True))
    # 30/10 tối: cấu hình C thắng pilot -> chạy đủ 5 fold x 2 seed (seed 1 fold 0, 3 đã có từ pilot); f = "seed:fold"
    FULL_C = ("s=${f%%:*}; k=${f##*:}; " + TRAIN.replace("--fold $f", "--fold $k").replace("--seed-start 1", "--seed-start $s")
              + " --line-attn --ev-loss 0.5 --save-repr --repr-train 500 --out OUT/C_s${s}_fold$k.json")
    print(notebook("p3_v10_c_a.ipynb", "v10 cấu hình C (chia đôi + điểm dòng + loss dòng): seed 1 fold 1, 2, 4 + seed 0 fold 0",
                   "p3-colab-v10-c-a", FULL_C, "1:1 1:2 1:4 0:0", DOC_CHECK, "A100", code=True))
    print(notebook("p3_v10_c_b.ipynb", "v10 cấu hình C (chia đôi + điểm dòng + loss dòng): seed 0 fold 1-4",
                   "p3-colab-v10-c-b", FULL_C, "0:1 0:2 0:3 0:4", DOC_CHECK, "A100", code=True))
    # 01/11: MC Dropout (Gal & Ghahramani 2016) trên weight C seed 0 đã lưu, không train lại: đoán lại 20 lần khi bật
    # dropout cho 120 run `?` người gán + 500 run test có nhãn quy tắc mỗi fold
    MC = (TRAIN.replace("--seed-start 1", "--seed-start 0") + " --line-attn --ev-loss 0.5 --unknown /content/p3unk "
          "--load-model /content/p3w/C_s0_fold{fold}.model_soft0.pt --mc 20 --mc-ids /content/p3w/mc_ids.json "
          "--mc-sub 500 --out OUT/MC_fold$f.json")
    print(notebook("p3_mc.ipynb", "MC Dropout trên mô hình HCL bản cuối (weight C seed 0, không train lại): 5 fold",
                   "p3-colab-mc", MC, "0 1 2 3 4", DOC_CHECK, "L4", code=True,
                   extra={"p3-unknown-data": "/content/p3unk", "p3-c-weights": "/content/p3w"}))
    print(notebook("p3_v10_attn_b.ipynb", "v10 seed 1 + attention: fold 3", "p3-colab-v10-attn-b", V10_ATTN, "3", DOC_CHECK, "A100"))
    print(notebook("p3_v10_oom.ipynb", "v10 soft: 5 fold, nhãn mới", "p3-colab-v10-oom",
                   "python -m project3.model.train --data {D} --fold $f --variants soft --feats all --chunks error "
                   "--max-tokens 512 --window 1600 --out OUT/results_fold$f.json"))
    print(notebook("p3_bert_oom.ipynb", "B2 BERT 512 token cuối (ICSE 2024 poster): 5 fold, nhãn mới", "p3-colab-bert-oom",
                   "mkdir -p OUT/fold$f && python -m project3.model.ladder --data {D} --out OUT/fold$f --models bert "
                   "--folds $f"))
