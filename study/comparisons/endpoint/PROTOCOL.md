# Certain-edge timing against the eligible exact controls

The earlier endpoint study measured the sparse dispatcher on four versions of 75 fresh matrices. Its auxiliary enumeration records served as correctness references on the 50 small cases. The new study times every eligible method on all four versions in one campaign. The unit for a speedup is one matrix at one marking rate. The reported results are descriptive for these fixed queries.

## Inputs and timing design

1. Select all 25 small Cora, 25 small OGB and 25 larger OGB queries from the archived endpoint ledger. The zero-rate arm uses each original expansion matrix. The other three arms use the exact bytes of the 1%, 5% and 20% variants saved in the earlier experiment. These have nested masks, drawn once per query using PCG64 seeded with 701900 plus the case index and one uniform variate per supported second-hop edge in row-major order. Compare every file with its prior SHA-256 digest and check its matrix dimensions, support size and mark count.
2. Pin the driver and its serial child processes to one allowed logical CPU (10 in the recorded run). Use the original optimized C++ executables. Each process measures repeated kernel calls for at least 20 ms and reports mean kernel time per call, setup time, repeat count and the complete vector of probabilities. Process startup and reading the matrix are outside the kernel clock. The driver reads the input files for fingerprint verification before timing.
3. Visit case indices in ascending order. In each of three rounds per case, shuffle all rate–method pairs with Python's standard random generator seeded by the string `endpoint-envelope-r2/{case}/{round}`. Include the sparse dispatcher, incidence-only recomputation, component-local recomputation and direct evaluation on all 75 cases. Include first-hop enumeration whenever the original witness count satisfies `W <= 18`. This permits enumeration for 25 small Cora, 25 small OGB and seven larger OGB queries. The full design has 4,284 timed invocations, including 684 timed enumeration invocations.
4. Within each case and rate, compute the three-round median for each eligible method. Divide the minimum of the eligible control medians by the sparse median. A strict win requires a ratio above one. Take the median of those 25 ratios in each stratum and count strict wins. All cases at each assigned rate enter the comparison, including those with no marked edges.
5. Verify order, completeness, repeat clock budgets, fallback flags, deterministic output across rounds, probability bounds, total mass and the absolute discrepancy from direct evaluation for each vector (tolerance \(10^{-10}\)). The comparison with enumeration is independent where eligible. On triggered cases the three optimized methods and the direct control execute the same direct formula. Their agreement on those calls therefore provides no independent numerical validation.

## Frozen dispatch

The shared input reader in `source/k2.cpp` sets the query-wide endpoint flag when **any** second-hop probability equals one (lines 15–19). Before building recurrence state, the sparse dispatcher returns `direct(p)` at line 33, incidence-only recomputation returns it at line 50, and component-local recomputation returns it at line 6 of `source/component.cpp`. Explicit direct calls use that same implementation. The two optimized control binaries do not expose a reason field for this branch. The sparse binary emits the reason `b_equals_one`. First-hop enumeration uses its own witness-state calculation at lines 66–72 of `source/k2.cpp`, including on marked inputs.

When these paths coincide, timing differences can come from invocation overhead, binary layout and run-to-run variation. Taking the fastest of several measured controls can push the ratio below one even when the underlying algorithm is identical. Strict win counts alone therefore cannot demonstrate a distinct computational advantage on triggered queries. Enumeration remains a genuinely different competitor when eligible.

## Verify and regenerate

From the extracted replication root, run with Python 3.11+ (standard library only).

~~~bash
E=study/comparisons/endpoint
python "$E/analyze.py" "$E/evidence" --table "$E/endpoint_table.tex"
~~~

The analysis verifies the three hashes in `transfer.json` and every raw timing record before producing `evidence/endpoint_cases.csv`, `evidence/summary.json` and the table. The ledger contains every input's eligibility, indicated by an empty enumeration-time field when ineligible, all eligible per-method medians in microseconds, winning control, paired speedup, strict win and largest absolute discrepancy against direct. File names and SHA-256 values for the 300 measured matrices are in `evidence/inputs.json`.

## Remeasure on Linux

Use an extracted replication package, Bash, Python 3.11+, GNU coreutils, `lscpu` and a C++17 compiler with the same extended-precision `long double` model for numerical comparison. The expansion directory must contain the archived input matrices. The prior directory must contain `case_manifest.json`, `endpoint_cases.csv`, `generated_hashes.json` and `generated_inputs.tar.gz`. These commands build both executables into a fresh temporary directory and reuse the saved matrices.

~~~bash
E=study/comparisons/endpoint
EXP=study/experiments/graph_queries
PRIOR=study/workloads/experiments/measurements
BUILD=$(mktemp -d)
ln -s "$(realpath "$EXP/results")" "$BUILD/results"
g++ -std=c++17 -O3 -march=native "$EXP/source/k2.cpp" -o "$BUILD/k2"
g++ -std=c++17 -O3 -march=native "$EXP/source/component.cpp" -o "$BUILD/component"
env LC_ALL=C OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  python "$E/measure.py" "$BUILD" "$PRIOR" "$BUILD/evidence" \
    --k2-sha256 "$(sha256sum "$BUILD/k2" | cut -d' ' -f1)" \
    --component-sha256 "$(sha256sum "$BUILD/component" | cut -d' ' -f1)"
python "$E/analyze.py" "$BUILD/evidence" --table "$BUILD/endpoint_table.tex"
~~~

The default affinity for a portable run is the first CPU permitted to the process. Use `--cpu 10` when available to match the recorded logical CPU index. The recorded environment includes both executable fingerprints, the driver fingerprint, the prior input manifests' fingerprints, CPU details and start/end times. Remeasurement produces separate timing values on each host.
