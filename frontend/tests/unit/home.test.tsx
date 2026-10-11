import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import Home from "../../app/page";

test("workbench requires login and honestly labels fixture processing", () => {
  render(<Home />);
  expect(screen.getByRole("heading", { name: /现场诊断工作台/ })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /登录工作台/ })).toBeInTheDocument();
  expect(screen.getByText(/尚未调用真实模型或外部 Jev/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /创建事件/ })).not.toBeInTheDocument();
});
