import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

test("SAFE-01 stops before expert acknowledgement and never releases ordinary checks", async ({ page }) => {
  const credentials = JSON.parse(readFileSync(path.resolve("../.private/demo-credentials.json"), "utf8"));
  await page.goto("/");
  await page.getByLabel("账号", { exact: true }).fill("expert");
  await page.getByLabel("密码", { exact: true }).fill(credentials.expert.password);
  await page.getByRole("button", { name: "登录工作台 →" }).click();
  await expect(page.getByText("expert · 已登录")).toBeVisible();
  await page.getByLabel("描述现象与现场读数").fill("A203，现场出现烟雾和焦味");
  await page.getByRole("button", { name: "创建事件并开始诊断 →" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "立即停止进一步排查" })).toContainText("立即停止进一步排查", { timeout: 15000 });
  await expect(page.getByRole("alert").filter({ hasText: "立即停止进一步排查" })).toContainText("SAFE-01 · 第3页");
  await expect(page.getByRole("heading", { name: "已暂停，等待授权专家接管" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "下一步排查顺序" })).toHaveCount(0);
  const action = page.getByRole("button", { name: "记录停机与升级处置 →" });
  await expect(action).toBeDisabled();
  await page.getByLabel("停机与转交记录").fill("已停机并转交，未批准试运行或复机。");
  await action.click();
  await expect(page.getByText("已升级专家", { exact: true })).toBeVisible({ timeout: 15000 });
  await expect(page.getByRole("alert").filter({ hasText: "立即停止进一步排查" })).toContainText("立即停止进一步排查");
  await expect(page.getByRole("heading", { name: "下一步排查顺序" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "记录停机与升级处置 →" })).toHaveCount(0);
});

