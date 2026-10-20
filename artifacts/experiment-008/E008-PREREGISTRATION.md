# E008 Preregistration

## Question

How much of the outcome difference between the original SWE-2 benchmark and E007 reflects case-level instability, and what is the smallest targeted repeated-trial set that can characterize those disagreements?

## Outcomes and analysis

Primary outcome is the frozen binary `TASK_SUCCESS`. The paired case-level matrix is primary for replication. Exact two-sided McNemar tests compare original and E007 outcomes; agreement proportions receive Wilson 95% intervals. Difficulty-stratified results are descriptive at n=10. Secondary telemetry is limited to fields with comparable definitions and adequate coverage. No hidden-reasoning claims or causal drift attribution will be made from observational traces.

## Selection rule

A case/effort setting is eligible only if its original and E007 outcome differs and the cell has valid evaluator output. Select all such Medium/Max cells; do not add stable cases or automatically run High. The frozen default is three new independent trials per selected cell. If any comparability blocker emerges, do not execute the affected cells until resolved.

## Approval gate

Execution is not authorized by this preregistration. Return the completed audit and exact proposed matrix for explicit user approval first. New direct overage must remain at or below $50.
