"use client";

export default function GraphStatusPanel({ state, checkpoint, jobStatus }: {
  state: string; checkpoint?: number; jobStatus?: string;
}) {
  return <div className="execution-meta" aria-label="Agent 执行状态">
    <b>{state}</b><span>Checkpoint {checkpoint ?? "—"}</span>
    <span>执行 Job：{jobStatus || "等待查询"}</span>
    <small>人工等待释放 worker；恢复会创建新 Job，沿用同一诊断线程。</small>
  </div>;
}
