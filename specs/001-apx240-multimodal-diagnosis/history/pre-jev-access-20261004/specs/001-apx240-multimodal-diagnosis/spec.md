# Feature Specification: APX-240 Multimodal Field Diagnosis Loop

**Feature Branch**: `001-apx240-multimodal-diagnosis`

**Created**: 2026-10-04

**Status**: Draft

**Input**: User description: Create a field-ready multimodal APX-240 equipment fault diagnosis loop with reviewed evidence, safety escalation, grounded retrieval, expert handoff, and repair feedback.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Submit and Diagnose a Field Incident (Priority: P1)

As a field engineer, I want to enter a fault description and available readings so that I can receive a structured diagnosis grounded in the APX-240 materials.

**Why this priority**: Text-based incident diagnosis is the core value of the assignment and must remain useful even when no media is available.

**Independent Test**: Submit a complete A203 report with the set temperature, actual temperature, heating current, and preheating status; receive a report containing facts, possible causes, cited evidence, safe checks, missing information, and escalation status.

**Acceptance Scenarios**:

1. **Given** an engineer enters A203, 165°C set temperature, 128°C actual temperature, 0A heating current, and completed preheating, **When** the engineer submits the incident, **Then** the system returns a structured diagnosis that cites A203, H02, and the relevant maintenance record and labels the H1 open circuit as a possible cause rather than a confirmed root cause.
2. **Given** an engineer enters an unsupported or unrecognized alarm, **When** the incident is submitted, **Then** the system states that the knowledge base does not cover the condition, lists the safe information to collect, and recommends expert escalation without inventing a cause.

---

### User Story 2 - Stop or Escalate Unsafe Conditions (Priority: P1)

As a field engineer, I want dangerous symptoms to be identified before normal troubleshooting so that I do not receive instructions that could cause injury or equipment damage.

**Why this priority**: The APX-240 manual makes safety escalation a hard requirement and a wrong recommendation has greater impact than an incomplete diagnosis.

**Independent Test**: Submit a report containing smoke, burning smell, abnormal high temperature, severe vibration, metal friction, or a loose component; verify that the system presents immediate stop and expert escalation instructions and does not present ordinary trial-run steps.

**Acceptance Scenarios**:

1. **Given** a report mentions burning smell and abnormal high temperature, **When** the report is submitted, **Then** the system immediately requires shutdown and expert escalation, cites SAFE-01, and prohibits continued trial operation.
2. **Given** a proposed check would involve opening a guard, checking wiring, touching a heater, or clearing a jam, **When** the system generates next steps, **Then** it includes power isolation, lockout/tagout, residual-energy release, and authorized-person requirements before that check.
3. **Given** evidence is contradictory or the risk cannot be determined, **When** the system evaluates the incident, **Then** it stops further troubleshooting and routes the incident to expert review.

---

### User Story 3 - Confirm Multimodal Evidence Before Diagnosis (Priority: P1)

As a field engineer, I want to review OCR, visual, video, and QR findings before diagnosis so that uncertain observations do not become false facts.

**Why this priority**: The first phase explicitly includes images, video, text, and QR information, but every automated observation must remain reviewable.

**Independent Test**: Upload a control-panel image, a short equipment video, and a QR code; verify that each produces a candidate evidence item that can be accepted, corrected, or rejected before diagnosis begins.

**Acceptance Scenarios**:

1. **Given** an image contains a readable A203 code and temperature value, **When** image analysis finishes, **Then** the system displays the extracted candidates, confidence, source region, and review actions.
2. **Given** OCR cannot read a blurred or occluded panel, **When** the image is reviewed, **Then** the system marks the reading as unavailable, explains the reason, and requests a clearer image instead of guessing.
3. **Given** a QR code resolves to an APX-240 asset, **When** the engineer accepts it, **Then** the system associates the incident with that asset and related history; the QR result itself is not treated as proof of a root cause.
4. **Given** a video contains a potentially periodic friction sound or vibration, **When** video analysis finishes, **Then** the system identifies the observation as a candidate with a time range and does not claim an internal failure that cannot be observed directly.

---

### User Story 4 - Ask for Missing Information (Priority: P1)

As a field engineer, I want the system to ask only for information that can change the diagnosis or safety decision so that an incomplete report can be completed efficiently.

**Why this priority**: Real field reports are often partial, and the assignment requires explicit handling of missing information instead of speculation.

**Independent Test**: Submit “A310, seems to be leaking”; verify that the system asks for upstream pressure, equipment-side pressure, and whether a continuous leak sound is present, while avoiding a definitive loose-connector conclusion.

**Acceptance Scenarios**:

1. **Given** A310 is reported without pressure readings, **When** the system evaluates completeness, **Then** it enters an information-needed state and asks for upstream pressure, equipment-side pressure, and leak-sound evidence.
2. **Given** the engineer answers only some questions, **When** the report is re-evaluated, **Then** the system preserves the prior facts, marks unanswered items as unconfirmed, and asks only the remaining high-value questions.
3. **Given** the available information cannot distinguish multiple causes, **When** the question budget is reached, **Then** the system reports the uncertainty and recommends expert escalation rather than guessing.

---

### User Story 5 - Record Repair Outcome and Curate a New Case (Priority: P2)

As an engineer or domain expert, I want to record the confirmed root cause, repair action, and restart validation so that a future incident can benefit from verified experience.

**Why this priority**: The project should close the operational loop, while protecting the production knowledge base from unverified model guesses.

**Independent Test**: Complete a diagnosis, enter a confirmed root cause and restart validation, and verify that the result becomes a reviewable case draft and is not searchable as official knowledge until approved.

**Acceptance Scenarios**:

1. **Given** a diagnosis has completed, **When** an authorized engineer records a root cause, repair action, and restart validation, **Then** the system creates a candidate case linked to the original incident and diagnosis versions.
2. **Given** a candidate case lacks confirmation or restart validation, **When** it is submitted for curation, **Then** it remains unapproved and cannot enter the production knowledge set.
3. **Given** an expert approves a candidate case, **When** it is published, **Then** it becomes a new versioned knowledge item while the original incident, AI report, and expert decision remain immutable.

### Edge Cases

- A report contains no alarm code and only a vague symptom; the system must request the minimum information needed and must not fabricate an alarm.
- An OCR result conflicts with the engineer-entered alarm code; both observations must be shown, and the incident must require confirmation before diagnosis.
- A QR code is unreadable, resolves to a non-APX-240 asset, or has no asset record; the engineer must be able to continue with manual identification or proceed without asset history.
- A video is too long, too dark, silent, or has no relevant equipment region; the system must report the limitation and allow a text-only diagnosis.
- A historical case appears similar but current readings differ; the report must show the difference and prioritize current evidence and alarm-code instructions.
- A requested check crosses an authorization boundary; the system must describe the boundary and route the action to the proper expert.
- A model, OCR, or retrieval service fails; the incident must remain recoverable and show a user-facing failure or information-needed state rather than a fabricated success.
- The same repair feedback is submitted twice; the system must avoid creating duplicate case drafts while preserving the original submission.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST allow a field engineer to create a fault incident containing a free-text description and available structured facts such as alarm code, device identifier, readings, time, sound, smell, vibration, and actions already taken.
- **FR-002**: The system MUST accept image and video evidence and MUST allow an incident to continue with text-only input when media is unavailable or unusable.
- **FR-003**: The system MUST produce reviewable candidate evidence for OCR, visual observations, video observations, and QR decoding, including source, confidence or limitation, and an association to the originating media.
- **FR-004**: The system MUST allow each candidate evidence item to be accepted, corrected, or rejected before it is included in the diagnosis context.
- **FR-005**: The system MUST treat a QR result as an asset lookup signal only and MUST NOT treat it as proof of a fault cause.
- **FR-006**: The system MUST normalize the submitted facts and confirmed evidence into a single incident context while preserving the original input and each evidence source.
- **FR-007**: The system MUST evaluate SAFE-01 through SAFE-05 before ordinary troubleshooting and MUST display immediate stop, forbidden actions, required isolation, authorization, and escalation instructions when a rule applies.
- **FR-008**: The system MUST keep known facts, observations, possible causes, unconfirmed information, and contradictions as distinct report categories.
- **FR-009**: The system MUST retrieve safety rules, alarm-code guidance, equipment information, historical cases, maintenance records, and approved cases as logically distinct evidence sources.
- **FR-010**: The system MUST use current alarm-code instructions and safety rules ahead of similar historical cases when evidence differs.
- **FR-011**: The system MUST cite the specific source for each reported possible cause and each material troubleshooting instruction.
- **FR-012**: The system MUST use a bounded diagnosis loop whose actions are limited to retrieving more evidence, requesting information, escalating to an expert, or producing a final report.
- **FR-013**: The system MUST stop and report the reason when the diagnosis reaches its step, retrieval, question, token, or time budget.
- **FR-014**: The system MUST enter an information-needed state when required readings, observations, timestamps, or authorization facts are missing, and MUST ask only questions relevant to the next decision.
- **FR-015**: The system MUST enter expert review when safety risk is unclear, evidence is contradictory, the knowledge base has no coverage, or an action requires authorized personnel.
- **FR-016**: The system MUST produce a report containing fault phenomenon, known facts, possible causes, evidence sources, safety preconditions, check order, missing information, stop conditions, and expert-escalation status.
- **FR-017**: The system MUST preserve the original evidence, AI report, expert revision, and repair outcome as separate records or versions.
- **FR-018**: The system MUST record the versions or identities of the diagnosis process, instructions, model, knowledge set, evidence snapshot, and citations used for each diagnosis.
- **FR-019**: The system MUST allow an authorized engineer to submit confirmed root cause, repair action, responsible role, and restart validation after a diagnosis.
- **FR-020**: The system MUST create an unapproved case draft from repair feedback and MUST prevent it from entering the production knowledge set until an authorized reviewer approves it.
- **FR-021**: The system MUST provide a user-facing explanation when an image, video, OCR, QR, model, or retrieval operation cannot produce reliable evidence.
- **FR-022**: The system MUST NOT send equipment-control commands, modify equipment settings, bypass interlocks, or execute physical repair actions.

### Key Entities *(include if feature involves data)*

- **Fault Incident**: A field-reported equipment event containing original description, structured facts, asset association, lifecycle status, and linked evidence and diagnoses.
- **Media Asset**: An uploaded image or video with its processing status, source metadata, and retention association.
- **Evidence Item**: A confirmed, corrected, rejected, or pending observation derived from text, a media asset, OCR, visual analysis, video analysis, or QR decoding.
- **Asset**: The APX-240 equipment identity that can be entered manually or resolved from a QR code and can link to applicable maintenance history.
- **Diagnosis Run**: One bounded evaluation of an incident with its evidence snapshot, decisions, report, citations, and process versions.
- **Citation**: A traceable reference to a specific alarm-code entry, manual section, historical case, maintenance record, or approved case.
- **Expert Review**: A human takeover or revision created when risk, uncertainty, conflict, authorization, or knowledge coverage requires expert judgment.
- **Repair Outcome**: The confirmed root cause, repair action, responsible role, and restart validation recorded after field work.
- **Case Draft**: A proposed reusable case derived from a repair outcome and awaiting review.
- **Approved Case**: A reviewed and versioned case eligible for future diagnosis retrieval.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In the reference A203 scenario, at least 100% of the required report fields are populated, and the report cites A203 plus the relevant H02 and maintenance evidence without labeling the historical root cause as confirmed.
- **SC-002**: In the incomplete A310 scenario, the system asks for upstream pressure, equipment-side pressure, and leak-sound evidence before presenting a connector-related cause as anything more than possible.
- **SC-003**: In every SAFE-01 test scenario, the safety stop and expert-escalation instruction appears before ordinary troubleshooting steps, with zero permitted continued-trial-run recommendations.
- **SC-004**: In media review tests, 100% of OCR, visual, video, and QR candidates expose a review action and a source or limitation before diagnosis begins.
- **SC-005**: At least 90% of reference diagnosis scenarios return a source citation for every possible cause and material next step.
- **SC-006**: At least 90% of reference incidents with intentionally removed required facts enter an information-needed or expert-review state rather than producing a definitive root cause.
- **SC-007**: A field engineer can submit a normal text-only incident and reach a structured report in one continuous session without uploading media.
- **SC-008**: A repair outcome can be recorded without changing the original AI report, and an unapproved case draft is not returned as official knowledge in subsequent retrieval checks.
- **SC-009**: In a moderated usability check, engineers can identify the immediate safety action, the leading possible cause, the next check, and the cited source from the report without reading hidden system logs.
- **SC-010**: A failed or unavailable media, model, or retrieval operation produces an explicit limitation and recoverable next action in 100% of tested failure cases.

## Assumptions

- The first release targets APX-240 and the supplied seven alarm-code entries, five historical cases, and five maintenance records; support for other device families is outside this feature.
- Field engineers can provide at least a text description, but reports may be incomplete, uncertain, or contradictory.
- Expert reviewers are available to confirm high-risk diagnoses and approve new reusable cases.
- The supplied manual is the authoritative source for the first release's safety rules, normal parameters, alarm-code order, and authorization boundaries.
- Images and videos are provided as ordinary field media; media quality and coverage cannot be assumed, so the product must support explicit inability-to-determine outcomes.
- QR data may identify an asset only when an asset record exists; manual asset entry remains available.
- Diagnosis is advisory and read-only with respect to the equipment; all physical actions remain with authorized personnel.
- An ordinary web session and stable connectivity are available for the first field demonstration. Offline execution is outside this feature.
- Retention, access control, and deployment details will be defined during technical planning, subject to the constitution's evidence and safety requirements.
