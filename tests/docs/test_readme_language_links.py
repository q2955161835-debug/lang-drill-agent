"""验证三语 README 互相链接且包含必备章节。

每个 README 必须：
1. 通过相对路径链接到另外两个 README。
2. 包含安装、Web/桌面使用、创造模式警告、RAG/知识库、记忆、真题版权边界、
   更新、实验版状态和 License 章节。
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

README_ZH = REPO_ROOT / "README.md"
README_EN = REPO_ROOT / "README.en.md"
README_JA = REPO_ROOT / "README.ja.md"

README_FILES = {
    "zh-CN": README_ZH,
    "en-US": README_EN,
    "ja-JP": README_JA,
}

# 每个 README 必须包含的章节关键词（按语言分组）。
# 关键词匹配不区分大小写，只要出现在文件中即可。
REQUIRED_SECTIONS = {
    "zh-CN": {
        "installation": "安装",
        "web_desktop_usage": "Web",
        "creative_mode_warning": "创造模式",
        "rag_knowledge_base": "知识库",
        "memory": "记忆",
        "true_paper_copyright": "真题",
        "updates": "更新",
        "experimental_status": "实验",
        "license": "License",
    },
    "en-US": {
        "installation": "Install",
        "web_desktop_usage": "Web",
        "creative_mode_warning": "Creative mode",
        "rag_knowledge_base": "Knowledge base",
        "memory": "Memory",
        "true_paper_copyright": "Past paper",
        "updates": "Update",
        "experimental_status": "Experimental",
        "license": "License",
    },
    "ja-JP": {
        "installation": "インストール",
        "web_desktop_usage": "Web",
        "creative_mode_warning": "クリエイティブモード",
        "rag_knowledge_base": "ナレッジベース",
        "memory": "メモリ",
        "true_paper_copyright": "過去問",
        "updates": "アップデート",
        "experimental_status": "実験",
        "license": "License",
    },
}


@pytest.fixture(scope="module")
def readme_contents() -> dict[str, str]:
    """读取三语 README 内容，缺失文件返回空字符串以便给出清晰断言。"""
    contents: dict[str, str] = {}
    for locale, path in README_FILES.items():
        if path.is_file():
            contents[locale] = path.read_text(encoding="utf-8")
        else:
            contents[locale] = ""
    return contents


@pytest.mark.parametrize("locale", list(README_FILES))
def test_readme_file_exists(locale: str) -> None:
    """每个语言的 README 文件必须存在。"""
    assert README_FILES[locale].is_file(), f"{README_FILES[locale]} 不存在"


@pytest.mark.parametrize("locale", list(README_FILES))
def test_readme_links_to_other_two_locales(locale: str, readme_contents: dict[str, str]) -> None:
    """每个 README 必须通过相对路径链接到另外两个 README。"""
    content = readme_contents[locale]
    others = [path for loc, path in README_FILES.items() if loc != locale]
    for other_path in others:
        link = f"]({other_path.name})"
        assert link in content, (
            f"{locale} README 缺少到 {other_path.name} 的相对链接"
        )


@pytest.mark.parametrize("locale", list(README_FILES))
def test_readme_contains_required_sections(locale: str, readme_contents: dict[str, str]) -> None:
    """每个 README 必须包含全部必备章节关键词。"""
    content = readme_contents[locale]
    required = REQUIRED_SECTIONS[locale]
    missing = []
    for section, keyword in required.items():
        if keyword.lower() not in content.lower():
            missing.append(f"{section}（关键词 '{keyword}'）")
    assert not missing, f"{locale} README 缺少章节：{', '.join(missing)}"


@pytest.mark.parametrize("locale", list(README_FILES))
def test_readme_is_not_placeholder(locale: str, readme_contents: dict[str, str]) -> None:
    """每个 README 不应是缩略占位页（至少 1500 字符）。"""
    content = readme_contents[locale]
    assert len(content) >= 1500, (
        f"{locale} README 过短（{len(content)} 字符），疑似占位页"
    )
