# HTTP and Event Contracts — v2

2026-10-04. Breaking design revision; original v1 preserved in history/pre-jev-access-20261004/. No implemented client exists. JSON schemas in this directory are normative payload shapes; service validation adds provenance/ACL/semantic/order constraints they cannot express.

## 1. Identity and common errors

POST /api/session: login name/password → opaque HttpOnly session Cookie and public user context, never password hash. Invalid login generic401 with bounded throttling.
DELETE /api/session: revoke session; idempotent204. GET /api/me: current user/organization/roles and applicable capabilities, no hidden grants/other-user records.

All resource requests require trusted server-derived ActorContext. Client actor_id/role/organization fields cannot assign authority and are rejected as unexpected business fields. Mutations require CSRF validation for cookie auth and record actor, scope, policy versions and outcome. Unauthorized sensitive ID lookup returns404 consistently with absence; missing session401, action-role forbidden403, invalid payload422, oversized media413, stale/duplicate/concurrent mutation409. Errors contain safe code/trace_id, no source text/secrets/local paths.

Each request scopes Incident/Asset/source before returning data. Jobs/SSE/checkpoint/exports inherit event access. Account/role/resource revocation rechecked during worker nodes, calls and streams, not only submission. Same Idempotency-Key with conflicting payload409; exact duplicate write replay also409/no new effects except DELETE session. Caller fetches existing state rather than expecting duplicate recreation.

## 2. Incidents and assets

POST /api/incidents: raw_description required; optional accessible asset_id, alarm, readings/unit, observation time, smell/sound/vibration and prior actions. Returns incident_id/status, normalized confirmed/unconfirmed facts, immediate_safety_notice nullable and evidence actions. Persist immutable input and immediate local risk notice before media/model wait. Known dangers cannot be hidden by missing qualification/warranty.
GET /api/incidents/{id}: authorized versions, evidence summaries, current runs/feedback; field filtering follows inherited lineage scope.
GET /api/assets/lookup?qr=...: scoped lookup; unknown/non-APX-240/no-history cases explicit only where permitted; unauthorized and absent assets do not leak existence. QR never root-cause evidence.
GET /api/assets/{id}: authorized identity/history/service/warranty summary. Warranty/source UNKNOWN displayed, no assumed service restriction.

## 3. Media and evidence

POST /api/incidents/{id}/media: Idempotency-Key, image/video. Limits5images/10MB each/25M decoded pixels;1video/60s/100MB/8frames. Verify actual type, dimensions/duration and decoding deadline30s. Response media_id/job_id/scan_status/processing_status; NOT_PERFORMED is not CLEAN when demo lacks scanner. Externally accessible deployment requires configured scanner/quarantine. Private storage, no unrestricted links.
GET /api/incidents/{id}/evidence: reviewed/candidate/limitations/version/source locators, no unauthorized observations.
POST /api/incidents/{id}/evidence/{evidence_id}/review: decision CONFIRMED|CORRECTED|REJECTED, expected_evidence_version, corrected_content nullable, review_note. Required content for CORRECTED; append version/reviewer, never overwrite candidate. UNAVAILABLE is system inability status, not a selectable human acceptance decision.
POST /api/incidents/{id}/evidence/{evidence_id}/exclude: explicitly exclude optional non-risk candidate from current snapshot; retains raw candidate/audit. Cannot remove confirmed conflicts or material risk from evaluation. Review/exclude mismatch409.
GET /api/media/{id}/content: authorized backend proxy or short60s signed URL per policy; derived frames/thumbnails same ACL; issued URL remains valid until expiry, strict revocation uses proxy.

Only CONFIRMED/CORRECTED versions enter snapshot; QR association excluded from fault-fact context. Text/FORM Evidence already exists in text MVP. Sound observations are human TEXT/FORM linked to video time, not automatic audio inference.

## 4. Jobs

GET /api/jobs/{id}: job-status.schema.json with status QUEUED|RUNNING|SUCCEEDED|FAILED|TIMED_OUT|CANCELLED|RETRY_WAIT, kind/attempt/deadline/idempotency_key/result refs/mode.
POST /api/jobs/{id}/cancel: scope, expected status version, Idempotency-Key; cancel/fence invocation and future output. Already transmitted provider inputs cannot be recalled. Diagnosis cancellation graph FAILED/reason USER_CANCELLED. Media cancellation records unavailable candidate/limitation; no fabricated success.

Human wait: Job SUCCEEDED/result_kind PAUSED with persistent graph checkpoint, worker released. Resume creates a new QUEUED DIAGNOSIS Job, same run/thread, parent_job_id previous segment. Job success does not imply diagnosis complete.

## 5. Diagnosis lifecycle and report

POST /api/incidents/{id}/diagnoses: accessible ready input, selected EvidenceSnapshot, Idempotency-Key. Required media reviewed; optional non-risk items can be explicitly excluded. Returns run_id/thread_id equal, job_id, state and manifest summary. safety_gate before ordinary retrieval and independent support check after retrieval before instructions.
GET /api/diagnoses/{id}: ten-state diagnosis status, public safety notice, report DRAFT/PUBLISHED/WITHHELD, needed info, timeline, citations and safe manifest view. No raw prompts/checkpoint secrets/hidden reasoning.
GET /api/diagnoses/{id}/checkpoint: graph-state.schema.json public status, app checkpoint_version, interrupt_id/type, pending safe actions and counters; not native checkpoint body.
GET /api/diagnoses/{id}/retrieval-assessments: retrieval-assessment.schema.json authorized source/rank/route/mode summaries, necessary/history/conflict indicators, actual model/version; never names/counts other users' forbidden sources.
GET /api/diagnoses/{id}/citation-assessments: authorized claim IDs/hashes/citation set, relation/status/mode/review requirements. RULE and HUMAN results distinguished from REAL_JEV; policy/unknown mode not semantic success.
POST /api/diagnoses/{id}/claim-reviews: authorized assigned FIELD_ENGINEER/EXPERT within scope (applicable technical qualification checked), Idempotency-Key, report_version_id/hash, claim_id/hash, decision ACCEPT|CORRECT|REJECT, note, verified_source_refs, correction nullable. Returns immutable review_id. Stale/hash mismatch or duplicate409; ACCEPT cannot override contradictory evidence, prohibited actions or source restrictions. CORRECT retains old draft, creates correction/new draft and invalidates old report approval; REJECT blocks that claim from publication. Only valid per-claim review IDs can be used in REPORT_REVIEW.
GET /api/diagnoses/{id}/exports/report: reauthorize all contributing source scopes and redact/withhold entire derived content as needed. Source privilege is not bypassed by summary export.

POST /api/diagnoses/{id}/resume:
- expected checkpoint_version, interrupt_id, idempotency_key;
- exactly one payload matching INFORMATION|EXPERT|HIGH_RISK|REPORT_REVIEW;
- identity/role from session, never body;
- information answers include observation provenance; expert resolves facts with evidence, cannot authorize prohibited operation;
- REPORT_REVIEW includes report_version/hash and individual claim review refs for every unknown/policy-skipped material claim, not just a global accept button.

Under transaction lock reserve action+oneJob, increment accepted resume budget, validate checkpoint CAS. Fenced worker resumes same graph; all accepted resumes reroute safety, then branch by interrupt type. INFORMATION with changed facts proceeds to retrieval. Unchanged REPORT_REVIEW commits the same reviewed draft hash after safety/access checks, without retrieval/regeneration or another interrupt. Changed evidence/report hash invalidates approval and requires a new draft/review; expert/high-risk resolutions cannot bypass blocking rules. Duplicate/stale/concurrent409 no additional jobs/effects. Node replay uses durable effect key; graph/business writes reconcile interruptions.
POST /api/diagnoses/{id}/information: compatibility alias for INFORMATION resume with same fields/checks, new evidence/report version within same run, no automatic new diagnosis/thread.
POST /api/diagnoses/{id}/linked-runs: expert authority, broader explicit source scope and reason; newrun/thread parent link with shared budget ledger; no report/privileged checkpoint leak to original scope. Scope reduction/revocation cannot continue old privileged context.

## 6. Jev contract and source routing

Retrieval always invokes assessment stage. Normal permitted/budgeted candidates call POST https://api.typesafe.ai/v1/systemone through private provider adapter, not browser. Input state/questions authorized/minimized together; API key server-only, questions carry full instructions, keys only result mapping.

Default4/new candidates/max8 per round,2 concurrent,3s request/15s round, one bounded retry. Reserve6 tools for finalization before scheduling; skipped-budget candidates retain hybrid rank. All requests/retries/token reservations count shared32steps/3retrieval/5questions/20tools/12000tokens/5resumes/120active seconds. Missing usage deducts conservative reservation and marksUNKNOWN.

Pinned SAFE/alarm sources remain regardless of score; initial irrelevant routes FOLDED (inspectable), not deletion. Conflict signals preserved; historical differences displayed separately. Unsupported/no-coverage evaluates necessary sources too, not merely optional candidate scores.

Processing statuses SUCCESS/PARTIAL/UNAVAILABLE/SKIPPED_POLICY/SKIPPED_BUDGET/NO_CANDIDATES/FIXTURE/CACHED are explicit; cache original mode/version retained. malformed response/model mismatch/errors never default to supported. External policies cover incident/source/claim/media lineage and every provider including embeddings.

Citation existence/version/locator/quote verified locally first. Jev checks claim against citation set when permitted; rule/human fallback explicit. Individual ClaimReview corrects unsupported material claims; conflict requires resolution, confidence does not overrule safety/ACL.

## 7. Expert, repair and case

POST /api/diagnoses/{id}/expert-reviews: assigned EXPERT, pending_action_id, reason, reportversion; create review idempotently, permits existing diagnosis-owned human action before repair module.
POST /api/expert-reviews/{id}/revision: assigned EXPERT, reviewed facts/evidence/citations, new report and conclusion version; execute shared resume service where relevant; root-cause confirmation separate from AI POSSIBLE. Broader data scope linked run only.
POST /api/incidents/{id}/repair-outcomes: authorized FIELD_ENGINEER/EXPERT, executor_id, confirmed_root_cause + confirmation evidence, repair_action/evidence_ids, qualification refs, restart_validation/evidence_ids, reportversion, Idempotency-Key. Payload accepts nullable/empty incomplete fields and restart_validation UNKNOWN|FAILED|PASSED. Server returns validation_status UNVERIFIED|READY_FOR_REVIEW; READY_FOR_REVIEW requires confirmed root cause, confirmation ref, authorized executor/action, nonempty repair evidence and PASSED restart with nonempty evidence. Incomplete/failed results remain UNVERIFIED and cannot approve case; complete submission appends a new version, not overwrite.
POST /api/repair-outcomes/{id}/case-draft: create excluded draft with lineage and proposed publication_scope, no automatic official index.
POST /api/case-drafts/{id}/review: assigned CASE_REVIEWER, APPROVE|REJECT, note, complete evidence, deidentification decision, publication scope. EXPERT alone403; self-review rejected unless explicit audited demo exception.
POST /api/case-drafts/{id}/publish: approved authorized reviewer, scope/policy version checks, Idempotency-Key; create VerifiedCase and new KnowledgeRelease publication, idempotent release activation. Sharing external and internal permissions separately checked; rawsource remains unchanged.

## 8. Events, replay and privacy

GET /api/incidents/{id}/events SSE with Last-Event-ID; event_id, incident_id, sequence, type, occurred_at, filtered payload, trace_id. Authorization before each sensitive event and reconnect; revoke/expire terminates stream. Sequence/order/idempotent handling plus resource-API resync; no log or event reveals secrets or denied sources.

Event types: job.queued/progress/failed/cancelled; graph.interrupted/resumed; evidence.candidate_ready/reviewed; safety.decision; retrieval.assessed; citation.assessed; diagnosis.report_ready; expert.review_opened; repair.outcome_saved; case.reviewed/published. Events are append-only progress, DB APIs authoritative.

Current source-processing permissions, actual provider models and hardware availability are deployment conditions listed in integration-review.md; safe policy-skip behavior is contractual, not permission to publish the examination materials.
