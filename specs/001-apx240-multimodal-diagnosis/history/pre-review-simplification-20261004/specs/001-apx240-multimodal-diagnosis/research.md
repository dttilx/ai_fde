# Research and Architectural Decisions — Revision 2.0.0

2026-10-04. Current decisions below supersede incompatible original wording; history/pre-jev-access-20261004/ preserves it. See integration-review.md for severity, rationale and unresolved conditions. Research is documentation, not benchmark/implementation evidence.

## R01 Modular monolith
Decision: one FastAPI backend and Next.js frontend, no microservices. Rationale: personally maintainable transactions and evidence UI. Alternative: microservices/enterprise platform rejected for examination scope.

## R02 PostgreSQL/pgvector, keyword and exact rules
Decision: one DB, logical collections, authorized exact vector distance at demo size, keyword/alarm dictionaries and RRF. Rationale: versions, scope and retrieval together; Chinese keyword normalization explicit. Alternative: OpenSearch, separate vector stores and GraphRAG rejected.

## R03 MinIO with private objects
Decision: S3-compatible MinIO default, scoped filesystem fallback. Rationale: bounded media outside DB, future portability. Alternative: DB blobs rejected. No-Docker fallback still needs PostgreSQL; signed URL revocation is not instantaneous.

## R04 Market-model adapters and truthful fixtures
Decision: real/local or explicitly permitted external LLM/VLM/embedding, fixture for deterministic workflow tests. Rationale: keys and hardware not fixed. Alternative: training prohibited; fixture-only final submission insufficient. Exact generator/VLM/local embedding model is a deployment selection requiring capacity/license and data-policy verification, not claimed settled.

## R05 Bounded video
Decision: short video/8 frames, visual observations, manually confirmed sound with time locator. Rationale: fulfill user's phase-one video request without pretending keyframes identify sound. Alternative: ASR/acoustic fault detection and continuous streaming deferred; cannot infer leak/friction automatically.

## R06 Two-stage independent safety
Decision: local preflight before ordinary retrieval; independent safety support check after retrieval for uncovered guidance/new conflicts before any troubleshooting. Rationale: SAFE-05 coverage cannot be known before lookup. Alternative: prompt-only safety or Jev clearance rejected. A205 exact alarm itself requires stop.

## R07 LangGraph and persistent checkpoints
Decision: seven nodes, ten public states, PostgreSQL checkpointer and stable run/thread. Rationale: real interrupts; not a replacement for domain services. Alternative: custom resume framework superseded. Budgets are 32 steps/3 retrieval/5 questions/20 calls/12000tokens/5resume/120 active seconds, report max2500; 8-step and wall-time versions superseded.

## R08 Append-only governance
Decision: raw inputs, Evidence versions, AI/expert reports, repair, draft and published case separate. Rationale: audit and non-contamination. Alternative: overwrite last report rejected. Retention/tombstones explicit, not infinite storage.

## R09 Local run and market-model acceptance
Decision: Compose DB/MinIO or local PostgreSQL + filesystem, local front/backend. Rationale: repeatable field entry. Alternative: Kubernetes rejected. Real model acceptance on original materials requires permitted local/remote processing, while permitted simulations validate real Jev.

## R10 Persisted Job and replay-safe effects
Decision: bounded in-process worker with DB claims/fenced leases, retries and cancellation. Paused graph segment completes Job PAUSED and releases worker; resume new Job. Rationale: no Redis needed. Alternative: synchronous media requests rejected. Checkpoint/library and business DB effects reconcile via durable invocation/outbox, not assumed one transaction.

## R11 Source release idempotency
Decision: PDF page/section/table locators, checksum/config release key. Same input+parser/index config reuses release; change creates new release. Rationale: avoid duplicate import and hidden index overwrite. Alternative: every import new release or JSON-only source loses fidelity.

## R12 Trusted identity and resource scope
Decision: opaque server-side local session, role grants and event/asset members; auth_version caches/rechecks. Rationale: clients cannot assign actor/role. Alternative: anonymous declared-role demo superseded; enterprise SSO/permission engines/RLS deferred.

## R13 Citation-complete reports
Decision: v2 report separates facts/observations/unknowns/conflicts/manual values, sorted possibilities and historical comparison; all material instructions cited; hazardous report has zero ordinary checks. Rationale: p7/Constitution. Alternative: 90% citation acceptance, mixed known_facts and global confidence superseded.

## R14 QR and asset/warranty
Decision: QR resolves scoped asset only; unknown/nonmodel/no-history fixtures; optional confirmed warranty/service references. Rationale: identity not root-cause proof. Alternative: auto loss-of-warranty inference rejected. No automatic claim system.

## R15 Business roles versus maintenance qualification
Decision: FIELD_ENGINEER/EXPERT/CASE_REVIEWER, ELECTRICAL/MECHANICAL grants independently recorded. Rationale: SAFE-04. CASE_REVIEWER plus assigned scope required to publish; EXPERT alone insufficient. Alternative: expert as superuser rejected.

## R16 Independent data classification and egress
Decision: TECHNICAL_REFERENCE/FIELD_RECORD with separate read scopes and provider/purpose-specific DENY/APPROVED_REDACTED/APPROVED_RAW. Rationale: readability not external permission. Derived scopes intersection, policies most restrictive, all input objects covered. Alternative: public technical bucket or redaction-as-permission rejected. Exam sources remain DENY pending documented basis.

## R17 Jev retrieval assessment is part of the product
Decision: every candidate passes assessment stage, real calls when allowed/available/budgeted, explicit SKIPPED_POLICY/SKIPPED_BUDGET/UNAVAILABLE/fixture modes otherwise. Rationale: user's requested highlight; official API supports typed decisions, not free report generation. Alternative: optional unspecified reranker superseded; replacing safety/permissions with probabilistic judgment rejected.

## R18 Atomic candidate questions and conservative routing
Decision: per-passage relevance Score, applicability/conflict Choice and anomalous-instruction Noul; key not inference input. Necessary sources and conflicts preserved; unrelated candidates initially folded, not destroyed or permanently excluded. Default evaluate4/max8/per-round, concurrency2,3s request/15s round. Rationale: explainable narrow questions and bounded cost. Alternative: whole-library/whole-checkpoint payload rejected. Any provisional threshold is versioned and must be tested, not vendor accuracy guarantee.

## R19 Budgets include Jev and reserve finalization
Decision: shared atomic ledger; reserve6 call slots for later work, shrink candidates dynamically, valid scoped caches; unknown token usage conservatively deducted. Rationale: 8*3 candidate requests already exceed20. Alternative: reset on resume or count batched parallel requests as one rejected.

## R20 Claim support separate from citation lookup
Decision: code checks ID/version/quote/ACL, Jev evaluates material claim with its source set when permitted; policy skipped/unknown need individual ClaimReview. Rationale: multiple citations can jointly support; historical cause not proof current cause. Alternative: one global approval or numerical confidence as proof rejected. One automatic repair round max. ClaimReview has a write API bound to claim/report hashes; unchanged REPORT_REVIEW resumes safety then publishes the existing draft, not another generation/review loop.

## R21 Fixed-scope resume
Decision: recheck access on node/source/external-call/publication/stream delivery; linked run for expert broader scope with shared budget. Rationale: persistent checkpoints must not freeze stale privilege or transfer expert data to engineer. Alternative: blindly resume stored privileged state rejected. Cancellation cannot recall already transmitted input.

## R22 Seven-alarm and actual deliverable coverage
Decision: parameterized seven alarms, unknown codes, current/history comparisons, safety/ACL/egress/resume errors, real-provider tests and five submission items. Rationale: three showcases do not exhaust manual. Alternative: fixture-only checklist inadequate. Demo sample metrics not industrial reliability claims.

Incomplete repair outcomes use UNVERIFIED (nullable/empty fields); complete confirmed repair with successful restart evidence uses READY_FOR_REVIEW, independently of case approval.

## R23 Remaining external prerequisites
Decision: fail-closed DENY until data-processing permission, usable Jev account/version/data retention/region terms and generator/VLM/local capacity verified. Rationale: docs cannot decide source owner's external consent or invent available model hardware. These are deploy-time blockers for full real-provider acceptance, not unresolved behavior: safe fallback is defined. See integration-review.md.

## Primary technical references

- https://docs.typesafe.ai/api — System One state/questions, typed responses, model and usage.
- https://docs.typesafe.ai/cookbooks/classifying_rag_passages — retrieved passage assessments, evidence/conflict separation.
- https://docs.typesafe.ai/cookbooks/citation_check — lookup then semantic support checks.
- https://docs.typesafe.ai/confidence — statistics/thresholds need domain validation.
- https://docs.typesafe.ai/model-jaggedness/jev-1.13 — numerical/date/indirection/context/adversarial limitations.

These references support integration shape only; Jev benefits and thresholds on APX-240 remain empirical. Exact dependencies will be pinned in implementation after compatibility validation.
