import { describe, expect, it } from "vitest";
import { informationAnswers } from "../../lib/information";

describe("information answers preserve missing values", () => {
  it("omits blank and stale fields instead of converting blanks to zero", () => {
    expect(informationAnswers({ heating_current_a: "", actual_temperature_c: "128" }, ["heating_current_a"])).toEqual({});
  });
  it("preserves explicitly entered zero and false", () => {
    expect(informationAnswers({ heating_current_a: "0", preheating_confirmed: "false" }, ["heating_current_a", "preheating_confirmed"])).toEqual({ heating_current_a: 0, preheating_confirmed: false });
  });
  it.each(["NaN", "Infinity", "0x10", "unknown", "1e999"])("rejects invalid numeric input %s", value => {
    expect(() => informationAnswers({ heating_current_a: value }, ["heating_current_a"])).toThrow();
  });
  it("does not translate unknown preheating into false", () => {
    expect(() => informationAnswers({ preheating_confirmed: "unknown" }, ["preheating_confirmed"])).toThrow();
  });
});
