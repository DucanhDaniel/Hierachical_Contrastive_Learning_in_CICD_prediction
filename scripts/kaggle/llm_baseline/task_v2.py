# %% [markdown]
# Baseline LLM phân loại lỗi CI từ log, bản 2: prompt ghi rõ quy ước của đề tài (project3, 20/10/2026). Chỉ để so sánh, không phải nguồn nhãn.
# Dữ liệu: dataset ducanhpham2k5/p3-llm-sample (sample.jsonl do `python -m project3.pilot.llm_baseline prepare`).
# Mỗi dòng trả về chỉ số lá trong LEAVES (-1 = unknown / trả lời không hợp lệ).
#   kaggle b t push p3-llm-baseline-v2 -f scripts/kaggle/llm_baseline/task_v2.py -d ducanhpham2k5/p3-llm-sample --wait
#   kaggle b t run p3-llm-baseline-v2 -m gemini-3.5-flash-lite --wait

# %%
import dataclasses
import glob

import pandas as pd
import kaggle_benchmarks as kbench

MODEL = "gemini-3.5-flash-lite"  # mô hình chạy toàn bộ (rẻ nhất); push tự chạy một lượt với mô hình mặc định -> chỉ 20 dòng
LEAVES = ["testfailure", "itestfailure", "compile", "buildconfig", "dependency", "quality", "doc", "license",
          "compatibility", "git", "crash", "androidsdk", "network", "flaky", "infra"]

GUIDE = """You classify the root cause of a failed GitHub Actions CI run of a Java/Kotlin project (Maven/Gradle).
Follow the ORGANISATION CONVENTIONS below exactly, even where you would judge differently.

STEP 1 - pick the failure category, using the EARLIEST cause in this priority order when several errors appear:
  buildconfig > compile > dependency > lint > test > flaky > infra(environment).
  (Environment problems such as network or crash win only if no code/build error explains the failure.)
STEP 2 - pick the leaf inside the category:

buildconfig: the build definition itself is broken: invalid/unparseable pom.xml or build.gradle(.kts), "Could not find the
  selected project in the reactor", unknown module/subproject, Gradle script compilation error, "Non-resolvable parent POM"
  caused by a local mistake, plugin misconfiguration.
compile: javac/kotlinc/scalac/groovyc errors in main OR test sources ("cannot find symbol", "incompatible types",
  "Compilation failure", "e: file.kt: ...", "error: ..." with a .java/.kt line).
dependency: dependency/plugin/artifact cannot be resolved or is inconsistent ("Could not resolve", "Could not find artifact",
  "Failed to collect dependencies", missing plugin version), maven-enforcer failures (requireUpperBoundDeps,
  dependencyConvergence, bannedDependencies), dependency:analyze failures, JDK/class-version mismatch
  ("class file has wrong version", UnsupportedClassVersionError, "invalid target release", Gradle JVM toolchain mismatch),
  linkage errors from external classes (NoClassDefFoundError / NoSuchMethodError at build/test time caused by versions).
  BUT: resolution failures that show network symptoms (timeout, connection reset/refused, HTTP 401/403/429/5xx) are network.
lint leaves:
  doc: javadoc errors ("error: reference not found", "unknown tag", "javadoc" goal failing).
  license: apache-rat / license / copyright header check fails ("Unapproved licenses", "Rat check").
  compatibility: API compatibility check (revapi, japicmp, metalava, binary-compatibility-validator, "incompatibilit").
  quality: any other static check: checkstyle, spotless, PMD, SpotBugs, ktlint, detekt, errorprone, formatting, sortpom.
test leaves (tests ran and some failed: "Tests run: ... Failures", "There are test failures", AssertionError, "test FAILED"):
  itestfailure: the failing tests are integration-type. DECIDE BY NAMES: if the failing test, the workflow name or the job
    name matches integration, IT, ITCase, "IT " , e2e, end-to-end, cluster, quickstart, smoke or compatib(ility) -> itestfailure.
  testfailure: all other failing tests (unit tests).
flaky: ONLY if the log explicitly shows a test that is known flaky / passed on rerun ("Flakes:", "flaky", rerunFailingTests
  reporting it passed later). Do not guess flaky.
infra leaves (environment, not caused by the code change), first match wins:
  git: "fatal: ...", git checkout/push/fetch failed, "unable to access 'https://github...", "could not read Username".
  androidsdk: Android SDK / sdkmanager / avdmanager / emulator setup, unaccepted SDK licenses.
  crash: runner shutdown or lost communication, OutOfMemory / heap space / GC overhead, exit code 137 / Killed,
    "No space left on device", forked VM terminated/crashed, job or step timeout, "The operation was canceled".
  network: connection refused/reset, SocketTimeout, UnknownHost / DNS failure, HTTP 5xx/429/401/403 from a repository,
    "Could not transfer artifact", "Failed to download", Docker pull failed, rate limit, "Peer disconnected".
  infra: any other environment problem (credentials/secrets missing, CI service error, docker daemon, permissions).

Answer "unknown" only if the log gives no usable evidence of the cause."""


@dataclasses.dataclass
class Answer:
    leaf: str
    evidence: str


@kbench.task(name="p3-llm-baseline-v2")
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
