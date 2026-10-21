"""Đếm run có log chứa từng dạng tín hiệu dependency, theo nhãn hiện hành (?, dependency, infra). 18/10/2026.

    uv run python scripts/analysis/dep_signal_stats.py
"""
import csv, json, re, sys
from collections import Counter
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
from project3.crawl.gold_labels import diagnostic_text
P = {
 "resolve_summary": r"Could not resolve dependencies|Could not resolve all (?:files|dependencies|artifacts)|could not be resolved|Non-resolvable (?:parent|import) POM|Unresolveable build extension",
 "artifact_descriptor": r"Failed to read artifact descriptor",
 "transfer": r"Could not transfer artifact|Could not GET|Could not HEAD",
 "enforcer": r"maven-enforcer-plugin|RequireUpperBoundDeps|DependencyConvergence|BannedDependencies|Rule \d+: org\.apache\.maven\.enforcer",
 "jdk_version": r"UnsupportedClassVersionError|Unsupported class file major version|class file version \d+|invalid target release|release version \d+ not supported|requires (?:Java|JDK) \d+|has been compiled by a more recent version",
 "gradle_conflict": r"Conflict\(s\) found for|Cannot find a version of|Could not resolve all artifacts|Dependency resolution is looking for a library compatible with|incompatible because this component declares",
 "plugin_resolve": r"Plugin \S+ or one of its dependencies could not be resolved|Could not resolve plugin|Plugin \[id: [^\]]+\] was not found",
 "lockfile": r"lockfile|dependency lock|--write-locks|Resolved dependencies were missing from the lock",
 "runtime_linkage": r"NoClassDefFoundError|NoSuchMethodError|ClassNotFoundException|NoSuchFieldError|AbstractMethodError",
 "status_401_403": r"(?:status code[: ]+|HTTP[/\d.]*\s+)(?:401|403)\b|Unauthorized|Forbidden",
 "js_deps": r"ERESOLVE|Cannot find module|npm ERR! code E404|ERR_PNPM_",
}
R = {k: re.compile(v, re.M) for k, v in P.items()}
stat = {g: Counter() for g in ("?", "dependency", "infra")}
n, union = Counter(), Counter()
for root in (Path("data/crawl_pr"), Path("data/validate")):
    want = {}
    for r in csv.DictReader(open(root / "gold_labels.csv", encoding="utf-8-sig")):
        if r["non_build"] == "False" and r["gold"] in stat:
            want[(r["repo"].replace("/", "__"), int(r["run_id"]))] = r["gold"]
    for d in root.iterdir():
        f = d / "jobs.jsonl"
        if not f.exists(): continue
        for line in f.open(encoding="utf-8"):
            row = json.loads(line)
            g = want.get((d.name, row["run_id"]))
            if not g: continue
            texts = [(d / "logs" / f"{j['id']}.txt") for j in row["jobs"] if j["conclusion"] == "failure"]
            texts = [diagnostic_text(p.read_text(encoding="utf-8", errors="ignore")) for p in texts if p.exists()]
            if not texts: continue
            n[g] += 1
            t = "\n".join(texts)
            hit = False
            for k, r in R.items():
                if r.search(t):
                    stat[g][k] += 1
                    hit = hit or k != "status_401_403"
            union[g] += hit
print("run có log:", dict(n))
print("run duy nhất khớp >= 1 dạng (không tính 401/403):", dict(union))
for k in P:
    print(f"{k:20s}", {g: stat[g][k] for g in stat})
