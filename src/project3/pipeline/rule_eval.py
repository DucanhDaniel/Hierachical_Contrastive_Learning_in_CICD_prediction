"""Offline dependency-rule review. Never calls relabel or writes source datasets.

python -B -m project3.pipeline.rule_eval --out data/rule_eval/dependency-20261018
Use --inventory-only to discover signals using the frozen CSV labels first.
"""
import argparse
import csv
import hashlib
import json
import random
import re
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from project3.crawl import gold_labels as gold
from project3.crawl.build_log_labels import PRIORITY
from project3.crawl.fine_labels import PARENT, subtype

SIGNALS = {
    "resolve_summary": r"Could not resolve dependencies|Could not resolve all (?:files|dependencies|artifacts)|could not be resolved|Non-resolvable (?:parent|import) POM|Unresolveable build extension",
    "artifact_descriptor": r"Failed to read artifact descriptor",
    "transfer": r"Could not transfer artifact|Could not GET|Could not HEAD",
    "enforcer": r"RequireUpperBoundDeps|Require upper bound dependencies|DependencyConvergence|BannedDependencies|dependency convergence|Used undeclared dependencies|Non-test scoped test only dependencies",
    "jdk_version": r"UnsupportedClassVersionError|Unsupported class file major version|class file has wrong version|invalid target release|release version \d{1,3} not supported|has been compiled by a more recent version",
    "gradle_conflict": r"No matching variant|Conflict\(s\) found for|Cannot find a version of|incompatible because this component declares",
    "plugin_resolve": r"Plugin \S{1,200} or one of its dependencies could not be resolved|Could not resolve plugin|Plugin \[id: [^\]\n]{1,400}\] was not found",
    "lockfile": r"lockfile|dependency lock|--write-locks|Resolved dependencies were missing from the lock",
    "runtime_linkage": r"NoClassDefFoundError|NoSuchMethodError|ClassNotFoundException|NoSuchFieldError|AbstractMethodError|IncompatibleClassChangeError",
    "status_401_403": r"(?:status code[: ]{1,8}|error code[: ]{1,8}|HTTP[/\d.]{0,10}\s{1,8})(?:401|403)\b|Unauthorized|Forbidden",
    "js_deps": r"ERESOLVE|Cannot find module|npm ERR! code E404|ERR_PNPM_",
}
SIGNAL_RX = {k: re.compile(v, re.M) for k, v in SIGNALS.items()}
CORE = [(label, re.compile(pattern, re.M)) for label, pattern in gold.GOLD_RULES]
# Từ 2026-10-18 file quy tắc có lớp q3_override và quy tắc tắt (enabled=false): trace chỉ đọc lớp dự phòng đang bật,
# lớp Q3 hiện hành áp bằng current_decision() để khớp gold_label.
FALLBACK = sorted((r for r in json.loads(gold.FALLBACK_RULES_PATH.read_text(encoding="utf-8"))["rules"]
                   if r.get("enabled", True) and r.get("layer") != "q3_override"), key=lambda r: r["priority"])


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class Output:
    def __init__(self, directory):
        self.root = Path(directory).resolve()
        workspace = Path.cwd().resolve()
        # Keep all audit writes in a dedicated area, including tests and subprocesses.
        if not self.root.is_relative_to(workspace / "data" / "rule_eval") or self.root == workspace / "data" / "rule_eval":
            raise ValueError("Output must be a new subdirectory of data/rule_eval")
        self.root.mkdir(parents=True, exist_ok=False)

    def path(self, name):
        p = (self.root / name).resolve()
        if not p.is_relative_to(self.root):
            raise ValueError("Output escapes audit directory")
        return p

    def json(self, name, value):
        self.path(name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

    def csv(self, name, rows, fields):
        with self.path(name).open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)


@dataclass(frozen=True)
class Decision:
    label: str
    evidence: str = ""
    job: int | None = None
    rule: str = ""


def trace(jobs, fallback=None):
    """Exact original rule/job/match traversal; job evidence is preserved."""
    unresolved = ""
    for index, (lab, pattern) in enumerate(CORE):
        for j, text in enumerate(jobs):
            for match in pattern.finditer(text):
                if lab == "resolution":
                    context = gold.resolution_context(text, match)
                    net, missing = gold.NETWORK.search(context), gold.MISSING_ARTIFACT.search(context)
                    if net:
                        return Decision("infra", gold.evidence_line(context, net), j, "resolution")
                    if missing:
                        return Decision("dependency", gold.evidence_line(context, missing), j, "resolution")
                    unresolved = unresolved or gold.evidence_line(text, match)
                    continue
                if lab == "dependency":
                    context = gold.resolution_context(text, match)
                    net = gold.NETWORK.search(context)
                    if net:
                        return Decision("infra", gold.evidence_line(context, net), j, "dependency-network")
                return Decision(lab, gold.evidence_line(text, match), j, f"core:{index}:{lab}")
    for row, pattern in (fallback if fallback is not None else BASE_FALLBACK):
        for j, text in enumerate(jobs):
            if row.get("hints") and not any(h in text for h in row["hints"]):
                continue
            match = gold.first_match(pattern, row.get("guard"), text)
            if match:
                return Decision(row["label"], gold.evidence_line(text, match), j, row.get("id", f"fallback:{row['priority']}"))
    return Decision("?", unresolved)


BASE_FALLBACK = [(r, re.compile(r["regex"], re.M)) for r in FALLBACK]


def current_decision(jobs):
    """trace + lớp Q3 hiện hành của gold_label (job quyết định cho compile/test, mọi job cho `?`)."""
    base = trace(jobs)
    if base.label not in ("compile", "test", "?"):
        return base
    for pattern, guard in gold.Q3_RULES:
        for j in (range(len(jobs)) if base.label == "?" else [base.job]):
            if m := gold.first_match(pattern, guard, jobs[j]):
                return Decision("dependency", gold.evidence_line(jobs[j], m), j, "q3-current")
    return base


def guard_matches(row, text, match):
    guard = row.get("guard")
    context = gold.resolution_context(text, match)
    if guard == "no_network":
        return not gold.NETWORK.search(context)
    if guard == "network_context":
        return bool(gold.NETWORK.search(context))
    if guard == "missing_artifact_context":
        return not gold.NETWORK.search(context) and "Searched in the following locations" in context
    if guard == "plugin_missing_context":
        return not gold.NETWORK.search(context) and bool(re.search(r"Could not find|Searched in the following locations|(?:status code[: ]{1,8}|HTTP[/\d.]{0,10}\s{1,8})404\b",context))
    if guard == "missing_class_failure":
        following = "\n".join(text[match.start():].splitlines()[:60])
        class_name = match.group(1).replace("/", ".")
        cause = re.search(r"Caused by: java\.lang\.ClassNotFoundException: " + re.escape(class_name) + r"(?:\s|$)", following)
        if not cause:
            return False
        tail = "\n".join(following[cause.end():].splitlines()[:30])
        return "Caused by:" not in tail and bool(re.search(r"BUILD FAILED|<<< (?:ERROR|FAILURE)!", tail))
    if guard == "failure_context":
        before = "\n".join(text[:match.start()].splitlines()[-20:])
        return bool(re.search(r"Exception in thread|<<< (?:ERROR|FAILURE)!|Failed to execute goal|Execution failed for task|FAILURE: Build failed",before+context))
    return True


def apply_q3(base, jobs, rules):
    if base.label not in ("compile", "test", "?"):
        return base
    indices = range(len(jobs)) if base.label == "?" else [base.job]
    for row, rx in rules:
        for j in indices:
            if j is None:
                continue
            if row.get("hints") and not any(h in jobs[j] for h in row["hints"]):
                continue
            for m in rx.finditer(jobs[j]):
                if not guard_matches(row, jobs[j], m):
                    continue
                return Decision("dependency", gold.evidence_line(jobs[j], m), j, row["id"])
    return base


def proposed_decision(base, jobs, fallback, rules, q3):
    # Replacing fallback decisions is intentional for Q1; primary precedence stays intact.
    candidate = trace(jobs, fallback) if base.rule.startswith("fallback:") or base.label == "?" else base
    for row, rx in rules:
        if candidate.label not in row.get("applies_to", ["?"]):
            continue
        indices = [candidate.job] if candidate.label != "?" else range(len(jobs))
        for j in indices:
            if j is None:
                continue
            if row.get("hints") and not any(h in jobs[j] for h in row["hints"]):
                continue
            for m in rx.finditer(jobs[j]):
                if not guard_matches(row, jobs[j], m):
                    continue
                candidate = Decision(row["label"], gold.evidence_line(jobs[j], m), j, row["id"])
                break
            else:
                continue
            break
    return apply_q3(candidate, jobs, q3)


def iter_scope(scope):
    groups = defaultdict(dict)
    seen = set()
    with Path(scope).open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            key = (row["repo"], int(row["run_id"]))
            if key in seen:
                raise ValueError(f"Duplicate scoped run {key}")
            seen.add(key)
            if row["root"] not in ("data/crawl_pr", "data/validate") or ".." in row["repo"] or len(row["repo"].split("/")) != 2:
                raise ValueError(f"Invalid scope row {row}")
            groups[(row["root"], row["repo"])][key[1]] = row
    for (root, repo), wanted in groups.items():
        d = Path(root) / repo.replace("/", "__")
        runs = {r["id"]: r for r in map(json.loads, (d / "runs.jsonl").read_text(encoding="utf-8").splitlines()) if r["id"] in wanted}
        jobs = {}
        jf = d / "jobs.jsonl"
        if jf.exists():
            with jf.open(encoding="utf-8") as f:
                for line in f:
                    r = json.loads(line)
                    if r["run_id"] in wanted:
                        jobs[r["run_id"]] = r["jobs"]  # same last-record semantics as relabel
        for rid, row in wanted.items():
            if rid not in runs:
                raise ValueError(f"Missing run metadata {repo}:{rid}")
            run = runs[rid]
            all_jobs = jobs.get(rid, [])
            failed = [j for j in all_jobs if j.get("conclusion") == "failure" and not gold.AGG_JOB.search(j["name"])]
            paths = [d / "logs" / f"{j['id']}.txt" for j in failed]
            available = [(j, p) for j, p in zip(failed, paths) if p.exists()]
            yield row, run, all_jobs, available, [str(p) for p in paths if not p.exists()]


def human_references():
    """Keep independent sources separate; cluster decisions are never integrated."""
    h = Path("data/human_labels")
    refs = defaultdict(list)
    for folder, tier in [(h, 2), (h / "blind3", 3)]:
        merged = {}
        for name in ("labels.jsonl", "adjudication.jsonl"):
            p = folder / name
            if p.exists():
                for line in p.read_text(encoding="utf-8").splitlines():
                    r = json.loads(line)
                    merged[int(r["run_id"])] = (r["label"], str(p))
        for rid, (lab, source) in merged.items():
            refs[rid].append({"label": lab, "tier": tier, "source": source})
    clusters = json.loads((h / "clusters.json").read_text(encoding="utf-8"))
    by_id = {r["id"]: r for r in clusters}
    for name in ("round3_decisions.json", "round4_decisions.json"):
        for r in json.loads((h / name).read_text(encoding="utf-8"))["decisions"]:
            if not r.get("use") or r.get("human") in (None, "unclear", "?"):
                continue
            if r["cluster"] not in by_id:
                raise ValueError(f"Missing cluster {r['cluster']} for {name}")
            for rid in by_id[r["cluster"]]["all_runs"]:
                refs[int(rid)].append({"label": r["human"], "tier": 2, "source": name, "cluster": r["cluster"]})
    return refs


def prepare_run(item):
    row, run, all_jobs, available, absent = item
    started = time.perf_counter()
    raw = [p.read_text(encoding="utf-8", errors="ignore") for _, p in available]
    jobs = [gold.diagnostic_text(x) for x in raw]
    base = current_decision(jobs)
    original = gold.gold_label(raw) if raw else ("?", "")
    if (base.label, base.evidence) != original:
        raise AssertionError(f"Trace parity error {row['repo']}:{row['run_id']}: {base} != {original}")
    return item, jobs, base, time.perf_counter()-started


def prepared_scope(scope, workers):
    if workers:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            yield from pool.map(prepare_run, iter_scope(scope), buffersize=workers*2)
    else:
        for item in iter_scope(scope):
            yield item, None, None, 0


def main(scope, proposed, directory, inventory_only=False, seed=20261018, workers=0):
    start = time.perf_counter()
    out = Output(directory)
    out.path("rule_eval.input.py").write_bytes(Path(__file__).read_bytes())
    if proposed:
        out.path("proposal.input.json").write_bytes(Path(proposed).read_bytes())
    refs = human_references()
    proposal = json.loads(Path(proposed).read_text(encoding="utf-8")) if proposed else {"rules": []}
    rules = proposal["rules"]
    allowed = {"dependency", "infra", "compile", "buildconfig", "lint", "test", "flaky", "non_build"}
    if len({r["id"] for r in rules}) != len(rules):
        raise ValueError("Duplicate proposal rule id")
    for r in rules:
        if r["label"] not in allowed:
            raise ValueError(f"Invalid tier-2 label {r['label']}")
    q3 = [(r, re.compile(r["regex"], re.M)) for r in rules if r.get("layer") == "q3_override" and r.get("enabled", True)]
    extra = [(r, re.compile(r["regex"], re.M)) for r in rules if r.get("layer") not in ("q3_override", "fallback_replace") and r.get("enabled", True)]
    replacements = {r["replaces_priority"]: r for r in rules if r.get("layer") == "fallback_replace" and r.get("enabled", True)}
    fallback = [(replacements.get(r["priority"], r), re.compile(replacements.get(r["priority"], r)["regex"], re.M)) for r in FALLBACK]
    csv_labels = {}
    for root in ("data/crawl_pr", "data/validate"):
        with (Path(root) / "gold_labels.csv").open(encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                csv_labels[(root, r["repo"], int(r["run_id"]))] = r
    scope_manifest = json.loads(Path(scope).with_suffix(".manifest.json").read_text(encoding="utf-8"))
    if sha(scope) != scope_manifest["scope_sha256"]:
        raise ValueError("Frozen scope hash mismatch")
    csv_drift = {root: sha(Path(root) / "gold_labels.csv") != expected for root, expected in scope_manifest["gold_labels_csv_sha256"].items()}
    if any(csv_drift.values()):
        print(f"WARNING: CSV input drift {csv_drift}; full evaluation recomputes labels from logs", flush=True)
    rng = random.Random(seed)
    pools, pool_counts = defaultdict(list), Counter()
    clusters, signal_counts, union = {}, Counter(), Counter()
    rule_hits, rule_unknown, rule_examples = Counter(), Counter(), defaultdict(list)
    matrix, leaf_matrix, labels_count = Counter(), Counter(), Counter()
    conflicts, missing, read_paths, changes, drift = [], [], set(), [], []
    commits = defaultdict(list)
    count = nonbuild_count = parity_errors = 0
    slow = []
    limited = []
    snapshot = {"scope": sha(scope), "gold_labels.py": sha(gold.__file__), "label_rules.json": sha(gold.FALLBACK_RULES_PATH), "fine_labels.py": sha(Path(__file__).parents[1] / "crawl/fine_labels.py")}
    with out.path("run_results.jsonl").open("w", encoding="utf-8") as results:
        for item, prepared_jobs, prepared_base, prepare_seconds in prepared_scope(scope, workers if not inventory_only else 0):
            row, run, all_jobs, available, absent = item
            t = time.perf_counter()
            rid, repo = int(row["run_id"]), row["repo"]
            raw = [p.read_text(encoding="utf-8", errors="ignore") for _, p in available] if prepared_jobs is None else None
            jobs = [gold.diagnostic_text(x) for x in raw] if prepared_jobs is None else prepared_jobs
            read_paths.update(p.as_posix() for _, p in available)
            if absent or not available:
                missing.append({"repo": repo, "run_id": rid, "missing_paths": absent, "no_available_logs": not available})
            stored = csv_labels.get((row["root"], repo, rid), {})
            base = Decision(stored.get("gold", "?"), stored.get("evidence", ""), rule="csv-inventory") if inventory_only else (prepared_base or trace(jobs))
            if not inventory_only and prepared_base is None:
                original = gold.gold_label(raw) if raw else ("?", "")
                if (base.label, base.evidence) != original:
                    parity_errors += 1
                    raise AssertionError(f"Trace parity error {repo}:{rid}: {base} != {original}")
            if not jobs:
                base = Decision("(không có log)")
            is_nonbuild = bool(gold.NON_BUILD_WF.search(run.get("name") or "")) or base.label == "non_build"
            nonbuild_count += is_nonbuild
            q = apply_q3(base, jobs, q3)
            full = proposed_decision(base, jobs, fallback, extra, q3) if not inventory_only else base
            decisions = [base, q, full]
            names = " ".join(j["name"] for j in all_jobs if j.get("conclusion") == "failure")
            leaves = [subtype(d.label, d.evidence, run.get("name") or "", names) for d in decisions]
            nonbuilds = [bool(gold.NON_BUILD_WF.search(run.get("name") or "")) or d.label == "non_build" for d in decisions]
            record = {"repo": repo, "root": row["root"], "run_id": rid, "workflow": run.get("name"), "labels": [d.label for d in decisions], "leaves": leaves, "evidence": [d.evidence for d in decisions], "rules": [d.rule for d in decisions], "job": base.job, "non_build": nonbuilds, "paths": [p.as_posix() for _, p in available]}
            results.write(json.dumps(record, ensure_ascii=False) + "\n")
            if not inventory_only and stored and (base.label != stored.get("gold")):
                drift.append({"run_id": rid, "repo": repo, "csv": stored.get("gold"), "recomputed": base.label})
            if q.label != base.label and not (base.label in ("compile", "test", "?") and q.label == "dependency"):
                raise AssertionError("Q3 transition outside approved scope")
            for a, b, title in ((0, 1, "baseline_to_q3"), (0, 2, "baseline_to_full"), (1, 2, "q3_to_full")):
                if not nonbuilds[a] or not nonbuilds[b]:
                    matrix[(title, decisions[a].label, decisions[b].label)] += 1
                    leaf_matrix[(title, str(leaves[a]), str(leaves[b]))] += 1
                if decisions[a] != decisions[b] and (decisions[a].label != decisions[b].label or leaves[a] != leaves[b]):
                    changes.append({"comparison": title, "repo": repo, "run_id": rid, "old": decisions[a].label, "new": decisions[b].label, "old_leaf": leaves[a], "new_leaf": leaves[b], "old_evidence": decisions[a].evidence, "new_evidence": decisions[b].evidence, "rule": decisions[b].rule})
            for i, d in enumerate(decisions):
                if not nonbuilds[i]:
                    labels_count[(str(i), d.label)] += 1
            for ref in refs.get(rid, []):
                if ref["label"] in ("unclear", "?"):
                    continue
                observed = [d.label for d in decisions] if ref["tier"] == 2 else leaves
                if any(x != ref["label"] for x in observed):
                    conflicts.append({"repo": repo, "run_id": rid, **ref, "baseline": observed[0], "q3": observed[1], "full": observed[2], "introduced": observed[0] == ref["label"] and observed[2] != ref["label"]})
            seq = f"pr:{run.get('head_repository') or repo}:{run.get('head_branch')}" if run.get("event", "").startswith("pull_request") else "push"
            commits[(repo, seq, run["head_sha"])].append((decisions, leaves, nonbuilds))
            if not is_nonbuild and jobs:
                hits = {}
                for key, rx in SIGNAL_RX.items():
                    found = next(((j, m) for j, text in enumerate(jobs) if (m := rx.search(text))), None)
                    if found:
                        hits[key] = found
                        signal_counts[(base.label, key)] += 1
                if any(k != "status_401_403" for k in hits):
                    union[base.label] += 1
                groups = []
                if base.label == "dependency":
                    groups.append("dependency/" + base.rule)
                if base.label == "infra" and "resolve_summary" in hits:
                    groups.append("infra/resolve_summary")
                if base.label == "infra" and "status_401_403" in hits:
                    groups.append("infra/status_401_403")
                groups += ["signal/" + k + "/" + base.label for k in hits]
                for group in groups:
                    key = group.split("/")[1] if group.startswith("signal/") else ("status_401_403" if group.endswith("401_403") else "resolve_summary")
                    j, m = hits.get(key, next(iter(hits.values()), (0, None)))
                    if m:
                        lo = jobs[j].rfind("\n", 0, m.start())
                        excerpt = jobs[j][max(0, lo - 600):m.end() + 2400]
                        line = gold.evidence_line(jobs[j], m)
                    else:
                        excerpt, line = jobs[j][-3200:], base.evidence
                    sample = {"group": group, "repo": repo, "run_id": rid, "label": base.label, "rule": base.rule, "evidence": base.evidence, "path": available[j][1].as_posix(), "excerpt": excerpt, "signal_line": line}
                    pool_counts[group] += 1
                    pool = pools[group]
                    if len(pool) < 30:
                        pool.append(sample)
                    else:
                        k = rng.randrange(pool_counts[group])
                        if k < 30:
                            pool[k] = sample
                if base.label == "?":
                    for key, (j, m) in hits.items():
                        signature = gold.evidence_line(jobs[j], m)
                        signature = re.sub(r"\d{2,}", "<n>", signature)
                        signature = re.sub(r"https?://\S{1,400}", "<url>", signature)
                        ck = (key, signature)
                        c = clusters.setdefault(ck, {"signal": key, "signature": signature, "count": 0, "examples": []})
                        c["count"] += 1
                        if len(c["examples"]) < 3:
                            c["examples"].append({"run_id": rid, "repo": repo, "path": available[j][1].as_posix(), "excerpt": jobs[j][max(0, m.start()-300):m.end()+1600]})
                for rule in rules:
                    rx = re.compile(rule["regex"], re.M)
                    found = next(((j, m) for j, text in enumerate(jobs) if (not rule.get("hints") or any(h in text for h in rule["hints"])) and (m := rx.search(text))), None)
                    if found:
                        rule_hits[rule["id"]] += 1
                        rule_unknown[rule["id"]] += base.label == "?"
                        if len(rule_examples[rule["id"]]) < 15:
                            j, m = found
                            rule_examples[rule["id"]].append({"run_id": rid, "repo": repo, "label": base.label, "path": available[j][1].as_posix(), "excerpt": jobs[j][max(0,m.start()-350):m.end()+1800]})
                if q3 and base.label in ("compile", "test") and q == base:
                    other = apply_q3(Decision("?"), jobs, q3)
                    if other.label == "dependency":
                        limited.append({"repo": repo, "run_id": rid, "label": base.label, "deciding_job": base.job, "q3_job": other.job, "evidence": other.evidence})
            count += 1
            slow.append((round(time.perf_counter()-t+prepare_seconds, 4), rid, repo))
            slow = sorted(slow, reverse=True)[:20]
            if count % 1000 == 0:
                print(f"{count} runs, {(time.perf_counter()-start)/60:.1f} min, {repo}", flush=True)
                out.json("progress.json", {"runs":count,"repo":repo,"elapsed_seconds":round(time.perf_counter()-start,2)})
                out.json("samples.partial.json", dict(pools))
    commit_changes, commit_matrix = [], Counter()
    for (repo, seq, head_sha), runs in commits.items():
        states = []
        for i in range(3):
            known = [lab for lab in PRIORITY if any(not nb[i] and ds[i].label == lab for ds, ls, nb in runs)]
            included = any(not nb[i] for ds, ls, nb in runs)
            lab = known[0] if known else ("?" if included else "(excluded)")
            leaf = Counter(ls[i] for ds, ls, nb in runs if not nb[i] and ds[i].label == lab and ls[i]).most_common(1)
            states.append((lab, leaf[0][0] if leaf else None))
        for a, b, title in ((0,1,"baseline_to_q3"),(0,2,"baseline_to_full"),(1,2,"q3_to_full")):
            commit_matrix[(title, str(states[a]), str(states[b]))] += 1
            if states[a] != states[b]:
                commit_changes.append({"comparison": title, "repo": repo, "sequence": seq, "head_sha": head_sha, "old": states[a][0], "new": states[b][0], "old_leaf": states[a][1], "new_leaf": states[b][1]})
    out.csv("run_changes.csv", changes, ["comparison","repo","run_id","old","new","old_leaf","new_leaf","old_evidence","new_evidence","rule"])
    out.csv("commit_changes.csv", commit_changes, ["comparison","repo","sequence","head_sha","old","new","old_leaf","new_leaf"])
    out.json("human_conflicts.json", conflicts)
    out.json("samples.json", dict(pools))
    out.json("sample_population.json", dict(pool_counts))
    out.json("clusters.json", sorted(clusters.values(), key=lambda x: -x["count"]))
    out.json("rule_examples.json", dict(rule_examples))
    out.json("csv_drift.json", drift)
    out.json("missing_logs.json", missing)
    out.json("q3_other_job_limit.json", limited)
    out.path("log_paths.txt").write_text("\n".join(sorted(read_paths))+"\n",encoding="utf-8")
    summary = {"mode": "inventory_csv_labels" if inventory_only else "full_evaluation", "runs": count, "non_build": nonbuild_count, "seed": seed,
               "labels": {f"{a}:{b}": n for (a,b),n in labels_count.items()}, "signal_counts": {f"{a}:{b}":n for (a,b),n in signal_counts.items()}, "signal_union": dict(union),
               "run_matrix": {"|".join(k):v for k,v in matrix.items()}, "leaf_matrix": {"|".join(k):v for k,v in leaf_matrix.items()}, "commit_matrix": {"|".join(k):v for k,v in commit_matrix.items()},
               "rule_hits": dict(rule_hits), "rule_unknown_hits": dict(rule_unknown), "parity_errors": parity_errors, "slowest": slow,
               "elapsed_seconds": round(time.perf_counter()-start,2), "q3_other_job_limit": len(limited), "human_conflict_records": len(conflicts), "new_human_conflicts": sum(r["introduced"] for r in conflicts),
               "commit_scope_note": "Only scoped failed runs; commit counts are estimates, missing successful/non-scoped runs. Key is (repo, sequence, head_sha)."}
    out.json("summary.json", summary)
    after = {"scope":sha(scope), "gold_labels.py":sha(gold.__file__), "label_rules.json":sha(gold.FALLBACK_RULES_PATH), "fine_labels.py":sha(Path(__file__).parents[1] / "crawl/fine_labels.py")}
    if snapshot != after:
        raise RuntimeError("Inputs changed during evaluation")
    out.json("manifest.json", {"scope":str(scope),"input_hashes":snapshot,"proposal_hash":sha(proposed) if proposed else None,"scope_manifest_hash":sha(Path(scope).with_suffix('.manifest.json')),"csv_drift":csv_drift,"log_count":len(read_paths),"log_paths_sha256":sha(out.path('log_paths.txt')),"elapsed_seconds":summary['elapsed_seconds'],"missing_runs":len(missing),"status":"completed","inventory_only":inventory_only})
    print(json.dumps({"output":str(out.root),"runs":count,"seconds":summary["elapsed_seconds"]}),flush=True)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scope", type=Path, default=Path("data/rule_eval/scope_r1_20261018.csv"))
    ap.add_argument("--proposed", type=Path)
    ap.add_argument("--out", type=Path, default=Path("data/rule_eval/dependency-20261018"))
    ap.add_argument("--inventory-only", action="store_true")
    ap.add_argument("--seed", type=int, default=20261018)
    ap.add_argument("--workers", type=int, default=0, help="Parallel read/normalize/classify workers; zero runs inline")
    args = ap.parse_args()
    main(args.scope, args.proposed, args.out, args.inventory_only, args.seed, args.workers)
