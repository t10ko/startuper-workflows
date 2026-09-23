---
name: critical-thinking
description: Use when complex proposals, architecture changes, systemic bugs, or multi-agent assumptions need adversarial critical review.
metadata:
  origin: ECC
---

# /critical-thinking — Adversarial Analysis & Decision Engineering

Structured capability for bounded iterative Socratic premise deconstruction, prospective hindsight (Premortem) risk identification, Multi-Criteria Decision Analysis (Pugh Matrix), and Fishbone (Ishikawa) diagnostics.

## Trigger

Use this skill when:
- Evaluating a complex feature proposal or major architectural change.
- Deciding between multiple implementation strategies or libraries.
- Investigating system bugs that require systemic architecture fixes rather than symptom patches.
- Challenging unverified assumptions in multi-agent designs or developer inputs.

---

## 1. Iterative Critical Loop

Critical thinking is not a single pass. Run the analysis as bounded rounds until the claim package stabilizes.

### Loop Controls
- `max_iterations`: 3 by default. Use fewer only when the first pass finds a specific, verified owner boundary or a clear user approval gate.
- `iteration_scope`: one failure class, design claim, contract boundary, or decision at a time. Do not broaden into whole-system speculation.
- `evidence_first`: every round must add source, log, schema, test, runtime, or operator-provided evidence. If no new evidence is available, stop and mark uncertainty.

### Per-Round Protocol
Each iteration must run the phase sequence below and record:
- `claim_delta`: what changed in the working conclusion since the previous round.
- `new_evidence`: concrete files, logs, commands, schemas, traces, or user-approved facts added this round.
- `invalidated_assumptions`: assumptions disproven or downgraded.
- `remaining_uncertainty`: unresolved evidence gaps that could change the decision.
- `next_probe`: the narrowest next verification step, or `STOP`.

### Stop Conditions
Stop the loop when one condition is true:
- The conclusion is stable for one full round: no material `claim_delta`, no high-risk `remaining_uncertainty`, and no stronger alternative hypothesis.
- The root cause or selected design is tied to a specific, controllable owner boundary.
- Further analysis would require user approval, unavailable external evidence, or speculative assumptions.
- `max_iterations` is reached. If so, report the remaining uncertainty explicitly instead of forcing confidence.

Never keep looping only to "think harder." Iteration must change evidence, invalidate assumptions, or narrow the decision.

## 2. Phase-by-Phase Execution Runbook

### Phase 1: Socratic Claim Deconstruction
1.  **Decompose Premises:** Extract every explicit and implicit claim in the input proposal.
2.  **Verify Against Local Source:** Query the codebase configurations and files to validate dependency versions, API contracts, database schemas, and performance constraints.
3.  **Grounding Check:** Write a list of verified claims vs. unverified hypotheses. Align with the operator on a grounded specification (`spec.md`) before proceeding.

### Phase 2: Gary Klein's Premortem (Risk Analysis)
1.  **Prospective Hindsight:** Project forward 6 months. Assume the proposed design has failed catastrophically in production.
2.  **Expose Defect Scenarios:** Brainstorm and document the sequence of events that caused this catastrophic failure.
3.  **Risk Profile Scoring:** Grade each defect scenario by Likelihood (High/Medium/Low) and Impact (Critical/Serious/Moderate), mapping out telemetry alerts or detection triggers for each.

### Phase 3: Multi-Criteria Pugh Decision Matrix
1.  **Identify 3 Alternatives:** Synthesize at least three alternative design or coding approaches.
2.  **Weighted Criteria Evaluation:** Score each alternative ($S_{ij}$) against the baseline design ($0$) using values from $+3$ (major improvement) to $-3$ (major regression).
3.  **Utility Score Equation:** Compute final utility scores using value-weighted criteria:
    $$U_i = \sum_{j} w_j S_{ij}$$
    where $w_j$ represents the weights ($\sum w_j = 1$).
4.  **ADR Record:** Commit the optimal decision as an Architecture Decision Record (ADR).

---

## 3. Root Cause Analysis (Fishbone & 5 Whys)

When diagnosing a system failure:
1.  **Ishikawa Categories:** Classify possible failure causes across:
    -   *Man:* Developer guidance, manual ops, workflow boundaries.
    -   *Machine:* Runtimes, compilers, environments.
    -   *Method:* Algorithms, design patterns, testing gaps.
    -   *Material:* Schema definitions, external packages, API dependencies.
    -   *Measurement:* Logging resolution, metric discrepancies.
    -   *Environment:* Latency, bandwidth constraints, OS version.
2.  **Iterative 5 Whys:** Trace downstream to upstream. Every answer must form the subject of the next "Why?" question.
3.  **Validation:** Ensure the identified root cause is Specific, Systemic, Controllable, and logically Valid.

## 4. Output Schema

> [!IMPORTANT]
> **Output Clarity & Readability Rules**
> 1. **Structured, Detail-Rich Presentation:** Conduct a full, unconstrained analysis internally. Present the final report in a well-structured, clear, human-readable format.
> 2. **Guidelines:**
>    - *Tone:* Objective, direct, clear, and professional.
>    - *Executive Summary:* 2-3 readable paragraphs synthesizing target, key risks, Pugh choice, and final verdict, following the guidelines in `.agents/workflows/explain.md`.
>    - *Failure Scenarios:* Detailed, natural description of the failure propagation path and specific, clear triggers.
>    - *Remediations & Log:* Structured action points explaining how, why, and what fallback mechanism is active.
>    - *Pugh Matrix:* Display raw scoring table accompanied by a detailed trade-off analysis explaining candidate selection.

The final report must follow this layout:

```markdown
# 💀 ADVERSARIAL STRESS-TEST & CRITICAL REVIEW REPORT

## 📝 EXECUTIVE SUMMARY (HUMAN-READABLE)
*Provide a high-level overview of stress-test findings adhering to the professional explanation rules defined in `.agents/workflows/explain.md`. Detail proposed changes, system-level context, key failure scenarios, Pugh choice trade-offs, and final recommendation.*

## 🎯 OBJECTIVE UNDER REVIEW
* **Target Subsystem:** [Name of subsystem]
* **Reference Commit / Spec:** [Path/SHA]
* **Sycophancy Risk Index:** [High / Medium / Low]

## 🔁 ITERATION LOG
| Round | claim_delta | new_evidence | invalidated_assumptions | remaining_uncertainty | next_probe |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | [What changed] | [Evidence added] | [Assumptions downgraded] | [Evidence gaps] | [Next probe or STOP] |

## 💀 SYSTEMIC PREMORTEM FAILURE NARRATIVE
*Looking back from T+180 days, the proposed implementation failed catastrophically under production load due to:*

### Failure Scenarios
* **❌ [Title of Failure Mode]**
  * **Catastrophic Scenario:** [Detailed human-oriented explanation of failure propagation and dependencies]
  * **Early Detection Trigger:** [Specific log lines, alert thresholds, or metric monitoring details]
  * **Risk Profile:** Likelihood: [H/M/L] | Impact: [Critical/Serious/Moderate]

## 📊 MULTI-CRITERIA DECISION ANALYSIS (PUGH MATRIX)

| Candidate Solution | Latency (w=0.3) | Security (w=0.4) | Complexity (w=0.3) | Utility Score |
| :--- | :--- | :--- | :--- | :--- |
| **Proposed Design (Baseline)** | 0 | 0 | 0 | **0.00** |
| **Alternative A: [Name]** | [Score] | [Score] | [Score] | **[Total]** |
| **Alternative B: [Name]** | [Score] | [Score] | [Score] | **[Total]** |

Scoring: +3 (Catastrophic Improvement) to -3 (Catastrophic Regression) relative to Baseline (0).

### Recommendation & Trade-Off Analysis
* **Selected Candidate:** **Alternative [X]**
* **Trade-Off Justification:** [Detail the specific trade-offs made between complexity, safety, performance, and why the selected candidate is optimal.]

## 🛡️ CRITICAL COUNTERMEASURES & REMEDIATION PLAN
### 🔴 Risk Target: [Name of top prioritized failure mode]
* **Prevention Strategy:** [Detailed structural implementation or design adjustment to eliminate root cause]
* **Detection Mechanism:** [Specific tests, automated checks, or CI/CD assertions to guard against regression]
* **Plan B Fallback:** [Detailed fallback path or graceful degradation behavior when under load]
* **Accountable Role / SLA:** [Role / Timeframe]

## 🔍 LOW-CONFIDENCE FINDINGS & UNCERTAINTY LOG
* **Potential Vulnerability:** [Detailed unverified risk under review]
* **Downgrade Rationale:** [Reasoning for why it does not block immediate progress]
* **Verification Runbook:** [Commands or diagnostic runbooks to confirm/refute risk]
```
