"use client";
import { useState } from "react";

export default function ExpertInterruptPanel({ canConfirm, busy, onConfirm }: {
  canConfirm: boolean; busy: boolean; onConfirm: (resolution: string) => void;
}) {
  const [resolution, setResolution] = useState("");
  return <section className="danger"><h3>已暂停，等待授权专家接管</h3>
    <p>停止进一步现场排查。记录处置不会解除安全阻断，不批准试运行或复机。</p>
    {canConfirm ? <><label>停机与转交记录<textarea value={resolution} maxLength={1000}
      onChange={event => setResolution(event.target.value)} /></label>
      <button type="button" className="primary" disabled={busy || !resolution.trim()}
        onClick={() => onConfirm(resolution.trim())}>记录停机与升级处置 →</button></>
      : <p>请联系具备当前事件访问权限的专家。现场工程师不能确认此处置。</p>}
  </section>;
}
