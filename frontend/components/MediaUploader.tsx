"use client";
import { useEffect, useState } from "react";
import { apiRequest } from "../lib/api";
import ProviderStatus from "./ProviderStatus";

export default function MediaUploader({ incidentId, csrf, onUploaded }: {
  incidentId: string; csrf: string; onUploaded: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [jobs, setJobs] = useState<Record<string, string>>({});
  const ids = Object.keys(jobs).join(",");
  useEffect(() => {
    if (!ids) return;
    let stopped = false;
    const controller = new AbortController();
    async function poll() {
      try {
        const updates: Record<string, string> = {};
        for (const id of ids.split(",")) {
          const response = await fetch(`/api/jobs/${id}`, { signal: controller.signal });
          if (!response.ok) throw new Error("MEDIA_JOB_UNAVAILABLE");
          const result = await response.json(); updates[id] = result.status;
        }
        if (!stopped) setJobs(updates);
      } catch (e) { if (!stopped) setError(e instanceof Error ? e.message : "MEDIA_POLL_FAILED"); }
    }
    void poll(); const timer = setInterval(poll, 800);
    return () => { stopped = true; controller.abort(); clearInterval(timer); };
  }, [ids]);
  async function upload(file: File) {
    setBusy(true); setError("");
    try {
      const body = new FormData(); body.append("file", file);
      const response = await apiRequest(`/incidents/${incidentId}/media`, {
        method: "POST", body, csrf, idempotencyKey: crypto.randomUUID() });
      const data = await response.json();
      if (!response.ok) throw new Error(data.code || "MEDIA_UPLOAD_FAILED");
      setJobs(previous => ({ ...previous, [data.job_id]: "QUEUED" })); onUploaded();
    } catch (e) { setError(e instanceof Error ? e.message : "MEDIA_UPLOAD_FAILED"); }
    finally { setBusy(false); }
  }
  return <section className="panel report-detail"><h3>图片与视频</h3><ProviderStatus />
    <p>每事件最多 5 张图片（各 10MB），1 段视频（60秒、100MB）。本地演示未执行病毒扫描，不标记为 CLEAN。</p>
    <label>选择图片或视频<input type="file" accept="image/png,image/jpeg,video/mp4,video/webm" disabled={busy}
      onChange={e => { const file = e.target.files?.[0]; if (file) void upload(file); e.target.value = ""; }} /></label>
    {Object.entries(jobs).map(([id, state]) => <p key={id}>媒体任务 {id.slice(0, 8)} · {state}</p>)}
    {error && <p role="alert">媒体处理未完成：{error}</p>}
  </section>;
}
