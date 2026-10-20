# E008 Failure Taxonomy

Failures are grouped by evaluator suite outcomes: public-suite failure, held-out/incomplete fix, regression introduced, multiple-suite failure, evaluator/infrastructure anomaly, or successful repair. These categories identify where the external contract failed, not the underlying agent reasoning. The source ledgers retain detailed labels when recorded; the legacy taxonomies are not sufficiently uniform for a more granular causal comparison.

| Condition | held-out/incomplete fix | multiple-suite failure (public + heldout) | public-suite failure | regression introduced | successful repair |
| --- | --- | --- | --- | --- | --- |
| original_medium | 4 | 1 | 0 | 1 | 24 |
| E007_medium | 6 | 0 | 1 | 1 | 22 |
| original_max | 6 | 0 | 0 | 1 | 23 |
| E007_max | 5 | 0 | 0 | 1 | 24 |

The per-case and exact suite-class counts are in `E008-FAILURE-TAXONOMY.json`. A rise in public-suite failures or held-out failures is evidence about the failing contract, not proof of a model drift mechanism.
