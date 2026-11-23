# Reproducing the archived-case analysis

From the study package root, run the following with Python 3.10 or newer. The script uses the standard library and reads the original evidence. It writes the CSV and JSON files below next to the script.

~~~text
python workloads/analysis/analyze_archive.py
~~~

## Inputs

- The original 433 method rows are in `evidence/final_raw_runs.csv`. The original paired ratios in `evidence/exact_control_cases.csv` provide a cross-check.
- The expansion's 325 input records, matrices, 4,715 timing rows, and reference and method vectors are in `experiments/graph_queries/results/`. The original `experiments/graph_queries/case_summary.csv` supplies the published expansion ratios for cross-checking.
- The program verifies the SHA-256 of each matrix, reconstructs dimensions, edge counts, shared-witness pair counts and terminal components, and matches them to the archived metadata. It checks the expected method membership and round numbers and reproduces the stored paired ratios for both campaigns. The 96 archived timings and their expansion replays use the same case identities. There are 323 distinct serialized matrices among the 325 records because the three replayed empty matrices are identical.

## Output files

| File | Scope and interpretation |
|---|---|
| structure_cases.csv | All 325 records, reproducible case index and seed, SHA-256, support hash, structural counts, predecessor-loop counts, method times in microseconds, control minima, and proxy outcomes. |
| archive_envelopes.csv | Original per-case timings, control minimum, eligibility, and speedups for the 96 replayed cases under the first campaign. |
| envelope_summary.csv | Control attainment counts, enumeration eligibility, median speedups and wins with and without enumeration for the 14 reported strata. Divide each control's count by the case count to get its attainment share. |
| method_counts.csv | Number of archived and expansion method records for each experimental family. Each count includes one row per timed invocation, irrespective of its internal repetitions. |
| proxy_confusion.csv | Cross-tabulation of the input-only prediction, including ties, and measured outcomes in the matched and full control envelopes for each stratum. |
| proxy_settings.csv | Same cross-tabulation for each scale, degree, component and probability setting. |
| proxy_disagreements.csv | All 47 distinct cases misclassified by the binary rule on at least one target. Read the two strict-correctness flags to obtain the 37 misclassified cases for each target. |
| proxy_abstentions.csv | All 38 cases for which equal structural costs preclude a strict count-based prediction. |
| unit_costs.csv | Median time, work, within-case cost per unit, its range, and pair-work fraction at each of the 13 scale/degree settings. |
| probability_grid.csv | Separate sparse, incidence and component errors against full direct output, per-cell median times, and paired speedup at each of 25 settings. |
| probability_center_contrasts.csv | For each of 15 first-hop probability and support combinations, center-column values divided by the median across the remaining four columns. |
| archive_verification.json | Case and timing counts, agreement with prior summaries, replay outcome changes, partition winners, proxy totals and the within-degree descriptive fit. |

## Counting and comparison conventions

The dense text matrix uses one row per witness and its columns retain score order. An incidence exists when its entry is positive. Each witness contributes its number of unordered terminal pairs to Q. A terminal contributes its degree times the number of later terminals in its connected component to C and its degree times the total number of later terminals to I. Components are computed by joining terminals incident to each witness. Isolated terminals remain individual components. Two terminals can contribute several pair visits when they share multiple witnesses. The predecessor-loop columns count visits separately from incidences. Indices in the CSVs match the zero-based expansion record index.

For expansion cases, each method time is its within-case median of the recorded round times. Each sparse speedup divides the minimum eligible control time by the sparse time. The original campaign has one timed invocation per eligible method and case, with repeated kernel calls inside it. The matched envelope contains incidence-only and component-local recomputation. The full envelope includes direct and eligible enumeration where the case protocol timed them. With enumeration removed every replay and fresh-real case retains direct and both recomputation controls. All measured controls attained their minima uniquely. A strict measured win requires speedup greater than one.

The input-only rule predicts a strict sparse saving if Q is smaller than the lesser of C and I. Algebra gives Q ≤ C ≤ I in every case. The reported binary sensitivity treats equality as a prediction of no strict sparse win. The tables also retain equality as its own outcome to permit evaluation with abstention. The descriptive degree fit regresses within-case sparse nanoseconds per unit on the fraction of those units contributed by Q using all 21 degree cases with equal weight.

For the probability grid, the script recomputes signed differences in Python binary64 from every stored vector and its full-direct reference and takes absolute maxima across terminals, methods separately. Each cell then reports the maximum across three structure seeds and all three rounds. It also checks that the 25 matrices per seed have the same binary support. For each (seed, first-hop probability) pair the center-column contrast preserves the pairing before division and before aggregation across pairs.
