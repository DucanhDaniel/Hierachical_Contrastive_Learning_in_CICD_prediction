# %% [markdown]
# Baseline B3 (project3, 27/10/2026): LLM zero-shot với log đã lọc theo LogSage (arXiv 2506.03691, ASE 2025 Industry
# Showcase). Chỉ để so sánh, không phải nguồn nhãn. Dữ liệu: dataset ducanhpham2k5/p3-llm-logsage
# (sample.jsonl do `python -m project3.model.llm_logsage prepare`). Prompt theo cấu trúc của paper (vai trò, kỹ năng:
# tìm dòng lỗi chính -> suy nguyên nhân gốc, ràng buộc đầu ra) nhưng đầu ra là MỘT lá của cây nhãn đề tài.
# Mỗi dòng trả về chỉ số lá trong LEAVES (-1 = unknown / không hợp lệ).
#   kaggle b t push p3-llm-logsage -f scripts/kaggle/llm_logsage/task.py -d ducanhpham2k5/p3-llm-logsage --wait
#   kaggle b t run p3-llm-logsage -m gemini-3.5-flash-lite --wait

# %%
import dataclasses
import glob

import pandas as pd
import kaggle_benchmarks as kbench

MODEL = "gemini-3.5-flash-lite"  # push tự chạy một lượt với mô hình mặc định -> chỉ 20 dòng
LEAVES = ["testfailure", "itestfailure", "compile", "buildconfig", "dependency", "quality", "doc", "license",
          "compatibility", "git", "crash", "androidsdk", "network", "flaky", "infra"]

ROLE = """You are a CI/CD failure diagnosis assistant. You analyse the execution log of a failed GitHub Actions run of a
Java/Kotlin project (Maven/Gradle) and its CI configuration context (workflow, failed job, failed step).
The log below was pre-filtered: it keeps the lines most likely to contain errors (keywords, end of log) with a few
lines of context; '...' separates kept blocks.

Skills:
1. Identify the type of task that failed (build, static check, unit test, integration test, deploy, setup...).
2. Identify the key error lines (ignore normal output and warnings).
3. Infer the single ROOT cause; if several errors appear, choose the EARLIEST one in the build
   (configuration -> dependency -> compile -> static checks -> tests); do not suggest fixes.
4. Map the root cause to exactly ONE label:"""

LABELS = """- compile: compiling main/test code failed (javac, kotlinc, scalac errors).
- quality: code-check rule violation: format (spotless, ktlint, google-java-format), checkstyle, pmd, spotbugs, detekt, Android lint.
- doc: documentation failure: javadoc (e.g. 'error: reference not found' while generating javadoc), dokka.
- license: missing/wrong license header, Apache RAT, license compliance checks.
- compatibility: API/ABI incompatibility: revapi, japicmp, metalava, apiCheck.
- testfailure: an automated unit test failed (surefire / Gradle `test`).
- itestfailure: an integration / e2e / functional / instrumentation test failed (failsafe, integrationTest, connectedAndroidTest, e2e modules).
- flaky: unstable test only: tests reported FLAKY while no test really failed (Failures: 0, Errors: 0).
- buildconfig: broken build configuration: pom.xml/build.gradle/settings syntax, duplicate/missing declarations, Gradle script compilation error.
- dependency: dependency cannot be resolved (missing artifact, non-resolvable import POM/BOM), version conflict or mismatch incl. JDK/class-file version and Kotlin metadata version, missing external class.
- git: git interaction failure: clone/fetch/push, submodule.
- androidsdk: Android SDK/emulator failure: SDK download, SDK licenses not accepted, emulator does not boot, adb cannot connect to emulator port 5554/5555.
- infra: other infrastructure: credentials/secrets, local services/containers used by tests not starting (connection refused to localhost), Maven local-repository lock ('Could not acquire shared lock'), runner configuration.
- network: network failure: connection reset/timeouts while downloading, DNS, HTTP 401/403/429/5xx from repositories, failed action download.
- crash: the environment crashed: runner shutdown signal, OOM / Java heap space, disk full, job time limit exceeded, forked VM crash."""


@dataclasses.dataclass
class Answer:
    task_type: str
    key_error: str
    root_cause: str
    leaf: str


@kbench.task(name="p3-llm-logsage")
def classify_row(llm, row_id: str, context: str, log: str) -> int:
    prompt = (f"{ROLE}\n{LABELS}\n\nCI context: {context}\n\nFiltered log:\n<log>\n{log}\n</log>\n\n"
              "Return JSON with fields: task_type (short), key_error (the single most relevant log line, max 200 chars), "
              "root_cause (one sentence), leaf (one label from the list, or \"unknown\" only if the log gives no usable "
              "evidence).")
    with kbench.chats.new(row_id) as chat:
        ans = llm.prompt(prompt, schema=Answer)
        u = chat.usage
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
