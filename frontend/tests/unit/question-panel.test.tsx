import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import QuestionPanel from "../../components/QuestionPanel";
import { informationAnswers } from "../../lib/information";

const pending = ["upstream_pressure_mpa", "device_pressure_mpa", "continuous_leak_sound"];
afterEach(cleanup);
describe("partial information", () => {
  it("does not silently default unknown observations or readings", () => {
    render(<QuestionPanel pending={pending} values={{}} busy={false} onChange={vi.fn()} onSubmit={vi.fn()} />);
    expect(screen.getByRole("button")).toBeDisabled();
    expect(screen.getByRole("combobox")).toHaveValue("");
    expect(informationAnswers({}, pending)).toEqual({});
  });
  it("submits only an explicitly supplied partial answer", () => {
    const submit = vi.fn();
    render(<QuestionPanel pending={pending} values={{ upstream_pressure_mpa: "0.64" }} busy={false} onChange={vi.fn()} onSubmit={submit} />);
    fireEvent.click(screen.getByRole("button"));
    expect(submit).toHaveBeenCalledOnce();
    expect(informationAnswers({ upstream_pressure_mpa: "0.64" }, pending)).toEqual({ upstream_pressure_mpa: 0.64 });
  });
  it("preserves false as an observed fact instead of absence", () => {
    expect(informationAnswers({ continuous_leak_sound: "false" }, pending)).toEqual({ continuous_leak_sound: false });
  });
});
