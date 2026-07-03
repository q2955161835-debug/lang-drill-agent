const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const repoRoot = path.resolve(__dirname, "..");
const demoRoot = path.join(repoRoot, "测试数据", "演示数据库", "产品网站演示-20260703");
const outputDir = path.join(demoRoot, "product-screenshots");
const inputDir = path.join(demoRoot, "input-screenshots");
const baseUrl = "http://127.0.0.1:5173";

fs.mkdirSync(outputDir, { recursive: true });

const shots = [];
const consoleMessages = [];

function shotPath(name) {
  return path.join(outputDir, name);
}

async function capture(page, name, note = "") {
  const target = shotPath(name);
  await page.screenshot({ path: target, fullPage: false });
  shots.push({ file: target, note });
}

async function clickText(page, text, timeout = 15000) {
  const locator = page.getByText(text, { exact: false }).first();
  await locator.waitFor({ state: "visible", timeout });
  await locator.click();
}

async function clickButton(page, name, timeout = 15000) {
  const locator = page.getByRole("button", { name }).first();
  await locator.waitFor({ state: "visible", timeout });
  await locator.click();
}

async function ensureWorkbenchOpen(page) {
  const tabs = page.locator(".workbench-tabs").first();
  if (await tabs.isVisible().catch(() => false)) {
    return;
  }
  await clickButton(page, "展开右侧工作台");
  await tabs.waitFor({ state: "visible", timeout: 15000 });
}

async function openSettingsTab(page, label) {
  await page.getByRole("button", { name: "设置" }).first().click();
  await page.locator(".settings-modal").waitFor({ state: "visible", timeout: 15000 });
  await page.locator(".settings-tabs button").filter({ hasText: label }).click();
  await page.waitForTimeout(500);
}

async function switchSettingsTab(page, label) {
  await page.locator(".settings-tabs button").filter({ hasText: label }).click();
  await page.waitForTimeout(500);
}

async function closeSettings(page) {
  const cancel = page.getByRole("button", { name: "取消" }).last();
  if (await cancel.isVisible().catch(() => false)) {
    await cancel.click();
    await page.locator(".settings-modal").waitFor({ state: "hidden", timeout: 10000 });
  }
}

async function selectSession(page, dateText, sessionText) {
  await clickButton(page, new RegExp(dateText));
  await clickButton(page, new RegExp(sessionText));
  await page.waitForTimeout(1200);
}

async function waitForBodyText(page, patterns, timeout = 60000) {
  const checks = patterns.map((pattern) => pattern.toString());
  await page.waitForFunction(
    (rawPatterns) => {
      const text = document.body.innerText || "";
      return rawPatterns.some((raw) => {
        if (raw.startsWith("/") && raw.endsWith("/")) {
          return new RegExp(raw.slice(1, -1)).test(text);
        }
        return text.includes(raw);
      });
    },
    checks,
    { timeout }
  );
}

async function fillLabeledField(page, labelText, value) {
  const field = page.locator("label").filter({ hasText: labelText }).locator("input, textarea").first();
  await field.waitFor({ state: "visible", timeout: 15000 });
  await field.fill(value);
}

async function parseScreenshotImport(page) {
  const files = [
    path.join(inputDir, "65a03fb7c59367f9d718b38c3a590827.png"),
    path.join(inputDir, "b305dcda304ff9d2744385d455cde101.png"),
  ];
  await page.locator(".screenshot-import-panel input[type=file]").setInputFiles(files);
  await waitForBodyText(page, ["待解析文件 2"], 15000);
  await capture(page, "06-cet4-screenshot-import-queued.png", "右侧截图导入：两张单词截图已入队，尚未解析。");

  const clear = page.getByRole("button", { name: "清空" }).first();
  const canClear = await clear.isVisible().catch(() => false) && await clear.isEnabled().catch(() => false);
  if (canClear) {
    await clear.click();
  }
  const ocrText = fs.readFileSync(path.join(inputDir, "english-vocab-ocr-text.txt"), "utf8");
  await fillLabeledField(page, "源图片路径 / 文件名", files.map((item) => path.basename(item)).join("、"));
  await fillLabeledField(page, "截图识别文本", ocrText);
  await page.getByRole("button", { name: "解析文本" }).click();
  await page.locator(".screenshot-word-list").first().waitFor({ state: "visible", timeout: 20000 });

  await capture(page, "07-cet4-screenshot-import-parsed.png", "截图导入解析结果：可编辑词条卡。");
  await page.locator(".screenshot-import-panel").evaluate((node) => {
    node.scrollTop = node.scrollHeight;
  });
  await page.waitForTimeout(400);
  await capture(page, "08-cet4-screenshot-import-bottom-action.png", "截图导入底部确认按钮。");
  await page.getByRole("button", { name: "导入并开始练习" }).click();
  await waitForBodyText(page, ["已导入", "本轮已先生成并入库", "当前进度", "模型暂时不可用"], 120000);
  await capture(page, "09-cet4-screenshot-import-auto-drill.png", "确认导入后自动创建练习会话和题卡。");
}

async function captureSettingsPages(page) {
  await openSettingsTab(page, "模型");
  await capture(page, "10-settings-model-mimo.png", "设置页模型配置：MiMo 当前模型、思考等级、视觉能力、模型列表。");

  await page.locator(".settings-modal select").first().selectOption("deepseek");
  await page.waitForTimeout(500);
  const customToggle = page.getByRole("button", { name: /添加自定义模型|收起自定义模型/ }).first();
  if (await customToggle.isVisible().catch(() => false)) {
    const label = await customToggle.innerText();
    if (label.includes("添加")) await customToggle.click();
  }
  await fillLabeledField(page, "模型 ID", "deepseek-reasoner-demo");
  await fillLabeledField(page, "显示名称", "DeepSeek Reasoner 演示");
  await fillLabeledField(page, "上下文容量", "1000000");
  await capture(page, "11-settings-model-deepseek-custom.png", "设置页演示 DeepSeek 自定义模型填写。");

  await switchSettingsTab(page, "考试");
  await capture(page, "12-settings-exam.png", "设置页考试选择、考试时间和目标语言。");

  await switchSettingsTab(page, "考纲");
  await capture(page, "13-settings-syllabus-papers.png", "设置页考纲、历年真题和题型勾选。");
  await page.getByRole("button", { name: /加入试卷/ }).first().click();
  await page.waitForTimeout(500);
  await capture(page, "14-settings-paper-import-expanded.png", "考纲页加入试卷表单展开。");

  await switchSettingsTab(page, "令牌");
  await capture(page, "15-settings-token-ledger.png", "令牌页使用台账、模型排行和最近调用。");

  await switchSettingsTab(page, "数据");
  await capture(page, "16-settings-data-paths.png", "数据页展示隔离演示数据库路径和表计数。");

  await switchSettingsTab(page, "权限");
  await capture(page, "17-settings-agent-permissions.png", "权限页默认能力、敏感设置权限。");

  await switchSettingsTab(page, "拓展 Skills");
  await capture(page, "18-settings-skills.png", "拓展 Skills 页：内置联网检索和可选技能开关。");

  await switchSettingsTab(page, "学习");
  await capture(page, "19-settings-study-custom-instruction.png", "学习设置页：目标、背景、自定义指令和复习强度。");

  await switchSettingsTab(page, "外观");
  await capture(page, "20-settings-appearance.png", "外观页：主题与字号。");

  await closeSettings(page);
}

async function switchToJapanese(page) {
  await page.evaluate(async () => {
    await fetch("/api/profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        target_language: "日语",
        exam_id: "cjt4",
        exam_name: "大学日语四级",
        deadline: "2026-12-13T09:00",
        learning_goal: "大学日语四级稳定通过，重点恢复文字与語彙、文法和阅读改写题。",
        learning_background: "高中日语基础仍在，但词汇读音、假名表记和语法接续遗忘较多；本演示库由旧日语四级真实数据迁移。"
      })
    });
  });
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForTimeout(1200);
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) {
      consoleMessages.push({ type: message.type(), text: message.text() });
    }
  });
  page.on("pageerror", (error) => {
    consoleMessages.push({ type: "pageerror", text: error.message });
  });

  await page.goto(baseUrl, { waitUntil: "networkidle" });
  await page.waitForTimeout(1000);
  await capture(page, "01-cet4-home-long-panel.png", "英语四级长期学习总面板。");

  await selectSession(page, "2026-07-02", "截图词表练习：collection");
  await waitForBodyText(page, ["当前题目：第 6 题"], 15000);
  await capture(page, "02-cet4-active-question.png", "英语四级当前题卡、历史消息和左侧当日面板。");

  await page.getByRole("button", { name: /^A\.\s*collection/ }).click();
  await page.locator('textarea[name="langdrill-question-followup"]').fill("为什么这里不能选 collision？请先回答这个问题。");
  await page.getByRole("button", { name: "提交" }).click();
  await waitForBodyText(page, ["当前题目：第 7 题"], 120000);
  await page.locator(".message.assistant").filter({ hasText: "这里不能选 collision" }).last().scrollIntoViewIfNeeded();
  await page.waitForTimeout(500);
  await capture(page, "03-cet4-answer-feedback-extra-question.png", "答题后带补充提问的判题讲解和下一题自动推进。");

  await ensureWorkbenchOpen(page);
  await waitForBodyText(page, ["分支对话"], 15000);
  await capture(page, "04-right-workbench-branch-empty.png", "右侧分支工作台打开状态。");

  await page.getByRole("button", { name: /基于当前题创建分支/ }).click();
  await page.locator(".branch-quote-card").waitFor({ state: "visible", timeout: 15000 });
  await capture(page, "05-branch-reference-card.png", "基于当前题创建分支引用卡，未直接发送主消息。");
  await page.locator(".branch-composer textarea").fill("把这题的 collection 和 collision 做成对比复习卡。");
  await page.locator(".branch-send-button").click();
  await waitForBodyText(page, ["当前分支"], 120000);
  await capture(page, "05b-branch-conversation.png", "分支对话生成结果。");

  await ensureWorkbenchOpen(page);
  await page.locator(".workbench-tabs button").filter({ hasText: "截图导入" }).click();
  await page.waitForTimeout(500);
  await parseScreenshotImport(page);

  await ensureWorkbenchOpen(page);
  await page.locator(".workbench-tabs button").filter({ hasText: "手机映像" }).click();
  await page.getByRole("button", { name: "检查环境" }).click();
  await waitForBodyText(page, ["adb", "需要安装"], 15000);
  await capture(page, "21-right-workbench-phone-mirror.png", "手机映像环境检查页。");

  await captureSettingsPages(page);

  await switchToJapanese(page);
  await capture(page, "22-cjt4-home-long-panel.png", "切换到日语四级后的长期学习总面板。");
  await selectSession(page, "2026-07-01", "日语四级错题回流");
  await waitForBodyText(page, ["当前题目：第 5 题"], 15000);
  await capture(page, "23-cjt4-active-question.png", "日语四级旧数据迁移后的错题回流会话。");
  await openSettingsTab(page, "考纲");
  await capture(page, "24-cjt4-syllabus-papers.png", "日语四级考纲和真题题型页。");
  await closeSettings(page);

  const mobile = await context.newPage();
  await mobile.setViewportSize({ width: 390, height: 844 });
  await mobile.goto(baseUrl, { waitUntil: "networkidle" });
  await mobile.waitForTimeout(1200);
  await capture(mobile, "25-mobile-home.png", "移动视口首页。");
  await mobile.close();

  await browser.close();
  const report = {
    created_at: new Date().toISOString(),
    base_url: baseUrl,
    output_dir: outputDir,
    shots,
    console_messages: consoleMessages,
  };
  fs.writeFileSync(path.join(outputDir, "screenshot-report.json"), JSON.stringify(report, null, 2), "utf8");
  console.log(JSON.stringify({ outputDir, count: shots.length, consoleMessages: consoleMessages.length }, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
