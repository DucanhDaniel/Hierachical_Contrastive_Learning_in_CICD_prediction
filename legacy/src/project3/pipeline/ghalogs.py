"""Lấy dữ liệu từ GHALogs (Moriconi et al., MSR 2025, Zenodo 10154920) mà không tải cả file log 142 GB.

File zip trên Zenodo hỗ trợ HTTP Range, nên:
  index   đọc central directory (~100 MB) -> data/external/ghalogs/zip_index.parquet (đường dẫn, offset, kích thước)
  stats   duyệt runs.json.gz + repositories.json.gz -> thống kê repo JVM có run fail
  fetch   tải log (tar.gz) của các run fail đã chọn bằng Range request

Đường dẫn log trong zip: logs/<owner>/<repo>/_<tên workflow>_<hash>/<run_number>-<run_attempt>.tar.gz

    uv run python -m project3.pipeline.ghalogs index
    uv run python -m project3.pipeline.ghalogs stats
    uv run python -m project3.pipeline.ghalogs fetch --max-runs 50
"""
import argparse
import gzip
import http.client
import json
import re
import struct
import sys
import time
import urllib.request
import zlib
from pathlib import Path

import duckdb

URL = "https://zenodo.org/api/records/10154920/files/github_run_logs.zip/content"
DIR = Path("data/external/ghalogs")
JVM = {"Java", "Kotlin", "Groovy", "Scala"}


def get(a: int, b: int, tries: int = 5) -> bytes:
    for i in range(tries):
        try:
            req = urllib.request.Request(URL, headers={"Range": f"bytes={a}-{b - 1}"})
            data = urllib.request.urlopen(req, timeout=120).read()
            if len(data) != b - a:
                raise OSError(f"nhận {len(data)}/{b - a} byte")
            return data
        except (OSError, http.client.HTTPException):
            if i == tries - 1:
                raise
            time.sleep(5 * (i + 1))


def index() -> None:
    size = int(urllib.request.urlopen(urllib.request.Request(URL, method="HEAD")).headers["Content-Length"])
    tail = get(size - 200, size)
    loc = tail.rfind(b"PK\x06\x07")
    eocd = struct.unpack("<Q", tail[loc + 8:loc + 16])[0]
    e = get(eocd, eocd + 56)
    n, cd_size, cd_off = struct.unpack("<QQQ", e[32:56])
    print(f"{n} mục, central directory {cd_size / 1e6:.0f} MB")
    cd, step = bytearray(), 4 << 20
    for a in range(cd_off, cd_off + cd_size, step):
        cd += get(a, min(a + step, cd_off + cd_size))
        print(f"  {len(cd) / 1e6:.0f}/{cd_size / 1e6:.0f} MB", flush=True)
    rows, p = [], 0
    while p < len(cd) and cd[p:p + 4] == b"PK\x01\x02":
        method = struct.unpack("<H", cd[p + 10:p + 12])[0]
        csize, usize = struct.unpack("<II", cd[p + 20:p + 28])
        fl, el, cl = struct.unpack("<HHH", cd[p + 28:p + 34])
        off = struct.unpack("<I", cd[p + 42:p + 46])[0]
        name = cd[p + 46:p + 46 + fl].decode("utf-8", "replace")
        extra = cd[p + 46 + fl:p + 46 + fl + el]
        q = 0
        while q + 4 <= len(extra):  # ZIP64 extra: các trường 0xFFFFFFFF theo thứ tự usize, csize, offset
            hid, hl = struct.unpack("<HH", extra[q:q + 4])
            if hid == 1:
                vals, r = list(struct.unpack(f"<{hl // 8}Q", extra[q + 4:q + 4 + hl - hl % 8])), 0
                if usize == 0xFFFFFFFF:
                    usize, r = vals[r], r + 1
                if csize == 0xFFFFFFFF:
                    csize, r = vals[r], r + 1
                if off == 0xFFFFFFFF:
                    off = vals[r]
            q += 4 + hl
        if name.endswith(".tar.gz"):
            rows.append((name, method, csize, off))
        p += 46 + fl + el + cl
    con = duckdb.connect()
    con.sql("CREATE TABLE z (path VARCHAR, method INT, csize BIGINT, offset BIGINT)")
    con.executemany("INSERT INTO z VALUES (?,?,?,?)", rows)
    out = DIR / "zip_index.parquet"
    con.sql(f"COPY z TO '{out.as_posix()}' (FORMAT parquet)")
    print(f"Đã lưu {out}: {len(rows)} file log")


def stats() -> None:
    lang = {}
    with gzip.open(DIR / "repositories.json.gz", "rt", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                r = d.get("repo") or {}
                lang[d["_id"]] = (r.get("mainLanguage"), r.get("stargazers") or 0, r.get("contributors") or 0)
    rows = []
    with gzip.open(DIR / "runs.json.gz", "rt", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            m = d.get("metadata") or {}
            repo = d["repository_name"]
            l, stars, contrib = lang.get(repo, (None, 0, 0))
            rows.append((repo, l, stars, contrib, d["workflow_path"], m.get("name"), d["run_number"], d["run_attempt"],
                         m.get("id"), m.get("event"), m.get("conclusion"), m.get("head_sha"), m.get("head_branch"),
                         m.get("created_at")))
    con = duckdb.connect()
    con.sql("CREATE TABLE runs (repo VARCHAR, lang VARCHAR, stars INT, contributors INT, workflow_path VARCHAR, "
            "workflow VARCHAR, run_number INT, run_attempt INT, run_id BIGINT, event VARCHAR, conclusion VARCHAR, "
            "head_sha VARCHAR, head_branch VARCHAR, created_at VARCHAR)")
    con.executemany("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    out = DIR / "runs.parquet"
    con.sql(f"COPY runs TO '{out.as_posix()}' (FORMAT parquet)")
    print(con.sql("SELECT count(*) runs, count(DISTINCT repo) repos, min(created_at)[:10] tu, max(created_at)[:10] den FROM runs"))
    print(con.sql("SELECT lang, count(DISTINCT repo) repos, count(*) runs, sum((conclusion='failure')::int) fail "
                  "FROM runs GROUP BY 1 ORDER BY 2 DESC LIMIT 12"))
    jvm = "lang IN ('Java','Kotlin','Groovy','Scala')"
    print(con.sql(f"""WITH r AS (SELECT repo, any_value(lang) lang, any_value(stars) stars, count(*) runs,
            sum((conclusion='failure')::int) fail FROM runs WHERE {jvm} GROUP BY 1)
        SELECT lang, count(*) repos, sum((fail>=1)::int) co_fail, sum((fail>=5)::int) fail_ge5,
            sum((fail>=20)::int) fail_ge20, sum(runs) runs, sum(fail) fail FROM r GROUP BY ROLLUP(lang) ORDER BY 2 DESC"""))
    print(f"Đã lưu {out}")


def fetch(max_runs: int, min_fail: int) -> None:
    """Tải log các run fail của repo JVM có >= min_fail run fail; giải nén tar.gz vào DIR/logs/."""
    import io
    import tarfile
    con = duckdb.connect()
    con.sql(f"CREATE VIEW runs AS SELECT * FROM '{(DIR / 'runs.parquet').as_posix()}'")
    con.sql(f"CREATE VIEW z AS SELECT * FROM '{(DIR / 'zip_index.parquet').as_posix()}'")
    picks = con.sql(f"""WITH f AS (SELECT * FROM runs WHERE lang IN ('Java','Kotlin','Groovy','Scala') AND conclusion='failure'),
            keep AS (SELECT repo FROM f GROUP BY 1 HAVING count(*) >= {min_fail})
        SELECT f.repo, f.run_id, f.head_sha, z.path, z.method, z.csize, z.offset FROM f JOIN keep USING (repo)
        JOIN z ON z.path LIKE 'logs/' || f.repo || '/%/' || f.run_number || '-' || f.run_attempt || '.tar.gz'
            AND z.path LIKE '%' || regexp_replace(f.workflow, '[^A-Za-z0-9]+', '_', 'g') || '%'
        ORDER BY f.repo, f.run_id LIMIT {max_runs}""").fetchall()
    print(f"{len(picks)} run cần tải")
    for repo, run_id, sha, path, method, csize, off in picks:
        dest = DIR / "logs" / repo.replace("/", "__") / str(run_id)
        if dest.exists():
            continue
        head = get(off, off + 30)
        fl, el = struct.unpack("<HH", head[26:30])
        data = get(off + 30 + fl + el, off + 30 + fl + el + csize)
        if method == 8:
            data = zlib.decompress(data, -15)
        dest.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as t:
            for m in t.getmembers():
                if m.isfile():
                    name = re.sub(r"[^\w.\-]+", "_", m.name)[-150:]
                    (dest / name).write_bytes(t.extractfile(m).read())
        (dest / "meta.json").write_text(json.dumps({"repo": repo, "run_id": run_id, "head_sha": sha, "zip_path": path}))
    print("Xong")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["index", "stats", "fetch"])
    ap.add_argument("--max-runs", type=int, default=50)
    ap.add_argument("--min-fail", type=int, default=5)
    a = ap.parse_args()
    {"index": index, "stats": stats, "fetch": lambda: fetch(a.max_runs, a.min_fail)}[a.cmd]()
