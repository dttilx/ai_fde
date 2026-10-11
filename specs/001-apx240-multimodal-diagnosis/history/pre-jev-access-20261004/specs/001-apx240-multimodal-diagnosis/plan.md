# Implementation Plan: APX-240 Multimodal Field Diagnosis Loop

**Branch**: `001-apx240-multimodal-diagnosis` | **Date**: 2026-10-04 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-apx240-multimodal-diagnosis/spec.md`

## Summary

为 APX-240 现场工程师提供一个可试用的多模态故障诊断闭环：先确认文字、图片、OCR、视频和 QR 产生的证据，再执行安全规则和有界 Agent Loop，使用分层混合 RAG 生成带引用的诊断报告，并支持专家修订、维修结果回填和审核案例沉淀。第一阶段采用模块化单体，优先完成 A203、A310 和 SAFE-01 三条可演示垂直路径。

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: Python 3.11+ backend; TypeScript 5.x frontend

**Primary Dependencies**: FastAPI, Pydantic, SQLAlchemy, LangGraph, LangChain core interfaces, Next.js, React, OpenAI-compatible model adapters, PaddleOCR-compatible OCR adapter, OpenCV/FFmpeg media utilities

**Storage**: PostgreSQL with pgvector for structured records and embeddings; MinIO as the default local S3-compatible object store for media; local filesystem provider as a no-Docker fallback; Redis is optional and not required for the first local demonstration

**Testing**: pytest unit/integration tests, JSON Schema contract validation, deterministic rule tests, scripted end-to-end acceptance scenarios, and manual browser verification

**Target Platform**: Windows development host with Docker Desktop or Python/Node local processes; browser-based field demonstration; Linux-compatible deployment path

**Project Type**: Browser web application with Python web service and bounded asynchronous media/diagnosis jobs

**Performance Goals**: Text-only diagnosis visible to the user within 30 seconds under normal local conditions; media candidates within 60 seconds for a single image or short video; normal page actions within 2 seconds excluding model work

**Constraints**: No equipment-control commands; deterministic SAFE-01..05 gate must complete before normal retrieval or troubleshooting; no unreviewed multimodal evidence in diagnosis; no unreviewed case in production retrieval; bounded diagnosis execution; text-only fallback when media or model providers fail

**Scale/Scope**: Single APX-240 device family, one demonstration tenant, seven supplied alarm codes, five historical cases, five maintenance records, and fewer than 20 concurrent demonstration users

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The following gates pass before research:

- **Safety gate**: Safety rules are an independent pre-diagnosis decision layer; no physical device control is included.
- **Evidence gate**: Every possible cause and material next step is linked to a confirmed input or cited knowledge item.
- **Multimodal gate**: OCR, visual, video, and QR output remains candidate evidence until accepted, corrected, or rejected.
- **Bounded-agent gate**: The loop has explicit step, retrieval, question, token, and time limits.
- **Knowledge gate**: Safety rules, alarm codes, manual content, cases, maintenance records, and approved cases remain logically separated and versioned.
- **Human-governance gate**: Expert revisions and approved cases are append-only; raw events cannot enter production retrieval.
- **Scope gate**: The design is a modular monolith and does not require complete GraphRAG, model training, PLC integration, or a full enterprise service platform.

## Project Structure

### Documentation (this feature)

```text
specs/001-apx240-multimodal-diagnosis/
├── plan.md              # This file ($speckit-plan command output)
├── research.md          # Phase 0 output ($speckit-plan command)
├── data-model.md        # Phase 1 output ($speckit-plan command)
├── quickstart.md        # Phase 1 output ($speckit-plan command)
├── contracts/           # Phase 1 output ($speckit-plan command)
└── tasks.md             # Phase 2 output ($speckit-tasks command - NOT created by $speckit-plan)
```

### Source Code (repository root)
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```text
backend/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── shared/                 # database, storage, jobs, model adapters, audit, roles
│   ├── incidents/              # event lifecycle and normalized FaultEvent
│   ├── evidence/               # media, OCR/VLM/QR candidates and review
│   ├── safety/                 # SAFE-01..05 deterministic decisions
│   ├── knowledge/              # ingestion, retrieval, citations, releases
│   ├── diagnosis/              # LangGraph loop, checkpointing, state, report validation
│   ├── expert/                 # takeover and append-only revisions
│   └── feedback/               # repair outcome and case curation
├── migrations/
└── tests/
    ├── unit/
    ├── integration/
    ├── contract/
    └── acceptance/

frontend/
├── app/
│   ├── incidents/new/
│   ├── incidents/[incidentId]/
│   ├── diagnoses/[diagnosisRunId]/
│   ├── expert/[reviewId]/
│   └── cases/[caseId]/
├── components/
├── lib/
└── tests/

knowledge/
├── seed/
│   ├── apx240-manual.pdf
│   ├── apx240-manual-manifest.json
│   ├── alarm-codes.json
│   ├── safety-rules.json
│   ├── assets.json
│   ├── qr-fixtures.json
│   ├── historical-cases.json
│   └── maintenance-records.json
└── manifests/

contracts/
└── (feature-level contracts are stored under this feature directory)
```

**Structure Decision**: Use one repository containing a TypeScript web frontend and a Python
modular-monolith backend. Domain modules own their schemas and services, while shared adapters
provide storage, model, audit, and job interfaces. Knowledge seed data is kept separate from
runtime code so the supplied APX-240 materials can be re-indexed and versioned without changing
diagnosis logic. The first demonstration may run backend and frontend as local processes, with
PostgreSQL/pgvector and MinIO media storage provided by Docker Compose. The local filesystem
provider remains available for fixture-mode validation without Docker.

## Revised Execution and Design Decisions

### Safety-first dependency gate

The diagnosis entry point is ordered as `prepare -> safety_gate -> retrieve -> decide -> finish`.
The deterministic safety gate runs for text-only incidents as well as confirmed multimodal
evidence. A diagnosis run cannot enter normal retrieval or emit troubleshooting steps until the
gate returns `CLEAR`. `STOP_AND_ESCALATE`, `RISK_UNKNOWN`, and `CONFLICT_BLOCKED` transition to an
expert review or terminal stop state. The text MVP includes SAFE-01..05 implementation and tests
before its A203 acceptance checkpoint.

### Local asynchronous job boundary

Media processing and diagnosis execution use a shared persisted `Job` abstraction with states
`QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `TIMED_OUT`, `CANCELLED`, and `RETRY_WAIT`. A local
in-process worker is the default demonstration provider; an optional Redis-backed worker can be
added without changing the domain contract. Each job has an idempotency key, attempt count,
deadline, error code, and append-only events. HTTP polling and the incident SSE stream expose
progress, while PostgreSQL remains authoritative.

### Manual ingestion and source locator

The supplied APX-240 PDF is imported through a versioned manifest. Text extraction preserves page,
section, table, and paragraph locators; chunks retain source checksums and knowledge releases.
Safety rules and alarm-code entries link to their manual locators. Ingestion is repeatable and
does not overwrite an earlier release.

### Lightweight role context

The demonstration uses request role context with `FIELD_ENGINEER`, `EXPERT`, and `CASE_REVIEWER`.
This is an application-level authorization boundary, not an enterprise identity platform. Repair
outcomes require `FIELD_ENGINEER` or `EXPERT`; report revision requires `EXPERT`; case publication
requires `CASE_REVIEWER` or `EXPERT`. Mutations record actor and role in the audit trail.

### Citation-complete report contract

`possible_causes`, `safety_preconditions`, and every `check_sequence` item are structured objects
with one or more `citation_ids`. Report validation rejects material instructions without a
resolvable citation, including deterministic safety output and model-composed text.

### Asset and QR fixtures

The seed release includes one valid APX-240 asset, maintenance links, valid and unknown QR values,
a non-APX-240 QR value, and an APX-240 asset without history. QR acceptance only attaches an
asset; it never creates diagnostic evidence or a root cause.

### Usability acceptance

The field-demo validation includes a five-minute moderated walkthrough. A participant must locate
the immediate safety action, leading possible cause, next check, and source citation for A203 and
SAFE-01 without opening logs. The result records task completion, errors, and pass/fail criteria.

### LangGraph orchestration and human pause

LangGraph is used only inside `backend/app/diagnosis/graph.py` as the diagnosis orchestration
layer. The rest of the system remains a FastAPI modular monolith. The graph nodes are
`prepare`, `safety_gate`, `retrieve`, `decide`, `ask_information`, `expert_review`, and
`finalize`. The independent `safety` module executes SAFE-01..05 before the graph can enter
`retrieve`; no graph node or model response can override a blocking safety decision.

The graph state contains `diagnosis_run_id`, `incident_id`, `state`, confirmed evidence snapshot,
citations, counters, pending questions, pending expert action, report draft, and manifest data.
The graph uses `diagnosis_run_id` as its stable `thread_id` and a PostgreSQL-backed checkpointer.
`interrupt()` pauses at information-needed, expert review, high-risk confirmation, and report
review points. A resume request loads the same checkpoint, validates the expected checkpoint
version and actor role, applies the answer or review, increments `resume_count`, and continues the
same thread. A compare-and-swap checkpoint version and idempotency key prevent duplicate or
concurrent resumes.

The graph states are `PREPARING`, `SAFETY_CHECK`, `RETRIEVING`, `NEEDS_INFORMATION`,
`WAITING_EXPERT`, `CONFLICT_BLOCKED`, `FINALIZING`, `COMPLETED`, `ESCALATED`, and `FAILED`.
The graph is bounded by maximum steps, retrieval rounds, questions, tokens, wall time, and
resumes. LangGraph checkpoints are linked to the Job record; Job status remains the external
polling/SSE contract and PostgreSQL remains authoritative for business records.

LangGraph is deliberately not used for media pipelines, safety rule evaluation, storage, or
expert/case CRUD. Those remain ordinary domain services with replaceable provider adapters.

## Complexity Tracking

No constitution violations. PostgreSQL/pgvector, asynchronous media processing, and a separate
frontend are justified by the feature's evidence, media, citation, and browser-workbench needs;
they do not introduce device control, model training, complete GraphRAG, or an enterprise
microservice platform.

## Post-Design Constitution Check

All design artifacts pass the constitution gates:

- The safety gate remains independent of model generation and blocks unsafe ordinary checks.
- The evidence gate is represented by reviewed Evidence records, Citation records, and the report schema.
- The multimodal gate preserves candidate, confirmed, corrected, rejected, and unavailable states.
- The bounded-agent gate has explicit limits and no equipment-control action.
- The knowledge gate keeps safety, alarm codes, manual content, cases, maintenance records, and approved cases separate.
- The human-governance gate keeps AI reports, expert revisions, repair outcomes, and case publication append-only.
- The scope gate leaves complete GraphRAG, training, PLC integration, and enterprise platform work out of phase one.
