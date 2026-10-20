# E008 Behavioral Drift

## Common run telemetry

Steps, wall time, and input-plus-output tokens have complete, per-case values for all 30 original and E007 Medium/Max cells. Each row is case-paired; the distributions are right-skewed.

| Effort | Metric | N paired | Missing / 30 | Original mean | Original median | E007 mean | E007 median | Mean paired Δ | Median paired Δ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Medium | steps | 30 | 0 | 26.1 | 17.0 | 24.5 | 16.5 | -1.6 | -0.5 |
| Medium | wall_seconds | 30 | 0 | 283.2 | 118.2 | 185.5 | 117.9 | -97.7 | +9.0 |
| Medium | tokens | 30 | 0 | 289736.0 | 111184.0 | 418475.0 | 134985.0 | +128739.0 | +14798.5 |
| Max | steps | 30 | 0 | 36.8 | 19.0 | 41.3 | 19.5 | +4.5 | +0.0 |
| Max | wall_seconds | 30 | 0 | 529.0 | 407.0 | 524.9 | 297.0 | -4.0 | -25.3 |
| Max | tokens | 30 | 0 | 907169.9 | 174535.5 | 1851498.1 | 369133.5 | +944328.2 | +101550.5 |

Tokens are raw model counters, not cost. Complete paired differences are in `E008-BEHAVIORAL-DRIFT.json`.

## Trace-derived measures (heuristic)

| Effort | Trace metric | Original n | E007 n | Original median | E007 median | Original mean | E007 mean |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Medium | tool_calls | 30 | 30 | 14.5 | 13.5 | 24.4 | 20.7 |
| Medium | exploration_calls_heuristic | 30 | 30 | 11.5 | 12.5 | 17.8 | 15.9 |
| Medium | edit_calls_heuristic | 30 | 30 | 2.0 | 3.0 | 3.9 | 3.9 |
| Medium | test_calls_heuristic | 30 | 30 | 3.0 | 3.5 | 4.9 | 4.6 |
| Medium | first_edit_step_heuristic | 30 | 30 | 12.0 | 11.5 | 14.2 | 14.0 |
| Medium | source_files_changed_heuristic | 30 | 5 | 1.0 | 1.0 | 1.7 | 1.2 |
| Max | tool_calls | 30 | 30 | 27.0 | 25.5 | 40.1 | 47.2 |
| Max | exploration_calls_heuristic | 30 | 30 | 23.5 | 20.5 | 27.4 | 31.4 |
| Max | edit_calls_heuristic | 30 | 30 | 3.0 | 3.0 | 6.5 | 9.1 |
| Max | test_calls_heuristic | 30 | 30 | 3.0 | 3.0 | 4.7 | 7.0 |
| Max | first_edit_step_heuristic | 30 | 30 | 15.0 | 15.0 | 19.5 | 18.8 |
| Max | source_files_changed_heuristic | 30 | 5 | 1.0 | 1.0 | 1.7 | 1.0 |

Tool-call classes use the same name/command regex for both formats. First edit is the first detected edit/write call. Source-file changes use original normalized source counts and E007 changed paths after excluding cache/bytecode/binaries, so that row is descriptive rather than perfectly definition-identical. Counts of exact unique files inspected cannot be recovered uniformly; exploration calls are only a proxy. Hidden planning/reasoning steps are **not comparable or inferred**. Tests executed are command-level regex counts, not unique test cases passed. See case-level trace rows in `E008-DISCORDANT-CASES.md`.

## Observation

Step and wall-time medians are similar across experiment dates; token medians are higher in E007, especially for Max. Heuristic exploration, edit, test, and first-edit comparisons are descriptive and do not establish a private model change.
