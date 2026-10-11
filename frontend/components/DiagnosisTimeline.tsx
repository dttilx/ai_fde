"use client";

const labels: Record<string, string> = {
  prepare: "准备", safety_gate: "安全门", retrieve: "检索", decide: "决策",
  ask_information: "补充信息", expert_review: "专家", finalize: "报告",
};

export default function DiagnosisTimeline({ nodes }: { nodes: { node: string; status?: string; state?: string }[] }) {
  return <div className="timeline" aria-label="诊断时间线">
    {nodes.map((node, index) => <span key={`${node.node}-${index}`}>
      <b>{String(index + 1).padStart(2, "0")}</b>{labels[node.node] || node.node}
      <small>{node.status || node.state || "完成"}</small>
    </span>)}
  </div>;
}
