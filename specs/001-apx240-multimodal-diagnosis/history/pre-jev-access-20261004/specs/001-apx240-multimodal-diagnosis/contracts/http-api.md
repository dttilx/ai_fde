# HTTP and Event Contracts

These contracts define the user-facing application boundary. They are intentionally described
without implementation bodies. Every mutating request carries a lightweight actor context with
`actor_id` and one role: `FIELD_ENGINEER`, `EXPERT`, or `CASE_REVIEWER`.

## Incident APIs

### Create incident

`POST /api/incidents`

Request includes free-text description, optional asset identifier, alarm code, readings, time,
observed smell/sound/vibration, and actions already taken.

Response returns `incident_id`, lifecycle status, normalized facts, and required evidence actions.

### Get incident

`GET /api/incidents/{incident_id}`

Returns the immutable original input, structured facts, evidence summaries, diagnosis runs,
expert reviews, and repair outcomes visible to the current user.

## Media and Evidence APIs

### Upload media

`POST /api/incidents/{incident_id}/media`

Accepts an image or short video. Returns `media_id`, `job_id`, scan status, processing status, and
a polling/event reference. A rejected or failed media item must include a user-facing reason.

### List evidence candidates

`GET /api/incidents/{incident_id}/evidence`

Returns candidate and reviewed evidence, confidence, source media, image/video locator, and
limitation details.

### Review evidence

`POST /api/incidents/{incident_id}/evidence/{evidence_id}/review`

Request:

```json
{
  "decision": "CONFIRMED|CORRECTED|REJECTED",
  "corrected_content": null,
  "review_note": "optional reason"
}
```

Only confirmed or corrected evidence can be included in a diagnosis snapshot. A candidate marked
unavailable remains visible with its limitation and cannot enter the snapshot.

### Get job

`GET /api/jobs/{job_id}`

Returns `kind`, `status`, `attempt`, `deadline_at`, `error_code`, `result_ref`, and progress
events. The status is one of `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `TIMED_OUT`,
`CANCELLED`, or `RETRY_WAIT`. Repeated requests are read-only; the idempotency key prevents
duplicate media or diagnosis work.

## Diagnosis APIs

### Start diagnosis

`POST /api/incidents/{incident_id}/diagnoses`

Starts a bounded run only when the incident is ready for diagnosis and required candidate
evidence has been reviewed. The run always executes the deterministic SAFE-01..05 gate before
normal retrieval. Returns `diagnosis_run_id`, `job_id`, status, and the process manifest summary.

### Get diagnosis

`GET /api/diagnoses/{diagnosis_run_id}`

Returns status, report, missing information, contradictions, safety decision, citations, step
timeline, and manifest references. It must not expose hidden model reasoning.

### Submit missing information

`POST /api/diagnoses/{diagnosis_run_id}/information`

Adds an engineer-confirmed answer or new evidence and creates a new diagnosis version. It never
mutates the prior report.

### Resume interrupted diagnosis

`POST /api/diagnoses/{diagnosis_run_id}/resume`

Request includes `checkpoint_version`, `idempotency_key`, the actor role, and exactly one resume
payload: an answer to pending questions, an expert decision, a high-risk confirmation, or a report
review decision. The service loads the PostgreSQL LangGraph checkpoint identified by
`diagnosis_run_id`, validates the version and role, applies compare-and-swap, and resumes the same
graph thread. A duplicate or concurrent resume returns a conflict without changing state.

Response returns `diagnosis_run_id`, `job_id`, `checkpoint_version`, graph state, and current
interrupt status. It never exposes hidden model reasoning.

### Get graph checkpoint

`GET /api/diagnoses/{diagnosis_run_id}/checkpoint`

Returns the current graph node, public state, checkpoint version, pending interrupt type, and
resume count. It never returns internal prompts or chain-of-thought.

## Expert APIs

### Request expert takeover

`POST /api/diagnoses/{diagnosis_run_id}/expert-reviews`

Creates an expert review with a required reason and current report version.

### Submit expert revision

`POST /api/expert-reviews/{review_id}/revision`

Creates a new report version with reviewed facts, conclusions, citations, missing information,
next checks, and final escalation status.

## Repair and Case APIs

### Submit repair outcome

`POST /api/incidents/{incident_id}/repair-outcomes`

Requires confirmed root cause, repair action, responsible role, and restart validation. Repeated
submissions for the same diagnosis must be idempotent.

### Create or review case draft

`POST /api/repair-outcomes/{repair_outcome_id}/case-draft`

Creates a non-production case draft linked to the incident and diagnosis manifest.

`POST /api/case-drafts/{case_id}/review`

Accepts `APPROVE` or `REJECT` with reviewer identity and review note. Approval creates a new
versioned `VerifiedCase`; it does not alter the source incident or report.

### Role requirements

- `FIELD_ENGINEER` or `EXPERT`: submit repair outcome and answer diagnosis questions.
- `EXPERT`: request or submit expert report revision.
- `CASE_REVIEWER` or `EXPERT`: approve or reject a case draft.

The service must reject a mutation when the actor role is insufficient and must append an audit
event for accepted mutations.

## Event Contract

The UI may subscribe to `GET /api/incidents/{incident_id}/events` using a server-sent event
stream. Events are append-only and include:

```json
{
  "event_id": "evt-...",
  "incident_id": "inc-...",
  "sequence": 12,
  "type": "job.queued|job.progress|job.failed|graph.interrupted|graph.resumed|evidence.candidate_ready|evidence.reviewed|safety.decision|diagnosis.step|diagnosis.report_ready|expert.review_opened|repair.outcome_saved|case.reviewed",
  "occurred_at": "2026-10-04T10:00:00Z",
  "payload": {},
  "trace_id": "trace-..."
}
```

The event stream is for display and progress only; authoritative state is read from the resource
APIs.
