from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from html import unescape
from urllib.parse import parse_qs, unquote, urlparse

import httpx


_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class WebSearchItem:
    title: str
    url: str
    snippet: str
    source: str

    def to_dict(self) -> dict[str, str]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "source": self.source,
        }


class BuiltinWebSearchService:
    """No-key web search used by the built-in networking permission."""

    SEARCH_URL = "https://html.duckduckgo.com/html/"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36 LangDrillAgent/1.0"
    )

    def __init__(self, timeout: float = 12.0):
        self.timeout = timeout

    def search(self, query: str, *, max_results: int = 5) -> dict:
        clean_query = query.strip()
        if not clean_query:
            raise RuntimeError("联网检索关键词为空。")
        response = httpx.get(
            self.SEARCH_URL,
            params={"q": clean_query},
            headers={"User-Agent": self.USER_AGENT},
            timeout=self.timeout,
            follow_redirects=True,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"搜索引擎返回 {exc.response.status_code}。") from exc
        results = self._parse_duckduckgo_html(response.text, max_results=max_results)
        if not results:
            raise RuntimeError("没有检索到可用网页结果。")
        return {
            "id": "builtin-web-search",
            "label": "内置联网检索",
            "provider": "duckduckgo-html",
            "query": clean_query,
            "retrieved_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "results": [item.to_dict() for item in results],
            "requires_api_key": False,
            "requires_token": False,
            "permission_feature_id": "web_search_import",
            "skill_dependency": False,
        }

    def _parse_duckduckgo_html(self, html_text: str, *, max_results: int) -> list[WebSearchItem]:
        anchors = list(re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html_text, re.DOTALL))
        results: list[WebSearchItem] = []
        seen_urls: set[str] = set()
        for index, anchor in enumerate(anchors):
            href = self._decode_result_url(anchor.group(1))
            if not href or href in seen_urls:
                continue
            title = self._clean_html(anchor.group(2))
            if not title:
                continue
            next_start = anchors[index + 1].start() if index + 1 < len(anchors) else len(html_text)
            block = html_text[anchor.end():next_start]
            snippet = self._snippet_from_block(block)
            results.append(
                WebSearchItem(
                    title=title,
                    url=href,
                    snippet=snippet,
                    source=urlparse(href).netloc.removeprefix("www."),
                )
            )
            seen_urls.add(href)
            if len(results) >= max_results:
                break
        return results

    def _snippet_from_block(self, block: str) -> str:
        snippet_match = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', block, re.DOTALL)
        if not snippet_match:
            snippet_match = re.search(r'class="result__snippet"[^>]*>(.*?)</div>', block, re.DOTALL)
        return self._clean_html(snippet_match.group(1)) if snippet_match else ""

    def _decode_result_url(self, href: str) -> str:
        clean = unescape(href).strip()
        parsed = urlparse(clean)
        query = parse_qs(parsed.query)
        if "uddg" in query and query["uddg"]:
            clean = unquote(query["uddg"][0])
        if clean.startswith("//"):
            clean = f"https:{clean}"
        if not clean.startswith(("http://", "https://")):
            return ""
        return clean

    def _clean_html(self, value: str) -> str:
        text = _TAG_RE.sub(" ", unescape(value))
        return _SPACE_RE.sub(" ", text).strip()
