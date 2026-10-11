# Research: APX-240 Multimodal Field Diagnosis Loop

**Date**: 2026-10-04

## Decision 1: Use a modular monolith for the first release

**Decision**: Use one Python backend with explicit domain modules and one browser frontend. Run
long media and diagnosis work as background jobs, but keep business ownership in the backend.

**Rationale**: The feature needs clear boundaries between evidence, safety, diagnosis, knowledge,
expert review, and feedback, but the supplied material and demonstration scale do not justify
independent deployable microservices. A modular monolith is easier to run on a Windows host and
keeps transactional state consistent.

**Alternatives considered**: Microservices were rejected because they add deployment and
observability overhead without improving the single-device demonstration. A single unstructured
script was rejected because it would mix safety decisions, model calls, and persistence.

## Decision 2: Use a browser workbench with a Python service

**Decision**: Use a Next.js/React browser interface and a FastAPI/Pydantic service boundary.

**Rationale**: The examiner needs a directly openable interface with media upload, evidence
review, diagnosis timeline, citation drawer, expert handoff, and repair feedback. The Python
service can expose one stable boundary to model and retrieval adapters.

**Alternatives considered**: A Python-only server-rendered UI was rejected because evidence
review and timeline interactions would be less polished. A desktop-only application was rejected
because the submission requires a directly testable web entry point.

## Decision 3: Use PostgreSQL with pgvector and logical knowledge collections

**Decision**: Store business records and immutable versions in PostgreSQL, use pgvector for
semantic retrieval, and use PostgreSQL full-text/keyword search for alarm codes and identifiers.
Keep safety rules and alarm-code records structured rather than relying only on embeddings.

**Rationale**: The feature needs relationships between incidents, evidence, citations, versions,
and review states as well as hybrid retrieval. A single PostgreSQL deployment is sufficient for
the target scale and leaves an upgrade path for more devices.

**Alternatives considered**: SQLite plus a separate embedded vector index would be easier for a
one-process demo but weakens concurrent review, versioning, and future deployment. A dedicated
OpenSearch/Neo4j stack was rejected for the first release because it adds operational complexity;
GraphRAG is explicitly optional.

## Decision 4: Use provider adapters for OCR, vision, video, QR, and language models

**Decision**: Define interfaces for OCR, visual observation, video frame analysis, QR decoding,
embeddings, reranking, and diagnosis generation. Provide a local/default adapter path and allow
an OpenAI-compatible or other approved provider to be configured without changing domain logic.

**Rationale**: Model credentials, GPU availability, and provider choice are not fixed by the
exam materials. Adapters keep evidence status, confidence, and failure handling stable when a
provider is unavailable.

**Alternatives considered**: Hard-coding one vendor was rejected because it prevents offline or
local fallback and makes acceptance tests depend on a remote service. Training a custom model was
rejected by the assignment boundary.

## Decision 5: Treat video as bounded observable evidence in phase one

**Decision**: For a short uploaded video, extract a bounded number of key frames and, when
available, an audio observation; store time ranges and limitations. Do not claim internal causes
that are not directly observable.

**Rationale**: This satisfies the user's phase-one multimodal requirement while keeping latency,
storage, and model cost predictable. Friction, vibration, leak sound, and door state can be
reported as candidate observations without building a full video-understanding platform.

**Alternatives considered**: Full continuous video inference was rejected as unnecessary for the
exam and difficult to validate. Ignoring video was rejected because the feature scope explicitly
includes it.

## Decision 6: Implement a deterministic safety gate before the model loop

**Decision**: Evaluate SAFE-01..05 and authorization boundaries before normal retrieval or
generation. The model may explain the decision but cannot override it.

**Rationale**: Safety requirements are explicit and deterministic. A pre-gate reduces the chance
that a language-model response turns a high-risk event into a routine troubleshooting flow.

**Alternatives considered**: A prompt-only safety instruction was rejected because it is harder
to test and can be contradicted by retrieved text.

## Decision 7: Use LangGraph for the bounded diagnosis loop

**Decision**: Implement the diagnosis loop with LangGraph nodes `prepare`, `safety_gate`,
`retrieve`, `decide`, `ask_information`, `expert_review`, and `finalize`. Use PostgreSQL-backed
checkpoints, `diagnosis_run_id` as `thread_id`, and LangGraph `interrupt/resume` for missing
information, expert takeover, high-risk confirmation, and report review. Cap execution at 8 steps,
3 retrieval rounds, 5 questions, 5 resumes, and 120 seconds for the demonstration profile.

**Rationale**: The project has genuine human pause points. LangGraph supplies explicit checkpoint
and resume semantics while keeping the loop inspectable and bounded. The deterministic safety
module remains outside the graph and must return `CLEAR` before retrieval.

**Alternatives considered**: A hand-written state machine was viable but would duplicate checkpoint,
resume, and concurrent-recovery logic. One-shot generation was rejected because it cannot reliably
handle missing facts, conflicts, or citation constraints. An unrestricted tool-using agent was
rejected for safety and reproducibility reasons.

## Decision 8: Use append-only expert and case governance

**Decision**: Preserve AI reports, expert revisions, repair outcomes, case drafts, and approved
cases as separate versioned records. Only approved cases enter the production retrieval set.

**Rationale**: The reference project demonstrates that feedback must remain tied to the original
run and cannot silently rewrite what the model produced. This is essential for credible field
diagnosis.

**Alternatives considered**: Updating a single case row in place was rejected because it destroys
the evidence trail and makes later diagnosis impossible to reproduce.

## Decision 9: Use a local demonstration profile

**Decision**: Provide Docker Compose for PostgreSQL/pgvector and MinIO media storage, plus local
frontend/backend commands. Keep a local filesystem provider for fixture-mode fallback. Seed only
the supplied APX-240 materials and expose a health page and quickstart scenarios.

**Rationale**: The examiner needs a repeatable local launch path, while the architecture should
remain deployable beyond the demo. Keeping providers configurable avoids requiring a GPU or
external service to verify rule and report behavior.

**Alternatives considered**: A Kubernetes-first deployment was rejected because it does not help
the interview demonstration. A remote-only runtime was rejected because network or credentials
could make the submission unusable.

## Decision 15: Use MinIO as the default local media store

**Decision**: Store original images and videos in a MinIO bucket through the S3 API. Keep the
storage interface provider-based so a local filesystem provider can be selected when Docker is
unavailable and a managed S3 service can be used later.

**Rationale**: MinIO gives the field demo a concrete, inspectable object store without coupling
domain modules to a vendor SDK. Its bucket and object semantics match the intended deployment
path, while the fallback keeps fixture tests lightweight.

**Alternatives considered**: PostgreSQL large objects were rejected because media retention and
inspection would be coupled to relational storage. A filesystem-only default was rejected because
it hides the object-storage boundary that the planned deployment already requires.

## Decision 16: Persist LangGraph checkpoints in PostgreSQL

**Decision**: Use a PostgreSQL-backed LangGraph checkpointer and link each checkpoint to the
DiagnosisRun, Job, evidence snapshot, and manifest version. Resume requests use checkpoint version
compare-and-swap plus an idempotency key.

**Rationale**: In-memory checkpoints would lose A310 answers and expert pauses on process restart.
PostgreSQL is already the authoritative store and can support the demonstration's concurrency
without adding another mandatory service.

**Alternatives considered**: In-memory checkpointing was rejected because it cannot recover a field
session. A separate checkpoint database was rejected because it adds unnecessary operational
complexity.

## Decision 10: Use a persisted local job abstraction

**Decision**: Media analysis and diagnosis runs are represented by a persisted Job record with
`QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `TIMED_OUT`, `CANCELLED`, and `RETRY_WAIT` states.
The default worker is an in-process local worker; Redis is an optional deployment adapter.

**Rationale**: The API already exposes polling and SSE progress, and video/OCR work may exceed a
normal request timeout. A small job boundary provides retries, idempotency, and recoverability
without requiring enterprise workflow infrastructure.

**Alternatives considered**: Synchronous request execution was rejected for media and diagnosis
because timeouts would make field recovery ambiguous. A mandatory queue cluster was rejected as
unnecessary for a single-device demonstration.

## Decision 11: Import the supplied manual as a versioned source release

**Decision**: Extract PDF text while preserving page, section, table, and paragraph locators;
store chunks with checksums and a knowledge-release ID. Safety rules and alarm-code rows retain
links to their manual locators.

**Rationale**: A citation such as SAFE-01 or A203 must be independently verifiable in the supplied
manual, and re-indexing must not silently change an existing diagnosis manifest.

**Alternatives considered**: Copying only hand-curated JSON was rejected because it loses the
manual's authoritative locator and makes report citations difficult to audit.

## Decision 12: Use lightweight role context

**Decision**: Use three application roles: `FIELD_ENGINEER`, `EXPERT`, and `CASE_REVIEWER`.
Authorization is checked at mutation boundaries and recorded in the audit event; no enterprise
identity or permission hierarchy is introduced.

**Rationale**: The project needs to prove that expert revision and case publication are human
actions while remaining appropriate for a personal field-demo project.

## Decision 13: Make every material instruction citation-bearing

**Decision**: Report causes, safety preconditions, and check steps are structured objects with
`citation_ids`; the report validator resolves every cited ID against the diagnosis snapshot.

**Rationale**: Plain strings allow a model to emit an uncited instruction even when the report has
a citation list. Structured references make the evidence boundary testable.

## Decision 14: Seed assets and QR fixtures

**Decision**: Seed a valid APX-240 asset, linked maintenance history, an unknown QR, a non-APX-240
QR, and an APX-240 asset without history. QR resolution is an asset lookup only.

**Rationale**: These fixtures cover the field workflow without treating an identifier as proof of a
fault cause.
