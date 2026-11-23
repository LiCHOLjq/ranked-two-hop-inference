# Support-level analyses for the graph workloads

Run the following command with Python 3 from the public repository root.

```sh
python study/inference/diagnostics/analyze_supports.py . --out reproduced
```

The script uses the archived case metadata and round-level method timings in `study/experiments/graph_queries/results` and the paired range experiment in `study/workloads/experiments/measurements/ranges_cases.csv`.

* `marking_sensitivity.csv` averages the probability of no marked edge over the recorded cases with equal case weight. The marks follow the independent sensitivity model in the paper. These figures do not estimate real citation-edge certainty rates.
* `small_controls.csv` gives the individual fresh small graph queries, support sizes, per-method median times in microseconds and fastest control under each arm of the separate range experiment.
* `small_summary.csv` groups these queries by dataset, direct-control attainment and candidate count. The length-at-most-eleven comparison describes the observed direct-control wins retrospectively.

The control analysis contains the table of matched and full-envelope prediction gains in `study/comparisons/analysis/rule_accuracy.csv` and the three support-specific center comparisons in `study/comparisons/analysis/grid_supports.csv`.
