import type { ReactNode } from "react";
import type { Citation, Instruction, Report } from "../lib/types";

export default function DiagnosisReport({ report, onCitation, children }: {
  report: Report; onCitation: (citation: Citation) => void; children?: ReactNode;
}) {
  function refs(ids: string[]) {
    return ids.map(id => {
      const cite = report.evidence_sources.find(c => c.citation_id === id);
      return cite ? <button key={id} type="button" className="source-link" onClick={() => onCitation(cite)}>{cite.source_ref} ↗</button> : null;
    });
  }
  function instruction(item: Instruction) {
    return <div key={item.instruction_id}><p>{item.text}</p>{refs(item.citation_ids)}</div>;
  }
  return <>
    <section className="report-head"><span className="eyebrow">{report.publication_status === "WITHHELD" ? "报告已阻断 · 待专家处理" : report.publication_status === "DRAFT" ? "待复核草稿" : "结构化报告"} / {report.release_mode}</span><h3>{report.fault_phenomenon}</h3><p>最终根因未确认</p></section>
    {report.publication_status === "WITHHELD" && <section role="alert" className="danger"><h3>停止进一步排查</h3>{report.immediate_safety_actions.map(instruction)}</section>}
    <section className="facts panel"><h3>已知事实</h3><div className="fact-grid">{report.known_facts.map((f, i) => <div key={i}><span className="fact-tick" aria-hidden="true">✓</span><span>{f.text}</span></div>)}</div></section>
    {report.confirmed_observations.length > 0 && <section className="panel report-detail"><h3>已确认观察</h3>{report.confirmed_observations.map((row, i) => <p key={i}>{row.text}</p>)}</section>}
    {report.unconfirmed_information.length > 0 && <section className="panel report-detail"><h3>未确认信息</h3>{report.unconfirmed_information.map((row, i) => <p key={i}>未确认项：{row.text}<span className="detail-reason">{row.reason}</span></p>)}</section>}
    {report.contradictions.length > 0 && <section className="danger"><h3>证据冲突</h3>{report.contradictions.map((row, i) => <p key={i}>{JSON.stringify(row)}</p>)}</section>}
    <section className="causes panel"><h3>可能原因 <span>依据强弱排序 · 尚未确认</span></h3>{report.possible_causes.map((c, i) => <article key={c.claim_id}><span className="rank">{String(i + 1).padStart(2, "0")}</span><div><h4>{c.cause}</h4><p>{c.ranking_reason}</p>{refs(c.citation_ids)}</div></article>)}</section>
    <section className="safety-card"><h3>安全前置条件</h3>{report.safety_preconditions.map(instruction)}</section>
    {report.publication_status !== "WITHHELD" && <section className="steps panel"><h3>下一步排查顺序</h3>{report.check_sequence.map((s, i) => <article key={s.instruction_id}><b>{i + 1}</b><div><p>{s.text}</p>{s.required_qualification.length > 0 && <span className="qualified">需对应技术授权：{s.required_qualification.map(q => q === "ELECTRICAL" ? "电气" : q === "MECHANICAL" ? "机械" : q).join("、")}</span>}{refs(s.citation_ids)}</div></article>)}</section>}
    <section className="panel report-detail"><h3>说明书参数与依据</h3><p className="detail-reason">手册参数供对照，不代表本次现场读数。</p>{report.manual_references.map((row, i) => <div key={i}><p>{row.text}</p>{refs(row.citation_ids)}</div>)}</section>
    {report.historical_comparisons.length > 0 && <section className="panel report-detail"><h3>历史案例对照</h3>{report.historical_comparisons.map((row, i) => <div key={i}>
      <h4>相同点</h4>{row.same_points.map((text, j) => <p key={j}>{text}</p>)}
      <h4>不同点</h4>{row.different_points.map((text, j) => <p key={j}>{text}</p>)}
      <h4>待补充验证</h4>{row.missing_information.map((text, j) => <p key={j}>{text}</p>)}
      <p className="detail-reason">{row.effect_on_diagnosis}</p>{refs(row.citation_ids)}
    </div>)}</section>}
    {report.missing_information.length > 0 && <section className="panel report-detail"><h3>后续补充信息</h3>{report.missing_information.map((row, i) => <div key={i}><p>{row.blocking ? "必须补充" : "可选补充"}：{row.text}</p><p className="detail-reason">{row.reason}</p>{refs(row.citation_ids)}</div>)}</section>}
    <section className="stop-card report-detail"><h3>停止条件与专家升级</h3>{report.stop_conditions.map(instruction)}<p>{report.escalate_expert ? "需要升级专家" : "本报告未要求立即升级；触发停止条件时仍须升级。"}</p>{report.escalation_reasons.map(instruction)}</section>
    {children}
    <details className="limits"><summary>报告限制与追溯信息</summary>{report.limitations.map((l, i) => <p key={i}>{l}</p>)}<code>报告版本 {report.report_version_id}</code>{report.policy_references.map((row, i) => <p key={i}>授权或服务依据：{row.basis_ref} · 版本 {row.version}</p>)}</details>
  </>;
}
