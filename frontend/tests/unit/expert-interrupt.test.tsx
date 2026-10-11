import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import ExpertInterruptPanel from "../../components/ExpertInterruptPanel";
import SafetyActionCard from "../../components/SafetyActionCard";

afterEach(cleanup);

test("field engineer sees stop instruction and has no disposition control", () => {
  render(<ExpertInterruptPanel canConfirm={false} busy={false} onConfirm={vi.fn()} />);
  expect(screen.getByText(/不批准试运行或复机/)).toBeInTheDocument();
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});

test("expert must write a disposition and cannot interpret the control as operation permission", () => {
  const confirm = vi.fn();
  render(<ExpertInterruptPanel canConfirm busy={false} onConfirm={confirm} />);
  const button = screen.getByRole("button", { name: /记录停机与升级处置/ });
  expect(button).toBeDisabled();
  fireEvent.change(screen.getByLabelText("停机与转交记录"), { target: { value: "   " } });
  expect(button).toBeDisabled();
  fireEvent.change(screen.getByLabelText("停机与转交记录"), { target: { value: "已停机并转交，未批准复机。" } });
  fireEvent.click(button);
  expect(confirm).toHaveBeenCalledExactlyOnceWith("已停机并转交，未批准复机。");
});

test("stop notice displays an actual manual locator", () => {
  render(<SafetyActionCard notice={{ safety_blocked: true, reasons: ["焦味"],
    citations: [{ source_ref: "SAFE-01", page: 3, section: "2. 安全红线" }] }} />);
  expect(screen.getByRole("alert")).toHaveTextContent("SAFE-01 · 第3页");
});
