# Feature Specification: APX-240 Multimodal Field Diagnosis Loop

**Feature Branch**: `001-apx240-multimodal-diagnosis`

**Created**: 2026-10-04

**Status**: Draft

**Revision**: 2.2.0, integrated Jev/access design, 2026-10-04. Original artifacts are preserved in `history/pre-jev-access-20261004/`; decisions and unresolved findings are recorded in `integration-review.md`. Nothing has been implemented or field-accepted.

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
4. **Given** a video shows possible vibration, **When** visual analysis finishes, **Then** the system produces a timestamped candidate without claiming an internal failure. Sound is recorded through a user's explicit time-located observation; without a validated audio adapter the system does not automatically identify friction or leak sounds.

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
3. **Given** an assigned case reviewer approves a candidate with repair evidence and restart verification, **When** de-identification and publication scope are also approved, **Then** it becomes versioned knowledge in that scope while original records remain immutable. Expert status alone does not grant publication rights.

### User Story 6 - Inspect Jev-Assessed Retrieval and Citation Support (Priority: P1)

As an engineer, I want retrieved sources assessed by Jev when processing is permitted and see why they were used, so that relevant evidence and unresolved differences remain visible.

**Independent Test**: Use authorized events and explicitly permitted simulation sources to run real Jev; retain necessary alarm sources, separate irrelevant passages and historical differences, and display actual processing mode. Repeat without credentials and with external-processing restrictions.

**Acceptance Scenarios**:
1. Related and unrelated passages produce source-use assessments; necessary safety and alarm guidance remains regardless of scores.
2. Potential contradictions are preserved for verification; different historical readings are differences, not automatically contradictory current facts.
3. A readable source forbidden for external processing is not transmitted and is marked policy-skipped.
4. A real citation not supporting its claim requires correction or human review; no AI root-cause confirmation occurs.

### User Story 7 - Respect Resource and Maintenance Authorization (Priority: P1)

As an authorized engineer, expert or reviewer, I want access limited to assigned resources and suggestions to identify qualification and known service restrictions.

**Independent Test**: Two accounts access separate events; cross-event records/media/progress are blocked. A business expert without electrical qualification cannot treat their role as circuit-work authorization. Unknown warranty terms remain unknown.

**Acceptance Scenarios**:
1. Verified identities control access; client role fields, guessed IDs or QR values never grant it.
2. Missing maintenance qualification routes applicable steps to authorized personnel without issuing control commands.
3. Revoked role/resource access blocks resume and cached sensitive output during a pause.
4. Warranty dates without contractual restrictions permit date calculation but no invented loss-of-warranty conclusion.
5. Case approval does not expand sharing until its publication scope is explicitly approved.

### Edge Cases

- A report contains no alarm code and only a vague symptom; the system must request the minimum information needed and must not fabricate an alarm.
- An OCR result conflicts with the engineer-entered alarm code; both observations must be shown, and the candidate must be reviewed before use; only a confirmed unresolved conflict blocks diagnosis and routes to expert review.
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
- **FR-007**: The system MUST execute independent pre-retrieval risk checks and post-retrieval SAFE-05 support/conflict checks before ordinary troubleshooting; it MUST display immediate stop, forbidden actions, isolation, qualification and escalation when applicable. Clear danger notice does not wait for media/model work.
- **FR-008**: The system MUST keep known facts, observations, possible causes, unconfirmed information, and contradictions as distinct report categories.
- **FR-009**: The system MUST retrieve safety rules, alarm-code guidance, equipment information, historical cases, maintenance records, and approved cases as logically distinct evidence sources.
- **FR-010**: The system MUST use current alarm-code instructions and safety rules ahead of similar historical cases when evidence differs.
- **FR-011**: The system MUST cite the specific source for each reported possible cause and each material troubleshooting instruction.
- **FR-012**: The system MUST use a bounded diagnosis loop whose actions are limited to retrieving more evidence, requesting information, escalating to an expert, or producing a final report.
- **FR-013**: The system MUST stop and report the reason when the diagnosis reaches its step, retrieval, question, token, or time budget.
- **FR-014**: The system MUST enter an information-needed state when required readings, observations, timestamps, or authorization facts are missing, and MUST ask only questions relevant to the next decision.
- **FR-015**: The system MUST enter expert review when safety risk is unclear, evidence is contradictory, the knowledge base has no coverage, or a proposed action crosses the current authorization boundary, lacks a verified applicable qualification, or requires an unresolved service restriction. A report may describe source-grounded steps reserved for qualified personnel without requiring expert approval solely because the step requires qualification; displaying advice never grants permission to execute it. Immediate stop and non-invasive information collection do not wait for maintenance qualification.
- **FR-016**: The system MUST produce a report containing fault phenomenon, known facts, possible causes, evidence sources, safety preconditions, check order, missing information, stop conditions, and expert-escalation status.
- **FR-017**: The system MUST preserve the original evidence, AI report, expert revision, and repair outcome as separate records or versions.
- **FR-018**: The system MUST record the versions or identities of the diagnosis process, instructions, model, knowledge set, evidence snapshot, and citations used for each diagnosis.
- **FR-019**: The system MUST allow an authorized engineer to submit confirmed root cause, repair action, responsible role, and restart validation after a diagnosis.
- **FR-020**: The system MUST create an unapproved case draft from repair feedback and MUST prevent it from entering the production knowledge set until an authorized reviewer approves it.
- **FR-021**: The system MUST provide a user-facing explanation when an image, video, OCR, QR, model, or retrieval operation cannot produce reliable evidence.
- **FR-022**: The system MUST NOT send equipment-control commands, modify equipment settings, bypass interlocks, or execute physical repair actions.
- **FR-023**: Jev MUST be the retrieval-result assessment stage when processing is permitted, separating relevance, applicability, historical differences and conflict signals; necessary safety and exact alarm sources MUST survive its scores.
- **FR-024**: Real Jev, fixture, partial, unavailable and policy-skipped assessment MUST be visibly distinct; skipped processing MUST NOT appear successful.
- **FR-025**: TECHNICAL_REFERENCE and FIELD_RECORD MUST have independent read and external-processing permissions. Classification/redaction alone MUST NOT permit external sharing.
- **FR-026**: Verified identities and resource scope MUST govern incidents, media, citations, jobs, events, checkpoints, exports and mutations; client-declared roles MUST NOT grant authority.
- **FR-027**: Retrieval MUST filter authorization before ranking/model use, excluding unapproved cases. Derived outputs, caches and shared cases MUST inherit source restrictions.
- **FR-028**: All external providers, including Jev, embeddings, vision and generation, MUST honor permissions/minimization; denied input MUST NOT leak through state, questions, retries or logs.
- **FR-029**: Business roles MUST be separate from scope-specific maintenance qualifications; EXPERT MUST NOT automatically authorize circuit/mechanical work or case publication.
- **FR-030**: Optional warranty/service constraints MUST have confirmed sources/versions and never delay emergency notice; unknown terms MUST NOT be invented.
- **FR-031**: Reports MUST rank possible causes with supporting, counter and missing evidence, compare current/historical records, and separate facts, observations, unknowns, contradictions and manual values.
- **FR-032**: All seven supplied alarms MUST follow manual safety order. A205 requires immediate shutdown without additional dangerous-symptom descriptions; historical matches MUST NOT override it.
- **FR-033**: Every material claim/instruction MUST have source/confirmed-input provenance. Citation existence/version and semantic support MUST be separately checked; unavailable semantic checks require a verified local source-bound template proof or explicit human review; Jev policy skip alone MUST NOT imply all claims need manual review.
- **FR-034**: Resume MUST recheck current access and changed facts against safety. Expert-only context MUST NOT leak into an engineer run; data-scope change requires a linked run, preserved records and shared budgets.
- **FR-035**: Incomplete or failed-restart repair feedback MUST be saved as explicitly unverified without inventing missing fields. Readiness for case review requires responsible executor, confirmed root cause, repair evidence and successful restart validation/evidence. Publication additionally requires reviewer authority, de-identification and scope approval. Self-review is disabled except an audited demonstration exception.
- **FR-036**: Deliverables MUST include a directly testable entry, supported-input guide, rule-use explanation, output guide and actual input/output self-test with provider/version evidence. Fixture-only tests MUST NOT count as real-model acceptance.
- **FR-037**: The fictional exam context MUST be visible and confidential source materials protected from public repositories/examples and unpermitted external processing.
- **FR-038**: Clear dangerous text MUST receive deterministic notice without waiting for media review or external processing; unknown/ambiguous risk requires clarification/escalation, not assumed clearance.
- **FR-039**: Failure, cancellation, checkpoint corruption and expired worker ownership MUST have explicit states, bounded recovery, durable budgets and idempotent effects.
- **FR-040**: Media MUST have defined upload/decoding limits and truthful visual/audio boundaries. Optional unresolved media MUST allow an independent safe text path; confirmed conflicts/material unknown risk still block.

- **FR-041**: Jev MUST receive only authorized, locally minimized allowlisted technical projections, with no raw event/media/checkpoint/identity/contract input; masking MUST NOT override DENY. Provider conditions, receipt and explicit policy skip MUST remain traceable without per-request approval popups.
- **FR-042**: Human intervention MUST be exception-based: explicit batch decisions for multimodal evidence, one consolidated expert action per unchanged risk snapshot, and automatic advisory reports only after verified templates plus all safety/provenance/access/qualification gates. Unknown non-template claims retain review; repair confirmation and case review remain human.

### Key Entities *(include if feature involves data)*

- **Fault Incident**: A field-reported equipment event containing original description, structured facts, asset association, lifecycle status, and linked evidence and diagnoses.
- **Media Asset**: An uploaded image or video with its processing status, source metadata, and retention association.
- **Evidence Item**: A confirmed, corrected, rejected, or pending observation derived from text, a media asset, OCR, visual analysis, video analysis, or QR decoding.
- **Asset**: The APX-240 equipment identity that can be entered manually or resolved from a QR code and can link to applicable maintenance history.
- **Diagnosis Run**: One bounded evaluation of an incident with its evidence snapshot, decisions, report, citations, and process versions.
- **Citation**: A traceable reference to a specific alarm-code entry, manual section, historical case, maintenance record, or approved case.
- **Expert Review**: A human takeover or revision created when risk, uncertainty, conflict, authorization, or knowledge coverage requires expert judgment.
- **Repair Outcome**: Versioned field-work feedback, explicitly unverified while incomplete; complete review-ready versions contain confirmed root cause, executor, repair action/evidence and successful restart evidence.
- **Case Draft**: A proposed reusable case derived from a repair outcome and awaiting review.
- **Approved Case**: A reviewed and versioned case eligible for future diagnosis retrieval.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In the reference A203 scenario, at least 100% of the required report fields are populated, and the report cites A203 plus the relevant H02 and maintenance evidence without labeling the historical root cause as confirmed.
- **SC-002**: In the incomplete A310 scenario, the system asks for upstream pressure, equipment-side pressure, and leak-sound evidence before presenting a connector-related cause as anything more than possible.
- **SC-003**: In every SAFE-01 test scenario, the safety stop and expert-escalation instruction appears before ordinary troubleshooting steps, with zero permitted continued-trial-run recommendations.
- **SC-004**: In media review tests, 100% of OCR, visual, video, and QR candidates expose a review action and a source or limitation before diagnosis begins.
- **SC-005**: 100% of published reports have resolvable provenance for each possible cause, safety prerequisite, material check and stop/escalation instruction. Invalid drafts are corrected/reviewed/withheld, not publication exceptions.
- **SC-006**: 100% of deterministic reference cases with removed required facts enter information-needed/expert review and never emit a definitive AI root cause; real-model results are measured separately without industrial accuracy claims.
- **SC-007**: A field engineer can submit a normal text-only incident and reach a structured report in one continuous session without uploading media.
- **SC-008**: A repair outcome can be recorded without changing the original AI report, and an unapproved case draft is not returned as official knowledge in subsequent retrieval checks.
- **SC-009**: In a five-minute moderated usability check, engineers identify all four applicable items without hidden logs: A203 safety prerequisite, leading possible cause, next permissible check and source; SAFE-01 immediate stop, prohibited action, expert escalation and source. Cause/ordinary checks are NOT_APPLICABLE in a stop-only report; do not require fabricated content.
- **SC-010**: A failed or unavailable media, model, or retrieval operation produces an explicit limitation and recoverable next action in 100% of tested failure cases.
- **SC-011**: Seven-alarm regression preserves manual order, authorization boundaries and historical separation with no prohibited action.
- **SC-012**: Cross-event API/media/citation/progress/checkpoint/export/resume tests disclose no protected payload; revoked users cannot regain it through caches.
- **SC-013**: Egress-denial tests transmit no restricted payload to any external provider including embeddings; real Jev tests on permitted simulation data expose actual model/mode.
- **SC-014**: With/without-Jev evaluation records relevance, necessary-source retention, conflicts, citation-support errors, latency and cost as measured values.
- **SC-015**: Case approval requires repair evidence, restart validation and publication scope; original reports and restricted retrieval are preserved.
- **SC-016**: Clean startup provides an entry and five submission items, including at least one actual market-model input/output self-test; fixtures are explicitly marked.

- **SC-017**: Captured permitted Jev requests satisfy the strict projection schema; denied or residual-sensitive requests make zero provider calls, and masking without permission remains denied. Retries, questions and logs preserve the same boundary.
- **SC-018**: Complete, qualified A203 template diagnosis requires no report-approval click; FORCE_REVIEW demonstrates report interrupt/resume. Media requires one explicit batch review screen, high-risk one consolidated expert action per snapshot, and approved case scope can be reviewed/published in one explicit action without bypassing separate authorization/audit.

## Assumptions

- The first release targets APX-240 and the supplied seven alarm-code entries, five historical cases, and five maintenance records; support for other device families is outside this feature.
- Field engineers can provide at least a text description, but reports may be incomplete, uncertain, or contradictory.
- Experts handle high-risk review; assigned CASE_REVIEWER authority is separately required for publication, even when one person holds both roles.
- The supplied manual is the authoritative source for the first release's safety rules, normal parameters, alarm-code order, and authorization boundaries.
- Images and videos are provided as ordinary field media; media quality and coverage cannot be assumed, so the product must support explicit inability-to-determine outcomes.
- QR data may identify an asset only when an asset record exists; manual asset entry remains available.
- Diagnosis is advisory and read-only with respect to the equipment; all physical actions remain with authorized personnel.
- An ordinary web session and stable connectivity are available for the first field demonstration. Offline execution is outside this feature.
- First release uses one organization, event-scoped access, recorded maintenance qualifications, optional confirmed warranty data and independently controlled external processing; enterprise SSO/multi-tenant administration/automatic claims remain out of scope.
- Confidential exam-source external processing is denied until a valid permission basis is recorded. Local market-model processing or permitted simulations validate real models; fixtures validate workflows only.

## Revision trace

The prior publication-by-EXPERT rule, implied automatic video-sound analysis, deferred identity design and 90% publication citation criterion are superseded. Their original wording remains in the pre-merge snapshot. `integration-review.md` lists changes, conflicts, remaining blockers and source mappings. Constitution and original exam files are unchanged.

## Revision 2.1.0 review/privacy refinement

See privacy-review-policy.md. Replaces blanket final-report review with strict template-validated advisory auto-publication and exception review. Report-review interrupts remain supported. Constitution unchanged; original2.0 preserved in history/pre-review-simplification-20261004/. No business task executed.

## Revision 2.2.0 contract clarification
FR-015 separates advice access from applicable execution authorization. Necessary missing information blocks diagnosis, optional context may remain in an otherwise valid advisory report; generated claims never gain publication permission from Jev confidence alone. Scope remains unchanged; see integration-review section9 for retained audit findings.
