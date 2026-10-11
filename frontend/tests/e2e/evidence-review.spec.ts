import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

test("image candidates require one explicit review batch before diagnosis", async ({ page }) => {
  const credentials = JSON.parse(readFileSync(path.resolve("../.private/demo-credentials.json"), "utf8"));
  await page.goto("/");
  await page.getByLabel("密码", { exact: true }).fill(credentials.engineer.password);
  await page.getByRole("button", { name: "登录工作台 →" }).click();
  await page.getByRole("button", { name: "载入 A203 参考输入" }).click();
  await page.getByRole("button", { name: "创建事件并补充图片 / 视频 →" }).click();
  await expect(page.getByRole("heading", { name: "证据复核" })).toBeVisible();
  await page.getByLabel("选择图片或视频").setInputFiles(path.resolve("../knowledge/fixtures/media/a203-panel-fixture.png"));
  await expect(page.getByLabel("复核 报警码")).toBeVisible({ timeout: 15000 });
  const start = page.getByRole("button", { name: "使用当前已确认事实开始诊断 →" });
  const save = page.getByRole("button", { name: "保存本轮证据复核 →" });
  await expect(start).toBeDisabled(); await expect(save).toBeDisabled();
  await expect(page.getByLabel("复核 报警码")).toHaveValue("");
  await page.getByLabel("复核 报警码").selectOption("CONFIRMED");
  await page.getByLabel("复核 设定温度").selectOption("CONFIRMED");
  await page.getByLabel("复核 实际温度").selectOption("CORRECTED");
  await page.getByLabel("修正值 实际温度").fill("128");
  await page.getByLabel("复核 加热电流").selectOption("REJECTED");
  await page.getByLabel("本轮复核说明").fill("对照合成fixture图片，确认读数；电流使用已确认文字，保留原始候选。 ");
  await save.click();
  await expect(page.getByLabel("复核 报警码")).toHaveCount(0);
  await expect(start).toBeEnabled(); await start.click();
  await expect(page.getByText("报告复核", { exact: true })).toBeVisible({ timeout: 15000 });
  await expect(page.getByRole("heading", { name: "已确认观察" })).toBeVisible();
  await expect(page.getByText(/已复核OCR候选：实际温度=128/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "H1 加热回路开路" })).toBeVisible();
  // A corrected/rejected candidate intentionally enters report review. The
  // browser flow stops here until each claim has an explicit human decision.
  await expect(page.getByRole("button", { name: "接受当前报告并恢复 →" })).toHaveCount(0);
});
