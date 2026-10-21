"""GitHub REST client nhỏ: đọc token từ .env, tự chờ khi chạm rate limit."""
import os
import time
from pathlib import Path

import requests

API = "https://api.github.com"


def load_token(env_path: Path = Path(".env")) -> str | None:
    token = os.environ.get("GITHUB_ACCESS_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token or not env_path.exists():
        return token
    for line in env_path.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        if key.strip() in ("GITHUB_ACCESS_TOKEN", "GITHUB_TOKEN"):
            return value.strip().strip('"').strip("'")
    return None


class GitHub:
    def __init__(self, token: str | None):
        self.s = requests.Session()
        self.s.headers.update({"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                               "User-Agent": "project3-build-failure-crawler"})
        if token:
            self.s.headers["Authorization"] = f"Bearer {token}"
        self.remaining = None

    def _wait_if_needed(self, r: requests.Response) -> bool:
        """Trả về True nếu cần gọi lại sau khi đã chờ."""
        self.remaining = r.headers.get("X-RateLimit-Remaining", self.remaining)
        if r.status_code in (403, 429):
            if r.headers.get("X-RateLimit-Remaining") == "0":
                wait = max(0, int(r.headers.get("X-RateLimit-Reset", time.time())) - time.time()) + 5
            elif r.status_code == 429 or "rate limit" in r.text.lower():  # secondary rate limit
                wait = int(r.headers.get("Retry-After", 60))
            else:  # lỗi quyền (vd. token thiếu scope public_repo khi tải log): không chờ
                raise PermissionError(f"{r.status_code} {r.url}: {r.text[:150]}")
            print(f"  rate limit ({r.status_code}), chờ {wait:.0f}s", flush=True)
            time.sleep(wait)
            return True
        return False

    def _request(self, url: str, **kw) -> requests.Response:
        """GET có thử lại khi lỗi mạng (mất kết nối, timeout)."""
        for k in range(5):
            try:
                return self.s.get(url, **kw)
            except requests.RequestException as e:
                print(f"  lỗi mạng ({type(e).__name__}), thử lại sau {10 * (k + 1)}s", flush=True)
                time.sleep(10 * (k + 1))
        return self.s.get(url, **kw)

    def get(self, path: str, **params) -> dict:
        url = path if path.startswith("http") else API + path
        for attempt in range(5):
            r = self._request(url, params=params, timeout=60)
            if self._wait_if_needed(r):
                continue
            if r.status_code in (500, 502, 503, 504):
                wait = 5 * (attempt + 1)
                print(f'  GitHub HTTP {r.status_code}, thử lại sau {wait}s', flush=True)
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError(f"Quá số lần thử: {url}")

    def get_log_tail(self, path: str, tail_bytes: int = 512_000) -> str | None:
        """Chỉ tải phần đuôi của log (lỗi luôn nằm ở cuối) qua Range request; None nếu log đã hết hạn.

        Kho log (Azure Blob) rất chậm từ VN (~30-50 KB/s, hay treo) nên không tải cả file."""
        for _ in range(5):
            r = self._request(API + path, timeout=60, allow_redirects=False)
            if self._wait_if_needed(r):
                continue
            if r.status_code in (404, 410):
                return None
            loc = r.headers.get("Location")
            if not loc:
                r.raise_for_status()
                return r.text
            for k in range(4):
                try:
                    size = int(requests.head(loc, timeout=30).headers.get("Content-Length", 0))
                    hdr = {"Range": f"bytes={max(0, size - tail_bytes)}-"} if size > tail_bytes else {}
                    blob = requests.get(loc, headers=hdr, timeout=(15, 60))  # không gửi token sang Azure
                    blob.raise_for_status()
                    text = blob.content.decode("utf-8", errors="ignore")
                    return text.split("\n", 1)[-1] if hdr else text  # bỏ dòng đầu bị cắt dở
                except requests.RequestException as e:
                    print(f"  tải log lỗi ({type(e).__name__}), thử lại", flush=True)
                    time.sleep(5 * (k + 1))
            return None
        return None

    def get_text(self, path: str) -> str | None:
        """Tải log (API trả redirect sang file text). None nếu log đã hết hạn."""
        for _ in range(5):
            r = self._request(API + path, timeout=120, allow_redirects=True)
            if self._wait_if_needed(r):
                continue
            if r.status_code in (404, 410):
                return None
            r.raise_for_status()
            return r.text
        return None
