# E007 SWE-2 Provenance Verification

**Verified:** 2026-09-25, before E007 execution.

## Original runs

E002, E004, E005, and E006 are the 30-case primary benchmark sources. Their frozen configs identify Cognition Devin, SWE-2, and the intended Medium/Max model variants. More importantly, preserved run evidence confirms what ran:

- E002 has per-run `run-metadata.json`, evaluator output, session summaries, and sanitized Devin session exports. The exports identify `SWE-2 Medium` / `SWE-2 Max` and their generation model IDs (`swe-2-medium` / `swe-2-max`). The run records specify matching `effort_level` values. The E002 config identifies Devin CLI `3000.10.21 (611c1cba)`, local Docker Linux/arm64 execution, and the frozen `devin-e002` image.
- E004's run metadata and session artifacts preserve the same SWE-2 model IDs and effort labels. Its frozen config identifies Devin CLI `3000.10.21 (611c1cba)`, the E002 Docker execution architecture, dangerous permission mode with effective Bypass, and the E004 container runner.
- E005's per-run metadata/session exports identify SWE-2 Medium or Max, with model selection in the run record; the frozen config identifies the corresponding `swe-2-medium` and `swe-2-max` conditions, the inherited Devin CLI/container, and its versioned runner.
- E006's run metadata, session summaries, session telemetry, and evaluator records identify SWE-2 Medium or Max. The frozen config explicitly pairs model IDs with `reasoning_effort: medium|max`; the freeze records Devin CLI `3000.10.21 (611c1cba)`, derived image digest `7557a0bc…`, Linux/arm64, and runner/runtime versions.

Thus the original Medium runs are verified as SWE-2 Medium and the original Max runs as SWE-2 Max. This is not inferred from condition labels alone: model IDs are present in preserved session/run evidence and agree with the frozen condition definitions. Run-specific session IDs and UTC timestamps remain in the source run metadata/evaluations. Session files are sanitized derivatives; private reasoning and credential data are intentionally not part of the preserved public artifacts.

## Current execution control

The installed interface is Devin CLI `3000.10.21 (611c1cba)`. `devin --help` exposes `--model`; `devin models list` returned the authenticated model catalog. Under SWE-2 it listed exactly these selectable variants:

| Condition | Exact model selector | Catalog label |
|---|---|---|
| Medium | `swe-2-medium` | SWE-2 Medium |
| High | `swe-2-high` | SWE-2 High |
| Max | `swe-2-max` | SWE-2 Max |

The controls are model variants, not a separate CLI effort flag. The first pre-session attempts exposed that the frozen Docker image could not fetch its catalog because the documented `egress-proxy` service was stopped. I restored the already-frozen proxy image (`e002-egress-proxy:1`, digest `adb28774…`) on `e002-internal` plus the default bridge, preserving the deny-by-default allowlist boundary. The catalog was then rechecked from inside the frozen `devin-e002:3000.10.21` image; it returned the exact three model IDs and Free labels. No fallback or effort remapping is allowed.

## Billing inspection

The same authenticated model catalog labeled all three SWE-2 variants **Free**. The CLI exposes no per-session overage forecast. The evidence supports $0 expected direct model overage, not a guarantee about unrelated account usage. The current CLI and in-container catalog excerpt, together with the first three session-returned model IDs, are preserved in `E007-CURRENT-CONTROLS.txt`. Two initial invocations were rejected before a Devin task session existed; both are retained separately under `devin-agent-benchmark-e007-private/pre-session-rejections/` and excluded from the 90 primary runs. The stopped proxy service was restored from the preserved image before the scored sequence began. E007 must capture any account-reported usage/cost available in session records and stop before any unexpected direct overage; ceiling $100.

## Limits of verification

Historical metadata establishes model/backend identity and effort selectors, but does not expose a separate private backend deployment revision for every generation. The run-specific execution surfaces, CLI version, container/runtime versions, timestamps, session IDs, and returned generation-model identifiers are retained in the source artifacts. No material discrepancy was found, so E007 proceeds under the preregistered protocol.
