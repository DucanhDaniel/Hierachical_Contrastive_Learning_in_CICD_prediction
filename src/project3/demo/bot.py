"""Bot phân tích CI lỗi trên pull request, kiểu CodeRabbit (17/11/2026).

Chế độ phân tích (workflow ci-triage.yml, khi workflow Build của một PR lỗi):
  1. tải run + log job lỗi (GITHUB_TOKEN của Actions)          -> predict.fetch_run
  2. mô hình phân loại (CPU) + dòng nguyên nhân               -> predict.Predictor (weight tải từ Kaggle)
  3. Claude Code CHỈ ĐỌC code ở commit lỗi (gói Claude, CLAUDE_CODE_OAUTH_TOKEN) -> agent.run: nguyên nhân, cách sửa,
     thay đổi đề xuất dạng thay chuỗi (edits)
  4. người nên xử lý theo QUY TẮC (không để AI đoán tên người) -> assignee()
  5. bình luận vào PR (sửa bình luận cũ nếu có) + gợi ý sửa trên dòng code nằm trong PR (GitHub hiện nút
     "Commit suggestion") + ô "Tạo pull request sửa lỗi" cho loại lỗi được phép (compile, quality, license, doc)
Chế độ sửa (--fix, workflow ci-fix.yml, khi người có quyền ghi tick ô đó): áp ĐÚNG các thay đổi đã đề xuất (lưu trong
bình luận) lên nhánh mới từ nhánh của PR, mở pull request vào nhánh đó. Agent không bao giờ ghi file.

Người nên xử lý: Dự án = tác giả PR nếu file nghi ngờ nằm trong thay đổi của PR -> chủ file theo CODEOWNERS -> người
sửa gần nhất file -> tác giả PR; Cấu hình CI = người sửa gần nhất file workflow (bỏ bot) -> `ci` trong cấu hình nhóm;
Hạ tầng ngoài = gợi ý chạy lại + `infra`. Mặc định KHÔNG @nhắc tên (`mention: true` trong .github/ci-triage.json).
"""
import argparse
import base64
import fnmatch
import json
import os
import re
import sys
from pathlib import Path

MARK = "<!-- p3-ci-triage -->"
FIX_RE = re.compile(r"<!-- p3-fix:([A-Za-z0-9+/=]+) -->")
BOX = "**Tạo pull request sửa lỗi**"
BOT = ("[bot]", "dependabot", "github-actions", "renovate")
MC = 5  # số lần đoán lại (MC Dropout) trên CPU — ít hơn demo (20) để nhanh; tự đặt
FIX_LEAVES = {"compile", "quality", "license", "doc"}  # loại lỗi bot được mở PR sửa (đề xuất 17/11, người dùng duyệt)
LANG = {"vi": "Vietnamese", "en": "English"}


def gh_token() -> str:
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GITHUB_ACCESS_TOKEN") or ""


def api(method: str, path: str, **body):
    import requests
    r = requests.request(method, "https://api.github.com" + path, timeout=60, json=body or None,
                         headers={"Authorization": f"Bearer {gh_token()}", "Accept": "application/vnd.github+json"})
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {path}: {r.status_code} {r.text[:300]}")
    return r.json() if r.text else {}


def esc(t) -> str:
    """Chữ của agent có <version>, <dependency>... -> GitHub hiểu là thẻ HTML và giấu đi; trong `code` giữ nguyên."""
    import html
    return "`".join(x if k % 2 else html.escape(x, quote=False) for k, x in enumerate(str(t).split("`")))


def is_bot(login: str) -> bool:
    return not login or any(b in login.lower() for b in BOT)


# ---------------------------------------------------------------- người nên xử lý
def codeowners(gh, repo: str, sha: str) -> list:
    for p in (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"):
        try:
            c = gh.get(f"/repos/{repo}/contents/{p}", ref=sha)
        except Exception:  # noqa: BLE001
            continue
        rules = []
        for line in base64.b64decode(c["content"]).decode("utf-8", "replace").splitlines():
            parts = line.split("#")[0].split()
            if len(parts) >= 2:
                rules.append((parts[0], [x.lstrip("@") for x in parts[1:]]))
        return rules
    return []


def owner_of(rules: list, path: str) -> list:
    hit = []
    for pat, owners in rules:  # quy tắc sau thắng, như GitHub
        p = pat.lstrip("/")
        if p.endswith("/"):
            p += "**"
        if fnmatch.fnmatch(path, p) or fnmatch.fnmatch(path, p + "/**") or (
                "/" not in p and fnmatch.fnmatch(path.rsplit("/", 1)[-1], p)):
            hit = owners
    return hit


def last_author(gh, repo: str, path: str, sha: str) -> str | None:
    from urllib.parse import urlencode  # GitHub.get(path, **params) -> không truyền được tham số tên "path"
    cs = []
    for kw in ({"sha": sha}, {}):  # commit của PR từ fork có thể không có trong repo gốc -> lấy theo nhánh mặc định
        try:
            cs = gh.get(f"/repos/{repo}/commits?" + urlencode({"path": path, "per_page": 10, **kw}))
            break
        except Exception:  # noqa: BLE001
            continue
    for c in cs:
        login = (c.get("author") or {}).get("login") or ""
        if not is_bot(login):
            return login
    return None


def assignee(gh, o: dict, ans: dict | None, run: dict, pr: dict | None, team: dict) -> tuple:
    repo, sha, t2 = o["repo"], o["head_sha"], o["pred"]["l2"]
    author = ((pr or {}).get("user") or {}).get("login")
    if o["pred"]["l1"] == "du_an":
        sus = [s["path"] for s in (ans or {}).get("suspects", [])]
        # file nghi ngờ nằm trong thay đổi của PR -> người gây lỗi là tác giả PR (thử trên jsoup PR #1)
        changed = [p for p in sus[:3] if p in set(o.get("diff_files") or [])]
        if changed and author and not is_bot(author):
            return author, f"tác giả pull request, đã sửa `{changed[0]}` trong PR này"
        if sus:
            own = owner_of(codeowners(gh, repo, sha), sus[0])
            if own:
                return own[0], f"chủ của `{sus[0]}` theo CODEOWNERS"
            who = last_author(gh, repo, sus[0], sha)
            if who:
                return who, f"người sửa gần nhất `{sus[0]}` (lỗi nằm ở code cũ, PR không sửa file này)"
        if author and not is_bot(author):
            return author, "tác giả pull request"
        return None, "không xác định được"
    if t2 == "cau_hinh_ci":
        wf = run.get("path", "")
        who = last_author(gh, repo, wf, sha) if wf else None
        if who:
            return who, f"người sửa gần nhất file workflow `{wf}`"
        if team.get("ci"):
            return team["ci"], "người phụ trách CI (cấu hình nhóm)"
        return None, "không xác định được người phụ trách CI"
    if team.get("infra"):
        return team["infra"], "người trực hạ tầng (cấu hình nhóm); trước hết nên chạy lại job"
    return None, "lỗi hạ tầng ngoài: nên chạy lại job; chưa khai báo người trực hạ tầng"


# ---------------------------------------------------------------- thay đổi đề xuất
def file_at(gh, repo: str, path: str, ref: str) -> str | None:
    try:
        c = gh.get(f"/repos/{repo}/contents/{path}", ref=ref)
        return base64.b64decode(c["content"]).decode("utf-8")
    except Exception:  # noqa: BLE001
        return None


def locate(text: str, e: dict) -> dict | None:
    """Thay chuỗi -> thay nguyên các dòng (gợi ý của GitHub thay theo dòng). None nếu old_text không xuất hiện đúng 1 lần."""
    old = e["old_text"]
    if not old or text.count(old) != 1:
        return None
    i = text.index(old)
    a, b = text.rfind("\n", 0, i) + 1, text.find("\n", i + len(old))
    b = len(text) if b < 0 else b
    first, last = text.count("\n", 0, a) + 1, text.count("\n", 0, b) + 1
    return {**e, "start": first, "end": last, "lines_new": text[a:i] + e["new_text"] + text[i + len(old):b]}


def diff_right_lines(gh, repo: str, pr: int) -> dict:
    """path -> tập số dòng (phía sau thay đổi) nằm trong các hunk của PR (gợi ý chỉ đặt được ở đây)."""
    out = {}
    for f in gh.get(f"/repos/{repo}/pulls/{pr}/files", per_page=100):
        rows, ln = set(), 0
        for line in (f.get("patch") or "").split("\n"):
            m = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)", line)
            if m:
                ln = int(m.group(1))
                continue
            if line.startswith("-"):
                continue
            rows.add(ln)
            ln += 1
        out[f["filename"]] = rows
    return out


def review_suggestions(gh, repo: str, pr: int, sha: str, edits: list) -> int:
    """Gợi ý sửa trên dòng code nằm trong PR -> GitHub hiện nút "Commit suggestion". Trả về số gợi ý đã đặt."""
    rows = diff_right_lines(gh, repo, pr)
    cm = []
    for e in edits:
        r = rows.get(e["path"], set())
        if all(n in r for n in range(e["start"], e["end"] + 1)):
            c = {"path": e["path"], "line": e["end"], "side": "RIGHT",
                 "body": f"**Gợi ý sửa lỗi CI** (bấm *Commit suggestion* để áp dụng)\n\n```suggestion\n{e['lines_new']}\n```"}
            if e["end"] > e["start"]:
                c.update(start_line=e["start"], start_side="RIGHT")
            cm.append(c)
    if cm:
        api("POST", f"/repos/{repo}/pulls/{pr}/reviews", commit_id=sha, event="COMMENT",
            body="Bot phân tích CI: gợi ý sửa trên các dòng do PR này thay đổi.", comments=cm)
    return len(cm)


# ---------------------------------------------------------------- bình luận
def comment(o: dict, r: dict | None, who: tuple, team: dict, edits: list, n_sugg: int, agent_in: str) -> str:
    from .catalog import LEAF
    from .predict import NAMES
    p, mc = o["pred"], o["mc"]
    a = (r or {}).get("answer") or {}
    blob = f"https://github.com/{o['repo']}/blob/{o['head_sha']}/"
    name = (f"@{who[0]}" if team.get("mention") else f"`{who[0]}`") if who[0] else "—"
    vi = LEAF.get(p["leaf"], (p["leaf"],))[0]
    conf = "đủ tin cậy" if mc["answered"] else "chưa đủ tin cậy — nên có người xem lại"
    tldr = esc(a.get("root_cause", "").split(". ")[0].rstrip(".") + ".") if a.get("root_cause") else vi
    can_pr = p["leaf"] in FIX_LEAVES and edits and a.get("needs_code_change")
    ai = ("đề xuất sửa; tạo pull request sửa khi bạn bấm" if p["leaf"] in FIX_LEAVES
          else "chỉ đề xuất, người xử lý tự sửa")
    out = [MARK, "## 🔎 Phân tích lỗi CI", f"> **Tóm tắt:** {tldr}",
           "| | |\n|---|---|\n"
           f"| **Loại lỗi** | {vi} (`{p['leaf']}`) · {NAMES.get(p['l1'], p['l1'])} → {NAMES.get(p['l2'], p['l2'])} |\n"
           f"| **Độ tin cậy** | xác suất {p['p_leaf'] or 0:.2f} · {conf} |\n"
           f"| **Người nên xử lý** | {name} — {who[1]} |\n"
           f"| **Job / bước lỗi** | {', '.join(o['failed_jobs'])} · {o['failed_steps'] or 'không rõ'} |\n"
           f"| **AI được làm** | {ai} |"]
    if a:
        out.append(f"### Nguyên nhân\n{esc(a.get('root_cause', ''))}")
        if a.get("suggested_fix"):
            out.append(f"### Cách sửa đề xuất\n{esc(a['suggested_fix'])}")
        if n_sugg:
            out.append(f"💡 Đã đặt **{n_sugg} gợi ý sửa** trực tiếp trên dòng code của PR — bấm *Commit suggestion* "
                       "ở tab *Files changed* để áp dụng.")
        if a.get("suspects"):
            out.append(f"<details><summary>📄 File nghi ngờ ({len(a['suspects'][:5])})</summary>\n\n" + "\n".join(
                f"{i}. [`{s['path']}{':' + str(s['line']) if s.get('line') else ''}`]"
                f"({blob}{s['path']}{'#L' + str(s['line']) if s.get('line') else ''}) — {esc(s['reason'])}"
                for i, s in enumerate(a["suspects"][:5], 1)) + "\n</details>")
    elif r and r.get("error"):
        out.append(f"_Agent chưa chạy được: {r['error'][:300]}_")
    lines = "\n".join(l["text"][:200] for l in (o.get("cause_lines") or [])[:5])
    if lines:
        out.append(f"<details><summary>🧾 Dòng log mô hình chọn làm căn cứ</summary>\n\n```\n{lines}\n```\n</details>")
    if agent_in:
        out.append("<details><summary>🤖 Prompt cho AI agent</summary>\n\nDán vào Claude Code (hoặc agent khác) đang mở "
                   f"repo ở commit lỗi:\n\n````\n{agent_in}\n````\n</details>")
    if can_pr:
        out.append(f"- [ ] {BOX} — bot áp đúng {len(edits)} thay đổi đề xuất vào nhánh mới và mở pull request vào "
                   "nhánh của PR này (cần quyền ghi repo).")
        out.append(f"<!-- p3-fix:{base64.b64encode(json.dumps(edits).encode()).decode()} -->")
    meta = f"{o['seconds']} giây phân loại"
    if r and r.get("seconds") is not None:
        meta += f" · agent {r['seconds']} giây, {r.get('turns')} bước, {r.get('in_tok', 0):,} token"
    out.append("<sub>Bot chỉ đọc code, không tự sửa file. Loại lỗi: mô hình phân loại của đề tài · nguyên nhân và cách "
               f"sửa: Claude Code · người xử lý: quy tắc (CODEOWNERS / lịch sử commit / cấu hình nhóm) · {meta}.</sub>")
    return "\n\n".join(out)


def upsert(gh, repo: str, pr: int, body: str) -> None:
    old = [c for c in gh.get(f"/repos/{repo}/issues/{pr}/comments", per_page=100) if MARK in (c.get("body") or "")]
    if old:
        api("PATCH", f"/repos/{repo}/issues/comments/{old[-1]['id']}", body=body)
    else:
        api("POST", f"/repos/{repo}/issues/{pr}/comments", body=body)


# ---------------------------------------------------------------- chế độ sửa
def fix(gh, repo: str, comment_id: int, sender: str) -> None:
    """Người có quyền ghi tick ô -> áp các thay đổi đã lưu lên nhánh mới từ nhánh của PR, mở PR vào nhánh đó."""
    perm = gh.get(f"/repos/{repo}/collaborators/{sender}/permission").get("permission")
    if perm not in ("admin", "maintain", "write"):
        print(f"{sender} không có quyền ghi ({perm}), bỏ qua")
        return
    c = gh.get(f"/repos/{repo}/issues/comments/{comment_id}")
    body = c["body"]
    m = FIX_RE.search(body)
    if MARK not in body or not m or f"- [x] {BOX}" not in body or "→ đã mở" in body:
        print("không có yêu cầu tạo PR")
        return
    pr_no = int(c["issue_url"].rsplit("/", 1)[-1])
    pr = gh.get(f"/repos/{repo}/pulls/{pr_no}")
    if pr["head"]["repo"]["full_name"] != repo:
        raise SystemExit("PR từ repo khác (fork): bot không ghi được vào nhánh đó")
    head, sha = pr["head"]["ref"], pr["head"]["sha"]
    edits = json.loads(base64.b64decode(m.group(1)))
    branch = f"ci-fix/pr-{pr_no}-{sha[:7]}"
    api("POST", f"/repos/{repo}/git/refs", ref=f"refs/heads/{branch}", sha=sha)
    done = []
    for path in dict.fromkeys(e["path"] for e in edits):
        f = gh.get(f"/repos/{repo}/contents/{path}", ref=branch)
        text = base64.b64decode(f["content"]).decode("utf-8")
        for e in [e for e in edits if e["path"] == path]:
            if text.count(e["old_text"]) != 1:
                raise SystemExit(f"{path}: đoạn cần thay không còn khớp (nhánh đã đổi?)")
            text = text.replace(e["old_text"], e["new_text"])
        api("PUT", f"/repos/{repo}/contents/{path}", branch=branch, sha=f["sha"],
            message=f"Fix CI failure in {path} (suggested by CI triage bot)",
            content=base64.b64encode(text.encode("utf-8")).decode())
        done.append(path)
    new = api("POST", f"/repos/{repo}/pulls", head=branch, base=head, title=f"Fix CI failure of #{pr_no}",
              body=f"Bot áp các thay đổi đã đề xuất trong bình luận phân tích lỗi CI của #{pr_no} "
                   f"(yêu cầu bởi `{sender}`).\n\nFile: " + ", ".join(f"`{p}`" for p in done) +
                   "\n\nLưu ý: pull request do GITHUB_TOKEN tạo không tự kích hoạt workflow; hãy chạy lại CI hoặc "
                   "gộp vào nhánh của PR để kiểm tra.")
    api("PATCH", f"/repos/{repo}/issues/comments/{comment_id}",
        body=body.replace(f"- [x] {BOX}", f"- [x] {BOX} → đã mở {new['html_url']}"))
    print("đã mở", new["html_url"])


# ---------------------------------------------------------------- main
def main() -> None:
    from project3.crawl.github import GitHub
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--run-id", type=int)
    ap.add_argument("--pr", type=int)
    ap.add_argument("--bundle")
    ap.add_argument("--weights")
    ap.add_argument("--cause-weights")
    ap.add_argument("--no-agent", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="in bình luận ra màn hình, không đăng")
    ap.add_argument("--fix-comment", type=int, help="chế độ sửa: id bình luận của bot vừa được tick")
    ap.add_argument("--sender", default="")
    a = ap.parse_args()
    gh = GitHub(gh_token())
    if a.fix_comment:
        fix(gh, a.repo, a.fix_comment, a.sender)
        return
    from .agent import run as run_agent
    from .predict import Predictor, agent_input, fetch_run
    team = {}
    try:
        c = gh.get(f"/repos/{a.repo}/contents/.github/ci-triage.json")
        team = json.loads(base64.b64decode(c["content"]))
    except Exception:  # noqa: BLE001 — không có cấu hình nhóm
        pass
    run = gh.get(f"/repos/{a.repo}/actions/runs/{a.run_id}")
    pr = gh.get(f"/repos/{a.repo}/pulls/{a.pr}") if a.pr else None
    rec = fetch_run(f"https://github.com/{a.repo}/actions/runs/{a.run_id}", gh)
    pred = Predictor(Path(a.bundle), a.weights, device="cpu", cause_weights=a.cause_weights)
    o = pred.predict(rec, mc=MC, per_job=False)
    if "error" in o:
        print(o["error"])
        return
    print("nhãn:", o["pred"]["leaf"], f"({o['seconds']}s)", flush=True)
    agent_in = agent_input(o)
    lang = LANG.get(team.get("language", "vi"), "Vietnamese")
    r = None if a.no_agent else run_agent(o, agent_in + f"\n\nWrite root_cause, reasons and suggested_fix in {lang}.", gh)
    if r:
        print("agent:", {k: v for k, v in r.items() if k != "answer"}, flush=True)
    ans = (r or {}).get("answer") or {}
    edits = []
    for e in ans.get("edits") or []:
        text = file_at(gh, a.repo, e["path"], o["head_sha"])
        loc = locate(text, e) if text is not None else None
        if loc:
            edits.append(loc)
        else:
            print("bỏ thay đổi không khớp file:", e["path"], flush=True)
    who = assignee(gh, o, ans, run, pr, team)
    n_sugg = 0
    if a.pr and not a.dry_run and edits:
        try:
            n_sugg = review_suggestions(gh, a.repo, a.pr, o["head_sha"], edits)
        except Exception as e:  # noqa: BLE001 — gợi ý trên dòng là phần phụ
            print("không đặt được gợi ý:", e, flush=True)
    body = comment(o, r, who, team, edits, n_sugg, agent_in)
    if a.dry_run or not a.pr:
        print(body)
    else:
        upsert(gh, a.repo, a.pr, body)
        print("đã bình luận vào PR", a.pr, "| gợi ý trên dòng:", n_sugg)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
