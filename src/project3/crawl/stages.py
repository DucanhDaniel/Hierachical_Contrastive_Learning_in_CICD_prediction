"""Nhãn 2 trục (25/10/2026, góp ý GVHD): thay cây nhiều tầng bằng hai thuộc tính độc lập của một run fail.

  location (lỗi nằm ở đâu / thay đổi gây hậu quả ở đâu):  code | build | env
      code  = mã nguồn và mã test (compile, testfailure, itestfailure, quality, doc, license, compatibility, flaky)
      build = cấu hình build và phụ thuộc (buildconfig, dependency)
      env   = môi trường CI: runner, mạng, dịch vụ ngoài (network, crash, git, androidsdk, infra)
  stage (lỗi phát sinh ở giai đoạn nào của pipeline):
      setup    chuẩn bị môi trường (checkout, cài JDK/SDK, cache, tải action, kéo image, runner)
      prepare  chuẩn bị build (đọc cấu hình Maven/Gradle, enforcer, tải phụ thuộc)
      compile  biên dịch và sinh mã (javac/kotlinc, kapt/ksp, protobuf, xử lý resource)
      check    kiểm tra tĩnh (format, checkstyle, lint, javadoc, license, tương thích API, phân tích phụ thuộc)
      test     test đơn vị
      itest    test tích hợp / e2e / chức năng / instrumentation
      package  đóng gói, phát hành, triển khai (jar, assemble, docker, publish)
  flaky không phải vị trí mà là tính chất (fail rồi chạy lại thì qua) -> cờ `flaky`, location = code, stage theo log.

Lỗi runner (mạng, crash, Android SDK) không còn phải chọn nhánh: location = env, stage = bước đang chạy khi hỏng.

Cách lấy stage, theo thứ tự (cột stage_src ghi nguồn):
  leaf     lá thuộc nhóm code/buildconfig đã tự xác định giai đoạn (compile -> compile, quality -> check, ...);
           riêng lá test/itest/flaky: test hay itest lấy theo công cụ fail trước (failsafe, connectedAndroidTest, funTest,
           surefire ở module integration -> itest), không có công cụ mới dùng lá (lá chia theo tên workflow/job, kém hơn)
  tool     goal Maven / task Gradle bị fail trong log các job fail ("Failed to execute goal", "Execution failed for
           task", "> Task :x FAILED"); nhiều công cụ fail thì lấy giai đoạn SỚM nhất (nguyên nhân gốc đi trước)
  evidence dòng bằng chứng của quy tắc khớp mẫu của một giai đoạn (vd. "Could not resolve" -> prepare)
  context  goal/task cuối cùng bắt đầu chạy trước dòng bằng chứng trong cùng đoạn log
  step     tên step fail / lệnh của step chứa bằng chứng
Run `?` (quy tắc không gán được loại lỗi) vẫn có thể có stage: location để trống, stage lấy từ tool/step.

    python -m project3.crawl.stages                    # -> data/run_dataset/axes.parquet + in thống kê
    python -m project3.crawl.stages --cells            # chỉ in bảng ô location × stage theo đợt crawl (từ axes.parquet)
"""
import argparse
import re
import sys
from collections import Counter
from pathlib import Path

STAGES = ("setup", "prepare", "compile", "check", "test", "itest", "package")
LOCATIONS = ("code", "build", "env")
ORDER = {s: i for i, s in enumerate(STAGES)}

LOCATION = {"compile": "code", "testfailure": "code", "itestfailure": "code", "quality": "code", "doc": "code",
            "license": "code", "compatibility": "code", "flaky": "code", "buildconfig": "build", "dependency": "build",
            "network": "env", "crash": "env", "git": "env", "androidsdk": "env", "infra": "env"}
# lá mà loại lỗi đã nói rõ giai đoạn; các lá còn lại (dependency, env, flaky) lấy giai đoạn từ log
LEAF_STAGE = {"compile": "compile", "testfailure": "test", "itestfailure": "itest", "quality": "check", "doc": "check",
              "license": "check", "compatibility": "check", "buildconfig": "prepare"}

TEST_LEAVES = {"testfailure", "itestfailure", "flaky"}

# --- công cụ bị fail -> giai đoạn. Thứ tự kiểm tra quan trọng (compileTestJava là compile, không phải test). ---
GRADLE_TASK = [  # tên task (phần cuối sau dấu :), không phân biệt hoa thường
    ("prepare", r"dependencies$|resolve|configurationerrors|aarmetadata|^check\w*gradle|^prepare\w*kotlinbuildscript"),
    ("check", r"spotless|checkstyle|^pmd|spotbugs|detekt|ktlint|^lint|lint$|javadoc|dokka|apicheck|apidump|japicmp|"
              r"revapi|breaking|^rat$|license|forbiddenapis|verification$|sonar|dependencycheck|validateplugins|"
              r"checkformat|format\w*check|^ktfmt|errorprone|^modernizer|apicompat|metalava"),
    ("compile", r"compile|kapt|^ksp|classes$|precompile|processresources|processtestresources|^generate|proto|antlr|"
                r"^dex|desugar|^merge\w*(?:resources|assets|manifest|jnilibs)|aidl|lombok|^link\w*(?:test|debug|release)|"
                r"^process\w*(?:manifest|resources)|^transform|kotlinnative"),
    ("itest", r"integ|integration|^it$|^it[A-Z_]|^int(?:ernal)?test$|inttest|e2e|functional|funtest|androidtest|"
              r"resttest|smoke|system|acceptance|cucumber|againstold|cluster|gametest|stories|benchmark"),
    ("test", r"test|report$|coverage"),
    ("package", r"jar$|shadow|^assemble|^bundle|publish|^dist|zip$|tar$|docker|^jib|sign|upload|apk$|aar$|^package|"
                r"^install|^build\w*image|nativecompile|nativeimage"),
]
MAVEN_GOAL = [  # "artifactId:goal"
    ("prepare", r"enforcer|toolchains?-|remote-resources|download-maven|bom-maven|dependency-plugin:(?:copy|unpack|go-offline|resolve|tree|get)|"
                r"flatten|build-helper|versions-maven"),
    ("check", r"spotless|checkstyle|apache-rat|license|formatter|airstyle|modernizer|revapi|japicmp|pmd|spotbugs|findbugs|"
              r"jacoco-maven-plugin:check|prettier|forbiddenapis|impsort|sortpom|logchange|openapi-diff|sonar|"
              r"dependency-plugin:analyze|artifact-plugin:compare|javadoc|javaformat|dependency-check|animal-sniffer|clirr|"
              r"duplicate-finder|maven-plugin-plugin:descriptor|editorconfig"),
    ("compile", r"compiler-plugin|scala-maven-plugin:(?:compile|testCompile|add-source)|kotlin-maven-plugin|groovy\S*:compile|"
                r"gmavenplus|protobuf|protoc|avro|antlr|javacc|jjtree|kiota|krpc|openapi-generator|jaxb|xjc|cxf-codegen|"
                r":generate|lombok|resources-plugin|replacer"),
    ("itest", r"failsafe|invoker|docker-maven-plugin:start|cargo|integration|autobahn|bnd-testing|selenium"),
    ("test", r"surefire|scalatest|junit-platform-maven|karma|:test$"),
    ("package", r"jar-plugin|assembly|shade|docker-maven-plugin:build|jib|quarkus-maven-plugin:build|deploy|install-plugin|"
                r"central-publishing|nexus-staging|source-plugin|war-plugin|site|p2-director|native-maven-plugin|"
                r"bundle-plugin|spring-boot-maven-plugin:repackage|gpg"),
]
AGG_TASK = {"build", "check", "assemble", "allTests"}  # task Gradle tổng hợp: fail vì task con fail
MAVEN_FAIL = re.compile(r"Failed to execute goal ([\w.\-]+):([\w.\-]+):[^:\s]+:([\w\-]+)(?: \([^)]*\))?(?: on project ([\w.\-]+))?")
# test chạy trong module/execution tích hợp (surefire ở module integration-tests, task :e2e:test) -> itest
IT_MODULE = re.compile(r"integ|(?:^|[\-_:])its?(?:$|[\-_:])|e2e|end-to-end|system-?tests?|acceptance|functional", re.I)
GRADLE_FAIL = re.compile(r"Execution failed for task '(:?[\w\-:]+)'|^> Task (:?[\w\-:]+) FAILED", re.M)
# ranh giới goal/task bắt đầu chạy (để biết đang ở đâu khi runner sập / mạng hỏng)
MAVEN_START = re.compile(r"^\[INFO\] --- (?:([\w.\-]+):)?([\w.\-]+):[^:\s]+:([\w\-]+)", re.M)
GRADLE_START = re.compile(r"^> Task (:?[\w\-:]+)", re.M)

EVIDENCE = [  # dòng bằng chứng -> giai đoạn, khi không có công cụ fail
    ("setup", r"runner has received a shutdown|Set up job|download action|Failed to download action|Docker pull failed|"
              r"unable to access 'https://github|actions/checkout|setup-java|sdkmanager|avdmanager|emulator|"
              r"licenses? (?:have|has) not been accepted|Unable to resolve action|wget: |apache-maven-\S+-bin"),
    ("prepare", r"Could not resolve|Could not find artifact|Could not find [\w.\-]+:[\w.\-]+:|Non-resolvable|"
                r"Could not GET|Could not HEAD|Could not transfer|artifact descriptor|could not be resolved|"
                r"Failed to collect dependencies|A problem occurred configuring|Could not compile build file|"
                r"Script compilation error|Plugin \[id: |settings file|Could not acquire shared lock|"
                r"Could not determine the dependencies|Dependency convergence|'dependencies\.dependency"),
    ("compile", r"COMPILATION ERROR|\.(?:java|kt|scala|groovy):\d+:? (?:error|e:)|^e: file:"),
    ("itest", r"Container (?:stopped|startup failed)|testcontainers|docker-compose|Could not start container"),
    ("test", r"Tests run: \d+.*(?:FAILURE|Failures: [1-9]|Errors: [1-9])|tests completed, \d+ failed|"
             r"There was a timeout in the fork|forked VM terminated"),
    ("package", r"failed to push some refs|docker push|Failed to deploy|publish(?:ing)? failed"),
]
STEP = [  # tên step / lệnh của step -> giai đoạn (tên chung như "build", "Build with Maven" không mang thông tin)
    ("setup", r"^set up|^setup|checkout|^install (?:jdk|java|node|python|android|sdk|go|rust)|cache|docker login|"
              r"^login|configure aws|free (?:up )?disk|^clone|submodule|^post |emulator-runner|android-emulator"),
    ("prepare", r"dependenc(?:y|ies)(?! ?check)|go-offline|resolve|npm (?:ci|install)|yarn install|pip install|"
                r"install (?:\S+ )*packages?|"
                r"download (?:deps|artifacts)|bootstrap|^prepare"),
    ("check", r"lint|spotless|checkstyle|format|style|detekt|ktlint|pmd|spotbugs|sonar|\brat\b|license|javadoc|"
              r"api ?check|japicmp|revapi|codeql|analy[sz]|pre-commit|changelog|dependency-check|owasp|"
              r"jira|link check|check links|validate|verify (?:pr|title|commit)|static|semgrep|errorprone|"
              r"strict-compilation|compat"),
    ("itest", r"integration|\bits?\b|\bit ?tests?\b|e2e|end.to.end|functional|system ?test|smoke|instrumentation|"
              r"connected\w*androidtest|acceptance|\bk8s\b|kubernetes|provider .*tests"),
    ("test", r"\btests?\b|unit|junit|surefire|jacoco|coverage"),
    ("compile", r"compile|javac|kotlinc|assemble ?debug|classes"),
    ("package", r"package(?!s)|publish|deploy|release|docker build|build (?:and push )?(?:docker )?image|push image|"
                r"jar\b|\bdist\b|upload|signing|snapshot"),
]
# step tổng hợp (chỉ đọc kết quả job khác) hoặc tên chung build+publish -> bỏ qua
AGG_STEP = re.compile(r"check (?:\S+ )?results?|check all|sub-job|status checks|fail job if|summary of failures|"
                      r"publish test report|parse junit|print test results|generic-build|^\s*$", re.I)
# thủ tục PR (changelog, Jira, tiêu đề, DCO/sign-off, nhãn): không phải lỗi build -> cờ governance, không có giai đoạn
GOVERNANCE = re.compile(r"changelog|jira|pr (?:title|description|quality)|title format|parameter changes and pr|"
                        r"sign-?off|\bdco\b|signatures|label|semantic-pull-request|commit ?message|sonar token", re.I)

_GRADLE = [(s, re.compile(p, re.I)) for s, p in GRADLE_TASK]
_MAVEN = [(s, re.compile(p, re.I)) for s, p in MAVEN_GOAL]
_EVIDENCE = [(s, re.compile(p, re.I | re.M)) for s, p in EVIDENCE]
_STEP = [(s, re.compile(p, re.I)) for s, p in STEP]


def _first(rules, text: str) -> str | None:
    return next((s for s, pat in rules if pat.search(text)), None)


def gradle_stage(task: str) -> str | None:
    name = task.rsplit(":", 1)[-1]
    return None if name in AGG_TASK else _first(_GRADLE, name)


def maven_stage(artifact: str, goal: str) -> str | None:
    return _first(_MAVEN, f"{artifact}:{goal}")


def failed_tools(text: str) -> list[tuple[str, str | None]]:
    """(công cụ, giai đoạn) của mọi goal Maven / task Gradle bị fail trong một đoạn log."""
    out = []
    for m in MAVEN_FAIL.finditer(text):
        st = maven_stage(m.group(2), m.group(3))
        if st == "test" and IT_MODULE.search(m.group(4) or ""):
            st = "itest"
        out.append((f"{m.group(2)}:{m.group(3)}" + (f"@{m.group(4)}" if m.group(4) else ""), st))
    for m in GRADLE_FAIL.finditer(text):
        task = m.group(1) or m.group(2)
        if task.rsplit(":", 1)[-1] not in AGG_TASK:
            st = gradle_stage(task)
            if st == "test" and IT_MODULE.search(task.rsplit(":", 1)[0]):
                st = "itest"
            out.append((task, st))
    return out


def context_stage(text: str, key: str) -> tuple[str | None, str | None]:
    """Goal/task cuối cùng bắt đầu trước dòng bằng chứng `key` trong đoạn (hoặc cuối đoạn nếu không thấy key)."""
    pos = text.find(key) if key else -1
    head = text[:pos] if pos >= 0 else text
    starts = [(m.start(), f"{m.group(2)}:{m.group(3)}", maven_stage(m.group(2), m.group(3))) for m in MAVEN_START.finditer(head)]
    starts += [(m.start(), m.group(1), gradle_stage(m.group(1))) for m in GRADLE_START.finditer(head)]
    starts = [s for s in starts if s[2]]
    if not starts:
        return None, None
    _, tool, stage = max(starts)
    return tool, stage


def step_stage(names: list[str]) -> str | None:
    """Giai đoạn sớm nhất trong các tên step/lệnh có nghĩa (bỏ step tổng hợp và tên chung)."""
    hits = [_first(_STEP, n) for n in names if n and not AGG_STEP.search(n) and not GOVERNANCE.search(n)]
    hits = [h for h in hits if h]
    return min(hits, key=ORDER.get) if hits else None


def earliest(stages) -> str | None:
    stages = [s for s in stages if s]
    return min(stages, key=ORDER.get) if stages else None


def run_axes(leaf: str | None, evidence: str, key: str, chunks: list[dict]) -> dict:
    """Hai trục của một run. chunks: các đoạn log của job fail (text, step_header, failed_steps, has_evidence)."""
    tools = [t for c in chunks for t in failed_tools(c["text"])]
    tool_stage = earliest(s for _, s in tools)
    ev_chunk = next((c for c in chunks if c["has_evidence"]), None)
    out = {"location": LOCATION.get(leaf), "flaky": leaf == "flaky",
           "failed_tool": next((t for t, s in tools if s == tool_stage), tools[0][0] if tools else None)}
    cands = []
    if leaf in TEST_LEAVES and tool_stage in ("test", "itest"):
        cands.append(("tool", tool_stage))  # test hay itest: theo công cụ/module fail, chính xác hơn tên workflow
    if leaf in LEAF_STAGE:
        cands.append(("leaf", LEAF_STAGE[leaf]))
    cands.append(("tool", tool_stage))
    cands.append(("evidence", _first(_EVIDENCE, evidence) if evidence else None))
    if ev_chunk is not None:
        cands.append(("context", context_stage(ev_chunk["text"], key)[1]))
    names = list(dict.fromkeys(s for c in chunks for s in c["failed_steps"].split(" | ") if s))
    if ev_chunk is not None:
        names.append(ev_chunk["step_header"])
    cands.append(("step", step_stage(names)))
    src, stage = next(((s, v) for s, v in cands if v), (None, None))
    out.update(stage=stage, stage_src=src, stage_tool=tool_stage,
               governance=leaf is None and stage is None and any(GOVERNANCE.search(n) for n in names))
    return out


def main(run_dataset: Path, out: Path) -> None:
    import pandas as pd
    import pyarrow.parquet as pq
    from project3.crawl.build_log_labels import GROUP as RULE_GROUP
    from project3.model.labels import leaf_of
    from project3.pipeline.run_dataset import clean

    runs = pd.read_parquet(run_dataset / "runs.parquet",
                           columns=["run_id", "repository", "label_l2", "label_l3", "evidence", "log_jobs"])
    runs = runs[runs.log_jobs > 0]
    info = {r.run_id: (leaf_of(r.label_l3, r.label_l2) if r.label_l2 in RULE_GROUP else None,
                       r.evidence if isinstance(r.evidence, str) else "", r.repository)
            for r in runs.itertuples(index=False)}
    rows, cur, cur_id = [], [], None

    def flush():
        if cur_id in info:
            leaf, ev, repo = info[cur_id]
            rows.append({"run_id": cur_id, "repository": repo, "leaf": leaf,
                         **run_axes(leaf, ev, clean(ev)[:120].strip(), cur)})

    cols = ["run_id", "text", "step_header", "failed_steps", "has_evidence"]
    for batch in pq.ParquetFile(run_dataset / "chunks.parquet").iter_batches(batch_size=20000, columns=cols):
        for c in batch.to_pylist():  # đoạn của một run nằm liền nhau (run_dataset ghi theo repo, theo job)
            if c["run_id"] != cur_id:
                flush()
                cur, cur_id = [], c["run_id"]
            cur.append(c)
    flush()
    df = pd.DataFrame(rows).drop_duplicates("run_id")
    df.to_parquet(out, index=False)
    report(df)
    cells(df)
    print(f"Đã lưu {out}")


def report(df) -> None:
    import pandas as pd
    lab = df[df.leaf.notna()]
    print(f"{len(df)} run có log; {len(lab)} có loại lỗi; stage gán được: có loại {lab.stage.notna().mean():.1%}, "
          f"`?` {df[df.leaf.isna()].stage.notna().mean():.1%}")
    print("\nlocation × stage (run có loại lỗi):")
    print(pd.crosstab(lab.location, lab.stage.fillna("-"), margins=True).to_string())
    print("\nlá × stage:")
    print(pd.crosstab(lab.leaf, lab.stage.fillna("-")).to_string())
    print("\nnguồn stage:", lab.stage_src.value_counts(dropna=False).to_dict())
    print("`?` stage:", df[df.leaf.isna()].stage.value_counts(dropna=False).to_dict(),
          "| thủ tục PR (governance):", int(df.governance.sum()))
    # tự kiểm: với lá đã biết giai đoạn, giai đoạn suy từ công cụ fail có khớp không
    chk = lab[lab.leaf.isin(LEAF_STAGE) & lab.stage_tool.notna()]
    agree = (chk.stage_tool == chk.leaf.map(LEAF_STAGE))
    print(f"\nkhớp lá↔công cụ fail: {agree.mean():.1%} trên {len(chk)} run;",
          agree.groupby(chk.leaf).mean().round(3).to_dict())


MIN_CELL = 300  # ô location × stage ít hơn thì gộp hoặc nhắm crawl, không học riêng


def batch_of(repo: str) -> str:
    """Đợt crawl của repo: scope trong crawl_status.json (targeted-r3, targeted-android) hoặc base (crawl_100 + đợt 2)."""
    import json
    for root in ("data/crawl_pr", "data/validate"):
        st = Path(root) / repo.replace("/", "__") / "crawl_status.json"
        if st.exists():
            scope = json.loads(st.read_text(encoding="utf-8")).get("scope")
            if scope:
                return scope
    return "base"


def cells(df) -> None:
    """Số run mỗi ô location × stage (run có loại lỗi), theo đợt; ô dưới MIN_CELL đánh dấu; độ tập trung theo repo."""
    import pandas as pd
    lab = df[df.leaf.notna() & df.stage.notna()].copy()
    lab["batch"] = lab.repository.map({r: batch_of(r) for r in lab.repository.unique()})
    lab["cell"] = lab.location + "×" + lab.stage
    t = pd.crosstab(lab.cell, lab.batch, margins=True, margins_name="tổng")
    top = lab.groupby("cell").repository.agg(lambda s: s.value_counts(normalize=True).iloc[0])
    t["repo_lớn_nhất"] = top.reindex(t.index).round(2)
    t["n_repo"] = lab.groupby("cell").repository.nunique().reindex(t.index)
    t["<ngưỡng"] = (t["tổng"] < MIN_CELL).map({True: "*", False: ""})
    print(f"\nô location × stage theo đợt (* = dưới {MIN_CELL} run):")
    print(t.sort_values("tổng", ascending=False).to_string())


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dataset", type=Path, default=Path("data/run_dataset"))
    ap.add_argument("--out", type=Path, default=Path("data/run_dataset/axes.parquet"))
    ap.add_argument("--cells", action="store_true", help="chỉ in bảng ô từ axes.parquet đã có")
    a = ap.parse_args()
    if a.cells:
        import pandas as pd
        cells(pd.read_parquet(a.out))
    else:
        main(a.run_dataset, a.out)
