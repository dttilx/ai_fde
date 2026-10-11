"use client";
import { useEffect, useState, type FormEvent } from "react";
import CitationDrawer from "./CitationDrawer";
import DiagnosisReport from "./DiagnosisReport";
import RetrievalAssessmentPanel from "./RetrievalAssessmentPanel";
import CitationAssessmentPanel, { type ClaimAssessment } from "./CitationAssessmentPanel";
import ReportReviewPanel from "./ReportReviewPanel";
import ExpertInterruptPanel from "./ExpertInterruptPanel";
import StopBanner from "./StopBanner";
import QuestionPanel from "./QuestionPanel";
import MediaUploader from "./MediaUploader";
import EvidenceReviewPanel from "./EvidenceReviewPanel";
import DiagnosisTimeline from "./DiagnosisTimeline";
import GraphStatusPanel from "./GraphStatusPanel";
import { apiRequest } from "../lib/api";
import { informationAnswers } from "../lib/information";

import type { Citation, Diagnosis, Checkpoint, Notice, RetrievalAssessment } from "../lib/types";
const LABELS: Record<string, string> = { PREPARING: "准备诊断", SAFETY_CHECK: "安全检查", RETRIEVING: "检索证据", FINALIZING: "报告复核", NEEDS_INFORMATION: "等待补充", WAITING_EXPERT: "等待专家", CONFLICT_BLOCKED: "证据冲突", COMPLETED: "报告已发布", ESCALATED: "已升级专家", FAILED: "执行失败" };

export default function Workbench({ initialRunId = "", initialIncidentId = "" }: { initialRunId?: string; initialIncidentId?: string }) {
  const [session, setSession] = useState<{ username: string; csrf: string; roles: string[] } | null>(null);
  const [username, setUsername] = useState("engineer");
  const [password, setPassword] = useState("");
  const [description, setDescription] = useState("");
  const [forceReview, setForceReview] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [runId, setRunId] = useState(initialRunId);
  const [incidentId, setIncidentId] = useState(initialIncidentId);
  const [mediaMode, setMediaMode] = useState(!!initialIncidentId);
  const [diagnosis, setDiagnosis] = useState<Diagnosis | null>(null);
  const [assessment, setAssessment] = useState<RetrievalAssessment | null>(null);
  const [claimAssessment, setClaimAssessment] = useState<ClaimAssessment[] | null>(null);
  const [checkpoint, setCheckpoint] = useState<Checkpoint | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [citation, setCitation] = useState<Citation | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [claimSelection, setClaimSelection] = useState<Record<string, boolean>>({});
  const [reviewNote, setReviewNote] = useState("");
  const [claimReviews, setClaimReviews] = useState<{ hash: string; ids: string[] } | null>(null);

  async function api(path: string, method = "GET", body?: unknown, key?: string) {
    const response = await apiRequest(path, { method, body, csrf: session?.csrf, idempotencyKey: key });
    const data = response.status === 204 ? {} : await response.json();
    if (!response.ok) { if (data.immediate_safety_notice) setNotice(data.immediate_safety_notice); throw new Error(data.code || "REQUEST_FAILED"); }
    return data;
  }

  useEffect(() => {
    if (!runId || !session) return;
    const controller = new AbortController(); let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const responses = await Promise.all([fetch(`/api/diagnoses/${runId}`, { signal: controller.signal }), fetch(`/api/diagnoses/${runId}/checkpoint`, { signal: controller.signal }), fetch(`/api/diagnoses/${runId}/retrieval-assessments`, { signal: controller.signal }), fetch(`/api/diagnoses/${runId}/citation-assessments`, { signal: controller.signal })]);
        if (responses.some(r => !r.ok)) throw new Error("DIAGNOSIS_UNAVAILABLE");
        const [run, cp, assessed, supported] = await Promise.all(responses.map(r => r.json()));
        if (!stopped) { setDiagnosis(run); setCheckpoint(cp); setAssessment(assessed); setClaimAssessment(supported.assessments); if (run.immediate_safety_notice) setNotice(run.immediate_safety_notice); timer = setTimeout(poll, 800); }
      } catch (e) { if (!stopped) { setDiagnosis(null); setCheckpoint(null); setAssessment(null); setClaimAssessment(null); setError(e instanceof Error ? e.message : "POLL_FAILED"); } }
    }
    void poll(); return () => { stopped = true; controller.abort(); clearTimeout(timer); };
  }, [runId, session]);

  async function login(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try { const data = await api("/session", "POST", { username, password }); sessionStorage.setItem("apx_csrf", data.csrf_token); setSession({ username: data.username, csrf: data.csrf_token, roles: data.roles }); setPassword(""); }
    catch (e) { setError(e instanceof Error ? e.message : "LOGIN_FAILED"); } finally { setBusy(false); }
  }
  async function start(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(""); setNotice(null); setRunId(""); setDiagnosis(null); setCheckpoint(null); setAssessment(null); setAnswers({});
    try {
      const incident = await api("/incidents", "POST", { raw_description: description }, crypto.randomUUID());
      setNotice(incident.immediate_safety_notice); setIncidentId(incident.incident_id); setMediaMode(false);
      const run = await api(`/incidents/${incident.incident_id}/diagnoses`, "POST", { force_review: forceReview }, crypto.randomUUID());
      setRunId(run.diagnosis_run_id);
      window.history.replaceState(null, "", `/diagnoses/${run.diagnosis_run_id}`);
    } catch (e) { setError(e instanceof Error ? e.message : "START_FAILED"); } finally { setBusy(false); }
  }
  async function createMediaEvent() {
    setBusy(true); setError(""); setRunId(""); setDiagnosis(null); setCheckpoint(null); setNotice(null);
    try {
      const created = await api("/incidents", "POST", { raw_description: description }, crypto.randomUUID());
      setIncidentId(created.incident_id); setMediaMode(true); setNotice(created.immediate_safety_notice);
      window.history.replaceState(null, "", `/incidents/${created.incident_id}`);
    } catch (e) { setError(e instanceof Error ? e.message : "INCIDENT_CREATE_FAILED"); }
    finally { setBusy(false); }
  }
  function openMediaForCurrentEvent() {
    if (!incidentId) return;
    setError(""); setMediaMode(true);
  }
  async function diagnoseReviewed() {
    setBusy(true); setError("");
    try {
      const started = await api(`/incidents/${incidentId}/diagnoses`, "POST", { force_review: forceReview }, crypto.randomUUID());
      setRunId(started.diagnosis_run_id); setMediaMode(false);
      window.history.replaceState(null, "", `/diagnoses/${started.diagnosis_run_id}`);
    } catch (e) { setError(e instanceof Error ? e.message : "DIAGNOSIS_START_FAILED"); }
    finally { setBusy(false); }
  }
  async function resume() {
    if (!checkpoint?.interrupt_id || !diagnosis) return;
    setBusy(true); setError("");
    try {
      const payload = checkpoint.interrupt_type === "REPORT_REVIEW" ? { report_version_id: diagnosis.report?.report_version_id, report_hash: diagnosis.report_hash,
        claim_review_ids: claimReviews?.hash === diagnosis.report_hash ? claimReviews.ids : [] } : {
        answers: informationAnswers(answers, checkpoint.pending_questions) };
      await api(`/diagnoses/${runId}/resume`, "POST", { type: checkpoint.interrupt_type, interrupt_id: checkpoint.interrupt_id,
        expected_checkpoint_version: checkpoint.checkpoint_version, idempotency_key: crypto.randomUUID(), ...payload }); setAnswers({}); setCheckpoint(null);
    } catch (e) { setError(e instanceof Error ? e.message : "RESUME_FAILED"); } finally { setBusy(false); }
  }
  async function submitClaims() {
    if (!diagnosis?.report || !diagnosis.report_hash) return;
    setBusy(true); setError("");
    try {
      const reviewed = await api(`/diagnoses/${runId}/claim-reviews/batch`, "POST", {
        report_version_id: diagnosis.report.report_version_id, report_hash: diagnosis.report_hash,
        decisions: diagnosis.claim_review_items.map(item => ({ claim_id: item.claim_id,
          claim_hash: item.claim_hash, decision: "ACCEPT", note: reviewNote,
          verified_source_refs: item.citation_ids })),
      }, crypto.randomUUID());
      setClaimReviews({ hash: diagnosis.report_hash, ids: reviewed.review_ids });
    } catch (e) { setError(e instanceof Error ? e.message : "CLAIM_REVIEW_FAILED"); } finally { setBusy(false); }
  }
  async function confirmExpert(resolution: string) {
    if (!checkpoint?.interrupt_id || !["EXPERT", "HIGH_RISK"].includes(checkpoint.interrupt_type || "")) return;
    setBusy(true); setError("");
    try {
      await api(`/diagnoses/${runId}/resume`, "POST", { type: checkpoint.interrupt_type,
        interrupt_id: checkpoint.interrupt_id, expected_checkpoint_version: checkpoint.checkpoint_version,
        idempotency_key: crypto.randomUUID(), resolution }); setCheckpoint(null);
    } catch (e) { setError(e instanceof Error ? e.message : "EXPERT_DISPOSITION_FAILED"); }
    finally { setBusy(false); }
  }
  const report = diagnosis?.report;
  const canStart = !!session && !busy && description.trim().length > 0 && (!diagnosis || ["COMPLETED", "FAILED", "ESCALATED"].includes(diagnosis.state));
  function refs(ids: string[]) { return ids.map(id => { const ref = report?.evidence_sources.find(c => c.citation_id === id);
    return ref ? <button type="button" className="source-link" key={id} onClick={() => setCitation(ref)}>{ref.source_ref} ↗</button> : null; }); }

  return <main className="workbench">
    <aside className="rail"><div className="monogram">APX<span>240</span></div><div className="rail-line" /><span className="vertical">FIELD DIAGNOSTICS / 01</span><span className="rail-bottom">试用</span></aside>
    <div className="workspace"><header className="topbar"><span className="eyebrow">制造现场 · 证据驱动诊断</span><div className="top-meta"><span className="mode">FIXTURE / RULE</span><span>{session ? `${session.username} · 已登录` : "本地演示"}</span>{session && <button type="button" className="quiet" onClick={async () => { try { await api("/session", "DELETE"); setSession(null); setRunId(""); setIncidentId(""); setMediaMode(false); setDiagnosis(null); setNotice(null); setCitation(null); setCheckpoint(null); setAssessment(null); setClaimAssessment(null); setDescription(""); setAnswers({}); } catch { setError("LOGOUT_FAILED"); } }}>退出</button>}</div></header>
      <section className="intro"><div><p className="eyebrow">APX-240 AUTOMATIC PACKAGING</p><h1>现场诊断工作台<span className="accent-dot">.</span></h1><p>先确认安全，再核对事实。每一步建议，都能找到依据。</p></div><div className="slice-tag"><b>APX</b><span>文字 · 安全 · 多模态<br />有证据的现场诊断</span></div></section>
      <div className="demo-notice">虚构考试设备 · 当前使用本地规则与测试数据，尚未调用真实模型或外部 Jev。不可用于真实设备维修。</div>
      {error && <div className="error-banner" role="alert">请求未完成：{error}。请核对输入或会话。</div>}
      <StopBanner notice={notice} />
      <div className="columns"><section className="intake panel"><div className="section-heading"><span className="section-number">01</span><h2>现场报障</h2><span className="small-tag">原始输入保留</span></div>
        {!session ? <form onSubmit={login} className="login"><p>使用本地初始化的演示账号登录。密码保存在私有 demo-credentials 文件中，不嵌入网页。</p><label>账号<input autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} /></label><label>密码<input type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required /></label><button className="primary" disabled={busy}>{busy ? "登录中…" : "登录工作台 →"}</button></form> : <form onSubmit={start}>
          <label htmlFor="description">描述现象与现场读数</label><textarea id="description" value={description} maxLength={5000} onChange={e => setDescription(e.target.value)} placeholder="输入报警码、读数、预热情况和现场现象。推测请明确注明。" rows={7} required />
          <div className="preset-row"><button type="button" className="quiet" onClick={() => setDescription("A203，设定165°C，实际128°C，加热电流0A，已预热")}>载入 A203 参考输入</button><span>{description.length}/5000</span></div>
          <label className="check"><input type="checkbox" checked={forceReview} onChange={e => setForceReview(e.target.checked)} />报告发布前强制人工复核</label><p className="helper">通过校验的参考模板可自动发布可能原因报告。此选项用于验证暂停恢复，不确认根因。</p><button className="primary" disabled={!canStart}>{busy ? "提交中…" : "创建事件并开始诊断 →"}</button><button type="button" className="quiet" disabled={busy || (!incidentId && !description.trim())} onClick={incidentId ? openMediaForCurrentEvent : createMediaEvent}>{incidentId ? "为当前事件补充图片 / 视频 →" : "创建事件并补充图片 / 视频 →"}</button></form>}
        {session && mediaMode && incidentId && <><MediaUploader key={`upload:${incidentId}`} incidentId={incidentId} csrf={session.csrf} onUploaded={() => setError("")} /><EvidenceReviewPanel key={`review:${incidentId}`} incidentId={incidentId} csrf={session.csrf} onDiagnose={diagnoseReviewed} busy={busy} /></>}<div className="boundary"><b>操作边界</b><p>电气检查需独立授权；AI 不控制设备、不确认根因、不批准复机。</p></div>{runId && <div className="identifier">诊断 <code>{runId.slice(0, 8)}</code></div>}
      </section><section className="output"><div className="section-heading"><span className="section-number">02</span><h2>诊断与依据</h2><span className={`status ${diagnosis?.state === "COMPLETED" ? "success" : ""}`}>{diagnosis ? LABELS[diagnosis.state] || diagnosis.state : "等待报障"}</span></div>
        {!diagnosis ? <div className="empty-state"><div className="empty-cross">＋</div><h3>从一条现场事实开始</h3><p>提交后显示安全检查、检索记录和引用完整的结构化报告。</p><div className="empty-flow">事实 → 安全门 → 检索 → 诊断报告</div></div> : <>
          <DiagnosisTimeline nodes={diagnosis.timeline} />
          <GraphStatusPanel state={diagnosis.state} checkpoint={checkpoint?.checkpoint_version} />
          {checkpoint && <div className="execution-meta">{checkpoint.counters.steps}/32 步 · {checkpoint.counters.retrieval_rounds}/3 轮检索 · 执行 {checkpoint.counters.active_seconds.toFixed(1)}s <span>Checkpoint {checkpoint.checkpoint_version}</span></div>}
          {checkpoint?.interrupt_type === "INFORMATION" && <QuestionPanel pending={checkpoint.pending_questions} details={checkpoint.question_details} values={answers} busy={busy} onChange={setAnswers} onSubmit={resume} />}
          {["EXPERT", "HIGH_RISK"].includes(checkpoint?.interrupt_type || "") && <ExpertInterruptPanel canConfirm={!!session?.roles.includes("EXPERT")} busy={busy} onConfirm={confirmExpert} />}
          {diagnosis.failure_reason && <div className="error-banner">执行已停止：{diagnosis.failure_reason}</div>}
          {report && <DiagnosisReport report={report} onCitation={setCitation}>
            {checkpoint?.interrupt_type === "REPORT_REVIEW" && <ReportReviewPanel disabled={busy || (diagnosis.claim_review_required && claimReviews?.hash !== diagnosis.report_hash)} onAccept={resume}>
              {diagnosis.claim_review_required && claimReviews?.hash !== diagnosis.report_hash && <div className="claim-review"><h4>非参考场景：逐项核对依据</h4><p>点击来源核对后，明确勾选接受的条目。没有依据请保留草稿；修改或拒绝可通过审核 API 提交。</p>
                {diagnosis.claim_review_items.map(item => <div key={item.claim_id}><label className="check"><input type="checkbox" name="claim-review" checked={!!claimSelection[`${diagnosis.report_hash}:${item.claim_id}`]} onChange={e => setClaimSelection({ ...claimSelection, [`${diagnosis.report_hash}:${item.claim_id}`]: e.target.checked })} />{item.text}</label>{refs(item.citation_ids)}</div>)}
                <label>审核说明<input value={reviewNote} onChange={e => setReviewNote(e.target.value)} maxLength={1000} /></label>
                <button type="button" className="primary" disabled={busy || !reviewNote.trim() || diagnosis.claim_review_items.some(item => !claimSelection[`${diagnosis.report_hash}:${item.claim_id}`])} onClick={submitClaims}>保存逐项审核记录 →</button>
              </div>}
              {diagnosis.claim_review_required && claimReviews?.hash === diagnosis.report_hash && <p>逐项审核记录已保存，绑定当前报告版本。</p>}
              </ReportReviewPanel>}
            {assessment && <RetrievalAssessmentPanel assessment={assessment} citations={refs} />}
            {claimAssessment && <CitationAssessmentPanel entries={claimAssessment} citations={refs} />}
          </DiagnosisReport>}
        </>}
      </section></div><footer>APX-240 / 本地演示 <span>事实与引用保留版本 · 未审核案例不进入知识库</span></footer>
    </div>{citation && <CitationDrawer citation={citation} onClose={() => setCitation(null)} />}
  </main>;
}



