#!/usr/bin/env python3
"""演示站下载资产验证脚本。

在 ``演示web2`` 构建前确认 ``releaseChannels.ts`` 声明的两个 GitHub Release
安装包 URL 静态合法；加 ``--live`` 时实际发起 HTTP 请求确认资产可达。

用法：

    python scripts/release/verify_demo_downloads.py           # 仅静态校验
    python scripts/release/verify_demo_downloads.py --live    # 实际请求资产

静态模式用于本地与 CI 快速失败；live 模式用于 GitHub Pages 构建前的最终闸门。
"""

from __future__ import annotations

import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RELEASE_CHANNELS = REPO_ROOT / "演示web2" / "src" / "releaseChannels.ts"

USER_AGENT = "lang-drill-demo-link-check/1"
_URL_PATTERN = re.compile(r'downloadUrl:\s*"([^"]+)"')
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_FALLBACK_STATUSES = {403, 405}


def load_download_urls(path: Path = RELEASE_CHANNELS) -> list[str]:
    """从 releaseChannels.ts 解析所有 downloadUrl，要求恰好两个不同 GitHub Release 直链。"""
    text = path.read_text(encoding="utf-8")
    urls = _URL_PATTERN.findall(text)
    if len(urls) != 2 or len(set(urls)) != 2:
        raise RuntimeError(
            f"expected exactly two distinct demo download URLs, got: {urls}"
        )
    for url in urls:
        if not url.startswith("https://github.com/") or "/releases/download/" not in url:
            raise RuntimeError(f"unexpected download URL: {url}")
    return urls


def open_request(request: urllib.request.Request):
    """urllib.request.urlopen 的可 mock 包装。"""
    return urllib.request.urlopen(request, timeout=30)


def _status(response) -> int:
    return response.getcode() if hasattr(response, "getcode") else getattr(response, "status", 0)


def verify_url(url: str) -> None:
    """验证单个 URL 可达。HEAD 优先，遇 403/405 回退 Range GET，3xx 手动跟随。"""
    current = url
    for _ in range(6):
        request = urllib.request.Request(
            current, method="HEAD", headers={"User-Agent": USER_AGENT}
        )
        try:
            with open_request(request) as response:
                status = _status(response)
                if status in _REDIRECT_STATUSES:
                    location = response.headers.get("Location") if hasattr(response, "headers") else None
                    if not location:
                        raise RuntimeError(f"redirect without location: {current}")
                    current = location
                    continue
                if status >= 400:
                    raise RuntimeError(f"HTTP {status}: {current}")
                return
        except urllib.error.HTTPError as exc:
            if exc.code not in _FALLBACK_STATUSES:
                raise RuntimeError(f"HTTP {exc.code}: {current}") from exc
            fallback = urllib.request.Request(
                current,
                headers={"Range": "bytes=0-0", "User-Agent": USER_AGENT},
            )
            with open_request(fallback) as response:
                status = _status(response)
                if status not in {200, 206}:
                    raise RuntimeError(f"HTTP {status}: {current}")
                return
    raise RuntimeError(f"too many redirects: {url}")


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。返回 0 成功，1 资产不可达，2 静态校验失败。"""
    args = sys.argv[1:] if argv is None else list(argv)
    live = "--live" in args

    try:
        urls = load_download_urls()
    except Exception as exc:
        print(f"FAIL: static validation: {exc}", file=sys.stderr)
        return 2

    if not live:
        print(f"OK: static validation passed ({len(urls)} URLs)")
        return 0

    failures = 0
    for url in urls:
        try:
            verify_url(url)
        except Exception as exc:
            print(f"FAIL: {url}: {exc}", file=sys.stderr)
            failures += 1
            continue
        print(f"OK: {url}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
