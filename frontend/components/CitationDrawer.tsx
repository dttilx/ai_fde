"use client";
import type { Citation } from "../lib/types";
export default function CitationDrawer({ citation, onClose }: { citation: Citation; onClose: () => void }) {
  return <div className="drawer-backdrop" onClick={onClose}><aside onKeyDown={e => { if (e.key === "Escape") onClose(); if (e.key === "Tab") e.preventDefault(); }} className="citation-drawer" role="dialog" aria-modal="true" aria-labelledby="citation-title" onClick={e => e.stopPropagation()}><button autoFocus className="close" type="button" aria-label="关闭引用" onClick={onClose}>×</button><p className="eyebrow">SOURCE EVIDENCE</p><h2 id="citation-title">{citation.source_ref}</h2><p className="locator">{citation.locator}</p><pre>{citation.excerpt}</pre><p className="helper">知识版本</p><code>{citation.knowledge_release_id}</code></aside></div>;
}
