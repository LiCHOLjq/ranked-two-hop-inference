# Kernel-comparison numerical audit

From the root of the extracted replication archive, run `python study/comparisons/analysis/audit_controls.py` using Python 3.10 or newer. To write the six CSV summaries elsewhere, append `--out OUTPUT_DIRECTORY`. No benchmark, network service or third-party package is required. The script reads the original expansion campaign's round timings and case metadata, the verified structural counts in `workloads/analysis/structure_cases.csv`, the three historical sampling archives with their per-invocation output vectors, and the prior endpoint study's raw timings and case table.

## Structural rule and seed-block resolution

On the matched target, the strict-saving rule classified 288/325 cases correctly. Predicting a sparse win in every case classified 284/325 correctly. All four additional correct classifications (1.23 percentage points overall) came from predicting no strict sparse win on structural ties. This prediction held for 21/38 ties (55.3%). A strict saving predicted the measured winner in 267/287 cases (93.0%). On the full envelope, the corresponding gain was 24/325 (7.38 points), where timed competitors include methods outside the structural comparison. See `rule_accuracy.csv`.

All five seed-block medians fell below one on small Cora and above one in each of the other three strata. With five independent block signs, the two-sided exact sign test attains its minimum of 2/32 = 0.0625 for unanimous signs. With four strata, the first Holm multiplier is four and each later adjusted value inherits the maximum reached. The resulting lower bound is 0.25, attained by all four observed values. The design therefore precluded rejection at 0.05 irrespective of the observed directions. See `sign_blocks.csv`.

## Sampling budget

At 4,096 draws per estimate, the sampler took 52.6–221.1 times the exact kernel time across the four real strata, using ratios of the unrounded stratum medians. The corresponding figures from the published table's rounded times are 52.7–220.9. Taking the time ratio within each case before the stratum median yields 57.0–242.1. All three calculations first take the median sampler time over each case's five seeds. Individual output vectors met the maximum-coordinate absolute tolerance of 10⁻¹⁰ in 0/300 real-stratum estimates (four strata, 15 cases each, five seeds per case). Stratum medians of the case-level worst-coordinate error were 0.00507–0.00597. The comparison applies to this untuned, fixed budget. See `sampling_ratios.csv`.

## Probability grid

The center-column incidence-only control time increased in three of the 15 within-support comparisons. The exceptions were seed 8101 at a = 0.2 (+0.166%), 8103 at a = 0.2 (+8.130%), and 8103 at a = 0.95 (+0.081%). At a = 0.2, the median control time over the three supports was 556.79 μs at the center, supplied by seed 8101. The support supplying the median paired speedup was 8102 in every center-column cell. At a = 0.2, this support's center control time fell to 548.91 μs from a median of 556.80 μs across its four other columns (−1.42%). Its sparse time moved from 65.92 to 65.90 μs (−0.032%). The three center speedups in ascending order were 7.9914 (8103), 8.3297 (8102) and 8.4871 (8101). Thus the grid minimum of 8.330 is consistent with the center-column decrease on its contributing support. The fixed run order prevents causal attribution. See `grid_supports.csv`.

## Degree sweep

Over 21 cases at seven tested degrees, the fitted intercept was 27.9580 and the slope was −22.9677, with R² = 0.98077. Both ratios contain the same deterministic count U in their denominator. Across the degree settings, median U rose monotonically from 1,772 to 2,125,601 and median Q/U rose monotonically from 0.27765 to 0.98422. The high R² describes that joint sweep. It provides no independent evidence for the linear form or for a particular hardware cost per pair visit. See `degree_fit.csv`.

## Common triggered subset in the original endpoint runs

The same per-edge uniform markers define nested triggered subsets, so the intersection at the three positive rates is exactly the 1% triggered subset. Ratios use each case's dispatcher time at its selected rate divided by that same case's zero-rate dispatcher time, after taking round medians within each arm.

| Stratum | Cases triggered at all three rates | 1% | 5% | 20% |
|---|---:|---:|---:|---:|
| Small Cora | 5/25 | 1.3281 | 1.3288 | 1.2384 |
| Small OGB20k | 7/25 | 1.9599 | 1.9349 | 1.8347 |
| Larger OGB20k | 25/25 | 11.8100 | 11.2343 | 10.6534 |

For small Cora the corresponding rate-specific triggered subsets contained 5, 14 and 21 cases, producing 1.33, 0.96 and 1.12. On the common five cases, all three medians exceeded one, so the 0.96 value cannot be taken as a within-cohort improvement at 5%. The fixed-cohort values describe the original dispatcher-only study. See `endpoint_common.csv` for case IDs as well as both series.
