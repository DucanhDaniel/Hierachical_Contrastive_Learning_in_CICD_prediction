"""Dòng log -> link tới file mã nguồn trên GitHub tại đúng commit của lần chạy (góp ý GVHD 05/11/2026: "dòng click một
phát thì mở ra source code"). Chỉ dùng chuỗi trong log, không gọi API.

Đường dẫn trong log đã được thay thư mục làm việc của runner bằng `<ws>/` (run_dataset.clean) nên phần sau `<ws>/` là
đường dẫn tương đối từ gốc repo. Ngoại lệ: workflow checkout repo vào thư mục con (actions/checkout `path:`), khi đó
đường dẫn bắt đầu bằng tên thư mục đó; nếu thành phần đầu trùng tên repo và phần còn lại khớp một file trong diff thì bỏ
thành phần đầu.
"""
import re
from urllib.parse import quote

EXT = r"(?:java|kt|kts|scala|groovy|gradle|xml|properties|toml|ya?ml|json|sql|proto|aidl|js|ts|tsx|py|sh|c|cc|cpp|h)"
# thứ tự quan trọng: mẫu có số dòng trước
PATTERNS = [
    re.compile(rf"<ws>/(?P<path>[^\s:'\"()\[\]]+\.{EXT}):\[?(?P<line>\d+)"),          # javac, javadoc, kotlinc
    re.compile(rf"Build file '<ws>/(?P<path>[^']+\.{EXT})' line: (?P<line>\d+)"),     # Gradle script
    re.compile(rf"<ws>/(?P<path>[^\s:'\"()\[\]]+\.{EXT})\b"),                          # chỉ có file (pom.xml, ...)
    re.compile(rf"^\s+(?:\[ERROR\]\s+)?(?P<path>[\w.-]+(?:/[\w.-]+)+\.{EXT})\s*$"),    # spotless: danh sách file lỗi
]
# stack trace chỉ có tên file: `at a.b.FooTest.m(FooTest.java:42)` -> chỉ nhận khi tên khớp đúng 1 file trong diff
FRAME = re.compile(r"\((?P<name>[\w$]+\.(?:java|kt|scala|groovy)):(?P<line>\d+)\)")


# file do build sinh ra, không có trong repo (kiểm 40 link 10/11/2026: 17 link 404 đều thuộc loại này hoặc bị che `***`)
GENERATED = re.compile(r"(?:^|/)(?:build|target|out|bin|build-results|build-scans|generated|\.gradle|node_modules)/|"
                       r"\*\*\*|(?:^|/)[^/]*report[^/]*\.xml$", re.I)


def find_refs(text: str) -> list:
    """[(path, line|None, rel)] theo thứ tự xuất hiện, không trùng; rel = đường dẫn không có <ws>/ (có thể tính từ module)."""
    out, seen = [], set()
    for pat in PATTERNS:
        for m in pat.finditer(text):
            path = m.group("path").replace("\\", "/").removeprefix("./")  # runner Windows in đường dẫn bằng dấu \
            line = int(m.group("line")) if "line" in pat.groupindex and m.group("line") else None
            if path in seen or GENERATED.search(path):
                continue
            seen.add(path)
            out.append((path, line, m.start(), "<ws>/" not in m.group(0) and "Build file" not in m.group(0)))
    return [(p, ln, rel) for p, ln, _, rel in sorted(out, key=lambda r: r[2])]


def resolve(path: str, repo: str, diff_files: list) -> tuple:
    """(đường dẫn trong repo, có nằm trong diff không)."""
    files = set(diff_files or [])
    if path in files:
        return path, True
    head, _, rest = path.partition("/")
    if rest and head == repo.split("/")[-1]:
        return rest, rest in files
    hit = [f for f in files if f.endswith("/" + path)]  # đường dẫn tương đối theo module (spotless in path từ module)
    return (hit[0], True) if len(hit) == 1 else (path, False)


def links(text: str, repo: str, sha: str, diff_files: list = None) -> list:
    """[{path, line, url, in_diff}] cho một dòng log."""
    if not (repo and sha):
        return []
    refs = []
    for p, ln, rel in find_refs(text):
        path, in_diff = resolve(p, repo, diff_files)
        if rel and not in_diff:  # spotless in đường dẫn từ module: không khớp diff thì không đoán (2/4 link 404 lần kiểm)
            continue
        refs.append((path, in_diff, ln))
    if not refs:
        for m in FRAME.finditer(text):
            hit = [f for f in diff_files or [] if f.rsplit("/", 1)[-1] == m.group("name")]
            if len(hit) == 1:
                refs.append((hit[0], True, int(m.group("line"))))
    out = []
    for path, in_diff, ln in refs:
        url = f"https://github.com/{repo}/blob/{sha}/{quote(path)}" + (f"#L{ln}" if ln else "")
        out.append({"path": path, "line": ln, "url": url, "in_diff": in_diff})
    return out
