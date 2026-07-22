from __future__ import annotations

import hashlib
import ipaddress
import mimetypes
import re
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Protocol
from urllib.parse import urljoin, urlparse

import httpx

from .models import PaperSourceInput


class PaperSourcePolicyError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class DownloadPolicy:
    allowed_hosts: frozenset[str]
    max_bytes: int = 100 * 1024 * 1024
    allowed_mime_types: frozenset[str] = frozenset(
        {
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "text/plain",
            "text/markdown",
        }
    )
    max_redirects: int = 5


@dataclass(frozen=True, slots=True)
class DownloadReceipt:
    path: Path
    source_url: str
    content_hash: str
    bytes_downloaded: int
    mime_type: str


class HttpClient(Protocol):
    def get(self, url: str, **kwargs): ...


class PastPaperSourceAdapter(Protocol):
    def discover(self, exam_id: str) -> list[PaperSourceInput]: ...


class CompositePastPaperSourceAdapter:
    def __init__(self, adapters: list[PastPaperSourceAdapter]) -> None:
        self.adapters = adapters

    def discover(self, exam_id: str) -> list[PaperSourceInput]:
        items: list[PaperSourceInput] = []
        seen_urls: set[str] = set()
        for adapter in self.adapters:
            for item in adapter.discover(exam_id):
                if item.source_url in seen_urls:
                    continue
                seen_urls.add(item.source_url)
                items.append(item)
        return sorted(
            items,
            key=lambda item: (
                -(item.year or 0),
                item.session,
                item.set_number or 0,
                item.source_url,
            ),
        )


class HtmlPaperSourceAdapter:
    def __init__(
        self,
        client: HttpClient,
        *,
        catalog_urls: dict[str, str],
        allowed_hosts: set[str] | frozenset[str],
    ) -> None:
        self.client = client
        self.catalog_urls = catalog_urls
        self.allowed_hosts = frozenset(host.lower() for host in allowed_hosts)

    def discover(self, exam_id: str) -> list[PaperSourceInput]:
        catalog_url = self.catalog_urls.get(exam_id, "").strip()
        if not catalog_url:
            return []
        _validate_public_url(catalog_url, self.allowed_hosts, resolve_dns=False)
        response = self.client.get(catalog_url, timeout=20)
        response.raise_for_status()
        parser = _LinkParser()
        parser.feed(response.text)
        items: list[PaperSourceInput] = []
        seen_urls: set[str] = set()
        for href, label in parser.links:
            source_url = urljoin(str(response.url), href)
            try:
                _validate_public_url(source_url, self.allowed_hosts, resolve_dns=False)
            except PaperSourcePolicyError:
                continue
            metadata = _paper_metadata(f"{label} {source_url}")
            if metadata is None or source_url in seen_urls:
                continue
            year, session, set_number = metadata
            seen_urls.add(source_url)
            source_id = _source_id(exam_id, source_url)
            items.append(
                PaperSourceInput(
                    id=source_id,
                    exam_id=exam_id,
                    title=label.strip() or f"{exam_id} {year} {session} Set {set_number}",
                    source_url=source_url,
                    year=year,
                    session=session,
                    set_number=set_number,
                    source_host=urlparse(source_url).hostname or "",
                    metadata={"catalog_url": catalog_url, "discovered_from_link": True},
                )
            )
        return items


class PaperDownloader:
    def __init__(
        self,
        *,
        policy: DownloadPolicy,
        client: httpx.Client | None = None,
    ) -> None:
        self.policy = policy
        self.client = client or httpx.Client(follow_redirects=False, timeout=60)

    def validate_url(self, url: str) -> None:
        _validate_public_url(url, self.policy.allowed_hosts, resolve_dns=True)

    def download(self, source_url: str, destination: Path) -> DownloadReceipt:
        current_url = source_url
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(destination.name + ".partial")
        resume_from = partial.stat().st_size if partial.is_file() else 0
        response = None
        for _ in range(self.policy.max_redirects + 1):
            self.validate_url(current_url)
            headers = {"Range": f"bytes={resume_from}-"} if resume_from else {}
            response = self._open_response(current_url, headers=headers)
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location", "").strip()
                response.close()
                if not location:
                    raise PaperSourcePolicyError("redirect response has no location")
                current_url = urljoin(current_url, location)
                continue
            response.raise_for_status()
            break
        else:
            raise PaperSourcePolicyError("too many redirects")
        if response is None:
            raise RuntimeError("download response unavailable")

        mime_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if not mime_type:
            mime_type = mimetypes.guess_type(urlparse(current_url).path)[0] or "application/octet-stream"
        if mime_type not in self.policy.allowed_mime_types:
            response.close()
            raise PaperSourcePolicyError(f"unsupported download MIME type: {mime_type}")
        declared_size = int(response.headers.get("content-length") or 0)
        content_range = response.headers.get("content-range", "").lower()
        resumes_existing = (
            resume_from > 0
            and response.status_code == 206
            and content_range.startswith(f"bytes {resume_from}-")
        )
        if not resumes_existing:
            resume_from = 0
            partial.unlink(missing_ok=True)
        if resume_from + declared_size > self.policy.max_bytes:
            response.close()
            partial.unlink(missing_ok=True)
            raise PaperSourcePolicyError("download exceeds configured size limit")

        digest = hashlib.sha256()
        bytes_downloaded = resume_from
        if resume_from:
            with partial.open("rb") as existing:
                for block in iter(lambda: existing.read(1024 * 1024), b""):
                    digest.update(block)
        try:
            with partial.open("ab" if resume_from else "wb") as handle:
                for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                    if not chunk:
                        continue
                    bytes_downloaded += len(chunk)
                    if bytes_downloaded > self.policy.max_bytes:
                        partial.unlink(missing_ok=True)
                        raise PaperSourcePolicyError("download exceeds configured size limit")
                    digest.update(chunk)
                    handle.write(chunk)
            partial.replace(destination)
        except PaperSourcePolicyError:
            partial.unlink(missing_ok=True)
            raise
        finally:
            response.close()
        return DownloadReceipt(
            path=destination,
            source_url=current_url,
            content_hash="sha256:" + digest.hexdigest(),
            bytes_downloaded=bytes_downloaded,
            mime_type=mime_type,
        )

    def _open_response(self, url: str, *, headers: dict[str, str]):
        build_request = getattr(self.client, "build_request", None)
        send = getattr(self.client, "send", None)
        if callable(build_request) and callable(send):
            return send(build_request("GET", url, headers=headers), stream=True)
        return self.client.get(url, follow_redirects=False, headers=headers)


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href = ""
        self._label: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        self._href = dict(attrs).get("href") or ""
        self._label = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._label.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href:
            self.links.append((self._href, " ".join(self._label).strip()))
            self._href = ""
            self._label = []


def _paper_metadata(text: str) -> tuple[int, str, int] | None:
    year_match = re.search(r"\b(20\d{2})\b", text)
    set_match = re.search(r"(?:set|套|第)[-_\s]*(\d{1,2})", text, re.IGNORECASE)
    session_match = re.search(
        r"\b(january|march|april|june|september|october|december|jan|mar|apr|jun|sep|oct|dec)\b",
        text,
        re.IGNORECASE,
    )
    if not year_match or not set_match or not session_match:
        return None
    aliases = {
        "jan": "january",
        "mar": "march",
        "apr": "april",
        "jun": "june",
        "sep": "september",
        "oct": "october",
        "dec": "december",
    }
    session = session_match.group(1).lower()
    return int(year_match.group(1)), aliases.get(session, session), int(set_match.group(1))


def _source_id(exam_id: str, source_url: str) -> str:
    digest = hashlib.sha256(source_url.encode("utf-8")).hexdigest()[:20]
    return f"paper-source-{exam_id}-{digest}"


def _validate_public_url(
    url: str,
    allowed_hosts: frozenset[str],
    *,
    resolve_dns: bool,
) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise PaperSourcePolicyError("only HTTPS paper sources are allowed")
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host or host not in allowed_hosts:
        raise PaperSourcePolicyError("paper source host is not allowed")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and not literal.is_global:
        raise PaperSourcePolicyError("private or local paper source is not allowed")
    if not resolve_dns:
        return
    try:
        addresses = {item[4][0] for item in socket.getaddrinfo(host, parsed.port or 443)}
    except socket.gaierror as exc:
        raise PaperSourcePolicyError("paper source host could not be resolved") from exc
    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise PaperSourcePolicyError("paper source resolves to a non-public address")
