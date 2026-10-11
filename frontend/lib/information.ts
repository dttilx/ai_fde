export function informationAnswers(values: Record<string, string>, pending: string[]): Record<string, number | boolean> {
  const result: Record<string, number | boolean> = {};
  for (const key of pending) {
    const value = values[key]?.trim();
    if (!value) continue;
    if (key === "preheating_confirmed" || key === "continuous_leak_sound") {
      if (value !== "true" && value !== "false") throw new Error("观察状态必须明确选择，未知请留空。");
      result[key] = value === "true";
    } else {
      if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?$/i.test(value) || !Number.isFinite(Number(value))) {
        throw new Error("读数必须是有效数字，未知请留空。");
      }
      result[key] = Number(value);
    }
  }
  return result;
}
