from pathlib import Path

import pytest

from langdrill_agent.past_papers.sources import (
    DownloadPolicy,
    HtmlPaperSourceAdapter,
    PaperDownloader,
    PaperSourcePolicyError,
)


class FakeResponse:
    def __init__(self, *, text: str, url: str) -> None:
        self.text = text
        self.url = url

    def raise_for_status(self) -> None:
        return None


class FakeHttpClient:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages

    def get(self, url: str, **_kwargs) -> FakeResponse:
        return FakeResponse(text=self.pages[url], url=url)


def test_adapter_uses_actual_link_metadata() -> None:
    catalog_url = "https://source.test/exams"
    client = FakeHttpClient(
        {
            catalog_url: '<a href="/2025-06-set1.pdf">2025 June Set 1</a>',
        }
    )
    adapter = HtmlPaperSourceAdapter(
        client,
        catalog_urls={"cet4": catalog_url},
        allowed_hosts={"source.test"},
    )

    items = adapter.discover("cet4")

    assert [(item.year, item.session, item.set_number) for item in items] == [
        (2025, "june", 1)
    ]
    assert items[0].source_url == "https://source.test/2025-06-set1.pdf"


def test_adapter_does_not_invent_missing_paper_metadata() -> None:
    catalog_url = "https://source.test/exams"
    client = FakeHttpClient(
        {catalog_url: '<a href="/download.pdf">Download latest paper</a>'}
    )
    adapter = HtmlPaperSourceAdapter(
        client,
        catalog_urls={"cet4": catalog_url},
        allowed_hosts={"source.test"},
    )

    assert adapter.discover("cet4") == []


@pytest.mark.parametrize(
    "url",
    [
        "file:///c:/secret",
        "http://127.0.0.1/admin",
        "http://169.254.1.2/metadata",
        "https://evil.test/x.pdf",
    ],
)
def test_downloader_rejects_untrusted_targets(url: str, tmp_path: Path) -> None:
    downloader = PaperDownloader(
        policy=DownloadPolicy(allowed_hosts=frozenset({"source.test"})),
    )

    with pytest.raises(PaperSourcePolicyError):
        downloader.validate_url(url)
