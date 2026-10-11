import { test, expect, type Page } from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
import path from "node:path";

async function login(page: Page) {
  const credentials = JSON.parse(readFileSync(path.resolve("../.private/demo-credentials.json"), "utf8"));
  await page.goto("/");
  await page.getByLabel("密码", { exact: true }).fill(credentials.engineer.password);
  await page.getByRole("button", { name: "登录工作台 →" }).click();
  await expect(page.getByText("engineer · 已登录")).toBeVisible();
}

test("A203 auto report, citation source and responsive layout", async ({ page }) => {
  await login(page);
  await page.getByRole("button", { name: "载入 A203 参考输入" }).click();
  await page.getByRole("button", { name: "创建事件并开始诊断 →" }).click();
  await expect(page.getByText("报告已发布", { exact: true })).toBeVisible({ timeout: 15000 });
  await expect(page.getByRole("heading", { name: "H1 加热回路开路" })).toBeVisible();
  await expect(page.getByText("最终根因未确认", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "历史案例对照" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "说明书参数与依据" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "停止条件与专家升级" })).toBeVisible();
  await expect(page.getByText("已预热：是", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "接受当前报告并恢复 →" })).toHaveCount(0);
  const assessment = page.getByRole("region", { name: "检索结果评估" });
  await expect(assessment).toContainText("SKIPPED_POLICY");
  await expect(assessment).toContainText("未调用 Jev");
  await assessment.getByText("查看已授权来源的评估记录").click();
  await expect(assessment.getByText(/相关性：未判断/).first()).toBeVisible();
  await expect(assessment.getByText(/无模型结果/).first()).toBeVisible();
  await assessment.getByText("查看已授权来源的评估记录").click();
  await page.getByRole("button", { name: "WO-240-042 ↗" }).first().click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await expect(page.getByRole("dialog")).toContainText("第6页");
  await page.getByRole("button", { name: "关闭引用" }).click();
  mkdirSync(path.resolve("../.private/output/playwright"), { recursive: true });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: "../.private/output/playwright/a203-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("heading", { name: /现场诊断工作台/ })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: "../.private/output/playwright/a203-mobile.png", fullPage: true });
});

test("A203 forced review pauses and resumes the same diagnosis", async ({ page }) => {
  await login(page);
  await page.getByRole("button", { name: "载入 A203 参考输入" }).click();
  await page.getByLabel("报告发布前强制人工复核").check();
  await page.getByRole("button", { name: "创建事件并开始诊断 →" }).click();
  const review = page.getByRole("button", { name: "接受当前报告并恢复 →" });
  await expect(review).toBeVisible({ timeout: 15000 });
  await expect(page.getByText(/待复核草稿/)).toBeVisible();
  await review.click();
  await expect(page.getByText("报告已发布", { exact: true })).toBeVisible({ timeout: 15000 });
  await expect(page.getByText(/HUMAN_REVIEWED/)).toBeVisible();
});

test("uncertain preheating asks for a fact instead of auto filling the fixture", async ({ page }) => {
  await login(page);
  await page.getByLabel("描述现象与现场读数").fill("A203，设定165，实际128，加热电流0，可能已预热");
  await page.getByRole("button", { name: "创建事件并开始诊断 →" }).click();
  await expect(page.getByRole("heading", { name: "需要补充现场事实" })).toBeVisible({ timeout: 15000 });
  await expect(page.getByText("报告已发布", { exact: true })).toHaveCount(0);
  const originalUrl = page.url();
  const submit = page.getByRole("button", { name: "提交事实并恢复 →" });
  await expect(submit).toBeDisabled();
  await page.getByLabel("是否已预热").selectOption("true");
  await submit.click();
  await expect(page.getByText("报告已发布", { exact: true })).toBeVisible({ timeout: 15000 });
  expect(page.url()).toBe(originalUrl);
  await expect(page.getByText("最终根因未确认", { exact: true })).toBeVisible();
});

test("non-template report requires explicit per-claim decisions before publication", async ({ page }) => {
  await login(page);
  await page.getByLabel("描述现象与现场读数").fill("A203，设定165，实际130，加热电流0，已预热");
  await page.getByRole("button", { name: "创建事件并开始诊断 →" }).click();
  await expect(page.getByRole("heading", { name: "非参考场景：逐项核对依据" })).toBeVisible({ timeout: 15000 });
  const publish = page.getByRole("button", { name: "接受当前报告并恢复 →" });
  const save = page.getByRole("button", { name: "保存逐项审核记录 →" });
  await expect(publish).toBeDisabled();
  await expect(save).toBeDisabled();
  const choices = page.locator('input[name="claim-review"]');
  expect(await choices.count()).toBeGreaterThan(1);
  for (const checkbox of await choices.all()) {
    await expect(checkbox).not.toBeChecked();
    await checkbox.check();
  }
  await expect(save).toBeDisabled();
  await page.getByLabel("审核说明").fill("浏览器模拟审核：逐项核对引用，只接受建议，未确认最终根因。");
  await save.click();
  await expect(page.getByText("逐项审核记录已保存，绑定当前报告版本。")).toBeVisible();
  await publish.click();
  await expect(page.getByText("报告已发布", { exact: true })).toBeVisible({ timeout: 15000 });
  await expect(page.getByText("最终根因未确认", { exact: true })).toBeVisible();
});
