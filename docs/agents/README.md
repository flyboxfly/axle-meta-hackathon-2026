# Axle runtime roles — proposed, not yet wired

These definitions adapt owner-supplied Axle and Lane Negotiator alpha instructions received
October 31, 2026. StarNet station language, Commander identity, legacy project status and
superseded alpha restrictions were removed. No StarNet runtime or private records are imported.

Read [pilot specification](../H13_TELEGRAM_PILOT.md).
One application coordinates five scoped roles. Roles do not require five services or five model calls.
The implementation must explicitly load/version instructions and validate outputs.
A Python function labeled with a role is not evidence of an independently executing AI agent.

| Role | Definition |
| --- | --- |
| Axle coordinator | [coordinator.md](coordinator.md) |
| Intake | [intake.md](intake.md) |
| Opportunity analyst | [opportunity-analyst.md](opportunity-analyst.md) |
| Schedule and feasibility | [schedule-feasibility.md](schedule-feasibility.md) |
| Lane Negotiator | [negotiator.md](negotiator.md) |

Shared contract: task ID, authenticated carrier scope (server-bound), opportunity/profile revisions,
minimum necessary facts with sources, missing facts, supported findings, requested next action,
tool references and status. Model output cannot change carrier scope, consent or confirmation.
Only actually executed roles and tools appear in evidence. No chain-of-thought capture.
