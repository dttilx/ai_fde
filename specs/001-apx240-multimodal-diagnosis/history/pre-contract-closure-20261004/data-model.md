# Data Model: APX-240 Diagnosis, Jev and Access

Revision 2.1.0 — 2026-10-04. Original schema descriptions are preserved in history/pre-jev-access-20261004/. All identifiers are immutable nonempty strings unless noted. New versions append; scope/policy/credential state changes use audited grants/revocations, never silently rewrite evidence/reports.

## 1. Common ownership, lineage and policy

Every business resource has organization_id, resource_id, created_at, created_by and policy_binding_id. Technical/reference and field-record are classification values, not database choices. Runtime is one organization; no public/default cross-organization visibility.

PolicyBinding: classification TECHNICAL_REFERENCE|FIELD_RECORD; scope_kind ORGANIZATION_REFERENCE|EVENT_MEMBERS|EXPLICIT_GRANTS; policy_version; egress_mode DENY|APPROVED_REDACTED|APPROVED_RAW; allowed_providers; allowed_purposes; permission_basis_ref; granted_by; valid_until nullable; lineage_resource_ids; revoked_at nullable. Missing binding or permission basis for external processing means DENY.

Incident text/form, Evidence, MediaAsset, KnowledgeSource/Chunk, summaries, claims and report versions all carry policy binding and lineage. Derived classification is FIELD_RECORD if any contributing input is FIELD_RECORD, otherwise TECHNICAL_REFERENCE. Derived scope is the intersection of dependencies; composite external requests require permission for every contributing input. Redaction and case approval do not expand permission. Explicitly approved de-identified publication creates a separate version with approved scope, never changes raw lineage records.

DB index releases/checkpoints/audit files remain private regardless of classification. Immutable policy snapshots explain old runs; current authorization overrides use of old snapshots in new operations.

## 2. User, Session, grants and ActorContext

| Entity | Fields and rules |
|---|---|
| User | user_id, organization_id, login_name unique per organization, password_hash, status ACTIVE|DISABLED, authorization_version monotonic |
| Session | session_id opaque, user_id, issued_at, expires_at, revoked_at nullable; no raw password; hashed/secure storage of opaque token |
| RoleGrant | grant_id, user_id, role FIELD_ENGINEER|EXPERT|CASE_REVIEWER, granted_by, status ACTIVE|REVOKED, valid_until nullable |
| IncidentMember | incident_id, user_id, capability READ|CONTRIBUTE|EXPERT_REVIEW|CASE_REVIEW, granted_by, grant_version; role and membership are both required |
| AssetGrant | asset_id, user_id, grant READ|REPORT, valid_until; QR never grants it |
| QualificationGrant | qualification_id, actor_id, category ELECTRICAL|MECHANICAL, asset_scope, authority_source_ref, granted_by, valid_from, valid_until nullable, status ACTIVE|REVOKED |
| ActorContext | server-derived actor_id/organization_id/roles/resource scope/authorization_version; never granted by request JSON |

Local administrative capability maintains grants without granting report/repair/reviewer privileges. Accounts with diagnosis permission receive baseline access to approved local SAFE/alarm rules; missing mandatory rules is fail-closed. Case self-review default disabled; demo exception requires explicit audited configuration.

## 3. Incident and Asset

Incident: incident_id, asset_id nullable (must be accessible APX-240 if present), immutable raw_description nonempty, raw_input_version, structured_facts with provenance/uncertainty/time, member_scope, policy_binding_id, status DRAFT|EVIDENCE_REVIEW|READY|RUNNING|NEEDS_INFORMATION|WAITING_EXPERT|COMPLETED|CLOSED, timestamps.

Asset: asset_id, model APX-240, serial_number nullable, organization/site/location, qr_value nullable (organization-unique), service_contact nullable, maintenance_history_refs, policy binding. Unknown/non-APX-240/unreadable/no-history cases remain explicit; ordinary users cannot distinguish unauthorized assets via lookup results.

WarrantyRecord: warranty_id, asset_id, start/end dates nullable, status UNKNOWN|ACTIVE|EXPIRED (computed from confirmed dates/as-of date), source_ref, confirmed_by/at, version. Without confirmed dates status UNKNOWN. ServiceRestriction: restriction_id, warranty/asset ref, action_kind, required_service_party, basis_ref/version, effective interval. These are service requirements, not diagnostic cause evidence.

## 4. Evidence — available in the text MVP

| Field | Rule |
|---|---|
| evidence_id / evidence_version_id | Immutable; version explicitly referenced in snapshots |
| incident_id | Required |
| source_type | TEXT, FORM, OCR, VISION, VIDEO, QR |
| content | Explicit reading/observation/asset candidate, not inferred missing values |
| status | CANDIDATE, CONFIRMED, CORRECTED, REJECTED, UNAVAILABLE |
| confidence | Optional 0..1 model observation confidence; not diagnostic correctness |
| source_media_id | Required for media-derived candidates |
| locator | bbox, frame/time range, or raw-input field; required when source is locatable |
| reviewed_by / reviewed_at | Required for CONFIRMED/CORRECTED; original text submission confirms only explicitly asserted observations, not speculation |
| observed_at | Nullable; never fabricated |
| supersedes_version_id | Nullable; correction appends new version; original preserved |
| policy_binding_id / lineage | Required |

CANDIDATE → CONFIRMED/CORRECTED/REJECTED/UNAVAILABLE; terminal decisions cannot silently edit the old row. A new correction version can supersede a reviewed fact with an explicit reason. User speculation remains unconfirmed, not a true root cause.

EvidenceSnapshot: snapshot_id, incident_id, evidence_version_ids, input_hash, source/authorization/policy version refs, created_at. Only CONFIRMED/CORRECTED enter diagnosis. QR is reviewed asset association, excluded from fault-fact snapshot; association/history lookup has its own provenance. Historical sources are Citation/KnowledgeSource, not user-confirmed current Evidence.

## 5. MediaAsset

media_id, incident_id, media_type IMAGE|VIDEO, storage_ref (private object key, no browser local path), checksum, policy/lineage, scan_status PENDING|CLEAN|REJECTED|FAILED|NOT_PERFORMED, processing_status NOT_STARTED|PROCESSING|CANDIDATES_READY|UNUSABLE|FAILED, scan_provider nullable, processing_mode, byte_size, dimensions, duration_ms nullable, created_by/at.

Image limits 5/event, 10MB/image, 25 megapixels decoded; video 1/event, 60s/100MB, 8 frames maximum, 30s decoder timeout. These are initial demonstration limits, not hardware promises. Frame assets inherit original policy. No scanner means NOT_PERFORMED not CLEAN; externally reachable deployment requires scan/quarantine. Tombstone deletion preserves identifiers/checksum/audit and marks unavailable media; retention is explicitly configured, not infinite.

Sound evidence is TEXT/FORM from the user, with video time locator; no automatic audio model result is invented.

## 6. KnowledgeSource, chunks and releases

KnowledgeSource: source_id, collection SAFETY_RULE|ALARM_CODE|MANUAL|HISTORICAL_CASE|MAINTENANCE_RECORD|APPROVED_CASE|ASSET, classification, scope/policy/lineage, source_ref, checksum, source_version, raw_path private, manual locator nullable.

ManualSource: source_id, PDF checksum, 7-page page map, parser_version. KnowledgeChunk: chunk_id, source_id, text, page_number, section/table/paragraph locator, text_checksum, knowledge_release_id, embedding_model/version, policy inherited.

KnowledgeRelease: release_id, source/checksum list, parser/chunking/embedding config versions, index config, status BUILDING|PUBLISHED|RETIRED, publication actor/time, manifest_hash. Same source+configuration reuses release (idempotent); changed source/parser/index/embedding creates new release. Drafts never become published chunks accidentally.

AlarmStep: alarm_code, step_id, order, action_kind, citation_ids, required_qualification, safety_requirements. Seven templates reflect manual p4; skipping completed non-safety steps requires current evidence. Code validates order/isolation, Jev cannot rewrite it.

Citation: citation_id unique within release, source_type SAFETY_RULE|ALARM_CODE|MANUAL|HISTORICAL_CASE|MAINTENANCE_RECORD|APPROVED_CASE, source_ref, source_id, chunk_id, knowledge_release_id, locator, excerpt, checksum, inherited policy. Assets/warranty/qualifications are PolicyReference or confirmed input, not cause citations.

PolicyReference: policy_reference_id, kind QUALIFICATION|WARRANTY|SERVICE_RESTRICTION|ACCESS_POLICY, resource/version/basis ref, scope; cannot satisfy a technical-cause citation requirement alone.

## 7. Retrieval and Jev assessment

RetrievalScope: scope_id, run_id, actor/organization, event/asset grants, source collection/release limits, authorization_version/policy_version, frozen_scope_hash. Runtime scope only narrows; broader scope requires linked run. Each source use and external request checks current grants too.

RetrievalResult: result_id, run_id, retrieval_round, source/citation/locator refs, keyword/vector/RRF ranks, pinned boolean, scope_hash, assessment_id nullable, final_route REQUIRED|EVIDENCE|HISTORICAL_REFERENCE|BACKGROUND|CONFLICT_REVIEW|FOLDED|UNASSESSED, exclusion/folding_reason nullable. FOLDED preserves auditable source, never destroys it.

PassageAssessment: assessment_id, run_id, result_id, source/checksum/release, state_hash, sanitized_input_hash, rubric_version, ranking_policy_version, provider, configured/actual model, processing_mode REAL|FIXTURE|RULE|HUMAN, status SUCCESS|PARTIAL|UNAVAILABLE|SKIPPED_POLICY|SKIPPED_BUDGET|NO_CANDIDATES|CACHED|FIXTURE, Choice/Score distributions and confidence nullable, Noul probability nullable, route, latency_ms, usage status KNOWN|UNKNOWN|NOT_CALLED, tokens/reservation, authorization/egress versions, error_code nullable, created_at. CACHED records original mode/model, not a new real call.

Assessment excludes forbidden source/request fields, not just source titles. Missing/invalid response never implies support; provider validates question IDs, option domains, probabilities and actual model. Assessment history/cache remains access-controlled.

CitationAssessment: assessment_id, claim_id, assessed_text_hash, citation_ids (one or more), evidence_ids, per-source locator checks, support_relation SUPPORTS|CONTRADICTS|UNSUPPORTED|UNKNOWN nullable, status/mode/model/rubric/policy/usage as above, human_review_ref nullable. Combined-citation evaluation avoids wrongly treating one insufficient source as all evidence failure. Numerical/confidence results are not root-cause probabilities.

ClaimReview: review_id, claim_id/hash, report_version_id, verified_source_refs, decision ACCEPT|CORRECT|REJECT, note, actor, qualification/scope if relevant, created_at. Required for material claims without valid semantic/template proof; a Jev skip with successful independent RULE template validation does not require another human review; one global report click is insufficient. Contradictions need resolution evidence/correction, not unconditional acceptance.

## 8. DiagnosisRun, budget and checkpoint

DiagnosisRun: diagnosis_run_id, incident_id, parent_run_id nullable, budget_ledger_id, fixed_scope_id, graph_thread_id equals diagnosis_run_id, graph_version, status PREPARING|SAFETY_CHECK|RETRIEVING|NEEDS_INFORMATION|WAITING_EXPERT|CONFLICT_BLOCKED|FINALIZING|COMPLETED|ESCALATED|FAILED, active_job_id nullable, checkpoint_version monotonic, native_checkpoint_id nullable, evidence_snapshot_id, report_version_refs, manifest, failure_reason nullable, started/completed timestamps. Completion timestamp only for terminal COMPLETED/ESCALATED/FAILED.

PublicGraphStatus is contracts/graph-state.schema.json; internal LangGraphState is internal-graph-state.schema.json and includes snapshot/citations/counters/manifest/pending actions. Native checkpoint IDs need not be application integers. GraphCheckpoint: native ID, thread, app version, state hash, node, interrupt_ref, timestamp; access only by trusted service, no session/API credentials.

Transitions: PREPARING → SAFETY_CHECK → RETRIEVING or waiting/block/terminal stop. RETRIEVING → safety support check → decision → more retrieval/NEEDS_INFORMATION/WAITING_EXPERT/CONFLICT_BLOCKED/FINALIZING. Every accepted resume routes SAFETY_CHECK; INFORMATION with changed facts then retrieves. Unchanged REPORT_REVIEW routes directly to finalize commit of the reviewed draft hash, not to new retrieval/generation/interrupt. Changed snapshot/report hashes invalidate approval and require a new draft and release-policy reevaluation, with renewed review when required. FINALIZING → COMPLETED on valid AUTO_VALIDATED release; otherwise REPORT_REVIEW interrupt → COMPLETED only after required review. FORCE_REVIEW preserves the full manual path. ESCALATED means this run stops, WAITING_EXPERT remains resumable. Cancel produces FAILED reason USER_CANCELLED.

BudgetLedger: shared by linked runs for the same diagnostic attempt; max_steps=32, retrieval=3, distinct_questions=5, tool_calls=20, aggregate_tokens=12000, resumes=5, active_seconds=120, max_report_tokens=2500. Counters/reservations monotonic; human waits excluded; new run ID cannot reset them. Explicit new diagnostic attempt after new physical event requires human reason and preserves lineage.

CallReservation: reservation_id, ledger_id, operation/input/effect key, tool_slots, estimated token upper bound, started_at, usage KNOWN|UNKNOWN, actual tokens, settlement, authorization/egress versions. Atomic reservations prevent concurrent overspend; unknown usage retains conservative reserved amount. Calls and retries count; necessary deterministic safety notice cannot be suppressed by exhausted model budget.

ResumeRequest: idempotency key unique per run, expected app checkpoint version, interrupt_id/type, trusted actor, payload hash, status RESERVED|QUEUED|APPLIED|FAILED|CANCELLED, job_id, lease/fencing token. Duplicate/stale/concurrent resume 409; transaction reserves one action/newJob, worker verifies fencing. Effects use stable run/node/input/effect keys; checkpoint and DB effects require durable invocation/outbox reconciliation, not assumed atomic across libraries.

PendingHumanAction: diagnosis-owned action_id, run/checkpoint, type INFORMATION|EXPERT|HIGH_RISK|REPORT_REVIEW, required_role, assignee/scope, status OPEN|RESOLVED|CANCELLED, payload refs, reason/citations, evidence/report hash, outcome/review refs. Exists before expert/feedback tables for independent P1.

## 9. Reports and manifest

ReportVersion: report_version_id, run_id, parent_report_version nullable, publication DRAFT|PUBLISHED|WITHHELD, report kind AI|EXPERT, schema version v3, release_decision_id, payload/hash, policy/lineage, reviewer refs, created_at. Reports keep current facts, observations, unknowns, contradictions, manual references and historical comparisons separate. PUBLISHED means validation and the applicable release policy passed (AUTO_VALIDATED or HUMAN_REVIEWED), never root cause confirmed by AI. EXPERT reports always HUMAN_REVIEWED.

ImmediateSafetyNotice is a separate deterministic record shown before model/human review: notice_id, incident/run nullable, risk status, confirmed or unconfirmed input signal, stop/forbidden instructions with citation IDs, timestamp. It does not wait for report approval.

Manifest contains graph/prompt/generator/Jev versions, rubric/ranking versions, knowledge release/parser/embedding/index config, evidence/input snapshot hashes, citations, selected/folded/conflict source IDs, scope/access/egress policy versions, public status, node logs, Job/native checkpoint/app version/ledger, call usage/time/fallback. Audit payload access is restricted; logs omit raw sensitive text and hidden reasoning.

## 10. Job and event semantics

Job: job_id, organization/resource refs, kind MEDIA_SCAN|OCR|VISION|QR|VIDEO|DIAGNOSIS|CASE_PUBLICATION, status QUEUED|RUNNING|SUCCEEDED|FAILED|TIMED_OUT|CANCELLED|RETRY_WAIT, idempotency_key, attempt, invocation lease/fence, active_deadline_at, error_code nullable, result_ref nullable, result_kind PAUSED|COMPLETED|null, parent_job_id nullable, created/updated_at. Exact schema names are defined in contracts/job-status.schema.json (deadline_at is active_deadline_at public projection).

PAUSED segment → SUCCEEDED after checkpoint commit, then release worker/lease. Resume new QUEUED Job same thread. No status WAITING added to Job. Expired RUNNING lease is reconciled with fencing and bounded retry; cancelled/terminal runs cannot resurrect. SENT external input cannot be recalled by later cancellation; only subsequent actions/publication are blocked.

Event: event_id, incident_id, sequence monotonic per event, type, occurred_at, filtered payload, trace_id. SSE checks authorization before each sensitive delivery/reconnect; gaps and duplicates are tolerated, authoritative APIs provide resync. Authorization expiry terminates stream, never spills prior privileged payload.

## 11. ExpertReview and feedback

ExpertReview: review_id, run_id, pending_action_id, assigned_actor, status OPEN|REVISED|ESCALATED|CLOSED, reason required OPEN, report_version_refs, resolution evidence/references, reviewer required closure, timestamps. Root cause confirmation remains separate from AI report. New privileged facts require a linked run if original scope would expand.

RepairOutcome: repair_outcome_id/version, supersedes_version_id nullable, incident/run/report refs, submitted_by, executor_id nullable, validation_status UNVERIFIED|READY_FOR_REVIEW, confirmed_root_cause/confirmation_actor/ref nullable, repair_action nullable, repair_evidence_ids possibly empty, qualification_refs, restart_validation UNKNOWN|FAILED|PASSED, restart_evidence_ids possibly empty, submitted_at, policy/lineage, idempotency key. UNVERIFIED stores truthful incomplete or failed-restart feedback. READY_FOR_REVIEW is server-validated: all confirmation/action/executor requirements, applicable qualifications, nonempty repair evidence and PASSED restart with nonempty evidence are required. Completion appends a version; this status is not case approval or authorization to restart. Case approval additionally requires reviewer and publication-scope checks; UNVERIFIED outcomes cannot create CaseDraft; only complete READY_FOR_REVIEW outcomes can become excluded draft candidates.

CaseDraft: case_id/version, source outcome/run/report, alarm/symptom/fact/root cause/action/restart, source/repair evidence refs, status DRAFT|IN_REVIEW|APPROVED|REJECTED, assigned reviewer, deidentification_review, requested/approved publication_scope, policy binding. VerifiedCase: reviewed immutable version, reviewer/publication actor/time, knowledge_release_id, status APPROVED|PUBLISHED|RETIRED. Approval alone does not publish broadly or overwrite origin.

## 12. Source-preservation and unresolved constraints

Old report confidence/known_facts enums, EXPERT publication, WAITING→ESCALATED mapping and old budget are documented in integration-review.md and original snapshots. No exam file or Constitution change. Provider/version/processing permission/hardware conditions remain deployment prerequisites, not fabricated completed facts.

## 13. Privacy projection and consolidated review

TemplateRegistry: template_id/version, approved_source_release/citation refs, field/unit/time predicates, forbidden/negative cases, rendering contract/hash, validation_suite_ref, status DRAFT|VERIFIED|RETIRED, approval actor/version. A model cannot register or approve its own templates. ValidationProof stores claim hash, evidence/source versions, matching template/predicate results and authorization/safety refs. Semantic source existence alone is not proof.

ReportReleaseDecision: decision_id, report_version/hash, evidence/scope/source hashes, release_mode AUTO_VALIDATED|HUMAN_REVIEWED|PENDING_REVIEW, release_policy_version, validation_check_ids, template_refs, reason_codes, actor/ref timestamps. AUTO requires no unresolved material unknown/conflict/risk/qualification/coverage/budget issue; every material cause/action must match valid verified template proof. HUMAN also requires all hard gates, reviewed unresolved claims or removal/correction, and reviewer refs. Pending has no final publication.

ProviderDataProfile: provider/approved endpoint, terms/ref/version/checked_at, retention_mode UNVERIFIED|STANDARD|ZDR_VERIFIED, confirmed region/limits, allowed data origins/purposes, reviewer/basis, status ENABLED|DISABLED. Data origin EXAM_SOURCE|LIVE_FIELD|SELF_AUTHORED_SIMULATION|PUBLIC_REFERENCE describes origin, not permission. EgressReceipt: event/run/source lineage IDs local-only, provider/profile version, projection version/input hash, policy/basis refs, ALLOWED|SKIPPED_POLICY|SKIPPED_RESIDUAL_SENSITIVE, call/usage refs; payload not default logged.

EvidenceReviewBatch/ClaimReviewBatch: request key, up to20 explicit item decisions+expected version/hash; no default accepts; atomic all-or-nothing records each decision. PendingHumanAction risk snapshots deduplicate HIGH_RISK/EXPERT reasons into one expert task without suppressing new evidence. Valid claim proof/review reuse requires unchanged content/evidence/citations/scope/policy/qualification; recheck current rights.

Case publication progress APPROVED_UNPUBLISHED is a UI projection of approved CaseDraft plus pending/failed publish Job, not a new case approval enum. Approval with publish_on_approval=true is an explicit scope-bound user choice; background publication reauthorizes and never expands rawscope/egress.
