"""Gán nhãn tay mù (US-08): đo độ chính xác của bộ quy tắc gán nhãn trên log thật.

  sample : rút mẫu run fail phân tầng theo nhãn quy tắc (kể cả `?`) và trải đều repo; nhãn quy tắc lưu riêng
           (`key.json`), giao diện không đọc file này.
  serve  : trang web trên máy (http://localhost:8765): hiện repo, workflow, job/step fail và log; người gán chọn
           nhãn bằng nút hoặc phím 1–7. Mỗi lần chọn ghi ngay một dòng vào `labels.jsonl` (lần sau cùng được tính).
  adjudicate : vòng phân xử sau vòng mù: chỉ các run mà quy tắc và người khác nhau, lúc này HIỆN nhãn quy tắc + dòng
           bằng chứng; người chọn nhãn đúng cuối cùng (và đánh dấu nếu định nghĩa mơ hồ). Ghi `adjudication.jsonl`.
  eval   : so nhãn người với nhãn quy tắc: precision/recall theo nhãn, ma trận nhầm lẫn, Cohen's kappa (vòng mù);
           nếu đã phân xử thì thêm precision của quy tắc so với nhãn cuối và phân loại bất đồng.

    uv run python -m project3.pipeline.label_ui sample --n 220
    uv run python -m project3.pipeline.label_ui serve
    uv run python -m project3.pipeline.label_ui adjudicate
    uv run python -m project3.pipeline.label_ui eval
"""
import argparse
import csv
import hashlib
import json
import random
import re
import sys
import webbrowser
from collections import Counter, defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOTS = [Path("data/validate"), Path("data/crawl_pr")]
OUT = Path("data/human_labels")
LABELS = ["buildconfig", "compile", "lint", "test", "dependency", "infra", "flaky", "unclear"]
# quota mặc định theo nhãn quy tắc; `?` để đo recall (run quy tắc bỏ sót)
# Gán mù tầng 3 (16/10/2026): người chọn lá theo bảng II Rausch (+ network, flaky); tầng 2 suy từ lá để so với mẫu cũ
LEAVES = ["testfailure", "itestfailure", "buildconfig", "compile", "dependency", "quality", "doc", "license",
          "compatibility", "git", "crash", "androidsdk", "network", "flaky", "unclear"]
QUOTA3 = {"testfailure": 20, "itestfailure": 15, "quality": 15, "license": 8, "doc": 6, "compatibility": 5, "compile": 15,
          "dependency": 10, "buildconfig": 8, "crash": 10, "network": 10, "git": 6, "flaky": 3, "?": 15}
QUOTA = {"test": 45, "compile": 40, "lint": 40, "infra": 35, "dependency": 25, "?": 33, "flaky": 2}
MAX_LOG_CHARS = 60_000


def run_logs(root: Path) -> dict:
    """run_id -> danh sách job fail có log: {name, steps fail, đường dẫn log}."""
    out = {}
    for d in (p for p in root.iterdir() if (p / "jobs.jsonl").exists()):
        for line in (d / "jobs.jsonl").open(encoding="utf-8"):
            r = json.loads(line)
            jobs = []
            for j in r["jobs"]:
                log = d / "logs" / f"{j['id']}.txt"
                if j.get("conclusion") == "failure" and log.exists():
                    jobs.append({"name": j["name"], "log": log.as_posix(),
                                 "failed_steps": [s["name"] for s in j.get("steps", []) if s.get("conclusion") == "failure"]})
            if jobs:
                out[r["run_id"]] = jobs
    return out


def rule_leaf(r: dict, jobs: list[dict]) -> str | None:
    """Lá tầng 3 mà quy tắc gán cho một run (cùng cách với fine_labels), `?` nếu tầng 2 chưa gán."""
    from project3.crawl.fine_labels import subtype
    if r["gold"] == "?":
        return "?"
    return subtype(r["gold"], r.get("evidence", ""), r["workflow"], " ".join(j["name"] for j in jobs))


def sample(n: int, seed: int, roots: list[Path], out: Path, tier3: bool = False) -> None:
    """Rút mẫu phân tầng theo nhãn quy tắc (tầng 2, hoặc lá tầng 3 với tier3) và trải đều repo."""
    out.mkdir(parents=True, exist_ok=True)
    quota = QUOTA3 if tier3 else QUOTA
    pool = defaultdict(list)
    for root in roots:
        logs = run_logs(root)
        for r in csv.DictReader(open(root / "gold_labels.csv", encoding="utf-8-sig")):
            rid = int(r["run_id"])
            if r["non_build"] == "True" or rid not in logs:
                continue
            key = rule_leaf(r, logs[rid]) if tier3 else r["gold"]
            if key not in quota:
                continue
            pool[key].append({"repo": r["repo"], "run_id": rid, "workflow": r["workflow"], "jobs": logs[rid][:2],
                              "rule": r["gold"], "rule3": key})
    rng = random.Random(seed)
    scale = n / sum(quota.values())
    chosen = []
    for lab, q in quota.items():
        by_repo = defaultdict(list)
        for x in pool[lab]:
            by_repo[x["repo"]].append(x)
        for v in by_repo.values():
            rng.shuffle(v)
        repos, k = sorted(by_repo), max(1, round(q * scale))
        rng.shuffle(repos)
        picked = []
        while len(picked) < k and any(by_repo.values()):  # vòng tròn qua các repo cho đa dạng
            for rp in repos:
                if by_repo[rp] and len(picked) < k:
                    picked.append(by_repo[rp].pop())
        chosen += picked
        print(f"  {lab:10} {len(picked):3} / {len(pool[lab])} run, {len({x['repo'] for x in picked})} repo")
    rng.shuffle(chosen)
    items = [{"id": i, **{k: v for k, v in x.items() if k not in ("rule", "rule3")}} for i, x in enumerate(chosen)]
    (out / "sample.json").write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "key.json").write_text(json.dumps({x["run_id"]: x["rule"] for x in chosen}), encoding="utf-8")
    if tier3:  # có key3.json thì giao diện cho chọn lá tầng 3
        (out / "key3.json").write_text(json.dumps({x["run_id"]: x["rule3"] for x in chosen}), encoding="utf-8")
    print(f"Đã lưu {len(items)} mẫu vào {out}/sample.json (nhãn quy tắc ở key.json, giao diện không đọc)")


# ---------------------------------------------------------------- open coding theo cụm (giống LogCat của Rausch, MSR 2017)
CANDIDATE = re.compile(r"##\[error\]|\[ERROR\]|FAILURE:|FAILED|Error:|Exception|error:|What went wrong", re.I)
GENERIC = re.compile(r"Process completed with exit code|^\s*(##\[error\])?\s*$|^\[ERROR\]\s*(-> \[Help \d+\])?$|"
                     r"Re-run Maven using|To see the full stack trace|For more information about the errors", re.I)


def signature(text: str) -> tuple[str, str]:
    """(chữ ký đã chuẩn hoá, dòng gốc) của dòng lỗi đầu tiên có thông tin; Gradle lấy dòng sau 'What went wrong'."""
    from project3.crawl.gold_labels import diagnostic_text
    lines = diagnostic_text(text).splitlines()
    for i, line in enumerate(lines):
        if "What went wrong" in line and i + 1 < len(lines):
            line = lines[i + 1]
        elif not CANDIDATE.search(line):
            continue
        if GENERIC.search(line.replace("##[error]", "").strip()) or GENERIC.search(line):
            continue
        s = re.sub(r"(/[\w.\-@]+)+", "<path>", line)
        s = re.sub(r"\b[0-9a-f]{7,}\b", "<hex>", s)
        s = re.sub(r"\d+", "<n>", s)
        return re.sub(r"\s+", " ", s).strip()[:160], line.strip()[:300]
    return "<không có dòng lỗi>", ""


def suggest_regex(raw: str) -> str:
    """Gợi ý regex từ dòng gốc: giữ chữ, thay số/đường dẫn/hash bằng mẫu chung. Người duyệt sửa lại."""
    if not raw:
        return ""
    raw = raw.replace("##[error]", "").strip()[:100]  # cắt dòng gốc trước khi escape để regex luôn hợp lệ
    raw = re.sub(r"(/[\w.\-@]+)+|\b[0-9a-f]{7,}\b|\d+", "\x00", raw).strip()
    parts = [re.escape(p) for p in raw.split("\x00")]
    rx = re.sub(r"(\\ )+", r"\\s+", "\\S+".join(parts))
    re.compile(rx)
    return rx


def cluster_id(sig: str) -> str:
    return "s" + hashlib.sha1(sig.encode("utf-8")).hexdigest()[:10]


def clusters(out: Path, top: int, samples: int, seed: int) -> None:
    """Gom các run `?` (nhãn quy tắc hiện hành) theo chữ ký dòng lỗi, xếp theo số run giảm dần."""
    rng = random.Random(seed)
    groups = defaultdict(list)
    for root in ROOTS:
        logs = run_logs(root)
        for r in csv.DictReader(open(root / "gold_labels.csv", encoding="utf-8-sig")):
            rid = int(r["run_id"])
            if r["gold"] != "?" or r["non_build"] == "True" or rid not in logs:
                continue
            sig, raw = signature(Path(logs[rid][0]["log"]).read_text(encoding="utf-8", errors="replace"))
            groups[sig].append({"repo": r["repo"], "run_id": rid, "workflow": r["workflow"], "raw": raw,
                                "job": logs[rid][0]})
    total = sum(map(len, groups.values()))
    items, acc = [], 0
    for k, (sig, runs) in enumerate(sorted(groups.items(), key=lambda x: -len(x[1]))[:top]):
        acc += len(runs)
        pick = rng.sample(runs, min(samples, len(runs)))
        # mã cụm theo chữ ký (không theo thứ tự): gom cụm lại không làm nhãn cũ gắn nhầm sang cụm khác cùng thứ tự
        items.append({"id": k, "run_id": cluster_id(sig), "signature": sig, "count": len(runs), "cum_share": round(acc / total, 3),
                      "repos": len({x["repo"] for x in runs}), "repo": f"{len(runs)} run, {len({x['repo'] for x in runs})} repo",
                      "workflow": sig, "regex": suggest_regex(pick[0]["raw"]),
                      "jobs": [{"name": f"{x['repo']} · run {x['run_id']}", "log": x["job"]["log"],
                                "failed_steps": x["job"]["failed_steps"]} for x in pick],
                      "all_runs": [x["run_id"] for x in runs]})
    (out / "clusters.json").write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{total} run `?` có log, {len(groups)} chữ ký; lưu top {len(items)} cụm (phủ {acc / total:.0%}) vào {out}/clusters.json")


_TEXT_CACHE = {}


def sample_text(path: str) -> str:
    """Log đã chuẩn hoá giống bộ quy tắc (bỏ mã màu, timestamp, phần echo lệnh), có cache."""
    if path not in _TEXT_CACHE:
        from project3.crawl.gold_labels import diagnostic_text
        _TEXT_CACHE[path] = diagnostic_text(Path(path).read_text(encoding="utf-8", errors="replace"))
    return _TEXT_CACHE[path]


def export_rules(out: Path) -> None:
    """Quy tắc đề xuất từ open coding: đo độ phủ trên run `?` và kiểm tra hồi quy trên tập người gán."""
    from project3.crawl.gold_labels import diagnostic_text
    decided = current_labels(out, "opencoding.jsonl")
    # thứ tự ưu tiên như GOLD_RULES: loại non_build trước, giai đoạn build sớm thắng giai đoạn muộn
    order = {lab: i for i, lab in enumerate(["non_build", "buildconfig", "compile", "lint", "dependency", "infra", "flaky", "test"])}
    rules = sorted((r for r in decided.values() if r["label"] not in ("unclear",) and r.get("regex")),
                   key=lambda r: (order[r["label"]], -r["count"]))
    excluded = [r for r in decided.values() if r["label"] == "non_build" and not r.get("regex")]
    text = {}

    def log_text(path):
        if path not in text:
            text[path] = diagnostic_text(Path(path).read_text(encoding="utf-8", errors="replace"))
        return text[path]

    unl = []  # run `?` hiện hành
    for root in ROOTS:
        logs = run_logs(root)
        for r in csv.DictReader(open(root / "gold_labels.csv", encoding="utf-8-sig")):
            if r["gold"] == "?" and r["non_build"] != "True" and int(r["run_id"]) in logs:
                unl.append([j["log"] for j in logs[int(r["run_id"])]])
    # nhãn cuối của tập người gán (vòng mù + phân xử) để kiểm tra quy tắc mới không gán sai
    human = {k: v["label"] for k, v in current_labels(out).items()}
    human |= {k: v["label"] for k, v in current_labels(out, "adjudication.jsonl").items()}
    sample = {x["run_id"]: [j["log"] for j in x["jobs"]] for x in json.loads((out / "sample.json").read_text(encoding="utf-8"))}
    report, covered = [], set()
    for r in rules:
        pat = re.compile(r["regex"], re.M)
        hit = {i for i, paths in enumerate(unl) if any(pat.search(log_text(p)) for p in paths)}
        covered |= hit
        conflicts = [rid for rid, paths in sample.items() if rid in human and human[rid] not in (r["label"], "unclear")
                     and any(pat.search(log_text(p)) for p in paths)]
        report.append({"priority": len(report) + 1, "label": r["label"], "regex": r["regex"], "signature": r["signature"],
                       "note": r.get("note", ""),
                       "matches_unlabeled": len(hit), "conflicts_in_human_sample": conflicts})
        print(f"  {r['label']:10} phủ {len(hit):4} run `?`, xung đột với nhãn người: {len(conflicts)}  | {r['regex'][:70]}")
    dest = Path("configs/label_rules_proposed.json")
    dest.write_text(json.dumps({"source": "open coding theo cụm (label_ui opencode)", "rules": report,
                                "non_build_signatures": [r["signature"] for r in excluded]},
                               ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{len(rules)} quy tắc đề xuất phủ {len(covered)}/{len(unl)} run `?` ({len(covered) / max(len(unl), 1):.0%}); "
          f"{len(excluded)} chữ ký đánh dấu non_build. Đã lưu {dest} (chuyển cho bước gán nhãn tích hợp và chạy lại).")


def current_labels(out: Path, name: str = "labels.jsonl") -> dict:
    labels = {}
    if (out / name).exists():
        for line in (out / name).read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            labels[r["run_id"]] = r
    return labels


PAGE = r"""<!doctype html><html lang="vi"><head><meta charset="utf-8"><title>Gán nhãn lỗi CI</title>
<style>
:root{--bg:#f7f8fa;--fg:#1f2328;--mut:#59636e;--line:#d0d7de;--card:#fff;--acc:#013364;--hi:#fff1c2;--err:#ffe3e3}
*{box-sizing:border-box}body{margin:0;font:14px/1.45 system-ui,Segoe UI,Arial;background:var(--bg);color:var(--fg)}
header{display:flex;gap:16px;align-items:center;padding:10px 16px;background:var(--acc);color:#fff}
header b{font-size:16px}#bar{flex:1;height:8px;background:#ffffff40;border-radius:4px}#bar i{display:block;height:100%;background:#7ee2a8;border-radius:4px}
main{display:grid;grid-template-columns:1fr 330px;gap:12px;padding:12px;height:calc(100vh - 48px)}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px;overflow:auto}
#log{white-space:pre;font:12px/1.4 Consolas,monospace;overflow:auto;height:calc(100vh - 230px)}
#log .e{background:var(--err)}#log .k{background:var(--hi)}#log .m{background:#cdeccf;outline:1px solid #2e7d32}
#log div{min-height:1.4em}#log div:hover{background:#eef3fb}#log ::selection{background:#9cc3ff}
#spanbox{margin:6px 0;padding:6px;border:1px dashed var(--line);border-radius:6px;font-size:12px}
#spanbox pre{margin:4px 0 0;max-height:110px;overflow:auto;white-space:pre-wrap;font:11px/1.35 Consolas,monospace}
.meta div{margin:2px 0}.mut{color:var(--mut)}
.btn{display:block;width:100%;text-align:left;margin:4px 0;padding:8px 10px;border:1px solid var(--line);border-radius:6px;background:#fff;cursor:pointer;font:inherit}
.btn:hover{border-color:var(--acc)}.btn.on{background:var(--acc);color:#fff;border-color:var(--acc)}
.btn small{display:block;color:inherit;opacity:.75}
nav{display:flex;gap:6px;margin:8px 0}nav button{flex:1;padding:6px;border:1px solid var(--line);border-radius:6px;background:#fff;cursor:pointer}
textarea{width:100%;height:54px;font:inherit}kbd{border:1px solid var(--line);border-radius:3px;padding:0 4px;background:#f0f0f0;color:#333}
.tabs button{margin-right:4px;padding:3px 8px;border:1px solid var(--line);border-radius:4px;background:#fff;cursor:pointer}.tabs .on{background:var(--acc);color:#fff}
</style></head><body>
<header><b>__TITLE__</b><span id="prog"></span><div id="bar"><i></i></div><span id="saved" class="mut"></span></header>
<main><section class="card"><div class="meta" id="meta"></div><div class="tabs" id="tabs"></div>
<div style="margin:6px 0"><button onclick="jumpErr()">Đến dòng ##[error] đầu tiên <kbd>e</kbd></button>
<label><input type="checkbox" id="hl" checked onchange="render()"> tô đậm dòng error/fail/exception</label></div>
<div id="log"></div></section>
<aside class="card">__EXTRA__<div id="spanbox"></div><div id="btns"></div><textarea id="note" placeholder="Ghi chú (tuỳ chọn)"></textarea>
<nav><button onclick="go(-1)">◀ Trước <kbd>p</kbd></button><button onclick="nextTodo()">Chưa gán tiếp ▶ <kbd>n</kbd></button></nav>
<details><summary>Hướng dẫn gán</summary><ul class="mut">
<li>Chỉ dựa vào log; nếu có nhiều lỗi, chọn <b>giai đoạn sớm nhất</b>: compile → lint → test.</li>
<li><b>compile</b>: lỗi biên dịch (cannot find symbol, Kotlin <code>e:</code>, Scala error, COMPILATION ERROR).</li>
<li><b>lint</b>: format/style/tĩnh: spotless, checkstyle, ktlint, detekt, license/RAT, API compatibility (revapi, japicmp).</li>
<li><b>test</b>: test/assertion fail (Tests run… Failures, There were failing tests).</li>
<li><b>dependency</b>: thiếu artifact/phiên bản (Could not find artifact) mà <i>không</i> có dấu hiệu lỗi mạng.</li>
<li><b>infra</b>: mạng, runner, timeout, hết dung lượng, dịch vụ ngoài lỗi (429/503, connection reset).</li>
<li><b>flaky</b>: log cho thấy test không ổn định (rerun pass, "flaky").</li>
<li><b>unclear</b>: log không đủ để kết luận.</li></ul></details></aside></main>
<script>
const LABELS=__LABELS__, DESC={compile:"lỗi biên dịch",lint:"format / style / license / API",test:"test hoặc assertion fail",
dependency:"thiếu artifact, không do mạng",infra:"mạng, runner, timeout",flaky:"test không ổn định",unclear:"không đủ thông tin",non_build:"không phải build, loại khỏi dữ liệu",
testfailure:"test tự động không đạt",itestfailure:"integration / e2e test không đạt",buildconfig:"cấu hình build sai (pom.xml, script Gradle)",
quality:"vi phạm quy tắc kiểm tra code (format, checkstyle, pmd...)",doc:"tài liệu, javadoc",license:"license / header bản quyền",
compatibility:"không tương thích API (revapi, japicmp)",git:"tương tác VCS (checkout, fetch, push)",
crash:"môi trường sập, hết tài nguyên, quá thời gian",androidsdk:"lỗi Android SDK",network:"lỗi do mạng / dịch vụ ngoài không truy cập được"};
let items=[],labels={},i=0,job=0,logs=[];
async function init(){items=await (await fetch('/api/items')).json();labels=await (await fetch('/api/labels')).json();
document.getElementById('btns').innerHTML=LABELS.map((l,k)=>`<button class="btn" id="b_${l}" onclick="pick('${l}')"><kbd>${k+1}</kbd> <b>${l}</b><small>${DESC[l]}</small></button>`).join('');
const h=decodeURIComponent(location.hash.slice(1)),j=items.findIndex(x=>String(x.run_id)==h);  // mở thẳng mục: /#c4
if(h&&j>=0){i=j;return show();}
nextTodo(true);}
window.addEventListener('hashchange',()=>{const h=location.hash.slice(1),j=items.findIndex(x=>String(x.run_id)==h);if(j>=0){i=j;show();}});
async function show(){const it=items[i];logs=await (await fetch('/api/log?id='+it.id)).json();job=0;
const done=Object.keys(labels).length;document.getElementById('prog').textContent=`#${i+1}/${items.length} · đã gán ${done}`;
document.querySelector('#bar i').style.width=(100*done/items.length)+'%';
document.getElementById('meta').innerHTML=`<div><b>${it.repo}</b> · <span class="mut">${it.workflow}</span> · <a href="https://github.com/${it.repo}/actions/runs/${it.run_id}" target="_blank">mở run trên GitHub</a></div>`+
it.jobs.map(j=>`<div class="mut">job: <b>${esc(j.name)}</b> · step fail: ${esc(j.failed_steps.join(', ')||'—')}</div>`).join('')+
(it.rule?`<div style="margin-top:6px;padding:6px;background:#eef3fb;border-radius:6px">Quy tắc: <b>${it.rule}</b> · Bạn (vòng mù): <b>${it.human}</b><br><span class="mut">bằng chứng của quy tắc: ${esc(it.evidence||'—')}</span></div>`:'');
document.getElementById('tabs').innerHTML=it.jobs.length>1?it.jobs.map((j,k)=>`<button class="${k==0?'on':''}" onclick="job=${k};render()">log job ${k+1}</button>`).join(''):'';
const cur=labels[it.run_id];LABELS.forEach(l=>document.getElementById('b_'+l).classList.toggle('on',cur&&cur.label==l));
document.getElementById('note').value=cur?cur.note||'':'';const a=document.getElementById('amb');if(a)a.checked=!!(cur&&cur.ambiguous);
const rg=document.getElementById('regex');if(rg){rg.value=(cur&&cur.regex)||it.regex||'';testRegex();}
setSpan(cur&&cur.evidence||'');
if(it.count)document.getElementById('meta').innerHTML+=`<div class="mut">cụm phủ ${it.count} run; cộng dồn tới cụm này: ${Math.round(100*it.cum_share)}% run "?"</div>`;
render();jumpErr();}
function esc(s){return s.replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
function jsRegex(){const rg=document.getElementById('regex');if(!rg||!rg.value)return null;try{return new RegExp(rg.value,'gm')}catch(e){return null}}
function render(){const hl=document.getElementById('hl').checked,rx=jsRegex();document.querySelectorAll('#tabs button').forEach((b,k)=>b.classList.toggle('on',k==job));
LINES=(logs[job]||'').split('\n');
// tô xanh mọi dòng nằm trong vùng khớp regex (regex có thể trải nhiều dòng khi bôi đen nhiều dòng)
const hit=new Set();if(rx){const plain=LINES.map(cleanLine),starts=[];let p=0;plain.forEach(x=>{starts.push(p);p+=x.length+1});
const all=plain.join('\n');let m,guard=0;while((m=rx.exec(all))&&guard++<500){const a=m.index,b=a+Math.max(m[0].length,1);
for(let n=0;n<starts.length;n++){if(starts[n]<b&&starts[n]+plain[n].length+1>a)hit.add(n)}if(!m[0].length)rx.lastIndex++;}}
document.getElementById('log').innerHTML=LINES.map((x,n)=>{
const c=hit.has(n)?'m':x.includes('##[error]')?'e':hl&&/error|fail|exception/i.test(x)?'k':'';
return `<div class="${c}" data-n="${n}">${esc(x)||' '}</div>`}).join('');}
// bỏ timestamp, ##[error], mã màu: giống log đã chuẩn hoá mà bộ quy tắc chạy trên đó
function cleanLine(x){return x.replace(/^\S+Z /,'').replace('##[error]','').replace(/\x1b\[[0-9;]*m/g,'')}
function partRegex(x,gen){x=x.trim();if(gen)x=x.replace(/(\/[\w.\-@]+)+|\b[0-9a-f]{7,}\b|\d+/g,'\u0000');
return x.split('\u0000').map(p=>p.replace(/[.*+?^${}()|[\]\\\-]/g,'\\$&')).join('\\S+').replace(/(\\ |\s)+/g,'\\s+');}
// đoạn bôi đen (một phần dòng hoặc nhiều dòng) -> regex; các dòng nối bằng khoảng cách ngắn để chịu được dòng bị lọc
function spanToRegex(text,gen){return text.split('\n').map(cleanLine).map(x=>x.trim()).filter(Boolean).slice(0,6)
.map(x=>partRegex(x.slice(0,200),gen)).join('[\\s\\S]{0,300}?');}
let LINES=[],rxTimer=null,SPAN='';
function setSpan(t){SPAN=t;document.getElementById('spanbox').innerHTML=t?
`<b>Đoạn lỗi đã chọn</b> <a href="#" onclick="setSpan('');return false">bỏ</a><pre>${esc(t)}</pre>`:
'<span class="mut"><b>Bôi đen đoạn lỗi</b> trong log (một phần dòng hoặc nhiều dòng) để làm bằng chứng'+
(document.getElementById('regex')?' và tạo regex; bấm một dòng để lấy cả dòng':'')+'.</span>';}
function useSpan(t){t=t.split('\n').map(cleanLine).join('\n').trim();if(!t)return;setSpan(t.slice(0,2000));
const rg=document.getElementById('regex'),g=document.getElementById('gen');
if(rg){rg.value=spanToRegex(t,!g||g.checked);testRegex();}}
document.getElementById('log').addEventListener('mouseup',()=>setTimeout(()=>{const s=getSelection();
if(!s.isCollapsed&&document.getElementById('log').contains(s.anchorNode))useSpan(s.toString());},0));
document.addEventListener('click',ev=>{const d=ev.target.closest('#log div');
if(d&&getSelection().isCollapsed)useSpan(LINES[+d.dataset.n]);});
document.addEventListener('change',ev=>{if(ev.target.id=='gen'&&SPAN)useSpan(SPAN);});
function testRegex(){clearTimeout(rxTimer);rxTimer=setTimeout(async()=>{const rg=document.getElementById('regex'),out=document.getElementById('rxres');
if(!rg||!out)return;render();if(!rg.value){out.textContent='';return;}
const r=await (await fetch('/api/test?id='+items[i].id+'&rx='+encodeURIComponent(rg.value))).json();
if(r.error){out.innerHTML=`<span style="color:#b00">${esc(r.error)}</span>`;return;}
out.innerHTML=`<b>khớp ${r.matches.filter(m=>m.match).length}/${r.matches.length} log mẫu</b>`+r.matches.map((m,k)=>
`<div class="mut">log ${k+1}: ${m.match?'✔ '+esc(m.line.slice(0,140)):'✘ không khớp'}</div>`).join('');},300);}
document.addEventListener('input',ev=>{if(ev.target.id=='regex')testRegex();});
function jumpErr(){const e=document.querySelector('#log .e');if(e)e.scrollIntoView({block:'center'});}
async function pick(l){const it=items[i];const a=document.getElementById('amb'),rg=document.getElementById('regex');
const body={run_id:it.run_id,label:l,note:document.getElementById('note').value,ambiguous:!!(a&&a.checked),regex:rg?rg.value:'',evidence:SPAN};
const resp=await fetch('/api/label',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
if(!resp.ok){alert((await resp.json()).error);return;}
const res=await resp.json();let msg='đã lưu '+it.run_id;
if(res.auto_covered&&res.auto_covered.length){labels=await (await fetch('/api/labels')).json();msg+=` · quy tắc này tự phủ thêm ${res.auto_covered.length} cụm khác`;}
labels[it.run_id]=body;document.getElementById('saved').textContent=msg;nextTodo();}
function go(d){i=Math.max(0,Math.min(items.length-1,i+d));show();}
function nextTodo(first){for(let k=1;k<=items.length;k++){const j=(first?k-1:i+k)%items.length;if(!labels[items[j].run_id]){i=j;return show();}}
alert('Đã gán hết. Chạy: uv run python -m project3.pipeline.label_ui eval');show();}
document.addEventListener('keydown',ev=>{if(ev.target.tagName=='TEXTAREA')return;const k=parseInt(ev.key);
if(k>=1&&k<=LABELS.length)pick(LABELS[k-1]);else if(ev.key=='n')nextTodo();else if(ev.key=='p')go(-1);else if(ev.key=='e')jumpErr();});
init();
</script></body></html>"""


def disagreements(out: Path) -> list[dict]:
    """Run mà quy tắc gán một nhãn (khác `?`) nhưng người chọn nhãn khác, kèm dòng bằng chứng của quy tắc."""
    key = {int(k): v for k, v in json.loads((out / "key.json").read_text(encoding="utf-8")).items()}
    human = current_labels(out)
    evidence = {}
    for root in ROOTS:
        for r in csv.DictReader(open(root / "gold_labels.csv", encoding="utf-8-sig")):
            evidence[int(r["run_id"])] = r["evidence"]
    items = json.loads((out / "sample.json").read_text(encoding="utf-8"))
    return [{**x, "rule": key[x["run_id"]], "human": human[x["run_id"]]["label"], "evidence": evidence.get(x["run_id"], "")}
            for x in items if x["run_id"] in human and key[x["run_id"]] != "?"
            and tier2(human[x["run_id"]]["label"]) != key[x["run_id"]]]


def tier2(label: str) -> str:
    """Nhãn người ở tầng 2: lá tầng 3 quy về cha, nhãn tầng 2 (mẫu cũ) giữ nguyên."""
    from project3.crawl.fine_labels import PARENT
    return PARENT.get(label, label)


def serve(out: Path, port: int, browser: bool = True, mode: str = "serve") -> None:
    labels = LABELS
    if mode == "adjudicate":
        items, store = disagreements(out), "adjudication.jsonl"
        extra = ('<p class="mut">Chọn nhãn <b>đúng cuối cùng</b> sau khi xem lại log và bằng chứng của quy tắc.</p>'
                 '<label><input type="checkbox" id="amb"> định nghĩa mơ hồ (cả hai cách hiểu đều hợp lý)</label>')
        title = f"Phân xử bất đồng ({len(items)} run)"
    elif mode == "opencode":
        items, store = json.loads((out / "clusters.json").read_text(encoding="utf-8")), "opencoding.jsonl"
        labels = LABELS + ["non_build"]
        extra = ('<p class="mut">Mỗi mục là <b>một cụm</b> run cùng chữ ký lỗi. Xem các log mẫu (tab), sửa regex nếu cần '
                 '(phải khớp đúng loại lỗi, không quá rộng), rồi chọn nhãn. <b>unclear</b> = để trống; '
                 '<b>non_build</b> = không phải build (loại khỏi dữ liệu).</p>'
                 '<p class="mut"><b>Bôi đen đoạn lỗi thật trong log</b> (hoặc bấm một dòng) để tạo regex; '
                 'dòng khớp regex tô xanh.</p>'
                 '<label class="mut"><input type="checkbox" id="gen" checked> thay số / đường dẫn / hash bằng mẫu chung</label>'
                 '<textarea id="regex" style="height:70px;font:12px Consolas,monospace" placeholder="regex"></textarea>'
                 '<div id="rxres" style="font-size:12px;margin-bottom:6px"></div>')
        title = f"Open coding theo cụm ({len(items)} cụm)"
    else:
        items, store, extra = json.loads((out / "sample.json").read_text(encoding="utf-8")), "labels.jsonl", ""
        title = "Gán nhãn lỗi CI (mù)"
        if (out / "key3.json").exists():
            labels = LEAVES
            title = "Gán nhãn lỗi CI tầng 3 – loại lỗi Rausch (mù)"
            extra = ('<p class="mut">Chọn <b>loại lỗi</b> (tầng 3, theo bảng II Rausch; network và flaky là đề tài thêm). '
                     'Nhiều lỗi thì lấy giai đoạn sớm nhất: buildconfig → compile → dependency → lint → test. '
                     'Bôi đen dòng lỗi làm bằng chứng.</p>')
    by_id = {x["id"]: x for x in items}
    by_run = {str(x["run_id"]): x for x in items}
    page = (PAGE.replace("__LABELS__", json.dumps(labels)).replace("__EXTRA__", extra).replace("__TITLE__", title)
            .encode("utf-8"))

    class H(BaseHTTPRequestHandler):
        def send(self, body, ctype="application/json; charset=utf-8", code=200):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.end_headers()
            self.wfile.write(body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8"))

        def do_GET(self):
            if self.path == "/":
                return self.send(page, "text/html; charset=utf-8")
            if self.path == "/api/items":
                return self.send(items)
            if self.path == "/api/labels":
                return self.send(current_labels(out, store))
            if self.path.startswith("/api/test?"):  # thử regex (cú pháp Python, như bộ quy tắc) trên log mẫu của cụm
                from urllib.parse import parse_qs, urlparse
                q = parse_qs(urlparse(self.path).query)
                try:
                    pat = re.compile(q.get("rx", [""])[0], re.M)
                except re.error as e:
                    return self.send({"error": f"regex lỗi: {e}"})
                res = []
                for j in by_id[int(q["id"][0])]["jobs"]:
                    text = sample_text(j["log"])
                    m = pat.search(text)
                    line = text[text.rfind("\n", 0, m.start()) + 1:].split("\n", 1)[0] if m else ""
                    res.append({"match": bool(m), "line": line})
                return self.send({"matches": res})
            if self.path.startswith("/api/log?id="):
                it = by_id[int(self.path.split("=", 1)[1])]
                return self.send([Path(j["log"]).read_text(encoding="utf-8", errors="replace")[-MAX_LOG_CHARS:]
                                  for j in it["jobs"]])
            self.send({"error": "not found"}, code=404)

        def do_POST(self):
            r = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if r.get("label") not in labels:
                return self.send({"error": "nhãn không hợp lệ"}, code=400)
            rec = {"run_id": r["run_id"] if mode == "opencode" else int(r["run_id"]), "label": r["label"],
                   "note": r.get("note", ""), "ambiguous": bool(r.get("ambiguous"))}
            if r.get("evidence"):  # đoạn lỗi người gán bôi đen trong log
                rec["evidence"] = str(r["evidence"])[:2000]
            if mode == "opencode":  # quy tắc đề xuất: regex do người duyệt + cụm nó sinh ra
                c = by_run[str(r["run_id"])]
                if r.get("regex"):
                    try:
                        re.compile(r["regex"])
                    except re.error as e:
                        return self.send({"error": f"regex lỗi: {e}"}, code=400)
                rec |= {"regex": r.get("regex", ""), "signature": c["signature"], "count": c["count"]}
            auto = []
            if mode == "opencode" and rec.get("regex") and rec["label"] != "unclear":
                # thử ngay quy tắc vừa duyệt trên log mẫu của các cụm chưa duyệt: khớp thì coi là đã phủ, bỏ qua
                pat, done = re.compile(rec["regex"], re.M), current_labels(out, store)
                for c in items:
                    if c["run_id"] != rec["run_id"] and c["run_id"] not in done and any(
                            pat.search(sample_text(j["log"])) for j in c["jobs"]):
                        auto.append({"run_id": c["run_id"], "label": rec["label"], "note": f"tự phủ bởi quy tắc của {rec['run_id']}",
                                     "ambiguous": False, "regex": "", "auto": True, "signature": c["signature"],
                                     "count": c["count"]})
            with open(out / store, "a", encoding="utf-8") as f:
                for x in [rec, *auto]:
                    f.write(json.dumps(x, ensure_ascii=False) + "\n")
            if mode == "opencode":
                return self.send({"ok": True, "auto_covered": [x["run_id"] for x in auto]})
            self.send({"ok": True})

        def log_message(self, *a):
            pass

    url = f"http://localhost:{port}"
    print(f"Mở {url}  (Ctrl+C để dừng; nhãn lưu ở {out / store})", flush=True)
    if browser:
        webbrowser.open(url)
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()


def evaluate(out: Path) -> None:
    key = {int(k): v for k, v in json.loads((out / "key.json").read_text(encoding="utf-8")).items()}
    human3 = {k: v["label"] for k, v in current_labels(out).items()}
    human = {k: tier2(v) for k, v in human3.items()}
    pairs = [(human[k], key[k]) for k in human if k in key]
    print(f"{len(pairs)} run đã gán / {len(key)} mẫu")
    if not pairs:
        return
    rule_labels = sorted({r for _, r in pairs} | {h for h, _ in pairs})
    print("\nNhãn quy tắc  → n, precision (người đồng ý với quy tắc)")
    res = {}
    for lab in rule_labels:
        pred = [(h, r) for h, r in pairs if r == lab]
        gold = [(h, r) for h, r in pairs if h == lab]
        prec = sum(h == r for h, r in pred) / len(pred) if pred else None
        rec = sum(h == r for h, r in gold) / len(gold) if gold else None
        res[lab] = {"n_rule": len(pred), "n_human": len(gold), "precision": prec, "recall_in_sample": rec}
        print(f"  {lab:10} n={len(pred):3}  precision={prec if prec is None else round(prec, 3)}  "
              f"recall(trong mẫu)={rec if rec is None else round(rec, 3)}")
    agree = sum(h == r for h, r in pairs) / len(pairs)
    ph, pr = Counter(h for h, _ in pairs), Counter(r for _, r in pairs)
    pe = sum(ph[c] * pr[c] for c in set(ph) | set(pr)) / len(pairs) ** 2
    kappa = (agree - pe) / (1 - pe) if pe < 1 else 1.0
    print(f"\nđồng thuận {agree:.3f}, Cohen's kappa {kappa:.3f}")
    print("\nMa trận nhầm lẫn (dòng = người, cột = quy tắc):")
    cm = Counter(pairs)
    print("            " + " ".join(f"{c[:8]:>8}" for c in rule_labels))
    for h in rule_labels:
        print(f"  {h[:10]:10}" + " ".join(f"{cm[(h, r)]:8}" for r in rule_labels))
    report = {"n": len(pairs), "agreement": agree, "kappa": kappa, "per_label": res,
              "confusion": {f"{h}|{r}": c for (h, r), c in cm.items()}}
    adj = current_labels(out, "adjudication.jsonl")
    if adj:  # nhãn cuối: theo phân xử nếu có, ngược lại nhãn người (người và quy tắc đồng ý, hoặc quy tắc để `?`)
        final = {k: adj[k]["label"] if k in adj else v for k, v in human.items()}
        kinds = Counter()
        for k, v in adj.items():
            kinds["người nhầm" if v["label"] == key[k] else "quy tắc sai" if v["label"] == human[k]
                  else "cả hai sai"] += 1
            kinds["định nghĩa mơ hồ"] += bool(v.get("ambiguous"))
        print(f"\nSau phân xử ({len(adj)} run): " + ", ".join(f"{k} {v}" for k, v in kinds.items()))
        print("Precision của quy tắc so với nhãn cuối:")
        final_prec = {}
        for lab in sorted({key[k] for k in final if key[k] != "?"}):
            ks = [k for k in final if key[k] == lab]
            final_prec[lab] = {"n": len(ks), "precision": sum(final[k] == lab for k in ks) / len(ks)}
            print(f"  {lab:10} n={len(ks):3}  precision={final_prec[lab]['precision']:.3f}")
        q = [k for k in final if key[k] == "?"]
        print(f"Run quy tắc để `?` ({len(q)}): nhãn cuối {dict(Counter(final[k] for k in q))}")
        report["adjudicated"] = {"n": len(adj), "kinds": dict(kinds), "precision_final": final_prec,
                                 "unlabeled_by_rule": dict(Counter(final[k] for k in q))}
    if (out / "key3.json").exists():  # tầng 3: so lá người chọn với lá quy tắc (bỏ run quy tắc để `?`)
        key3 = {int(k): v for k, v in json.loads((out / "key3.json").read_text(encoding="utf-8")).items()}
        p3 = [(human3[k], key3[k]) for k in human3 if key3.get(k) not in (None, "?")]
        if p3:
            a3 = sum(h == r for h, r in p3) / len(p3)
            ph3, pr3 = Counter(h for h, _ in p3), Counter(r for _, r in p3)
            pe3 = sum(ph3[c] * pr3[c] for c in set(ph3) | set(pr3)) / len(p3) ** 2
            k3 = (a3 - pe3) / (1 - pe3) if pe3 < 1 else 1.0
            prec3 = {lab: round(sum(h == lab for h, r in p3 if r == lab) / n, 3) for lab, n in pr3.items()}
            print(f"\nTầng 3 ({len(p3)} run): đồng thuận {a3:.3f}, kappa {k3:.3f}; precision theo lá {prec3}")
            report["tier3"] = {"n": len(p3), "agreement": a3, "kappa": k3, "precision": prec3,
                               "confusion": {f"{h}|{r}": c for (h, r), c in Counter(p3).items()}}
    (out / "eval.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nĐã lưu {out / 'eval.json'}. Recall chỉ tính trong mẫu phân tầng, chưa phải recall toàn tập.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["sample", "serve", "adjudicate", "eval", "clusters", "opencode", "rules"])
    ap.add_argument("--top", type=int, default=150, help="clusters: số cụm lớn nhất đưa vào open coding")
    ap.add_argument("--samples", type=int, default=4, help="clusters: số log mẫu mỗi cụm")
    ap.add_argument("--n", type=int, default=220)
    ap.add_argument("--seed", type=int, default=20261011)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--tier3", action="store_true", help="sample: phân tầng và gán theo lá tầng 3 (loại lỗi Rausch)")
    a = ap.parse_args()
    if a.cmd == "sample":
        sample(a.n, a.seed, ROOTS, a.out, a.tier3)
    elif a.cmd in ("serve", "adjudicate", "opencode"):
        serve(a.out, a.port, not a.no_browser, a.cmd)
    elif a.cmd == "clusters":
        clusters(a.out, a.top, a.samples, a.seed)
    elif a.cmd == "rules":
        export_rules(a.out)
    else:
        evaluate(a.out)
