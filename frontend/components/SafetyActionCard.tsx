import type { Notice } from "../lib/types";

export default function SafetyActionCard({ notice }: { notice: Notice }) {
  return <section className="danger" role="alert"><b>立即停止进一步排查 · 需要专家</b>
    {notice.reasons.map((reason, index) => <p key={index}>{reason}</p>)}
    <p>出现危险信号立即停机；禁止继续危险试运行或绕过安全装置。</p>
    {(notice.citations || []).map(cite => <p className="detail-reason" key={cite.source_ref}>
      依据 {cite.source_ref} · 第{cite.page}页 · {cite.section}</p>)}
  </section>;
}
