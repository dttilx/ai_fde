# Quickstart Validation: APX-240 Multimodal Field Diagnosis Loop

This guide defines the validation journey for the first demonstration. It is not an installation
guide for a production deployment and does not contain implementation code.

## Prerequisites

- Windows host with Python 3.11+, Node.js 20+, and Docker Desktop available;
- the APX-240 manual PDF and the supplied question-bank document in the repository root;
- a configured language-model provider, or a deterministic fixture provider for rule and contract
  checks;
- the database and media storage services started by the project development profile.

The development profile starts PostgreSQL and MinIO. The MinIO console is available for inspecting
media objects during a demo; fixture mode may select the local filesystem provider when Docker is
not available.

The local profile uses the in-process job worker by default. Redis and external model credentials
are optional. The seed command must import the supplied PDF into a versioned knowledge release and
print the release ID, source checksum, and number of page-addressable chunks.

## Start the demonstration

The eventual implementation must provide a documented start command for the backend, frontend,
and database profile. The command must print the browser URL and a health result. Provider keys
must be supplied through local environment configuration and must never be committed.

## Scenario 1: Complete A203 diagnosis

1. Open the field incident page.
2. Enter: `A203; set temperature 165°C; actual temperature 128°C; heating current 0A; preheating completed`.
3. Submit the incident without media.
4. Open the diagnosis report.

Expected result:

- The report is `COMPLETED` or requests only a clearly justified remaining fact.
- The SAFE-01..05 gate is recorded as `CLEAR` before any normal retrieval event.
- A203 is cited as the alarm source.
- H02 and the relevant maintenance record are shown as historical evidence.
- H1 open circuit is labeled a possible cause, not a confirmed root cause.
- Lockout/tagout and authorized electrical-person requirements appear before circuit checks.
- The report contains every required field from `contracts/diagnosis-report.schema.json`.
- Every safety precondition and check step exposes at least one citation ID that resolves in the
  report citation drawer.

## Scenario 2: Incomplete A310 diagnosis

1. Enter: `A310，似乎有漏气。`
2. Submit the incident without pressure readings or media.

Expected result:

- The run enters `NEEDS_INFORMATION`.
- The LangGraph run pauses with an `INFORMATION` interrupt and persists a PostgreSQL checkpoint.
- The system asks for upstream pressure, equipment-side pressure, and continuous leak-sound evidence.
- The system does not state that a loose downstream connector is confirmed.
- The user can answer one question through the resume endpoint and continue the same graph thread
  without losing prior facts. Repeating the same idempotency key does not duplicate the answer.

## Scenario 3: SAFE-01 escalation

1. Enter: `运行中有焦味，热封区域温度突然升高。`
2. Submit the incident.

Expected result:

- The safety decision appears before normal troubleshooting.
- The LangGraph run pauses with an `EXPERT` or `HIGH_RISK` interrupt and remains resumable.
- The report requires immediate stop and expert escalation.
- Continued trial operation and direct heater contact are explicitly prohibited.
- The source cites SAFE-01 and any applicable isolation rule.

## Scenario 4: Evidence review

1. Create an incident with a control-panel image containing an alarm code.
2. Upload a short video showing a possible periodic vibration.
3. Upload or scan a QR code for an APX-240 asset.
4. Review each candidate as confirmed, corrected, or rejected.

Expected result:

- Diagnosis cannot start until required candidates have a review decision.
- Upload and analysis progress is visible through the job status endpoint or SSE events.
- OCR includes a source region and confidence or a limitation.
- Video observations include a time range and remain observations rather than root causes.
- QR associates asset history only after acceptance and does not become diagnostic proof.
- A blurred image produces an explicit inability-to-determine result and a retake request.

## Scenario 4b: Evidence conflict and report review pause

1. Enter `A203` manually and upload an image whose OCR candidate conflicts with that alarm.
2. Leave both observations visible and start diagnosis.
3. Resume as an expert after reviewing the conflict, then pause before final report review.
4. Resume as the field engineer after reviewing the cited report.

Expected result:

- The graph enters `CONFLICT_BLOCKED` or `WAITING_EXPERT` and does not retrieve ordinary checks
  until the conflict is resolved.
- Checkpoint version and actor role are validated for every resume.
- A stale checkpoint version, duplicate key, or concurrent resume is rejected without mutation.
- The final report is a new version and retains both original observations and their citations.

## Scenario 5: Repair feedback and case governance

1. Complete a diagnosis.
2. Submit a confirmed root cause, repair action, responsible role, and restart validation.
3. Create a case draft and inspect retrieval results before approval.
4. Approve the draft as an expert.

Expected result:

- The AI report remains unchanged.
- The case is not returned as official knowledge before approval.
- Approval creates a new versioned case with incident, diagnosis, citation, and validation links.
- A duplicate repair submission does not create a second equivalent case draft.

## Scenario 6: Asset and QR fallback

1. Accept the valid APX-240 QR fixture and inspect linked maintenance history.
2. Try an unknown QR, a non-APX-240 QR, and an APX-240 asset without history.

Expected result:

- A valid QR attaches an asset only and never creates a possible cause.
- Unknown or non-APX-240 values remain reviewable with a limitation and allow manual asset entry.
- An asset without history remains usable for text diagnosis and reports that no history was found.

## Scenario 7: Moderated usability check

Use a five-minute walkthrough with a field engineer or a scripted evaluator. Ask the participant
to identify the immediate safety action, the leading possible cause, the next check, and the source
citation for the A203 and SAFE-01 reports without opening logs. Record completion, incorrect
actions, time to locate each item, and whether all four items were found. Pass requires all four
items to be found without hidden system information.

## Contract and failure checks

Validate the report, job, and event payloads against the schemas and contracts in `contracts/`.
Repeat selected scenarios with OCR failure, video unavailability, QR mismatch, model timeout,
empty retrieval, contradictory readings, job cancellation, retry exhaustion, checkpoint loss,
stale resume, concurrent resume, and duplicate repair feedback. Each failure must produce a
recoverable user-facing state and must never produce a fabricated diagnosis.

## Demonstration evidence

For the interview demonstration, capture:

- the input incident;
- evidence review decisions;
- safety decision;
- diagnosis timeline;
- citations opened in the source drawer;
- final report;
- repair feedback and case review status.

The demonstration is successful only when an evaluator can trace a conclusion back to the supplied
APX-240 materials and see the system stop or ask for information when evidence is insufficient.
