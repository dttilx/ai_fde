import type { ReactNode } from "react";
import type { RetrievalAssessment } from "../lib/types";

const STATUS: Record<string, string> = { SKIPPED_POLICY: "资料受限，未发送", SKIPPED_BUDGET: "预算不足，保留来源",
  FIXTURE: "本地模拟评估", CACHED: "复用已授权缓存", PARTIAL: "部分评估", SUCCESS: "评估完成",
  UNAVAILABLE: "评估不可用", NO_CANDIDATES: "当前没有评估候选" };
const ROUTE: Record<string, string> = { REQUIRED: "必要依据", EVIDENCE: "技术参考", HISTORICAL_REFERENCE: "历史对照",
  BACKGROUND: "背景参考", CONFLICT_REVIEW: "冲突或异常，须核实", FOLDED: "折叠保留", UNASSESSED: "尚无法判断" };

export default function RetrievalAssessmentPanel({ assessment, citations }: {
  assessment: RetrievalAssessment; citations?: (ids: string[]) => ReactNode;
}) {
  return <section className="assessment-note" aria-label="检索结果评估">
    <b>检索评估 · {assessment.status}</b>
    <p>{STATUS[assessment.status] || "评估状态待核对"} · 检索轮次 {assessment.retrieval_round}</p>
    {assessment.status === "SKIPPED_POLICY" && <p>未调用 Jev。保留本地必要依据与历史对照，不生成模型评分。</p>}
    <p>相关性等级不是根因概率；模拟结果只验证流程，缓存复用仍检查当前权限。</p>
    {assessment.assessments.length > 0 && <details><summary>查看已授权来源的评估记录</summary>
      <ul className="assessment-list">{assessment.assessments.map(row => <li key={row.assessment_id}>
        <div><strong>{row.source_ref}</strong> · {ROUTE[row.route] || "待核对"}{citations?.([row.citation_id])}</div>
        <p>{STATUS[row.status] || row.status} · {row.processing_mode} · {row.actual_model || "无模型结果"}</p>
        <p>相关性：{row.relevance_level === null ? "未判断" : `${row.relevance_level} / 3`} · 用量：{row.usage_state} · {row.latency_ms} ms</p>
        <p className="detail-reason">{row.reason_code} · {row.rubric_version} / {row.ranking_policy_version}</p>
      </li>)}</ul>
    </details>}
  </section>;
}
