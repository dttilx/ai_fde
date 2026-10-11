"use client";
import { use, useEffect, useState } from "react";
import { apiRequest } from "../../../lib/api";

type Draft = { status: string; payload: { confirmed_root_cause: string; repair_action: string; restart_validation: string }; requested_scope: { reader_user_ids: string[] }; publication_status: string; job: { job_id: string; status: string; status_version: number; error_code: string | null } | null };

export default function CaseReviewPage({ params }: { params: Promise<{ caseId: string }> }) {
  const { caseId } = use(params);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [note, setNote] = useState(""); const [readers, setReaders] = useState<string[]>([]);
  const [deidentified, setDeidentified] = useState(false); const [message, setMessage] = useState(""); const [busy, setBusy] = useState(false);
  async function refresh() { const result = await apiRequest(`/case-drafts/${caseId}`); if (result.ok) setDraft(await result.json()); else setMessage("读取被拒绝，权限可能已经撤销。"); }
  useEffect(() => { let active = true; apiRequest(`/case-drafts/${caseId}`).then(async result => { if (!active) return; if (result.ok) setDraft(await result.json()); else setMessage("案例不可访问，请登录指定的案例审核人账号。"); }).catch(() => { if (active) setMessage("无法连接服务，请重试。"); }); return () => { active = false; }; }, [caseId]);
  async function mutate(path: string, body?: unknown) { setBusy(true); try { const result = await apiRequest(path, { method: "POST", body, idempotencyKey: crypto.randomUUID() }); setMessage(result.ok ? "已保存，请查看最新审核与发布状态。" : `操作未完成：${result.status}`); await refresh(); } catch { setMessage("连接失败，未确认操作结果；请刷新状态后再操作。"); } finally { setBusy(false); } }
  function review(decision: "APPROVE" | "REJECT", publish = false) { return mutate(`/case-drafts/${caseId}/review`, { decision, note, approved_scope: { reader_user_ids: readers }, deidentification_status: deidentified ? "PASSED" : "FAILED", publish_on_approval: publish }); }
  const reviewable = draft && ["DRAFT", "IN_REVIEW"].includes(draft.status); const approvable = !busy && !!reviewable && !!note.trim() && readers.length > 0 && deidentified;
  return <main className="workspace standalone-page"><p className="eyebrow">CASE CURATION</p><h1>案例审核</h1><p className="helper">专家不能替代案例审核人。批准范围不代表允许向外部模型发送资料。</p>
    {draft && <><p>审核状态：{draft.status} · 发布状态：{draft.publication_status}</p><h2>待审核维修摘要</h2><p>确认根因：{draft.payload.confirmed_root_cause}</p><p>维修动作：{draft.payload.repair_action}</p><p>复机验证：{draft.payload.restart_validation}</p>
      <label>审核说明<textarea value={note} onChange={e => setNote(e.target.value)} maxLength={2000} /></label><fieldset><legend>明确批准的内部读者范围</legend>{draft.requested_scope.reader_user_ids.map(id => <label key={id}><input type="checkbox" checked={readers.includes(id)} onChange={e => setReaders(e.target.checked ? [...readers, id] : readers.filter(v => v !== id))} />{id}</label>)}</fieldset>
      <label><input type="checkbox" checked={deidentified} onChange={e => setDeidentified(e.target.checked)} />已检查摘要中的个人及客户信息，确认脱敏通过</label>
      <div><button className="primary" disabled={!approvable} onClick={() => review("APPROVE", true)}>批准并提交发布</button><button className="quiet" disabled={!approvable} onClick={() => review("APPROVE")}>仅批准案例</button><button className="quiet" disabled={busy || !reviewable || !note.trim()} onClick={() => review("REJECT")}>拒绝案例</button><button className="quiet" disabled={busy || draft.status !== "APPROVED" || !!draft.job} onClick={() => mutate(`/case-drafts/${caseId}/publish`)}>提交发布 Job</button></div>
      {draft.job && <><p>发布任务：{draft.job.status} {draft.job.error_code || ""}</p><button className="quiet" disabled={busy || !["FAILED", "TIMED_OUT"].includes(draft.job.status)} onClick={() => mutate(`/jobs/${draft.job!.job_id}/retry`, { expected_status_version: draft.job!.status_version })}>重试失败发布</button></>}<button className="quiet" disabled={busy} onClick={refresh}>刷新状态</button></>}
    <p role="status">{message}</p></main>;
}
