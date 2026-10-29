"""Nhãn tầng 3 cho HCL: từ dòng bằng chứng trong log (gold_labels.csv) suy ra loại lỗi của commit fail.

  subtype (tầng 3) = đúng tập nhãn bảng II của Rausch et al. (MSR 2017), cộng 2 lá đề tài thêm; mỗi lá thuộc đúng một nhãn tầng 2
  (người quyết 16/10/2026: chấp nhận mất dạng lỗi chi tiết để tập nhãn bám sát paper gốc):
      test        -> itestfailure (integration/e2e/cluster) | testfailure (test tự động khác không đạt)
      compile     -> compile        buildconfig -> buildconfig        dependency -> dependency
      lint        -> doc (javadoc) | license (rat, header) | compatibility (revapi, japicmp) | quality (còn lại: format,
                     checkstyle, pmd, spotbugs, detekt... vi phạm quy tắc khi kiểm tra code)
      infra       -> git (tương tác VCS) | androidsdk | crash (môi trường sập, hết tài nguyên, quá thời gian)
                     | network (đề tài thêm: lỗi do mạng, dịch vụ ngoài không truy cập được)
      flaky       -> flaky (đề tài thêm: test không ổn định, chạy lại thì đạt)
  Không dùng: unknown (đã là `?` ở tầng 2), buildout (riêng Crate.IO). Infra không khớp nhánh nào (vd. lỗi xác thực) để trống.
  module : module bị lỗi ("on project X" của Maven, ":a:b:task" của Gradle, hoặc thư mục cấp đầu của file lỗi)

Một commit có thể có nhiều run fail: lấy các run mang đúng loại lỗi của commit (cột label trong commits_all),
chọn subtype/module xuất hiện nhiều nhất.

    uv run --group exp python -m project3.crawl.fine_labels --out data/processed/fine_labels.parquet
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from project3.crawl.gold_labels import DOC_KINDS

ROOTS = [Path("data/validate"), Path("data/crawl_pr")]

LINT = [("doc", r"\.java:\d+: error: (?:" + DOC_KINDS + r")|javadoc"),
        ("license", r"rat|Rat check|Unapproved|license|copyright"),
        ("compatibility", r"revapi|japicmp|incompatibilit|metalava|BreakingChanges")]
# 26/10/2026 (người duyệt sau kiểm chứng 161 run, pipeline.leaf_review): khoá kho Maven cục bộ không phải git (-> infra
# khác); lỗi mạng rõ ràng (timeout đọc, tải action fail, handshake) xét trước androidsdk/crash; adb/cổng emulator là
# androidsdk; Connection refused tới localhost là dịch vụ/container của test không lên -> infra khác, không phải mạng.
INFRA = [("git", r"fatal: |/usr/bin/git' failed|unable to access 'https://github|failed to push some refs|upload-pack|"
                 r"could not read Username"),
         ("network", r"Failed to download action|ReadTimeout|SocketTimeout|Read timed out|connect timed out|"
                     r"ConnectTimeout|Remote host terminated the handshake|Primary download failed"),
         ("androidsdk", r"android sdk|sdkmanager|ANDROID_(?:HOME|SDK)|avdmanager|emulator|"
                        r"licenses? (?:have|has) not been accepted|TCP port 55\d\d|\badb\b"),
         ("crash", r"runner has received a shutdown|lost communication with the server|heap space|OutOfMemory|"
                   r"GC overhead|unable to create (?:new )?native thread|forked VM terminated|"
                   r"VM crash|No space left|exit code 137|Killed|GC overhead|Cannot allocate memory|timed? ?out|timeout|"
                   r"exceeded the maximum execution time|partial results|fatal error has been detected|operation was canceled"),
         ("network", r"Connection (?:refused|reset)|SocketTimeout|Service Unavailable|status code:? ?5\d\d|50[234]|"
                     r"Could not transfer|Failed to (?:download|fetch|resolve action)|Docker pull failed|"
                     r"Temporary failure in name resolution|UnknownHost|Premature end|rate limit|429|ECONNRESET|"
                     r"could not connect|Unable to connect|Peer disconnected|Could not GET 'https?://|Unable to download artifact")]
LOCAL_SERVICE = re.compile(r"Connection refused[^\n]*(?:localhost|127\.0\.0\.1)|(?:localhost|127\.0\.0\.1)[^\n]*Connection refused", re.I)
# 29/10/2026 (rà lá infra): dòng bằng chứng chỉ là triệu chứng, nguyên nhân nằm trong log.
# ZipException khi cài Android SDK/NDK (gói tải về hỏng) -> androidsdk
SDK_ARCHIVE = re.compile(r"ZipException|InstallFailedException|Failed to install")
SDK_INSTALL = re.compile(r"InstallFailedException|Failed to install the following (?:Android )?SDK|\"Install (?:NDK|Android SDK)[^\"]*\" failed")
# repo Maven/Gradle trả 403/4xx/5xx hoặc tải thất bại (Maven Central chặn, artifact tải dở) -> network
HTTP_FAIL = re.compile(r"Could not (?:GET|HEAD) 'https?://|Received status code \d{3} from server|HTTP response code: \d{3}|"
                       r"ClientProtocolException|failed to transfer from https?://|Download failed")
UNRESOLVED = re.compile(r"Non-resolvable parent POM|Could not resolve dependencies|Unable to resolve dependencies|"
                        r"or one of its dependencies could not be resolved")
TRANSFER = re.compile(r"Could not transfer artifact")
# compile -> lá khác (26/10): lỗi của bước format (google-java-format) và lệch phiên bản Kotlin metadata
FORMATTER = re.compile(r"googlejavaformat|FormatterException")
KOTLIN_VERSION = re.compile(r"incompatible version of Kotlin|metadata version|was compiled with an incompatible version|"
                            r"binary version of its metadata is", re.I)
# buildconfig -> dependency (26/10): 'dependency.version is missing' do BOM import không resolve được
IMPORT_POM = re.compile(r"Non-resolvable import POM")
IT = re.compile(r"integration|\bIT\b|ITCase|\bIT[ -]|e2e|end.to.end|cluster|quickstart|smoke|compatib|"
                r"connected\w*AndroidTest|androidTest", re.I)
MODULE = [re.compile(r"on project ([\w.\-]+)"),
          re.compile(r"task '?:([\w\-]+(?::[\w\-]+)*):\w+'?"),
          re.compile(r"/home/runner/work/[^/]+/[^/]+/([\w.\-]+)/"),
          re.compile(r"^(?:\S*\s)?([\w.\-]+)/src/(?:main|test)/")]


SUBTYPES = ("buildconfig", "compile", "dependency", "lint", "test", "infra", "flaky")
# lá (tầng 3) -> cha (tầng 2): kiểm tra cây ở main()
PARENT = {"testfailure": "test", "itestfailure": "test", "compile": "compile", "buildconfig": "buildconfig",
          "dependency": "dependency", "quality": "lint", "doc": "lint", "license": "lint", "compatibility": "lint",
          "git": "infra", "androidsdk": "infra", "crash": "infra", "network": "infra", "flaky": "flaky"}


def first(rules: list, ev: str) -> str | None:
    return next((name for name, pat in rules if re.search(pat, ev, re.I)), None)


def subtype(label: str, ev: str, workflow: str, job: str, log: str = "", test_stage: str | None = None) -> str | None:
    """Lá của một run. `log`: văn bản log job fail (nếu có); `test_stage`: test/itest suy từ công cụ fail
    (crawl.stages.failed_tools, vd. failsafe/connectedAndroidTest -> itest, surefire default-test -> test).
    Một số lá có thể khác nhánh tầng 2 của `label` (compile -> quality/dependency, buildconfig -> dependency):
    người gọi cập nhật label_l2 theo PARENT."""
    if label == "compile":
        if FORMATTER.search(ev):
            return "quality"
        return "dependency" if KOTLIN_VERSION.search(ev) else "compile"
    if label == "buildconfig":
        return "dependency" if IMPORT_POM.search(log) else "buildconfig"
    if label in ("dependency", "flaky"):  # nhánh chỉ có một lá
        return label
    if label == "test":
        if test_stage in ("test", "itest"):  # công cụ fail chính xác hơn tên workflow (26/10)
            return "itestfailure" if test_stage == "itest" else "testfailure"
        return "itestfailure" if IT.search(" ".join([ev, workflow, job])) else "testfailure"
    if label == "lint":
        return first(LINT, ev) or "quality"  # quality = vi phạm quy tắc kiểm tra code nói chung (người quyết 16/10)
    if label == "infra":
        if not ev or LOCAL_SERVICE.search(ev):
            return None
        if SDK_ARCHIVE.search(ev) and SDK_INSTALL.search(log):
            return "androidsdk"
        if HTTP_FAIL.search(ev) or (UNRESOLVED.search(ev) and TRANSFER.search(log)):
            return "network"  # xét trước crash: regex crash có "timeout" khớp cả lỗi tải
        return first(INFRA, ev)
    return None


def module(ev: str) -> str | None:
    for pat in MODULE:
        m = pat.search(ev)
        if m:
            return m.group(1).split(":")[0].removesuffix("_2.12").removesuffix("_2.13")
    return None


def main(commits: Path, out: Path) -> None:
    run_commit, run_job = {}, defaultdict(str)
    gold = []
    for root in ROOTS:
        g = pd.read_csv(root / "gold_labels.csv", encoding="utf-8-sig", dtype={"evidence": str}).fillna({"evidence": ""})
        gold.append(g)
        for d in (p for p in root.iterdir() if (p / "runs.jsonl").exists()):
            repo = d.name.replace("__", "/")
            for line in (d / "runs.jsonl").open(encoding="utf-8"):
                r = json.loads(line)
                run_commit[r["id"]] = (repo, r["head_sha"])
            if (d / "jobs.jsonl").exists():
                for line in (d / "jobs.jsonl").open(encoding="utf-8"):
                    r = json.loads(line)
                    run_job[r["run_id"]] = " ".join(j["name"] for j in r["jobs"] if j.get("conclusion") == "failure")
    g = pd.concat(gold).drop_duplicates("run_id")
    per = defaultdict(list)
    for r in g.itertuples():
        key = run_commit.get(int(r.run_id))
        if key and r.gold in SUBTYPES:
            # trước 15/10 dependency bị gộp vào compile ở bước này -> mọi commit dependency mang compile_main (sai)
            per[key].append((r.gold, subtype(r.gold, r.evidence, r.workflow, run_job[int(r.run_id)]), module(r.evidence)))
    c = pd.read_parquet(commits)
    c = c[(c.outcome == "fail") & c.label.isin(SUBTYPES)]
    rows = []
    for x in c.itertuples():
        lab = x.label
        hits = [h for h in per.get((x.repository, x.head_sha), []) if h[0] == lab]
        st = Counter(h[1] for h in hits if h[1]).most_common(1)
        md = Counter(h[2] for h in hits if h[2]).most_common(1)
        rows.append({"repository": x.repository, "head_sha": x.head_sha, "label": lab,
                     "subtype": st[0][0] if st else None, "module": md[0][0] if md else None})
    df = pd.DataFrame(rows).drop_duplicates(["repository", "head_sha", "label"])
    df.to_parquet(out, index=False)
    # lá đổi nhánh (compile -> quality/dependency...) chỉ áp dụng ở mức run (run_dataset); ở mức commit giữ nhãn commit
    cross = df.subtype.notna() & (df.subtype.map(PARENT) != df.label)
    print(f"lá khác nhánh nhãn commit (bỏ subtype): {int(cross.sum())}")
    df.loc[cross, "subtype"] = None
    print(f"{len(df)} commit fail có nhãn")
    print("có subtype:", df.subtype.notna().groupby(df.label).mean().round(3).to_dict())
    print("có module :", df.module.notna().groupby(df.label).mean().round(3).to_dict())
    print(df.subtype.value_counts(dropna=False).to_string())
    print("số module khác nhau:", df.dropna(subset=["module"]).groupby("repository").module.nunique().to_dict())
    print(f"Đã lưu {out}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--commits", type=Path, default=Path("data/processed/commits_all.parquet"))
    ap.add_argument("--out", type=Path, default=Path("data/processed/fine_labels.parquet"))
    a = ap.parse_args()
    main(a.commits, a.out)
