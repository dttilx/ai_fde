import type { ReactNode } from "react";

export default function ReportReviewPanel({ children, disabled, onAccept }: {
  children?: ReactNode; disabled: boolean; onAccept: () => void;
}) {
  return <section className="pause panel"><h3>发布前复核</h3>
    <p>核对事实、可能原因、引用和安全条件。接受只发布此版本建议，不确认最终根因。</p>
    {children}<button className="primary" type="button" disabled={disabled} onClick={onAccept}>接受当前报告并恢复 →</button>
  </section>;
}
