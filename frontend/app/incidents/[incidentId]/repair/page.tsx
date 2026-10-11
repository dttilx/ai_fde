"use client";
import { use, useEffect, useState } from "react";
import { apiRequest } from "../../../../lib/api";

export default function RepairPage({ params }: { params: Promise<{ incidentId: string }> }) {
  const { incidentId } = use(params);
  const [run, setRun] = useState(""); const [report, setReport] = useState("");
  const [cause, setCause] = useState(""); const [action, setAction] = useState("");
  const [confirmationRef, setConfirmationRef] = useState(""); const [executor, setExecutor] = useState("");
  const [repairEvidence, setRepairEvidence] = useState(""); const [qualification, setQualification] = useState("");
  const [restartEvidence, setRestartEvidence] = useState("");
  const [restart, setRestart] = useState("UNKNOWN"); const [message, setMessage] = useState("");
  const [authorized, setAuthorized] = useState<boolean | null>(null);
  useEffect(() => { apiRequest("/me").then(async response => {
    if (!response.ok) { setAuthorized(false); return; }
    const body = await response.json();
    setAuthorized(body.roles?.some((role: string) => ["FIELD_ENGINEER", "EXPERT"].includes(role)) ?? false);
  }).catch(() => setAuthorized(false)); }, []);
  async function submit() {
    const result = await apiRequest(`/incidents/${incidentId}/repair-outcomes`, { method: "POST",
      body: { diagnosis_run_id: run, report_version_id: report, confirmed_root_cause: cause,
        confirmation_ref: confirmationRef, repair_action: action, restart_validation: restart,
        executor_id: executor, repair_evidence_ids: repairEvidence.split(",").map(v => v.trim()).filter(Boolean),
        qualification_refs: qualification.split(",").map(v => v.trim()).filter(Boolean),
        restart_evidence_ids: restartEvidence.split(",").map(v => v.trim()).filter(Boolean) }, idempotencyKey: crypto.randomUUID() });
    setMessage(result.ok ? "维修反馈已保存，系统将按证据完整度标记状态" : "反馈未提交：请补齐授权执行人、证据和报告版本");
  }
  return <main className="workspace standalone-page"><p className="eyebrow">REPAIR OUTCOME / {incidentId}</p>
    <h1>维修结果回填</h1><p className="helper">维修结果是追加版本；没有复机证据时保持 UNVERIFIED，不能进入案例库。</p>
    {authorized === null && <p role="status">正在检查身份权限…</p>}{authorized === false && <p className="danger">当前身份没有维修结果提交权限，页面不会展示提交控件。</p>}
    {authorized === true && <>
    <label>诊断运行<input value={run} onChange={e => setRun(e.target.value)} /></label><label>报告版本<input value={report} onChange={e => setReport(e.target.value)} /></label>
    <label>确认根因<textarea value={cause} onChange={e => setCause(e.target.value)} /></label><label>确认依据<input value={confirmationRef} onChange={e => setConfirmationRef(e.target.value)} /></label>
    <label>维修动作<textarea value={action} onChange={e => setAction(e.target.value)} /></label><label>授权执行人 ID<input value={executor} onChange={e => setExecutor(e.target.value)} /></label>
    <label>维修证据 ID（逗号分隔）<input value={repairEvidence} onChange={e => setRepairEvidence(e.target.value)} /></label><label>资格依据（逗号分隔）<input value={qualification} onChange={e => setQualification(e.target.value)} /></label>
    <label>复机证据 ID（逗号分隔）<input value={restartEvidence} onChange={e => setRestartEvidence(e.target.value)} /></label>
    <label>复机验证<select value={restart} onChange={e => setRestart(e.target.value)}><option>UNKNOWN</option><option>FAILED</option><option>PASSED</option></select></label>
    <button className="primary" onClick={submit}>保存维修反馈</button><p role="status">{message}</p></>}
    </main>;
}

