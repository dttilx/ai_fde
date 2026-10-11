"use client";

const LABELS: Record<string, string> = {
  set_temperature_c: "设定温度（°C）", actual_temperature_c: "实际温度（°C）",
  heating_current_a: "加热电流（A）", preheating_confirmed: "是否已预热",
  upstream_pressure_mpa: "上游压力（MPa）", device_pressure_mpa: "设备端压力（MPa）",
  continuous_leak_sound: "是否有持续漏气声",
};
const BOOLEAN = new Set(["preheating_confirmed", "continuous_leak_sound"]);
export default function QuestionPanel({ pending, details, values, busy, onChange, onSubmit }: {
  pending: string[];
  details?: { field: string; reason: string; locator: string; source_ref: string }[];
  values: Record<string, string>; busy: boolean;
  onChange: (values: Record<string, string>) => void; onSubmit: () => void;
}) {
  const answered = pending.filter(key => values[key]?.trim());
  return <section className="pause panel">
    <h3>需要补充现场事实</h3>
    <p>执行任务已释放，诊断正在等待人工信息。可先提交已确认的部分；未知请留空，历史读数不能代填。</p>
    {pending.map(key => <div key={key}>
      <label>{LABELS[key] || key}{BOOLEAN.has(key)
        ? <select value={values[key] || ""} onChange={e => onChange({ ...values, [key]: e.target.value })}>
          <option value="">未知 / 待确认</option><option value="true">是</option><option value="false">否</option>
        </select>
        : <input type="number" min="0" step="any" value={values[key] || ""}
          onChange={e => onChange({ ...values, [key]: e.target.value })} />}</label>
      {details?.filter(item => item.field === key).map(item =>
        <p className="muted" key={item.field}>{item.reason} 依据 {item.source_ref} · {item.locator}</p>)}
    </div>)}
    <p>本次提交 {answered.length} / {pending.length} 项。恢复后重新检查安全，预算继续累计。</p>
    <button type="button" className="primary" disabled={busy || answered.length === 0} onClick={onSubmit}>
      提交事实并恢复 →
    </button>
  </section>;
}
