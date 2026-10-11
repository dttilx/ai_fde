"use client";
import { useEffect, useState } from "react";
import Image from "next/image";
import { apiRequest } from "../lib/api";

type Evidence = { evidence_id: string; version: number; state: string; source: string; key: string;
  media_id: string | null; value: { value: unknown; limitation: string | null }; locators: Record<string, unknown>;
  provenance: { mode?: string }; reviewable: boolean };
type Choice = { decision: string; correction: string };
const LABELS: Record<string, string> = { alarm_code: "报警码", set_temperature_c: "设定温度",
  actual_temperature_c: "实际温度", heating_current_a: "加热电流", asset_association: "关联设备", ocr_text: "图片识别文字" };
const STATES: Record<string, string> = { CANDIDATE: "待确认", CONFIRMED: "已确认",
  CORRECTED: "已修正", REJECTED: "已拒绝", UNAVAILABLE: "无法判断" };
export default function EvidenceReviewPanel({ incidentId, csrf, onDiagnose, busy }: {
  incidentId: string; csrf: string; onDiagnose: () => void; busy: boolean;
}) {
  const [rows, setRows] = useState<Evidence[]>([]);
  const [choices, setChoices] = useState<Record<string, Choice>>({});
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [processing, setProcessing] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController(); let stopped = false;
    async function refresh() {
      try {
        const response = await fetch(`/api/incidents/${incidentId}/evidence`, { signal: controller.signal });
        if (!response.ok) throw new Error("EVIDENCE_UNAVAILABLE");
        const data = await response.json(); if (!stopped) { setRows(data.evidence); setProcessing(data.processing_pending); }
      } catch (e) { if (!stopped) setError(e instanceof Error ? e.message : "EVIDENCE_UNAVAILABLE"); }
    }
    void refresh(); const timer = setInterval(refresh, 800);
    return () => { stopped = true; controller.abort(); clearInterval(timer); };
  }, [incidentId]);
  const candidates = rows.filter(row => row.reviewable);
  const selected = candidates.filter(row => choices[row.evidence_id]?.decision);
  async function commit() {
    setSaving(true); setError("");
    try {
      const decisions = selected.map(row => {
        const choice = choices[row.evidence_id];
        const value = choice.decision === "CORRECTED" ? (["alarm_code", "asset_association", "ocr_text"].includes(row.key)
          ? choice.correction : choice.correction ? JSON.parse(choice.correction) : undefined) : undefined;
        return { evidence_id: row.evidence_id, expected_evidence_version: row.version,
          decision: choice.decision, review_note: note,
          corrected_content: choice.decision === "CORRECTED" ? { value } : null };
      });
      const response = await apiRequest(`/incidents/${incidentId}/evidence/review-batch`, {
        method: "POST", csrf, idempotencyKey: crypto.randomUUID(), body: { decisions } });
      const data = await response.json(); if (!response.ok) throw new Error(data.code || "REVIEW_FAILED");
      setChoices({}); setNote("");
    } catch (e) { setError(e instanceof Error ? e.message : "REVIEW_FAILED"); }
    finally { setSaving(false); }
  }
  return <section className="panel report-detail"><h3>证据复核</h3>
    <p>逐项明确选择接受、修正或拒绝，再一次提交。当前未选择 {candidates.length - selected.length} 项；不自动接受。</p>
    {rows.filter(row => row.media_id).map(row => <article className="evidence-item" key={row.evidence_id}>
      <strong>{row.source} · {LABELS[row.key] || row.key} · {STATES[row.state] || row.state} · v{row.version}</strong>
      {row.media_id && ["OCR", "VISION", "QR"].includes(row.source) &&
        <Image src={`/api/media/${row.media_id}/content`} width={420} height={180} unoptimized alt="需人工对照的原始上传图片" style={{ objectFit: "contain", maxWidth: "100%" }} />}
      {row.media_id && typeof row.locators.frame_index === "number" && <Image
        src={`/api/media/${row.media_id}/frames/${row.locators.frame_index}/content`} width={420} height={180}
        unoptimized alt={`视频关键帧 ${row.locators.timestamp_ms} 毫秒`} style={{ objectFit: "contain", maxWidth: "100%" }} />}
      <p>候选值：{JSON.stringify(row.value.value)} · {row.provenance.mode}</p>
      <p>{row.value.limitation} 定位：{JSON.stringify(row.locators)}</p>
      {row.reviewable && <>
        <label>复核 {LABELS[row.key] || row.key}<select value={choices[row.evidence_id]?.decision || ""}
          onChange={e => setChoices({ ...choices, [row.evidence_id]: { decision: e.target.value, correction: choices[row.evidence_id]?.correction || "" } })}>
          <option value="">请选择决定</option><option value="CONFIRMED">接受</option><option value="CORRECTED">修正</option><option value="REJECTED">拒绝</option>
        </select></label>
        {choices[row.evidence_id]?.decision === "CORRECTED" && <label>修正值 {LABELS[row.key] || row.key}<input
          value={choices[row.evidence_id].correction} onChange={e => setChoices({ ...choices,
            [row.evidence_id]: { ...choices[row.evidence_id], correction: e.target.value } })} /></label>}
      </>}
    </article>)}
    <label>本轮复核说明<input value={note} onChange={e => setNote(e.target.value)} maxLength={1000} /></label>
    <button type="button" className="primary" disabled={saving || !selected.length || !note.trim()}
      onClick={commit}>保存本轮证据复核 →</button>
    <p>无法识别的媒体不进入事实，可使用已确认文字继续；候选未处理时不能开始诊断。危险证据不能通过排除绕过。</p>
    <button type="button" className="primary" disabled={busy || saving || processing || !!error || candidates.length > 0} onClick={onDiagnose}>
      使用当前已确认事实开始诊断 →
    </button>
    {error && <div role="alert"><p>证据复核未完成：{error}。版本过期时等待刷新后重新核对。</p>
      <button type="button" className="quiet" onClick={() => { setChoices({}); setError(""); }}>重新核对当前版本</button></div>}
  </section>;
}
