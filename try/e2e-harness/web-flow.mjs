import { expect } from "@playwright/test";
import { chromium } from "playwright";
import { readFileSync } from "node:fs";

const appUrl = process.env.LANGDRILL_E2E_URL || "http://127.0.0.1:5173";
const apiUrl = process.env.LANGDRILL_E2E_API || "http://127.0.0.1:8000";
const chromePath = process.env.LANGDRILL_CHROME_PATH || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const mimoKeyPath = process.env.LANGDRILL_MIMO_KEY_PATH || "D:\\0文件夹\\API key\\mimo.txt";

const consoleErrors = [];
const pageErrors = [];

async function resetDefaults() {
  const response = await fetch(`${apiUrl}/api/settings/defaults`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  if (!response.ok) {
    throw new Error(`reset defaults failed: ${response.status} ${await response.text()}`);
  }
}

async function send(page, text, expectedText, timeout = 20000) {
  const composer = page.locator(".composer textarea");
  const before = await page.locator("main .message.assistant .bubble").filter({ hasText: expectedText }).count();
  await composer.fill(text);
  await page.locator(".send-button").click();
  await page.waitForFunction(
    ({ expectedText, before }) => {
      return Array.from(document.querySelectorAll("main .message.assistant .bubble"))
        .filter((element) => element.textContent?.includes(expectedText)).length > before;
    },
    { expectedText, before },
    { timeout },
  );
}

async function expectNoRequestFailure(page) {
  await expect(page.getByText("请求失败")).toHaveCount(0);
}

function readMimoKey() {
  try {
    const raw = readFileSync(mimoKeyPath, "utf8");
    return raw.match(/sk-[A-Za-z0-9_-]+/)?.[0] || "";
  } catch {
    return "";
  }
}

await resetDefaults();

const browser = await chromium.launch({
  executablePath: chromePath,
  headless: true,
});

try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("dialog", async (dialog) => {
    if (dialog.type() === "prompt") {
      await dialog.accept("E2E Custom Provider");
    } else {
      await dialog.accept();
    }
  });

  await page.goto(appUrl);
  await expect(page.getByText("初始化设置")).toBeVisible();
  await page.getByLabel("供应商").selectOption("mock");
  await page.getByLabel("称呼").fill("boss");
  await page.getByLabel("目标语言").fill("日语");
  await page.getByLabel("目标考试").fill("大学日语四级");
  await page.getByLabel("学习目标").fill("按大学日语四级题型练习助词和阅读。");
  await page.getByLabel("学习背景").fill("已学过五十音和基础助词，需要真实刷题流程。");
  await page.getByLabel("真题参考年限").fill("5");
  await page.getByRole("button", { name: "进入日常使用" }).click();
  await expect(page.getByText("初始化设置")).toHaveCount(0);
  await expect(page.getByText("长期学习记录总面板")).toBeVisible();
  await expect(page.getByText("大学日语四级 · 日语")).toBeVisible();

  await send(page, "今天学习日语助词「まで」，按大学日语四级风格出题。", "已初始化今日学习面板，并准备好第一题。");
  await expect(page.getByText("当前题目")).toBeVisible();
  await expect(page.getByText("当日学习")).toBeVisible();
  if ((await page.locator(".session-link").count()) < 1) {
    throw new Error("session list did not show the created session");
  }

  await send(page, "请解释这题的考点，但先不要告诉我答案。", "\"task\":\"explanation\"");
  await expect(page.getByText("当前题目")).toBeVisible();

  await send(page, "A", "判断：正确");
  await expect(page.getByText("正确答案：A")).toBeVisible();
  await expectNoRequestFailure(page);

  await send(page, "总结今天", "今日学习总结");

  await page.evaluate(() => {
    const bubble = document.querySelector(".message.assistant .bubble");
    const stream = document.querySelector(".message-stream");
    if (!bubble || !stream) throw new Error("missing assistant bubble for branch selection");
    const range = document.createRange();
    range.selectNodeContents(bubble);
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);
    stream.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
  });
  await expect(page.getByText("开启分支对话")).toBeVisible();
  await page.getByText("开启分支对话").click();
  await expect(page.locator(".branch-panel").getByText("分支对话")).toBeVisible();
  await expect(page.getByText("已基于选中文本创建分支")).toBeVisible();
  await page.locator(".right-toggle").click();
  await expect(page.getByText("目前没有分支对话。")).toHaveCount(0);
  await page.locator(".right-toggle").click();
  await expect(page.locator(".branch-panel").getByText("分支对话")).toBeVisible();

  await page.locator(".rail-top .icon-button").click();
  await expect(page.getByText("Lang Drill")).toHaveCount(0);
  await page.locator(".rail-top .icon-button").click();
  await expect(page.getByText("Lang Drill")).toBeVisible();
  await page.locator(".session-link").click();
  await expect(page.locator("main .message.user .bubble").getByText("今天学习日语助词")).toBeVisible();

  await page.getByRole("button", { name: "设置" }).click();
  await expect(page.getByText("模型提供商")).toBeVisible();
  await page.locator('button[title="新增自定义提供商"]').click();
  await expect(page.getByText("添加成功")).toBeVisible();

  const modal = page.locator(".settings-modal");
  await modal.locator("select").nth(0).selectOption("mimo");
  const mimoKey = readMimoKey();
  if (mimoKey) {
    await modal.locator('input[type="password"]').fill(mimoKey);
  }
  await modal.getByPlaceholder("自定义模型名称，填写后优先使用").fill("mimo-v2.5");
  const saveModelResponse = page.waitForResponse((response) => response.url().endsWith("/api/model-config") && response.status() === 200);
  await page.getByRole("button", { name: "保存模型配置" }).click();
  await saveModelResponse;
  await modal.locator('input[type="password"]').fill("");
  await expect(page.getByText("模型配置已保存")).toBeVisible();
  await page.getByPlaceholder("目标考试、分数或能力目标").fill("本周完成大学日语四级助词专项。");
  await page.getByPlaceholder("当前水平、弱项、已学内容").fill("弱项是助词辨析和长句阅读。");
  await modal.locator("select").nth(2).selectOption("custom");
  await page.getByPlaceholder("填写自定义人格提示词").fill("语气冷静，少废话，每次先给结论。");
  const checkboxes = modal.locator('input[type="checkbox"]');
  const checkboxCount = await checkboxes.count();
  for (let i = 0; i < checkboxCount; i += 1) {
    await checkboxes.nth(i).click();
  }
  await modal.locator('input[type="range"]').nth(0).evaluate((element) => {
    element.value = "5";
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await page.getByRole("button", { name: "深色" }).click();
  await expect(page.getByRole("button", { name: "深色" })).toHaveClass(/active/);
  await page.getByRole("button", { name: "浅色" }).click();
  await expect(page.getByRole("button", { name: "浅色" })).toHaveClass(/active/);
  await page.getByRole("button", { name: "跟随系统" }).click();
  await expect(page.getByRole("button", { name: "跟随系统" })).toHaveClass(/active/);
  await modal.locator('input[type="range"]').nth(1).evaluate((element) => {
    element.value = "18";
    element.dispatchEvent(new Event("input", { bubbles: true }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await page.getByRole("button", { name: "重新打开初始化设置" }).click();
  await expect(page.getByText("初始化设置")).toBeVisible();
  await page.getByRole("button", { name: "稍后" }).click();

  if (mimoKey) {
    await send(page, "请再出一道日语助词选择题。", "已初始化今日学习面板，并准备好第一题。", 90000);
    await expectNoRequestFailure(page);
  }

  await page.getByRole("button", { name: "设置" }).click();
  await page.getByRole("button", { name: "取消" }).click();
  await expect(page.getByText("模型提供商")).toHaveCount(0);

  await page.getByRole("button", { name: "设置" }).click();
  await page.getByRole("button", { name: "恢复默认设置" }).click();
  await expect(page.getByText("已恢复默认设置。")).toBeVisible();
  await expect(modal.locator("select").nth(0)).toHaveValue("mock");
  await expect(page.locator("html")).toHaveAttribute("data-theme-mode", "system");
  await page.getByRole("button", { name: "取消" }).click();

  const bootstrap = await (await fetch(`${apiUrl}/api/bootstrap`)).json();
  if (bootstrap.profile.exam_id !== "unassigned") throw new Error("profile was not reset to defaults");
  if (bootstrap.model_config.provider_id !== "mock") throw new Error("model provider was not reset to mock");

  await expectNoRequestFailure(page);
  if (consoleErrors.length || pageErrors.length) {
    throw new Error(`browser errors: ${JSON.stringify({ consoleErrors, pageErrors })}`);
  }

  console.log("web flow e2e passed");
} finally {
  await resetDefaults().catch(() => {});
  await browser.close();
}
