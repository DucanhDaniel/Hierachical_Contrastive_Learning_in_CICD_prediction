# %% [markdown]
# Baseline LLM phân loại lỗi CI từ log (project3, 20/10/2026). Chỉ để so sánh, không phải nguồn nhãn.
# Dữ liệu: dataset ducanhpham2k5/p3-llm-sample (sample.jsonl do `python -m project3.pilot.llm_baseline prepare`).
# Mỗi dòng trả về chỉ số lá trong LEAVES (-1 = unknown / trả lời không hợp lệ).
#   kaggle b t push p3-llm-baseline -f scripts/kaggle/llm_baseline/task.py -d ducanhpham2k5/p3-llm-sample --wait
#   kaggle b t run p3-llm-baseline -m gemini-3.5-flash-lite --wait

# %%
import dataclasses
import glob

import pandas as pd
import kaggle_benchmarks as kbench

MODEL = "gemini-3.5-flash-lite"  # mô hình chạy toàn bộ (rẻ nhất); push tự chạy một lượt với mô hình mặc định -> chỉ 20 dòng
LEAVES = ["testfailure", "itestfailure", "compile", "buildconfig", "dependency", "quality", "doc", "license",
          "compatibility", "git", "crash", "androidsdk", "network", "flaky", "infra"]

GUIDE = """You classify the root cause of a failed GitHub Actions CI run of a Java/Kotlin project (Maven/Gradle).
Choose exactly ONE leaf label:
- testfailure: a unit test fails (assertion, test error) in the normal test phase.
- itestfailure: an integration / end-to-end / UI test fails (IT suites, e2e, emulator tests, failsafe).
- compile: compilation of main or test code fails (javac/kotlinc/scalac errors, symbol not found, type errors).
- buildconfig: the build configuration itself is broken (invalid pom.xml/build.gradle, unknown module/project, Gradle script error, misconfigured plugin).
- dependency: a dependency/plugin/artifact cannot be resolved or is inconsistent (missing artifact, version conflict,
  maven-enforcer upper-bound/convergence/banned dependencies, dependency:analyze), JDK/class-version mismatch
  (UnsupportedClassVersionError, invalid target release), or linkage errors from external classes (NoClassDefFoundError).
- quality: static analysis / formatting / style check fails (checkstyle, spotless, PMD, SpotBugs, ktlint, detekt, errorprone).
- doc: javadoc/documentation generation errors.
- license: license header / license compliance check fails (apache-rat, license plugin).
- compatibility: API/binary compatibility check fails (revapi, japicmp, binary-compatibility-validator).
- git: checkout / git operation fails.
- crash: the build environment crashes or times out (OOM, killed, runner lost, timeout, cancelled).
- androidsdk: Android SDK/emulator setup fails.
- network: network failure (connection reset/refused, DNS, timeouts while downloading, HTTP 401/403/429/5xx from repositories).
- flaky: a test that is known to be non-deterministic / passed on retry.
- infra: other environment/infrastructure failure not covered above (CI service, credentials, disk, docker).
Conventions: if several errors appear, choose the EARLIEST root cause in the build (configuration -> dependency -> compile
-> static checks -> tests). Answer "unknown" only if the log gives no usable evidence."""


@dataclasses.dataclass
class Answer:
    leaf: str
    evidence: str


@kbench.task(name="p3-llm-baseline")
def classify_row(llm, row_id: str, context: str, log: str) -> int:
    prompt = (f"{GUIDE}\n\nCI context: {context}\n\nLast part of the failed job logs:\n<log>\n{log}\n</log>\n\n"
              "Return JSON with fields: leaf (one label from the list, or \"unknown\") and evidence (the single most "
              "relevant log line, max 200 chars).")
    with kbench.chats.new(row_id) as chat:
        ans = llm.prompt(prompt, schema=Answer)
        u = chat.usage  # chi phí (nanodollar) để ước tính trước khi chạy toàn bộ
        print(f"USAGE {row_id} in={u.input_tokens} out={u.output_tokens} "
              f"cost_nd={(u.input_tokens_cost_nanodollars or 0) + (u.output_tokens_cost_nanodollars or 0)}", flush=True)
    leaf = (ans.leaf or "").strip().lower()
    return LEAVES.index(leaf) if leaf in LEAVES else -1


# %%
path = glob.glob("/kaggle/input/**/sample.jsonl", recursive=True)[0]
df = pd.read_json(path, lines=True, dtype={"row_id": str})
name = str(getattr(kbench.llm, "model", None) or getattr(kbench.llm, "name", None) or kbench.llm)
if MODEL not in name:
    df = df.groupby(df.row_id.str.split("|").str[0], group_keys=False).head(10)
print("mô hình:", name)
print(f"{len(df)} dòng từ {path}")

# %%
runs = classify_row.evaluate(llm=[kbench.llm], evaluation_data=df, on_failure="continue", max_attempts=3)
res = runs.completed_runs.as_dataframe()
print(f"xong {len(res)}, lỗi {len(runs.errored_runs)}; unknown/không hợp lệ: {(res['result'] == -1).sum()}")
