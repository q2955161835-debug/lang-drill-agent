from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright


ROOT = Path.cwd()
RUNTIME_DIR = ROOT / "try" / ".cache" / "browser-acceptance"
SKILLS_ROOT = RUNTIME_DIR / "skills"
APP_URL = os.getenv("LANGDRILL_ACCEPTANCE_URL", "http://127.0.0.1:5173")
API_URL = os.getenv("LANGDRILL_ACCEPTANCE_API", "http://127.0.0.1:8000")
RUN_ID = int(time.time())
CUSTOM_MODEL_ID = f"browser-acceptance-model-{RUN_ID}"
CUSTOM_MODEL_LABEL = f"Browser Acceptance Model {RUN_ID}"
BRANCH_WORDS = "meal: 一餐\nsteal: 偷盗\nsave: 节省；救助\nemerge: 出现\ndish: 菜肴"


def fail(message: str) -> None:
    raise AssertionError(message)


def expect_visible(locator, label: str) -> None:
    try:
        locator.first.wait_for(state="visible", timeout=7000)
    except PlaywrightTimeoutError as exc:
        raise AssertionError(f"{label} 不可见") from exc


def section_by_heading(page: Page, heading: str):
    section = page.locator("section.setting-section").filter(
        has=page.get_by_role("heading", name=heading)
    ).first
    expect_visible(section, f"设置区块：{heading}")
    return section


def click_tab(page: Page, label: str) -> None:
    page.get_by_role("button", name=label, exact=True).click()


def wait_post(page: Page, url_part: str, action) -> None:
    with page.expect_response(
        lambda response: url_part in response.url and response.request.method == "POST",
        timeout=10000,
    ) as response_info:
        action()
    response = response_info.value
    if not response.ok:
        fail(f"{url_part} 接口失败：{response.status}")


def wait_skill_save(page: Page, action) -> None:
    wait_post(page, "/api/skills/enabled", action)


def set_skill_toggle(page: Page, toggle, enabled: bool) -> None:
    if toggle.is_checked() == enabled:
        return
    wait_skill_save(page, toggle.click)


def write_skill_fixture(skill_id: str, description: str) -> None:
    skill_dir = SKILLS_ROOT / skill_id
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"""---
name: {skill_id}
description: {description}
---

# {skill_id.replace("-", " ").title()}

This skill does not require API keys.
""",
        encoding="utf-8",
    )


def prepare_runtime_files() -> tuple[Path, Path]:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    write_skill_fixture("multi-search-engine", "Build auditable search URLs with no API keys.")
    write_skill_fixture("browser-acceptance-skill", "Fixture skill for independent toggle checks.")
    word_file = RUNTIME_DIR / "browser-words.txt"
    paper_file = RUNTIME_DIR / "browser-paper.md"
    word_file.write_text(
        "collision: 碰撞；冲突\nsnowstorm: 暴风雪\nwaterfall: 瀑布\n",
        encoding="utf-8",
    )
    paper_file.write_text(
        "# Browser Acceptance Paper\n\nreading: short passage\nwriting: short essay\n",
        encoding="utf-8",
    )
    return word_file, paper_file


def normalized_path(value: str) -> str:
    return str(Path(value)).lower().rstrip("\\/")


def assert_acceptance_skill_root(page: Page) -> None:
    response = page.request.get(f"{API_URL}/api/skills", timeout=10000)
    if not response.ok:
        fail(f"/api/skills 接口不可用：{response.status}")
    status: dict[str, Any] = response.json().get("skills_status", {})
    roots = {normalized_path(str(root)) for root in status.get("skills_roots", [])}
    expected_root = normalized_path(str(SKILLS_ROOT))
    installed_ids = {str(skill.get("id", "")) for skill in status.get("installed", [])}
    required_ids = {"multi-search-engine", "browser-acceptance-skill"}
    if expected_root not in roots or not required_ids.issubset(installed_ids):
        fail(
            "浏览器验收需要服务端使用临时拓展 Skills 根目录启动。\n"
            "先设置环境变量后重启服务：\n"
            f"$env:LANGDRILL_DB_PATH='{RUNTIME_DIR / 'langdrill-agent.db'}'\n"
            f"$env:LANGDRILL_USER_DATA_DIR='{RUNTIME_DIR}'\n"
            f"$env:LANGDRILL_SKILLS_ROOTS='{SKILLS_ROOT}'"
        )


def prepare_learning_state(page: Page) -> None:
    model_response = page.request.post(
        f"{API_URL}/api/model-config",
        data={
            "provider_id": "mock",
            "base_url": "",
            "model": "mock-tutor-v1",
            "api_format": "mock",
            "thinking_level": "",
            "vision": False,
        },
        timeout=10000,
    )
    if not model_response.ok:
        fail(f"Mock Provider 配置失败：{model_response.status}")
    parse_response = page.request.post(
        f"{API_URL}/api/screenshot/parse",
        data={
            "text": BRANCH_WORDS,
            "session_id": None,
            "import_to_session": True,
            "auto_start_drill": True,
            "force_new_session": True,
            "source_image_path": "browser-acceptance-inline-words.txt",
        },
        timeout=15000,
    )
    if not parse_response.ok:
        fail(f"浏览器验收学习状态准备失败：{parse_response.status}")


def main() -> None:
    word_file, paper_file = prepare_runtime_files()
    console_issues: list[str] = []

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(channel="msedge", headless=True)
        except Exception:
            browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 980})
        page = context.new_page()

        page.on(
            "console",
            lambda message: console_issues.append(f"{message.type}: {message.text}")
            if message.type in {"error", "warning"}
            else None,
        )
        page.on("pageerror", lambda error: console_issues.append(f"pageerror: {error}"))
        page.on("dialog", lambda dialog: dialog.accept())

        assert_acceptance_skill_root(page)
        prepare_learning_state(page)
        page.goto(APP_URL, wait_until="domcontentloaded")
        expect_visible(page.get_by_text("Lang Drill").first, "首页品牌")
        page.locator("button").filter(has_text="设置").first.click()
        expect_visible(page.get_by_role("heading", name="设置"), "设置弹窗")

        click_tab(page, "权限")
        permissions = section_by_heading(page, "Agent 设置权限")
        permission_text = permissions.text_content() or ""
        if "拓展 Skills" in permission_text:
            fail("权限页仍显示拓展 Skills 总权限")
        if "默认关闭的扩展权限" in permission_text:
            fail("权限页仍显示空的扩展权限分组")
        web_permission = permissions.locator("label.permission-row").filter(has_text="联网功能").locator("input[type='checkbox']")
        custom_model_permission = permissions.locator("label.permission-row").filter(has_text="配置自定义模型").locator("input[type='checkbox']")
        if not web_permission.is_checked():
            fail("联网功能默认未勾选")
        if custom_model_permission.is_checked():
            fail("配置自定义模型默认应关闭")

        click_tab(page, "拓展 Skills")
        skills = section_by_heading(page, "拓展 Skills")
        skills_text = skills.text_content() or ""
        if "每个拓展 Skill 都有独立开关" not in skills_text:
            fail("拓展 Skills 页未说明单个拓展 Skill 独立开关")
        if "需要先在权限页开启" in skills_text:
            fail("拓展 Skills 页仍提示需要权限页总开关")
        if "内置工具始终开启" not in skills_text:
            fail("拓展 Skills 页未显示内置工具始终开启状态")
        if "联网权限已开启" not in skills_text:
            fail("拓展 Skills 页未显示联网权限状态")

        multi_card = skills.locator(".skill-card").filter(has_text="Multi Search Engine").first
        demo_card = skills.locator(".skill-card").filter(has_text="Browser Acceptance Skill").first
        expect_visible(multi_card, "Multi Search Engine Skill 卡片")
        expect_visible(demo_card, "Browser Acceptance Skill 卡片")
        multi_toggle = multi_card.locator("input[type='checkbox']")
        demo_toggle = demo_card.locator("input[type='checkbox']")
        set_skill_toggle(page, multi_toggle, False)
        set_skill_toggle(page, demo_toggle, False)
        set_skill_toggle(page, multi_toggle, True)
        if not multi_toggle.is_checked() or demo_toggle.is_checked():
            fail("开启第一个 Skill 时影响了其它 Skill")
        set_skill_toggle(page, demo_toggle, True)
        if not multi_toggle.is_checked() or not demo_toggle.is_checked():
            fail("两个 Skill 不能同时独立开启")
        set_skill_toggle(page, multi_toggle, False)
        if multi_toggle.is_checked() or not demo_toggle.is_checked():
            fail("关闭第一个 Skill 时影响了第二个 Skill")
        set_skill_toggle(page, demo_toggle, False)

        click_tab(page, "模型")
        model = section_by_heading(page, "模型提供商")
        model.get_by_role("button", name="添加自定义模型").click()
        custom_model_form = model.locator(".custom-model-form").first
        expect_visible(custom_model_form, "自定义模型表单")
        custom_model_form.locator("input[placeholder='例如：mimo-v2.5-ultra']").fill(CUSTOM_MODEL_ID)
        custom_model_form.locator("input[placeholder='可选，留空则同模型 ID']").fill(CUSTOM_MODEL_LABEL)
        custom_model_form.locator("input[type='number']").fill("123000")
        custom_model_form.locator("label").filter(has_text="该自定义模型支持图片输入").locator("input").check()
        wait_post(
            page,
            "/api/model-config/models/custom",
            lambda: custom_model_form.get_by_role("button", name="保存自定义模型").click(),
        )
        custom_model_row = model.locator(".model-visibility-row").filter(has_text=CUSTOM_MODEL_LABEL).first
        expect_visible(custom_model_row, "新增自定义模型行")
        row_text = custom_model_row.text_content() or ""
        if "自定义" not in row_text or "12.3万" not in row_text:
            fail("自定义模型行未显示自定义标记或上下文容量")
        wait_post(
            page,
            "/api/model-config/models/custom/delete",
            lambda: custom_model_row.get_by_role("button", name="删除").click(),
        )
        try:
            custom_model_row.wait_for(state="detached", timeout=7000)
        except PlaywrightTimeoutError as exc:
            raise AssertionError("删除后自定义模型仍在模型列表中") from exc

        click_tab(page, "考纲")
        past_papers = section_by_heading(page, "历年真题与题型")
        past_text = past_papers.text_content() or ""
        if "联网搜索导入" in past_text:
            fail("失效的联网搜索导入按钮仍存在")
        expect_visible(past_papers.get_by_role("link", name="打开来源网站"), "真题来源网站链接")
        past_papers.get_by_role("button", name="加入试卷").click()
        expect_visible(past_papers.locator(".paper-import-grid"), "加入试卷导入栏")
        past_papers.locator(".paper-import-grid input[type='file']").set_input_files(str(paper_file))
        expect_visible(past_papers.get_by_text("browser-paper.md"), "试卷待导入文件名")
        listening_type = past_papers.locator(".question-type-grid label").filter(has_text="听力").first.locator("input[type='checkbox']")
        expect_visible(listening_type, "听力题型复选框")
        if not listening_type.is_disabled() or listening_type.is_checked():
            fail("听力题型应预留为禁用且默认未勾选")
        if "暂未接入听力题和语音模型" not in (past_papers.text_content() or ""):
            fail("听力题型未说明预留原因")
        first_question_type = past_papers.locator(".question-type-grid input[type='checkbox']:not(:disabled)").first
        before_question_type = first_question_type.is_checked()
        wait_post(page, "/api/past-papers/question-types", first_question_type.click)
        if first_question_type.is_checked() == before_question_type:
            fail("题型勾选状态没有变化")
        wait_post(page, "/api/past-papers/question-types", first_question_type.click)

        click_tab(page, "数据")
        data_section = section_by_heading(page, "题目数据库")
        data_status = page.request.get(f"{API_URL}/api/data-paths", timeout=10000)
        if not data_status.ok:
            fail(f"/api/data-paths 接口不可用：{data_status.status}")
        counts: dict[str, int] = data_status.json().get("counts", {})
        expected_counts = {
            "题目": counts.get("questions", 0),
            "作答": counts.get("attempts", 0),
            "会话": counts.get("study_sessions", 0),
            "知识项": counts.get("knowledge_items", 0),
        }
        for _ in range(20):
            data_text = data_section.inner_text()
            if all(f"{label}\n{value}" in data_text for label, value in expected_counts.items()):
                break
            page.wait_for_timeout(250)
        else:
            fail(f"数据页计数未刷新到后端真实值：{expected_counts}")

        page.locator(".modal-head .icon-button").click()
        page.locator(".settings-modal").wait_for(state="detached", timeout=7000)
        page.locator("button.session-link").filter(has_text="截图词表练习").first.click()
        expect_visible(page.get_by_text("当前题目：第 1 题 / 共 5 题"), "当前题卡")
        expand_right = page.get_by_role("button", name="展开右侧工作台")
        if expand_right.is_visible():
            expand_right.click()
        page.get_by_role("tab", name="分支").click()
        branch_panel = page.locator("section.workbench-form").filter(has_text="分支对话").first
        expect_visible(branch_panel, "分支面板")
        create_branch_button = branch_panel.get_by_role("button", name="基于当前题创建分支")
        expect_visible(create_branch_button, "当前题分支创建按钮")
        wait_post(page, "/api/branch", create_branch_button.click)
        expect_visible(branch_panel.get_by_text("当前分支："), "分支编号")
        branch_panel.locator("textarea").fill("请用一句话解释正确答案。")
        wait_post(page, "/api/branch/", lambda: branch_panel.get_by_role("button", name="发送分支消息").click())
        expect_visible(branch_panel.get_by_text("请用一句话解释正确答案。"), "分支追问")

        page.get_by_role("tab", name="截图导入").click()
        screenshot_panel = page.locator("section.workbench-form").filter(has_text="截图导入").first
        expect_visible(screenshot_panel, "截图导入面板")
        screenshot_panel.locator("input[type='file']").set_input_files(str(word_file))
        expect_visible(screenshot_panel.get_by_text("browser-words.txt"), "截图导入待解析文件")
        page.get_by_role("tab", name="分支").click()
        page.get_by_role("tab", name="截图导入").click()
        expect_visible(screenshot_panel.get_by_text("browser-words.txt"), "页签切换后待解析文件")
        page.get_by_role("button", name="收起右侧工作台").click()
        page.get_by_role("button", name="展开右侧工作台").click()
        expect_visible(screenshot_panel.get_by_text("browser-words.txt"), "折叠展开后待解析文件")

        if console_issues:
            fail("浏览器控制台出现 error/warning：\n" + "\n".join(console_issues))

        page.request.post(f"{API_URL}/api/skills/enabled", data={"skill_id": "multi-search-engine", "enabled": False})
        page.request.post(f"{API_URL}/api/skills/enabled", data={"skill_id": "browser-acceptance-skill", "enabled": False})
        context.close()
        browser.close()


if __name__ == "__main__":
    main()
