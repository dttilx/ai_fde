# Data Model: APX-240 Multimodal Field Diagnosis Loop

## Incident

Represents one field-reported equipment event.

| Field | Type | Rules |
|---|---|---|
| incident_id | identifier | Immutable; generated at creation |
| asset_id | identifier, nullable | Must resolve to APX-240 when present |
| raw_description | text | Required; original wording is immutable |
| structured_facts | object | Readings, alarm codes, time, smell, sound, vibration, prior actions |
| status | enum | DRAFT, EVIDENCE_REVIEW, READY, RUNNING, NEEDS_INFORMATION, COMPLETED, WAITING_EXPERT, CLOSED |
| created_at | timestamp | Required |
| updated_at | timestamp | Required |

## MediaAsset

Represents an uploaded image or video.

| Field | Type | Rules |
|---|---|---|
| media_id | identifier | Immutable |
| incident_id | identifier | Must reference one Incident |
| media_type | enum | IMAGE or VIDEO |
| storage_ref | string | Must not expose untrusted local paths to the browser |
| scan_status | enum | PENDING, CLEAN, REJECTED, FAILED |
| processing_status | enum | NOT_STARTED, PROCESSING, CANDIDATES_READY, UNUSABLE, FAILED |
| duration_ms | integer, nullable | Required for video when known |
| checksum | string | Used for duplicate detection and provenance |

## Evidence

Represents a fact or observation proposed for diagnosis.

| Field | Type | Rules |
|---|---|---|
| evidence_id | identifier | Immutable |
| incident_id | identifier | Required |
| source_type | enum | TEXT, FORM, OCR, VISION, VIDEO, QR |
| content | text/object | Candidate observation or confirmed fact |
| confidence | decimal, nullable | 0 to 1 for automated candidates |
| status | enum | CANDIDATE, CONFIRMED, CORRECTED, REJECTED, UNAVAILABLE |
| source_media_id | identifier, nullable | Required for media-derived evidence |
| locator | object, nullable | Image bounding box or video time range |
| reviewed_by | identifier, nullable | Required for CONFIRMED/CORRECTED |
| observed_at | timestamp, nullable | Time of field observation if supplied |

Only CONFIRMED and CORRECTED evidence is eligible for the diagnosis snapshot.

## Asset

Represents an identifiable APX-240 device.

| Field | Type | Rules |
|---|---|---|
| asset_id | identifier | Unique within the demonstration scope |
| model | string | First release must be APX-240 |
| qr_value | string, nullable | Lookup key; not diagnostic evidence |
| location | string, nullable | Informational |
| maintenance_history_ref | list | Links to maintenance records |

## DiagnosisRun

Represents one bounded diagnosis attempt.

| Field | Type | Rules |
|---|---|---|
| diagnosis_run_id | identifier | Immutable |
| incident_id | identifier | Required |
| status | enum | RUNNING, NEEDS_INFORMATION, COMPLETED, ESCALATED, FAILED |
| state_snapshot | object | Checkpointed state and counters |
| report | object, nullable | Required for terminal states with a report |
| manifest | object | Agent, prompt, model, index, evidence and citation versions |
| graph_thread_id | string | Stable LangGraph thread ID; equals diagnosis_run_id |
| checkpoint_version | integer | Compare-and-swap version for resume operations |
| resume_count | integer | Bounded; incremented on every accepted interrupt resume |
| started_at | timestamp | Required |
| completed_at | timestamp, nullable | Required for terminal state |

## Citation

Represents a source shown to the engineer.

| Field | Type | Rules |
|---|---|---|
| citation_id | identifier | Unique within a knowledge release |
| source_type | enum | SAFETY_RULE, ALARM_CODE, MANUAL, HISTORICAL_CASE, MAINTENANCE_RECORD, APPROVED_CASE |
| source_ref | string | Human-readable source such as A203, H02, or WO-240-042 |
| section_or_locator | string | Manual page, table row, or record section |
| excerpt | text | Bounded source excerpt |
| knowledge_release_id | identifier | Required for reproducibility |
| checksum | string | Detects changed source content |

## ExpertReview

Represents an expert takeover or revision.

| Field | Type | Rules |
|---|---|---|
| review_id | identifier | Immutable |
| diagnosis_run_id | identifier | Required |
| status | enum | OPEN, REVISED, ESCALATED, CLOSED |
| reason | text | Required for OPEN |
| revised_report | object, nullable | New report version; never overwrites AI report |
| reviewer_id | identifier | Required for closure |
| created_at | timestamp | Required |

## RepairOutcome

Represents field work performed after diagnosis.

| Field | Type | Rules |
|---|---|---|
| repair_outcome_id | identifier | Immutable |
| incident_id | identifier | Required |
| diagnosis_run_id | identifier | Required |
| confirmed_root_cause | text | Must be entered by an authorized role |
| repair_action | text | Required |
| responsible_role | string | Must identify the executing role |
| restart_validation | text | Required before case approval |
| submitted_by | identifier | Required |
| submitted_at | timestamp | Required |

## CaseDraft and VerifiedCase

`CaseDraft` is generated from a RepairOutcome and remains excluded from production retrieval.
`VerifiedCase` is a reviewed, versioned copy eligible for retrieval.

Required fields for both include alarm codes, observed symptoms, evidence references, confirmed
root cause, repair action, restart validation, source incident, source diagnosis version,
review status, reviewer, and publication time. A draft without confirmed root cause and restart
validation cannot be approved.

## State Transitions

```text
Incident: DRAFT → EVIDENCE_REVIEW → READY → RUNNING
         → NEEDS_INFORMATION → READY → RUNNING
         → COMPLETED / WAITING_EXPERT / CLOSED

DiagnosisRun: RUNNING → NEEDS_INFORMATION / WAITING_EXPERT / CONFLICT_BLOCKED / COMPLETED / ESCALATED / FAILED

Evidence: CANDIDATE → CONFIRMED / CORRECTED / REJECTED / UNAVAILABLE

ExpertReview: OPEN → REVISED / ESCALATED → CLOSED

CaseDraft: DRAFT → IN_REVIEW → APPROVED / REJECTED
VerifiedCase: APPROVED → PUBLISHED → RETIRED
```

## LangGraphState and GraphCheckpoint

`LangGraphState` is the serializable state passed between graph nodes. It contains the
`diagnosis_run_id`, `incident_id`, current state, confirmed evidence snapshot, citations, pending
questions, expert action, report draft, counters, and manifest references. It never contains hidden
chain-of-thought or secrets.

`GraphCheckpoint` is persisted by the PostgreSQL LangGraph checkpointer:

| Field | Type | Rules |
|---|---|---|
| checkpoint_id | identifier | Immutable |
| diagnosis_run_id / graph_thread_id | identifier/string | Required and stable for the run |
| checkpoint_version | integer | Monotonic; resume uses compare-and-swap |
| graph_node | enum | prepare, safety_gate, retrieve, decide, ask_information, expert_review, finalize |
| state | object | Serialized LangGraphState snapshot |
| interrupt_type | enum, nullable | INFORMATION, EXPERT, HIGH_RISK, REPORT_REVIEW |
| created_at | timestamp | Required |

An interrupt creates a `NEEDS_INFORMATION`, `WAITING_EXPERT`, or `CONFLICT_BLOCKED` state. A
resume must provide the expected checkpoint version, actor role, and idempotency key. Duplicate or
concurrent resumes are rejected without mutating the checkpoint.

## LangGraph state transitions

```text
PREPARING → SAFETY_CHECK
SAFETY_CHECK → RETRIEVING | WAITING_EXPERT | CONFLICT_BLOCKED | ESCALATED
RETRIEVING → RETRIEVING | NEEDS_INFORMATION | WAITING_EXPERT | FINALIZING
NEEDS_INFORMATION --interrupt/resume--> RETRIEVING
WAITING_EXPERT --interrupt/resume--> RETRIEVING | FINALIZING | ESCALATED
CONFLICT_BLOCKED --expert resume--> WAITING_EXPERT | ESCALATED
FINALIZING --report review--> COMPLETED | WAITING_EXPERT | FAILED
```

Graph states are finer-grained than the public `DiagnosisRun.status`. The mapping is:

| Graph state(s) | DiagnosisRun.status |
|---|---|
| PREPARING, SAFETY_CHECK, RETRIEVING, FINALIZING | RUNNING |
| NEEDS_INFORMATION | NEEDS_INFORMATION |
| WAITING_EXPERT, CONFLICT_BLOCKED | ESCALATED |
| COMPLETED | COMPLETED |
| FAILED | FAILED |

## Job

Represents asynchronous media or diagnosis work. It is owned by the related Incident, MediaAsset,
or DiagnosisRun and is the authoritative source for polling status.

| Field | Type | Rules |
|---|---|---|
| job_id | identifier | Immutable |
| kind | enum | MEDIA_SCAN, OCR, VISION, QR, VIDEO, DIAGNOSIS |
| status | enum | QUEUED, RUNNING, SUCCEEDED, FAILED, TIMED_OUT, CANCELLED, RETRY_WAIT |
| idempotency_key | string | Unique per operation and source version |
| attempt | integer | Monotonic; bounded by provider policy |
| deadline_at | timestamp | Required |
| error_code | string, nullable | Required for FAILED/TIMED_OUT |
| result_ref | identifier, nullable | Points to created evidence or diagnosis version |
| created_at / updated_at | timestamp | Required |

Jobs emit append-only progress events. A local in-process worker implements the first release;
the job contract does not require Redis.

## Actor and Role Context

Every mutable API operation records an actor ID and one role: `FIELD_ENGINEER`, `EXPERT`, or
`CASE_REVIEWER`. Repair outcomes require FIELD_ENGINEER or EXPERT, expert revisions require
EXPERT, and case publication requires CASE_REVIEWER or EXPERT. This is a lightweight application
boundary for the demonstration, not a full enterprise permission system.

## ManualSource and KnowledgeChunk

`ManualSource` records the supplied PDF checksum and knowledge release. `KnowledgeChunk` stores
the extracted text, page number, section/table/paragraph locator, source checksum, and embedding
version. Safety rules and alarm-code rows must reference a chunk locator; a new import creates a
new release and never overwrites a prior release.

## Report Instruction Objects

The report contract represents each safety precondition and check step as an object containing
human-readable text, ordered position, and one or more `citation_ids`. A possible cause follows
the same citation rule. A report cannot enter a terminal state when a material instruction has no
resolvable citation in the diagnosis snapshot.
