"""Tìm nguyên nhân trong code bằng Claude Code trên MÁY CỦA NGƯỜI DÙNG (16/11/2026), dùng gói Claude đã đăng nhập
(không dùng API key). Cách 4 của thí nghiệm agent (scripts/analysis/rca_agent.py): agent nhận loại lỗi + dòng nguyên
nhân do mô hình trên Colab chọn (predict.agent_input), thay đổi của PR (_ci/pr.diff) và code của repo ở đúng commit.

Agent chỉ được đọc file / tìm chữ / tìm file (không chạy lệnh, không sửa file, không truy cập mạng); kho git của repo
giữ lại ở data/demo_repos (lần sau không tải lại), file của commit lấy ra thư mục tạm và xoá sau khi xong. Chỉ dành cho chính người dùng tự chạy (gói Claude là gói cá nhân).
"""
import glob
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

WS = Path(os.environ.get("P3_AGENT_WS", r"D:\projects\project3\data\demo_ws"))  # đường dẫn ngắn: Windows giới hạn 260 ký tự
CACHE = Path(os.environ.get("P3_REPO_CACHE", r"D:\projects\project3\data\demo_repos"))  # kho git giữ lại giữa các lần
MODEL = os.environ.get("P3_AGENT_MODEL", "claude-opus-5-5")
MAX_TURNS, MAX_USD = 60, 4.0  # như thí nghiệm (tự đặt); MAX_USD chỉ là trần ước tính, gói Claude không tính tiền theo token
DIFF_CHARS = 400_000          # pr.diff quá dài thì cắt (tự đặt)
SCHEMA = {
    "type": "object",
    "properties": {
        "needs_code_change": {"type": "boolean"},
        "suspects": {"type": "array", "maxItems": 5, "items": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "line": {"type": ["integer", "null"]},
                           "reason": {"type": "string"}},
            "required": ["path", "line", "reason"], "additionalProperties": False}},
        "root_cause": {"type": "string"},
        # 16/11: cách sửa cụ thể (file, dòng, thay gì bằng gì; có thể kèm đoạn code), agent không tự sửa file
        "suggested_fix": {"type": "string"},
        "confidence": {"type": "number"},
        # 17/11: thay đổi tối thiểu dạng thay chuỗi (agent vẫn KHÔNG sửa file; bot áp khi người dùng bấm nút)
        "edits": {"type": "array", "maxItems": 5, "items": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}},
            "required": ["path", "old_text", "new_text"], "additionalProperties": False}},
    },
    "required": ["needs_code_change", "suspects", "root_cause", "suggested_fix", "confidence", "edits"],
    "additionalProperties": False,
}
TASK = ("Read the failure description from standard input and investigate the repository in the current directory "
        "(checked out at the failing commit, no git history). `_ci/pr.diff` holds the changes introduced by the pull "
        "request (or the pushed commit). Paths must be relative to the repository root. Do not modify any file. In "
        "`suggested_fix`, describe the concrete change that fixes the failure (which file and line, what to replace with "
        "what; include a short code snippet when it helps), or say why no code change is needed. In `edits`, give the "
        "smallest set of exact text replacements that implements the fix: `old_text` must be copied verbatim from the "
        "file at this commit (whole lines, including indentation) and appear exactly once in it; `new_text` replaces it. "
        "Leave `edits` empty when no code change is needed or you are not confident.")


def claude_bin() -> str:
    """CLAUDE_BIN, hoặc `claude` trên PATH, hoặc bản mới nhất đi kèm extension VS Code."""
    if os.environ.get("CLAUDE_BIN"):
        return os.environ["CLAUDE_BIN"]
    if shutil.which("claude"):
        return shutil.which("claude")
    bins = glob.glob(os.path.expanduser(r"~\.vscode\extensions\anthropic.claude-code-*-win32-x64"
                                        r"\resources\native-binary\claude.exe"))
    if not bins:
        raise FileNotFoundError("Không tìm thấy Claude Code. Cài Claude Code hoặc đặt biến CLAUDE_BIN.")
    ver = lambda b: tuple(int(x) for x in Path(b).parents[2].name.split("-")[2].split("."))
    return max(bins, key=ver)


def sh(cmd, cwd=None, timeout=900, **kw):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, **kw)


def clone(repo: str, sha: str, ws: Path) -> None:
    """Code của repo tại đúng commit vào ws, KHÔNG có .git (agent không xem được lịch sử).

    16/11: giữ kho git của từng repo ở CACHE/<owner>__<repo> (không xoá sau khi chạy). Commit đã có trong kho -> không
    tải gì; commit mới -> chỉ tải 1 commit đó (--depth 1, phần file giống commit cũ git không tải lại). Sau đó lấy file
    của commit ra ws bằng `git --work-tree`, nên ws chỉ có file, không có .git."""
    if ws.exists():
        rm(ws)
    ws.mkdir(parents=True)
    git = CACHE / repo.replace("/", "__")
    g = lambda *a, cwd=git: sh(["git", "-c", "core.longpaths=true", *a], cwd=cwd)
    if not (git / "HEAD").exists():
        git.mkdir(parents=True, exist_ok=True)
        for a in (["init", "-q", "--bare"], ["remote", "add", "origin", f"https://github.com/{repo}.git"]):
            g(*a)
    if g("cat-file", "-e", f"{sha}^{{commit}}").returncode:  # commit chưa có trong kho -> tải
        p = g("fetch", "-q", "--depth", "1", "origin", sha)
        if p.returncode:
            raise RuntimeError(f"git fetch {repo}@{sha[:10]}: {p.stderr[:300]}")
    p = sh(["git", "-c", "core.longpaths=true", f"--git-dir={git}", f"--work-tree={ws}", "read-tree", sha], cwd=ws)
    if not p.returncode:
        p = sh(["git", "-c", "core.longpaths=true", f"--git-dir={git}", f"--work-tree={ws}", "checkout-index", "-a",
                "-f"], cwd=ws)
    if p.returncode:
        raise RuntimeError(f"git checkout {repo}@{sha[:10]}: {p.stderr[:300]}")


def cache_size() -> str:
    """Dung lượng kho repo đã lưu (để biết khi nào nên xoá bớt thư mục CACHE)."""
    n = sum(f.stat().st_size for f in CACHE.rglob("*") if f.is_file()) if CACHE.exists() else 0
    return f"{n / 1e9:.2f} GB, {len(list(CACHE.iterdir())) if CACHE.exists() else 0} repo"


def rm(p: Path) -> None:
    shutil.rmtree(p, onexc=lambda f, x, e: (os.chmod(x, 0o700), f(x)))  # file chỉ đọc trên Windows


def pr_diff(gh, repo: str, sha: str, event: str) -> str:
    """Như predict.diff_stats: PR = nhánh mặc định...head; push = commit so với cha. Ghép phần patch của từng file."""
    try:
        if event == "pull_request":
            base = gh.get(f"/repos/{repo}")["default_branch"]
            d = gh.get(f"/repos/{repo}/compare/{base}...{sha}")
        else:
            d = gh.get(f"/repos/{repo}/commits/{sha}")
    except Exception as e:  # noqa: BLE001 — thiếu diff thì agent vẫn chạy được, chỉ kém thông tin hơn
        return f"(could not fetch the diff: {str(e)[:200]})"
    out = [f"diff --git a/{f['filename']} b/{f['filename']}\n--- a/{f['filename']}\n+++ b/{f['filename']}\n"
           + (f.get("patch") or "(binary or too large, no patch)") for f in d.get("files") or []]
    return "\n".join(out)[:DIFF_CHARS] or "(empty diff)"


BACKEND = os.environ.get("P3_AGENT_BACKEND", "claude")  # claude | agy (Antigravity CLI, 17/11)
AGY_MODEL = os.environ.get("P3_AGY_MODEL", "gemini-4-argon-high")


def agy_bin() -> str:
    """Antigravity CLI: AGY_BIN, `agy` trên PATH, hoặc bản đi kèm Antigravity IDE (~/.gemini/bin/agy.exe)."""
    for b in (os.environ.get("AGY_BIN"), shutil.which("agy"), os.path.expanduser(r"~\.gemini\bin\agy.exe")):
        if b and Path(b).exists():
            return b
    raise FileNotFoundError("Không tìm thấy Antigravity CLI (agy). Cài agy hoặc đặt biến AGY_BIN.")


def call(ws: Path, prompt: str, backend: str = None) -> dict:
    """Gọi agent CHỈ ĐỌC trong ws -> {"answer", "turns", "in_tok", "out_tok", "error"?}.
    claude: --tools Read,Grep,Glob (chặn cứng). agy: --mode plan (thử 17/11: đọc được, tạo file / chạy lệnh ghi file
    không được; ở chế độ mặc định agy TỰ GHI ĐƯỢC file nên không bao giờ dùng chế độ đó)."""
    backend = backend or BACKEND
    if backend == "agy":
        sf = ws.parent / f"_schema_{ws.name}.json"
        sf.write_text(json.dumps(SCHEMA), encoding="utf-8")
        # 17/11 (đo trên lịch sử hội thoại agy): agy KHÔNG có công cụ tìm chữ (chỉ read_file/glob); tìm chữ phải qua lệnh
        # terminal, mà --mode plan giữ mọi lệnh chờ duyệt -> agy đọc nguyên file (log 1 MB) -> token rất lớn.
        # Cách đã thử thành công: chế độ thường + quy tắc quyền: CHO PHÉP findstr (tìm chữ, chỉ đọc), CẤM
        # write_file/edit_file; lệnh khác tự bị từ chối khi chạy không tương tác. (Không dùng --disable-slash-commands.)
        perm = ws.parent / f"_perm_{ws.name}.json"
        perm.write_text(json.dumps({"permissions": {"allow": ["command(findstr)"],
                                                    "deny": ["write_file", "edit_file", "write_file(*)",
                                                             "edit_file(*)"]}}), encoding="utf-8")
        rule = (" To search text, run the terminal command `findstr /s /n /i /c:\"<text>\" <files>` (read-only; it is "
                "the only command allowed). Do not read whole large files such as the CI log: search first, then read "
                "only the needed line ranges (read_file supports StartLine/EndLine). You cannot write or edit files. "
                "Do not launch subagents or background tasks and do not write a plan file: investigate yourself and "
                "return the final JSON answer in this turn.")
        cmd = [agy_bin(), "-p", TASK + rule + "\n\n" + prompt, "--output-format", "json", "--json-schema", str(sf),
               "--settings", str(perm), "--model", AGY_MODEL, "--print-timeout", "20m"]
        p = sh(cmd, cwd=ws, timeout=1500)
        sf.unlink(missing_ok=True)
        perm.unlink(missing_ok=True)
        try:
            res = json.loads(p.stdout)
        except json.JSONDecodeError:
            return {"error": f"agy không trả JSON (mã {p.returncode}): {(p.stderr or p.stdout)[-400:]}"}
        u = res.get("usage", {})
        out = {"answer": res.get("structured_output"), "turns": res.get("num_turns"),
               "in_tok": u.get("input_tokens", 0) + u.get("cache_read_tokens", 0),
               "out_tok": u.get("output_tokens", 0) + u.get("thinking_tokens", 0), "backend": f"agy:{AGY_MODEL}"}
        if res.get("status") != "SUCCESS" or not out["answer"]:
            out["error"] = str(res.get("error") or res.get("response") or p.stderr)[-400:]
        return out
    cmd = [claude_bin(), "-p", TASK, "--output-format", "json", "--json-schema", json.dumps(SCHEMA),
           "--model", MODEL, "--tools", "Read,Grep,Glob", "--strict-mcp-config", "--setting-sources", "project",
           "--disable-slash-commands", "--no-session-persistence", "--max-turns", str(MAX_TURNS),
           "--max-budget-usd", str(MAX_USD)]
    p = sh(cmd, cwd=ws, timeout=1800, input=prompt)
    try:
        res = json.loads(p.stdout)
    except json.JSONDecodeError:
        return {"error": f"Claude Code không trả JSON (mã {p.returncode}): {(p.stderr or p.stdout)[-400:]}"}
    u = res.get("usage", {})
    out = {"answer": res.get("structured_output"), "turns": res.get("num_turns"),
           "in_tok": u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0)
           + u.get("cache_creation_input_tokens", 0), "out_tok": u.get("output_tokens", 0), "backend": "claude"}
    if res.get("is_error") or not out["answer"]:
        out["error"] = str(res.get("result") or p.stderr)[-400:]  # ví dụ: chạm giới hạn 5 giờ của gói
    return out


def run(o: dict, prompt: str, gh) -> dict:
    """o: kết quả phân loại (cần repo, run_id, head_sha, event); prompt: predict.agent_input(o).
    -> {"answer": đầu ra theo SCHEMA hoặc None, "error", "seconds", "clone_seconds", "turns", "in_tok", "out_tok"}."""
    if not prompt:
        return {"error": "Chưa có dòng nguyên nhân (Colab chưa nạp mô hình dòng nguyên nhân?)."}
    repo, sha = o["repo"], o.get("head_sha")
    if not sha:
        return {"error": "Không biết commit của lần chạy."}
    ws = WS / str(o["run_id"])
    t0 = time.time()
    try:
        clone(repo, sha, ws)
        (ws / "_ci").mkdir()
        (ws / "_ci" / "pr.diff").write_text(pr_diff(gh, repo, sha, o.get("event", "")), encoding="utf-8")
        t1 = time.time()
        out = call(ws, prompt)
        out.update(seconds=round(time.time() - t1, 1), clone_seconds=round(t1 - t0, 1))
        return out
    except Exception as e:  # noqa: BLE001 — hiện lỗi cho người dùng
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        if ws.exists():
            rm(ws)
