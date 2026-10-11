import type { ReactNode } from "react";

export type ClaimAssessment = { claim_id: string; relation: string; mode: string; status: string;
  review_required: boolean; citation_ids: string[]; auxiliary_support_relation?: string;
  actual_model?: string | null; processing_mode?: string; jev_status?: string };

export default function CitationAssessmentPanel({ entries, citations }: {
  entries: ClaimAssessment[]; citations: (ids: string[]) => ReactNode;
}) {
  return <section className="panel report-detail" aria-label="引用支持核对">
    <h3>引用支持核对</h3><p className="detail-reason">检索相关不等于结论成立；Jev 判断不替代规则依据或人工确认。</p>
    <details><summary>查看当前报告的逐项依据</summary>{entries.map((item, index) => <article key={item.claim_id}>
      <p>条目 {index + 1} · {item.mode === "RULE" ? "规则验证" : item.mode === "HUMAN" ? "人工审核" : "支持未确认"}
        {item.review_required ? " · 仍需审核" : " · 已核对"}</p>
      <p className="detail-reason">{item.actual_model ? `${item.processing_mode} / ${item.actual_model} / ${item.auxiliary_support_relation}` : "未使用模型支持结论"}
        {item.jev_status ? ` · ${item.jev_status}` : ""}</p>{citations(item.citation_ids)}
    </article>)}</details>
  </section>;
}
