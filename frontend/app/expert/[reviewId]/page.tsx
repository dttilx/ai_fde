"use client";
import { use, useEffect, useState } from "react";
import { apiRequest } from "../../../lib/api";

export default function ExpertReviewPage({ params }: { params: Promise<{ reviewId: string }> }) {
  const { reviewId } = use(params);
  const [resolution, setResolution] = useState("");
  const [reportVersionId, setReportVersionId] = useState("");
  const [evidenceRefs, setEvidenceRefs] = useState("");
  const [authorized, setAuthorized] = useState<boolean | null>(null);
  const [message, setMessage] = useState("待专家填写审查结论");
  useEffect(() => { apiRequest("/me").then(async response => {
    if (!response.ok) { setAuthorized(false); return; }
    const body = await response.json();
    setAuthorized(body.roles?.includes("EXPERT") ?? false);
  }).catch(() => setAuthorized(false)); }, []);
  async function submit() {
    const result = await apiRequest(`/expert-reviews/${reviewId}/revision`, {
      method: "POST", body: { resolution, report_version_id: reportVersionId,
        evidence_refs: evidenceRefs.split(",").map(v => v.trim()).filter(Boolean) },
    });
    setMessage(result.ok ? "专家修订已追加保存" : "提交失败，请重新核对权限和报告版本");
  }
  return <main className="workspace standalone-page"><p className="eyebrow">EXPERT REVIEW / {reviewId}</p>
    <h1>专家接管与报告修订</h1><p className="helper">专家结论会生成新版本，不覆盖原始 AI 报告，也不解除 SAFE 禁止动作。</p>
    {authorized === null && <p role="status">正在检查身份权限…</p>}{authorized === false && <p className="danger">当前身份没有专家修订权限，页面不会展示提交控件。</p>}
    {authorized === true && <>
    <label>当前报告版本<input value={reportVersionId} onChange={e => setReportVersionId(e.target.value)} /></label>
    <label>依据证据 ID（逗号分隔）<input value={evidenceRefs} onChange={e => setEvidenceRefs(e.target.value)} /></label>
    <label>审查结论<textarea value={resolution} onChange={e => setResolution(e.target.value)} maxLength={4000} /></label>
    <button className="primary" disabled={!resolution.trim() || !reportVersionId} onClick={submit}>追加专家版本</button>
    <p role="status">{message}</p></>}
    </main>;
}

