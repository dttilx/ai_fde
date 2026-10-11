# Tasks: APX-240 Multimodal Field Diagnosis Loop

**Input**: `spec.md`, `plan.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`, and `.specify/memory/constitution.md`

**Scope**: Modular monolith for a field demonstration. The deterministic safety gate precedes all ordinary retrieval and troubleshooting. Hybrid retrieval uses structured rules, keyword search, vectors, and citations. No equipment-control commands, model training, predictive maintenance, GraphRAG, Neo4j, or complex enterprise authorization are included.

## Execution Rules and Design Differences

Only this task file is updated. Source documents remain unchanged. These differences must be reviewed by the next consistency analysis:

| Difference | Source locations | Execution convention for this task list |
|---|---|---|
| DiagnosisRun transition list contains WAITING_EXPERT/CONFLICT_BLOCKED while its enum excludes them and its mapping uses ESCALATED | data-model.md: DiagnosisRun, State Transitions, graph mapping | Keep ten graph states separate from public run status. Paused expert/conflict runs map to ESCALATED but remain resumable; terminality is determined by graph/checkpoint, not run status alone. |
| Information submission says new diagnosis version while resume continues the same run | contracts/http-api.md: information and resume APIs | Stable run/thread, append-only evidence/report versions. /information delegates to the one resume service. |
| Duplicate key behavior varies between no duplication and rejection | quickstart.md Scenario 2 vs HTTP resume API | Replayed resume returns 409 and makes no new Job, counter increment, or evidence write; UI refreshes current checkpoint. |
| The old graph transitions jump from human wait directly to retrieval | data-model.md: LangGraph state transitions | Changed facts/evidence must pass safety_gate again. Expert confirmation never bypasses existing prohibitions. |
| Original demonstration budget is 8 steps and 120 wall-clock seconds | research.md Decision 7 | This request requires cross-resume accounting: use 32 steps and 120 cumulative active seconds; human waiting is excluded. Additional concrete limits are in T026. |
| Raw OCR conflict appears eligible before review | quickstart.md Scenario 4b | Confirm or correct both evidence items before diagnosing a conflict. Unreviewed candidates are excluded. |

Tests are explicitly required by the specification and this request. Author acceptance tests before corresponding implementation, observe expected failures, then run them again at each story checkpoint. Numbered dependencies define execution order; acceptance-task dependencies define when tests must pass. `[P]` permits parallel work only after listed prerequisites are complete and only for disjoint files. Phase 2 blocks executable user-story runs.

LangGraph's native checkpoint ID is not an integer application revision. Use a separate monotonic application checkpoint_version and a fenced per-thread invocation lease. Native checkpoint migrations belong to the checkpointer, not hand-written SQLAlchemy replicas. Nodes containing interrupt can replay from their beginning; effect keys must guard writes before and after interruption. T019 dependency declaration changes to backend/pyproject.toml wait for T004 formatting/tool setup.

Failure routing: model timeout or retry exhaustion yields FAILED and an explicit limitation; no knowledge coverage yields expert interrupt/ESCALATED, never a guessed cause; contradictory confirmed evidence yields CONFLICT_BLOCKED; checkpoint unavailable/corrupt yields a non-executable recovery error and no new thread; invalid resume returns 403/409 with unchanged state. Cancellation ends the current Job CANCELLED, invalidates pending resume, and records graph FAILED with reason USER_CANCELLED (the graph contract has no CANCELLED state). Reaching a hard budget stops graph execution and emits a cited uncertainty/escalation notice. SAFE-01 emits a deterministic stop notice before interruption, without waiting for LLM output or final report review.

An interrupted execution Job ends SUCCEEDED after its checkpoint/pending action is durable, with a result indicating PAUSED; this is execution completion, not diagnosis completion. Release its worker/lease immediately. Resume creates a new QUEUED Job on the existing thread, preserves cumulative budgets, and acquires a new fenced lease. Persisted queue reconciliation handles crashes between checkpoint and Job writes; polling remains authoritative and SSE is presentation only.

## Phase 1: Setup

**Purpose**: Establish the local backend/frontend layout and fixture-first runtime.

- [ ] T001 Create the repository layout in `backend/app`, `backend/tests`, `frontend/app`, `frontend/components`, `frontend/tests`, `knowledge/seed`, `knowledge/manifests`, and `scripts`; depends on none; verify every planned package is importable and no business code is present.
- [ ] T002 Initialize Python 3.11 backend dependencies in `backend/pyproject.toml` and `backend/app/main.py` (FastAPI, Pydantic, SQLAlchemy, Alembic, pytest); depends on T001; verify `uvicorn app.main:app` and the empty test suite start.
- [ ] T003 [P] Initialize Next.js/React/TypeScript in `frontend/package.json`, `frontend/app/layout.tsx`, and `frontend/app/page.tsx`; depends on T001; verify `npm run build` succeeds.
- [ ] T004 [P] Configure backend linting, formatting, typing, and tests in `backend/pyproject.toml`, `backend/pytest.ini`, and `backend/tests/conftest.py`; depends on T002; verify the configured checks run locally.
- [ ] T005 [P] Configure frontend linting and browser tests in `frontend/eslint.config.mjs`, `frontend/vitest.config.ts`, and `frontend/tests/setup.ts`; depends on T003; verify lint and a sample component test run.
- [ ] T006 Add `.env.example`, `docker-compose.yml`, and `README.md` for PostgreSQL/pgvector, MinIO media storage, local filesystem fallback, in-process worker, and fixture mode; depends on T002 and T003; verify a clean local start exposes MinIO and does not require external model credentials.

## Phase 2: Foundational Infrastructure and Safety Gate

**Purpose**: Complete all blocking infrastructure, knowledge initialization, role context, and the deterministic safety gate before any user-story diagnosis path.

**Critical checkpoint**: No ordinary retrieval, model generation, or troubleshooting step may run until T017-T020 and their tests pass.

- [ ] T007 [P] Implement configuration, request IDs, structured logging, and safe error envelopes in `backend/app/shared/config.py`, `backend/app/shared/logging.py`, `backend/app/shared/errors.py`, and `backend/app/main.py`; depends on T002; verify errors include trace IDs and never expose prompts, secrets, or local paths.
- [ ] T008 [P] Implement SQLAlchemy/Alembic setup in `backend/app/shared/db.py`, `backend/alembic.ini`, and `backend/migrations/env.py`; depends on T002; verify migrations apply and rollback against the local database.
- [ ] T009 [P] Implement `StorageProvider` plus MinIO and local filesystem adapters in `backend/app/shared/storage.py`, `backend/app/shared/minio_storage.py`, and `backend/app/shared/local_storage.py`; depends on T002; verify upload, checksum, download, duplicate detection, and provider switching.
- [ ] T010 [P] Define provider protocols and fixture registry in `backend/app/shared/providers/protocols.py`, `backend/app/shared/providers/registry.py`, and `backend/app/shared/providers/fixtures.py` for LLM, embeddings, OCR, vision, QR, video, and reranking; depends on T002; verify fixture outputs are deterministic and provider failures are representable.
- [ ] T011 [P] Implement persisted Job model, status transitions, idempotency, deadlines, and append-only job events in `backend/app/shared/jobs/models.py`, `backend/app/shared/jobs/service.py`, and `backend/migrations/versions/0001_jobs.py`; depends on T008; verify `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `TIMED_OUT`, `CANCELLED`, and `RETRY_WAIT` transitions and duplicate suppression.
- [ ] T012 Implement the local in-process worker, database-backed job claim, cancellation/retry policy, and crash reconciliation in `backend/app/shared/jobs/worker.py` and `backend/app/shared/jobs/executor.py`; depends on T010 and T011; verify jobs run without Redis, time out with an explicit error, and retry within a bounded attempt limit. Provide graph PAUSED result support: successful checkpoint commits end the segment Job SUCCEEDED and release the worker; new resume Jobs reuse the run ID. Cancelled invocations are fenced against later result writes, and expired claims recover without concurrent execution.
- [ ] T013 [P] Implement actor/role context and audit records in `backend/app/shared/auth_context.py` and `backend/app/shared/audit.py`; depends on T007 and T008; verify `FIELD_ENGINEER`, `EXPERT`, and `CASE_REVIEWER` are accepted, insufficient roles are rejected, and actor/role/version are recorded.
- [ ] T014 [P] Implement immutable version and diagnosis manifest primitives in `backend/app/shared/versioning.py` and `backend/app/shared/manifest.py`; depends on T008; verify agent graph, prompt, model, knowledge release, evidence snapshot, citations, and job IDs are captured.
- [ ] T015 [P] Add the supplied APX-240 source files and seed manifests in `knowledge/seed/apx240-manual.pdf`, `knowledge/seed/apx240-manual-manifest.json`, `knowledge/seed/alarm-codes.json`, `knowledge/seed/safety-rules.json`, `knowledge/seed/historical-cases.json`, `knowledge/seed/maintenance-records.json`, `knowledge/seed/assets.json`, and `knowledge/seed/qr-fixtures.json`; depends on T001; verify A101/A203/A205/A310/A401/A520/A900, H01-H05, WO records, one valid asset, unknown/non-APX-240 QR values, and an asset without history are present.
- [ ] T016 Implement PDF extraction, page/section/table/paragraph locators, chunk checksums, and knowledge release import in `backend/app/knowledge/manual_ingest.py`, `backend/app/knowledge/models.py`, and `backend/migrations/versions/0002_knowledge.py`; depends on T008 and T015; verify re-import is idempotent, creates a new release instead of overwriting, and every safety/alarm entry resolves to a manual locator.
- [ ] T017 [P] Encode SAFE-01 through SAFE-05 as versioned deterministic rules in `backend/app/safety/rules.py` and `knowledge/seed/safety-rules.json`; depends on T015 and T016; verify triggers, forbidden actions, isolation requirements, authorized roles, stop conditions, and manual citations are present for every rule.
- [ ] T018 Implement the safety evaluator and blocking gate in `backend/app/safety/service.py`, `backend/app/safety/schemas.py`, and `backend/app/safety/routes.py`; depends on T013, T014, and T017; verify `CLEAR`, `STOP_AND_ESCALATE`, `RISK_UNKNOWN`, and `CONFLICT_BLOCKED` decisions are deterministic and occur before retrieval.
- [ ] T019 Establish LangGraph foundations in `backend/app/diagnosis/state.py`, `backend/app/diagnosis/graph.py`, `backend/app/diagnosis/checkpoints.py`, and `backend/pyproject.toml` using LangGraph and langgraph-checkpoint-postgres; depends on T008, T011, T014, and T018; define the seven nodes prepare/safety_gate/retrieve/decide/ask_information/expert_review/finalize and PostgreSQL checkpointer setup; verify graph_thread_id equals diagnosis_run_id, process restart restores a checkpoint, and safety_gate delegates to the independent safety service before retrieval. No in-memory-only checkpoint provider is permitted for integration acceptance.
- [ ] T020 [P] Add foundational contract and safety tests in `backend/tests/contract/test_job_status.py`, `backend/tests/unit/test_safety_rules.py`, and `backend/tests/integration/test_safety_gate.py`; depends on T011, T012, T018, and T019; verify all seven Job states, fixture pause/worker release, PostgreSQL checkpoint restoration, SAFE-01 immediate stop, SAFE-02/03 forbidden actions, SAFE-04 role boundary, and SAFE-05 uncertainty handling. A fresh process must load persisted graph state without an external model.

## Phase 3: User Story 1 - Submit and Diagnose a Field Incident (P1, MVP)

**Goal**: Provide a text-first diagnosis path whose A203 report is citation-complete and always passes the safety gate first.

**Independent test**: With only text and structured facts `A203`, set temperature `165°C`, actual temperature `128°C`, heating current `0A`, and preheating completed, obtain a report citing A203, H02, and the relevant work order while labeling H1 open circuit as possible only. The safety gate must be recorded as `CLEAR` before retrieval.

- [ ] T021 [P] [US1] Define Incident, Asset, and normalized fact models in `backend/app/incidents/models.py`, `backend/app/incidents/schemas.py`, and `backend/migrations/versions/0003_incidents.py`; depends on T008, T013, and T015; verify raw description is immutable, structured facts preserve provenance, and asset must resolve to APX-240 when present.
- [ ] T022 [US1] Implement incident creation and retrieval in `backend/app/incidents/service.py` and `backend/app/incidents/routes.py`; depends on T021; verify `POST /api/incidents` and `GET /api/incidents/{id}` preserve original input and do not infer missing facts.
- [ ] T023 [US1] Define DiagnosisRun, Citation, report snapshots, ResumeRequest, and pending human-action persistence in `backend/app/diagnosis/models.py`, `backend/app/diagnosis/schemas.py`, and `backend/migrations/versions/0004_diagnosis.py`; depends on T008, T014, T019, and T021; enforce graph_thread_id "equals diagnosis_run_id", checkpoint_version "Monotonic; resume uses compare-and-swap", citation_id "Unique within a knowledge release", and citation knowledge_release_id "Required for reproducibility"; verify one stable run/thread has multiple immutable evidence/report versions and pending expert actions do not depend on US5 tables.
- [ ] T024 [US1] Implement deterministic fact normalization and contradiction detection in `backend/app/diagnosis/normalization.py`; depends on T021 and T023; verify known facts, observations, possible causes, unconfirmed information, and contradictions remain distinct.
- [ ] T025 [US1] Implement structured/keyword/vector retrieval routing and citation snapshots in `backend/app/knowledge/retrieval.py`, `backend/app/knowledge/indexing.py`, and `backend/app/diagnosis/retrieval_context.py`; depends on T016, T023, and T024; verify A203 routes separately to safety, alarm, manual, historical case, maintenance, approved case, and asset sources.
- [ ] T026 [US1] Implement executable LangGraph routing and persistent budget guards in `backend/app/diagnosis/graph.py`, `backend/app/diagnosis/nodes.py`, and `backend/app/diagnosis/budgets.py`; depends on T020, T023, T024, and T025; implement all seven nodes and ten graph states from graph-state.schema.json, with only retrieve/ask/escalate/finalize decisions; configure limits of 32 node steps, 3 retrieval rounds, 5 distinct questions, 20 tool calls, 12000 aggregate tokens, 5 resumes, and 120 seconds cumulative active execution. Verify all counters include retries and replay work, survive interrupts/restarts, cannot reset on resume, and fail closed before an over-budget operation. Human waiting time is excluded from active execution time; actual token usage, not only estimates, is counted, and LangGraph recursion_limit is an additional guard.
- [ ] T027 [US1] Implement citation-complete report draft, REPORT_REVIEW interrupt, and publication in `backend/app/diagnosis/report.py` and `backend/app/diagnosis/nodes.py`; depends on T023, T024, T025, and T026; verify every possible cause, safety precondition, and check_sequence instruction has resolvable citation_ids, drafts are readable before review, and FIELD_ENGINEER/EXPERT acceptance publishes a new immutable AI report without confirming the root cause. Rejection preserves the draft and requests a review action within existing budgets; finalize replay cannot publish a duplicate report.
- [ ] T028 [US1] Implement start/query/checkpoint/resume APIs and Job integration in `backend/app/diagnosis/routes.py`, `backend/app/diagnosis/service.py`, and `backend/app/diagnosis/resume.py`; depends on T012, T013, T023, T026, and T027; provide /api/incidents/{id}/diagnoses, /api/diagnoses/{id}, /api/jobs/{id}, /api/diagnoses/{id}/checkpoint, and /api/diagnoses/{id}/resume. Validate interrupt identity/type, actor, payload, idempotency key, and expected checkpoint_version under a database lock; atomically reserve one ResumeRequest and enqueue one new Job on the same thread. Verify replayed/stale/concurrent requests return 409 without extra Jobs, checkpoints or budgets; worker claim is fenced and durable to prevent concurrent graph invocations.
- [ ] T029 [P] [US1] Add fixture A203 acceptance tests in `backend/tests/acceptance/test_a203.py`; depends on T020 and T028; verify safety CLEAR precedes retrieval, A203/H02/WO-240-042 citations resolve, H1 open circuit remains POSSIBLE, REPORT_REVIEW interrupts release the worker, and a reviewed final report is published once without any US5 dependency.
- [ ] T030 [P] [US1] Add unsupported-alarm and text-only fallback tests in `backend/tests/acceptance/test_unknown_alarm.py`; depends on T028; verify no cause is invented and the report asks for safe information or escalates.
- [ ] T031 [US1] Add text incident, draft/report, citation, and resume review pages in `frontend/lib/api.ts`, `frontend/components/ReportReviewPanel.tsx`, `frontend/components/DiagnosisReport.tsx`, `frontend/components/CitationDrawer.tsx`, `frontend/app/incidents/new/page.tsx`, and `frontend/app/diagnoses/[diagnosisRunId]/page.tsx`; depends on T022 and T028; verify a text-only engineer session displays the interrupt, accepts the draft with checkpoint version and key, and reaches a cited report without media, US4, or US5 implementation.

## Phase 4: User Story 2 - Stop or Escalate Unsafe Conditions (P1)

**Goal**: Expose the deterministic safety decision as the first field action and block ordinary troubleshooting when required.

**Independent test**: Submit smoke, burning smell, abnormal high temperature, severe vibration, metal friction, or a loose component and verify immediate stop, SAFE-01 citation, expert escalation, and zero continued-trial-run steps.

- [ ] T032 [US2] Implement immediate safety notice and EXPERT/HIGH_RISK interrupts in `backend/app/diagnosis/nodes.py` and `backend/app/diagnosis/human_actions.py`; depends on T018, T023, T026, and T028; verify SAFE-01 stop notice and citations appear before any human wait, blocking safety decisions create an idempotent pending expert action in the diagnosis module, and only EXPERT can confirm disposition. Confirmation never clears SAFE-01 or authorizes trial operation; changed facts rerun safety_gate before retrieval. Persist evidence conflicts as CONFLICT_BLOCKED; no ordinary retrieval until an expert resolves facts and safety permits it.
- [ ] T033 [US2] Implement authorization-aware check preconditions in `backend/app/safety/checks.py`; depends on T013 and T017; verify guard opening, jam clearing, wiring, heater, servo, and pressure work include isolation, lockout/tagout, residual-energy release, and required role.
- [ ] T034 [P] [US2] Add SAFE-01 through SAFE-05 acceptance tests in `backend/tests/acceptance/test_safety.py`; depends on T020, T032, and T033; verify safety output precedes retrieval/check steps, every instruction is cited, HIGH_RISK/EXPERT interrupts persist, confirmation cannot authorize dangerous trial operation, and replay does not duplicate pending expert actions. Run independently using diagnosis-owned human actions without US5 tables.
- [ ] T035 [US2] Add safety stop and expert interrupt panels in `frontend/components/SafetyActionCard.tsx`, `frontend/components/StopBanner.tsx`, `frontend/components/ExpertInterruptPanel.tsx`, and `frontend/app/diagnoses/[diagnosisRunId]/page.tsx`; depends on T031 and T032; verify stop action appears immediately before ordinary content, EXPERT disposition uses checkpoint/key validation, and no confirmation button implies permission to bypass safety.

## Phase 5: User Story 4 - Ask for Missing Information (P1)

**Goal**: Ask only decision-relevant questions and keep absent facts unconfirmed, prioritizing A310.

**Independent test**: Submit `A310, seems to be leaking` with no pressure readings and verify questions for upstream pressure, equipment-side pressure, and continuous leak sound without asserting a loose connector.

- [ ] T036 [US4] Implement ask_information node and required-fact policies in `backend/app/diagnosis/questions.py` and `backend/app/diagnosis/nodes.py`; depends on T024, T026, and T028; verify A310 requests upstream pressure, equipment-side pressure, and leak sound through INFORMATION interrupt; pending questions are immutable, each question has a decision/source, and missing answers remain unconfirmed within the cumulative question budget.
- [ ] T037 [US4] Implement the /information compatibility endpoint using the same resume service in `backend/app/diagnosis/service.py` and `backend/app/diagnosis/routes.py`; depends on T036 and T028; verify FIELD_ENGINEER/EXPERT answers append an evidence/report version while resuming the original graph_thread_id, validate expected checkpoint and idempotency key, rerun the safety gate on changed facts, and do not enqueue a second run or reset budgets.
- [ ] T038 [P] [US4] Add PostgreSQL-backed fixture A310 interrupt/resume tests in `backend/tests/acceptance/test_a310.py`; depends on T037; verify three questions, partial answers, preserved run/thread ID after process restart, release of worker during human wait, and cumulative question/resume exhaustion. Inject smoke in a resumed answer and verify safety stop before retrieval; no loose-connector fact is invented and no US5 service is required.
- [ ] T039 [US4] Add the information-needed panel in `frontend/components/QuestionPanel.tsx` and `frontend/app/diagnoses/[diagnosisRunId]/page.tsx`; depends on T037; verify answers submit the current interrupt/checkpoint and key, refresh after stale version conflicts, preserve original evidence, and display separate waiting and active Job statuses.

## Phase 6: User Story 3 - Confirm Multimodal Evidence (P1)

**Goal**: Add media processing as bounded Jobs while keeping OCR, vision, video, and QR outputs reviewable candidates.

**Independent test**: Upload an image, short video, and QR; verify each produces candidate evidence that can be confirmed, corrected, or rejected before diagnosis, and failed media falls back to text.

- [ ] T040 [P] [US3] Define MediaAsset and Evidence models, unified statuses, provenance, locators, and migrations in `backend/app/evidence/models.py`, `backend/app/evidence/schemas.py`, and `backend/migrations/versions/0005_evidence.py`; depends on T008, T009, T011, and T013; verify statuses are exactly CANDIDATE, CONFIRMED, CORRECTED, REJECTED, and UNAVAILABLE, with only confirmed/corrected evidence eligible for snapshots.
- [ ] T041 [US3] Implement media upload, checksum, scan, and Job creation in `backend/app/evidence/service.py` and `backend/app/evidence/routes.py`; depends on T009, T011, and T040; verify `POST /api/incidents/{id}/media` returns media/job IDs, rejects unsafe files, and is idempotent.
- [ ] T042 [P] [US3] Implement OCR and visual candidate adapters in `backend/app/evidence/ocr.py` and `backend/app/evidence/vision.py`; depends on T010, T011, and T040; verify fixture and replaceable providers return confidence, region, limitation, and candidate evidence without confirmation.
- [ ] T043 [P] [US3] Implement QR decoding, asset lookup, and asset history fixtures in `backend/app/evidence/qr.py`, `backend/app/incidents/assets.py`, and `knowledge/seed/qr-fixtures.json`; depends on T010, T015, and T040; verify valid, unknown, non-APX-240, and no-history QR paths never create a fault cause.
- [ ] T044 [P] [US3] Implement bounded video keyframe and observable-finding processing in `backend/app/evidence/video.py`; depends on T009, T010, T011, and T040; verify timestamped keyframes/observations or an explicit limitation for dark, silent, long, or irrelevant video.
- [ ] T045 [US3] Implement candidate review actions and audit records in `backend/app/evidence/review.py` and `backend/app/evidence/routes.py`; depends on T040-T044 and T013; verify CONFIRMED/CORRECTED/REJECTED/UNAVAILABLE actions preserve the original candidate and actor.
- [ ] T046 [US3] Gate diagnosis snapshots and resumed graph inputs on reviewed evidence in `backend/app/diagnosis/retrieval_context.py` and `backend/app/diagnosis/normalization.py`; depends on T045, T026, and T028; verify CANDIDATE/REJECTED/UNAVAILABLE items never affect diagnosis, corrected evidence appends a new snapshot, confirmed contradictions cause expert interrupt, and changed evidence reruns safety_gate before retrieval.
- [ ] T047 [P] [US3] Add multimodal acceptance tests in `backend/tests/acceptance/test_evidence_review.py`; depends on T041, T042, T043, T044, T045, and T046; verify OCR/VLM/QR/video locators, review actions, failure explanations, text-only fallback, and confirmed OCR/text conflicts pause for expert review. Assert changed evidence on resume triggers safety recheck without graph budget reset.
- [ ] T048 [US3] Add upload, Job progress, and evidence review UI in `frontend/components/MediaUploader.tsx`, `frontend/components/EvidenceReviewPanel.tsx`, `frontend/components/ProviderStatus.tsx`, and `frontend/app/incidents/[incidentId]/page.tsx`; depends on T041 and T045; verify diagnosis remains blocked until required candidates are reviewed.

## Phase 7: Agent and Provider Resilience

**Goal**: Make the bounded loop, providers, citations, and asynchronous failures observable and replaceable.

- [ ] T049 [P] Implement the LLM adapter with structured output, fixture fallback, timeout, and malformed-response handling in `backend/app/shared/providers/llm.py`; depends on T010, T012, and T027; verify model output cannot bypass the safety gate or report schema.
- [ ] T050 [P] Implement embedding, keyword, structured-rule, and vector fallback adapters in `backend/app/shared/providers/embeddings.py` and `backend/app/knowledge/retrieval.py`; depends on T010 and T016; verify diagnosis remains usable when vector retrieval is unavailable.
- [ ] T051 Implement node audit timeline and graph.interrupted/graph.resumed SSE events in `backend/app/diagnosis/events.py` and `backend/app/diagnosis/routes.py`; depends on T011, T014, T026, and T028; verify every node records its name, input evidence snapshot/hash, output state, tools, step/retrieval/question/tool/token/time/resume counters, citations, checkpoint, and graph/prompt/model/index versions. Redact secrets and hidden reasoning; sequence IDs support reconnect and duplicate event detection.
- [ ] T052 [P] Add PostgreSQL graph recovery/replay and provider/Job failure tests in `backend/tests/integration/test_graph_recovery.py`, `backend/tests/integration/test_provider_failures.py`, and `backend/tests/unit/test_job_worker.py`; depends on T028, T032, T037, T049, and T050; verify restart restoration, unavailable/corrupt checkpoints, stale/duplicate/concurrent resumes, node replay, model timeout, empty RAG, cancellation while running or paused, and retry exhaustion. Assert release of worker, fencing of cancelled work, no resurrection on resume, no lost counters, and no duplicate reports/pending expert actions. Capture expected/actual outputs and versions for each fixture.

## Phase 8: User Story 5 - Expert Takeover, Repair Outcome, and Case Curation (P2)

**Goal**: Preserve human revisions and close the repair-to-verified-case loop without contaminating production retrieval.

**Independent test**: Submit a confirmed root cause, repair action, responsible role, and restart validation; verify an unapproved CaseDraft is created, excluded from official retrieval, and only an authorized reviewer can publish a new VerifiedCase.

- [ ] T053 [P] [US5] Define ExpertReview and append-only report revision models in `backend/app/expert/models.py`, `backend/app/expert/schemas.py`, and `backend/migrations/versions/0006_expert.py`; depends on T008, T013, T014, and T023; enforce reason "Required for OPEN", reviewer_id "Required for closure", and revised_report "New report version; never overwrites AI report"; verify the model links diagnosis-owned human actions and immutable report versions.
- [ ] T054 [US5] Implement expert takeover/revision endpoints in `backend/app/expert/service.py` and `backend/app/expert/routes.py`; depends on T032, T051, and T053; consume pending human actions idempotently into ExpertReview, use the shared resume service for expert decisions, and verify only EXPERT can revise/resolve conflicts without clearing safety prohibitions. Expert conclusions and confirmed root cause remain separate from the AI possible-cause contract; preserve all original versions.
- [ ] T055 [P] [US5] Define RepairOutcome, CaseDraft, and VerifiedCase models in `backend/app/feedback/models.py`, `backend/app/feedback/schemas.py`, and `backend/migrations/versions/0007_feedback.py`; depends on T008, T013, and T014; verify required confirmed root cause, repair action, responsible role, restart validation, source incident, and source diagnosis version.
- [ ] T056 [US5] Implement idempotent repair outcome submission in `backend/app/feedback/service.py` and `backend/app/feedback/routes.py`; depends on T028, T055, and T013; verify FIELD_ENGINEER/EXPERT role checks, duplicate suppression, and immutable AI report.
- [ ] T057 [US5] Implement CaseDraft creation, review, and VerifiedCase publication in `backend/app/feedback/curation.py` and `backend/app/feedback/routes.py`; depends on T055 and T056; verify missing confirmation/restart validation blocks approval, CASE_REVIEWER/EXPERT is required, and only approved versions enter retrieval.
- [ ] T058 [P] [US5] Add expert, repair, and curation acceptance tests in `backend/tests/acceptance/test_expert_feedback.py`; depends on T054, T055, T056, and T057; verify report revision, role rejection, draft exclusion, approval/new knowledge release, and graph node replay cannot duplicate ExpertReview, repair outcome, CaseDraft, or VerifiedCase publication.
- [ ] T059 [US5] Add expert, repair, and case-review pages in `frontend/app/expert/[reviewId]/page.tsx`, `frontend/app/incidents/[incidentId]/repair/page.tsx`, and `frontend/app/cases/[caseId]/page.tsx`; depends on T054 and T057; verify reviewers see evidence/citations, enter revisions, validate restart, and approve/reject drafts.

## Phase 9: Cross-Cutting Acceptance and Field Workbench

**Purpose**: Prove each user story independently and provide the complete browser demonstration.

- [ ] T060 Add the incident timeline and paused/resumed graph display in `frontend/components/DiagnosisTimeline.tsx` and `frontend/components/GraphStatusPanel.tsx`; depends on T031 and T051; verify human waiting does not appear as a running Job, resumed execution has a new Job ID on the same thread, and the public timeline displays versions/citations rather than hidden reasoning.
- [ ] T061 [P] Add HTTP and JSON Schema contract tests in `backend/tests/contract/test_http_api.py` and `backend/tests/contract/test_report_schema.py`; depends on T020, T028, T041, T054, and T057; verify job IDs, role rules, evidence states, citation-bearing instructions, and event payloads match `contracts/`.
- [ ] T062 Add the independent A203 end-to-end demo in `backend/tests/acceptance/test_a203_e2e.py` and `frontend/tests/e2e/a203.spec.ts`; depends on T029 and T031; verify the report-review pause/resume and final A203/H02/WO-240-042 citations without US4, US5, or multimodal processing.
- [ ] T063 [P] Add the independent SAFE-01 browser/API regression in `backend/tests/acceptance/test_safe01_e2e.py` and `frontend/tests/e2e/safety-stop.spec.ts`; depends on T034 and T035; verify immediate stop before expert pause, same-thread expert disposition, and no ordinary check or safety override even after human confirmation; no US5 dependency.
- [ ] T064 [P] Add the independent A310 browser/API regression in `backend/tests/acceptance/test_a310_e2e.py` and `frontend/tests/e2e/question-loop.spec.ts`; depends on T038 and T039; verify partial answers, resume conflicts, preserved budgets, and report review without US5.
- [ ] T065 [P] Add multimodal browser workflow tests in `frontend/tests/e2e/evidence-review.spec.ts`; depends on T047 and T048; verify upload, Job progress, confirmed evidence conflicts, expert interrupt, correction/rejection, retry, and safety recheck on changed evidence.
- [ ] T066 [P] Add expert/repair/case browser workflow tests in `frontend/tests/e2e/expert-feedback.spec.ts`; depends on T058 and T059; verify takeover, role boundaries, resume/replay duplicate suppression, and publication gating.
- [ ] T067 Add the moderated usability protocol and record template in `docs/usability-check.md`; depends on T060, T063, and T064; verify the five-minute A203/SAFE-01 walkthrough records participant actions, errors, time-to-find, and pass/fail for four required report items.
- [ ] T068 Add the clean-start validation script in `scripts/verify_quickstart.ps1` and update `README.md`; depends on T006, T016, T029, T034, T038, T047, and T058; verify seed release, A203, SAFE-01, A310, media failure, and case governance run in fixture mode.
- [ ] T069 [P] Add integrity and append-only regression tests in `backend/tests/integration/test_integrity.py`; depends on T014, T045, T053, T055, and T057; verify original evidence, AI report, expert report, repair outcome, and case versions cannot be overwritten.
- [ ] T070 Add the field-demo checklist and known limitations in `docs/field-demo-checklist.md`; depends on T061-T069; verify the demonstration visibly proves safety precedence, evidence review, citations, bounded execution, and human approval.

## Dependencies and Execution Order

### Phase dependencies

- Phase 1 has no dependencies.
- Phase 2 depends on Phase 1 and blocks all user stories. T017-T020 are a hard safety checkpoint.
- US1 depends on the complete Phase 2 safety gate and provides the first text MVP.
- US2 exposes and tests the Phase 2 safety behavior independently of US1's report UI.
- US4 depends on normalized facts and the bounded loop, but its A310 path is independent of US5.
- US3 depends on storage, Job, provider interfaces, and incident persistence; confirmed evidence is the only multimodal input to diagnosis.
- Phase 7 hardens the shared loop and provider failure paths.
- US5 depends on immutable diagnosis/manifests and is independent from A203, A310, and SAFE-01 acceptance.
- Phase 9 runs after the relevant story implementation and contains independent regression paths.

### Parallel opportunities and examples per story

- T003 and T004 have disjoint frontend/backend files after T001/T002; T005 waits for T003. T004 edits pyproject.toml and must finish before T019 edits dependency declarations.
- T007-T010 have disjoint files; T013 and T014 can run concurrently after prerequisites. T017 waits for T016; Phase 2 must pass before US1 starts.
- T042-T044 are independent provider adapters; T053 and T055 are independent model definitions.
- US1 example: T029 and T030 tests in separate acceptance files after T028; T023 must wait for T021.
- US2 example: T034 test authoring and T035 frontend work after T032/T033.
- US4 example: T038 acceptance tests and T039 question panel after T037.
- US3 example: T042 OCR/vision, T043 QR, and T044 video after T040; shared registry changes are serialized.
- US5 example: T053 expert models and T055 feedback models after their prerequisites; Alembic revisions are ordered when applied.
- T062-T066 can run in parallel once their individual story checkpoints are complete.

## MVP Scope

1. Complete T001-T020, including the PDF/source release and safety gate.
2. Complete T021-T031 for text-only A203 diagnosis with citation-bearing report instructions.
3. Complete T032-T035 and validate T029, T034, T062, and T063; these paths use diagnosis-owned pending actions and require no US5.
4. Complete T036-T039 and T064 for A310 pause/resume, then add multimodal, recovery hardening, and expert/repair curation.

### Dependency graph and incremental delivery

```text
Setup T001-T006 -> Foundation T007-T020 -> US1 T021-T031
US1 -> US2 T032-T035 -> SAFE-01 acceptance T063
US1 -> US4 T036-T039 -> A310 acceptance T064
US1 -> A203 acceptance T062
US1 + shared storage/jobs -> US3 T040-T048 -> media acceptance T065
US1 + US2 + US4 -> recovery hardening T049-T052
Diagnosis persistence + US2 pending actions -> US5 T053-T059 -> closed-loop acceptance T066
All independent slices -> final field demo T067-T070
```

Integrate fixture LLM/embeddings through T010 in the initial text slice; T049/T050 add replaceable external provider implementations and failure handling. Each story has its own implementation and acceptance gate. Cross-cutting T061/T068 may wait for US5 but never block T029/T034/T038 or T062-T064. In the final phase all tasks intentionally have no story label.

## Explicitly Out of Scope

No task sends PLC or equipment-control commands, modifies parameters, executes physical repairs,
trains models, implements predictive maintenance, integrates a full MES/SCADA/EAM platform, adds
enterprise permission hierarchies, or introduces GraphRAG/Neo4j/causal graph infrastructure.
